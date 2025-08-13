# nomenclatures/services/document_service.py - FINAL ORCHESTRATOR


from typing import Dict, List, Optional, Any, Type, Union
from django.db import transaction, models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.apps import apps
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentService:
    """
    Document Service - CENTRAL ORCHESTRATOR

    Единствен entry point за всички document operations.
    Заменя hardcoded логика в purchases app с dynamic конфигурация.
    """

    # =====================
    # DOCUMENT CREATION
    # =====================

    @staticmethod
    @transaction.atomic
    def create_document(model_class: Type[models.Model],
                        data: Dict[str, Any],
                        user: User,
                        location: Optional[Any] = None) -> Dict:
        """
        Create document with automatic numbering and initial status

        Args:
            model_class: Document model class (PurchaseRequest, etc.)
            data: Document data dictionary
            user: User creating the document
            location: Location (optional, can be in data)

        Returns:
            Dict with success/failure and document instance
        """
        try:
            # 1. Get DocumentType
            document_type = DocumentService._get_document_type_for_model(model_class)
            if not document_type:
                return {
                    'success': False,
                    'message': f'No DocumentType found for {model_class.__name__}',
                    'error_code': 'DOCUMENT_TYPE_NOT_FOUND'
                }

            # 2. Extract location
            location = location or data.get('location')
            if not location:
                return {
                    'success': False,
                    'message': 'Location is required for document creation',
                    'error_code': 'LOCATION_REQUIRED'
                }

            # 3. Generate document number
            document_number = DocumentService._generate_document_number(
                document_type, location, user
            )

            # 4. Get initial status
            initial_status = DocumentService._get_initial_status(document_type)

            # 5. Prepare document data
            document_data = {
                **data,
                'document_type': document_type,
                'document_number': document_number,
                'status': initial_status,
                'created_by': user,
                'location': location,
            }

            # 6. Create document instance
            document = model_class(**document_data)
            document.full_clean()
            document.save(skip_validation=True)

            logger.info(f"Created {model_class.__name__} {document_number} by {user.username}")

            return {
                'success': True,
                'document': document,
                'message': f'Document {document_number} created successfully'
            }

        except Exception as e:
            logger.error(f"Error creating {model_class.__name__}: {e}")
            return {
                'success': False,
                'message': str(e),
                'error_code': 'DOCUMENT_CREATION_FAILED'
            }

    @staticmethod
    def create_purchase_request(supplier, location, user, lines_data=None, **kwargs) -> Dict:
        """Create Purchase Request with lines"""
        try:
            PurchaseRequest = apps.get_model('purchases', 'PurchaseRequest')
            PurchaseRequestLine = apps.get_model('purchases', 'PurchaseRequestLine')

            with transaction.atomic():
                # Create main document
                data = {
                    'supplier': supplier,
                    'location': location,
                    **kwargs
                }

                result = DocumentService.create_document(
                    PurchaseRequest, data, user, location
                )

                if not result['success']:
                    return result

                request = result['document']

                # Create lines if provided
                if lines_data:
                    for line_data in lines_data:
                        line = PurchaseRequestLine(
                            document=request,
                            **line_data
                        )
                        line.full_clean()
                        line.save()

                return {
                    'success': True,
                    'document': request,
                    'message': f'Purchase Request {request.document_number} created with {len(lines_data) if lines_data else 0} lines'
                }

        except Exception as e:
            return {
                'success': False,
                'message': str(e),
                'error_code': 'REQUEST_CREATION_FAILED'
            }

    # =====================
    # STATUS TRANSITIONS
    # =====================

    @staticmethod
    @transaction.atomic
    def transition_document(document, to_status: str, user: User,
                            comments: str = '', **kwargs) -> Dict:
        """
        Execute document status transition

        ИНТЕГРИРА:
        - DocumentType validation (allowed transitions)
        - ApprovalRule workflow (if requires approval)
        - Business rules validation
        - Post-transition actions
        """
        try:
            from_status = document.status

            logger.info(f"Transitioning {document.document_number}: {from_status} → {to_status}")

            # 1. Validate transition is allowed
            validation = DocumentService._validate_transition(document, to_status)
            if not validation['valid']:
                return {
                    'success': False,
                    'message': validation['message'],
                    'error_code': 'TRANSITION_NOT_ALLOWED'
                }

            # 2. Check if approval is needed
            if DocumentService._requires_approval(document, to_status):
                # Delegate to ApprovalService
                from .approval_service import ApprovalService
                return ApprovalService.execute_transition(
                    document, to_status, user, comments, **kwargs
                )

            # 3. Business rules validation
            business_validation = DocumentService._validate_business_rules(
                document, to_status, user, **kwargs
            )
            if not business_validation['valid']:
                return {
                    'success': False,
                    'message': business_validation['message'],
                    'error_code': 'BUSINESS_RULES_FAILED'
                }

            # 4. Execute transition
            document.status = to_status
            if hasattr(document, 'updated_by'):
                document.updated_by = user
            document.save()

            # 5. Post-transition actions
            DocumentService._execute_post_transition_actions(
                document, from_status, to_status, user, **kwargs
            )

            logger.info(f"Successfully transitioned {document.document_number} to {to_status}")

            return {
                'success': True,
                'document': document,
                'message': f'Document transitioned to {to_status}',
                'from_status': from_status,
                'to_status': to_status
            }

        except Exception as e:
            logger.error(f"Error transitioning {document.document_number}: {e}")
            return {
                'success': False,
                'message': str(e),
                'error_code': 'TRANSITION_FAILED'
            }

    @staticmethod
    def submit_for_approval(document, user: User, comments: str = '') -> Dict:
        """Submit document for approval"""
        submit_status = DocumentService._get_submission_status(document.document_type)
        return DocumentService.transition_document(
            document, submit_status, user, comments
        )

    @staticmethod
    def approve_document(document, user: User, comments: str = '') -> Dict:
        """Approve document"""
        approval_statuses = DocumentService._get_approval_statuses(document)
        if not approval_statuses:
            return {
                'success': False,
                'message': 'No approval statuses configured',
                'error_code': 'NO_APPROVAL_STATUS'
            }

        approve_status = approval_statuses[0]
        return DocumentService.transition_document(
            document, approve_status, user, comments
        )

    @staticmethod
    def reject_document(document, user: User, reason: str) -> Dict:
        """Reject document"""
        reject_status = DocumentService._get_rejection_status(document.document_type)
        return DocumentService.transition_document(
            document, reject_status, user, reason, reason=reason
        )

    # =====================
    # DYNAMIC STATUS QUERIES (REPLACES HARDCODED MANAGERS)
    # =====================

    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """
        Get documents pending approval - DYNAMIC από ApprovalRule

        ЗАМЕНЯ: hardcoded pending_approval() в managers
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        # Get pending statuses from ApprovalRule
        try:
            from ..models.approvals import ApprovalRule

            pending_statuses = set()

            # Get all document types for this model
            if hasattr(queryset.model, 'get_possible_document_types'):
                doc_types = queryset.model.get_possible_document_types()

                for doc_type in doc_types:
                    # Get statuses that are from_status in approval rules
                    rules = ApprovalRule.objects.filter(
                        document_type=doc_type,
                        is_active=True
                    )
                    pending_statuses.update(rules.values_list('from_status', flat=True))

            # Fallback to common pending statuses if no rules found
            if not pending_statuses:
                pending_statuses = {'submitted', 'pending_approval', 'pending_review'}

            return queryset.filter(status__in=pending_statuses)

        except ImportError:
            # Fallback if ApprovalRule not available
            return queryset.filter(status__in=['submitted', 'pending_approval'])

    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """
        Get documents ready for processing - DYNAMIC от ApprovalRule

        ЗАМЕНЯ: hardcoded ready_for_processing() в managers
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        # Get ready statuses from ApprovalRule
        try:
            from ..models.approvals import ApprovalRule

            ready_statuses = set()

            # Get all document types for this model
            if hasattr(queryset.model, 'get_possible_document_types'):
                doc_types = queryset.model.get_possible_document_types()

                for doc_type in doc_types:
                    # Get statuses that are to_status in approval rules (approved states)
                    rules = ApprovalRule.objects.filter(
                        document_type=doc_type,
                        is_active=True
                    )
                    ready_statuses.update(rules.values_list('to_status', flat=True))

            # Fallback to common ready statuses if no rules found
            if not ready_statuses:
                ready_statuses = {'approved', 'confirmed', 'ready', 'received'}

            return queryset.filter(status__in=ready_statuses)

        except ImportError:
            # Fallback if ApprovalRule not available
            return queryset.filter(status__in=['approved', 'confirmed'])

    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """
        Get active documents - DYNAMIC от DocumentType

        ЗАМЕНЯ: hardcoded active() в managers
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        # Get final statuses from DocumentType
        try:
            final_statuses = set()

            # Get all document types for this model
            if hasattr(queryset.model, 'get_possible_document_types'):
                doc_types = queryset.model.get_possible_document_types()

                for doc_type in doc_types:
                    # Get final statuses if method exists
                    if hasattr(doc_type, 'get_final_statuses'):
                        final_statuses.update(doc_type.get_final_statuses())

            # Fallback to common final statuses if no configuration found
            if not final_statuses:
                final_statuses = {'cancelled', 'closed', 'deleted', 'archived'}

            return queryset.exclude(status__in=final_statuses)

        except:
            # Fallback
            return queryset.exclude(status__in=['cancelled', 'closed', 'deleted'])

    # =====================
    # BUSINESS OPERATIONS
    # =====================

    @staticmethod
    def convert_request_to_order(request, user: User, **kwargs) -> Dict:
        """Convert approved Purchase Request to Purchase Order"""
        try:
            # Validate request can be converted
            if not DocumentService._can_convert_request(request):
                return {
                    'success': False,
                    'message': 'Request cannot be converted - invalid status or missing lines',
                    'error_code': 'REQUEST_NOT_CONVERTIBLE'
                }

            with transaction.atomic():
                # 1. Create Purchase Order
                PurchaseOrder = apps.get_model('purchases', 'PurchaseOrder')
                order_result = DocumentService.create_document(
                    PurchaseOrder,
                    {
                        'supplier': request.supplier,
                        'location': request.location,
                        'source_request': request,
                        **kwargs
                    },
                    user,
                    request.location
                )

                if not order_result['success']:
                    return order_result

                order = order_result['document']

                # 2. Copy lines from request to order
                DocumentService._copy_request_lines_to_order(request, order)

                # 3. Mark request as converted
                convert_status = DocumentService._get_conversion_status(request.document_type)
                if convert_status:
                    DocumentService.transition_document(
                        request, convert_status, user,
                        f'Converted to order {order.document_number}'
                    )

                # 4. Update request conversion tracking
                if hasattr(request, 'converted_to_order'):
                    request.converted_to_order = order
                    request.converted_at = timezone.now()
                    request.converted_by = user
                    request.save()

                return {
                    'success': True,
                    'request': request,
                    'order': order,
                    'message': f'Request {request.document_number} converted to order {order.document_number}'
                }

        except Exception as e:
            logger.error(f"Error converting request to order: {e}")
            return {
                'success': False,
                'message': str(e),
                'error_code': 'CONVERSION_FAILED'
            }

    # =====================
    # INFORMATION METHODS
    # =====================

    @staticmethod
    def get_available_actions(document, user: User) -> List[Dict]:
        """Get available actions for document and user"""
        try:
            actions = []

            # Get possible next statuses from DocumentType/ApprovalRule
            if document.document_type:
                next_statuses = DocumentService._get_next_statuses(document)

                for status in next_statuses:
                    # Check if user can perform this transition
                    can_perform = DocumentService._can_user_perform_transition(
                        document, status, user
                    )

                    # Get transition info
                    transition_info = DocumentService._get_transition_info(
                        document, status
                    )

                    actions.append({
                        'status': status,
                        'label': transition_info.get('label', status.replace('_', ' ').title()),
                        'can_perform': can_perform['allowed'],
                        'reason': can_perform.get('reason', ''),
                        'requires_approval': DocumentService._requires_approval(document, status),
                        'button_style': transition_info.get('button_style', 'secondary'),
                        'icon': transition_info.get('icon', 'fas fa-arrow-right')
                    })

            return actions

        except Exception as e:
            logger.error(f"Error getting available actions: {e}")
            return []

    @staticmethod
    def get_document_info(document) -> Dict:
        """Get comprehensive document information"""
        try:
            return {
                'document': {
                    'number': document.document_number,
                    'status': document.status,
                    'type': document.document_type.name if document.document_type else None,
                    'created_at': document.created_at,
                    'created_by': document.created_by.username if document.created_by else None,
                },
                'workflow': {
                    'current_status': document.status,
                    'next_statuses': DocumentService._get_next_statuses(document),
                    'is_final': DocumentService._is_final_status(document),
                    'requires_approval': document.document_type.requires_approval if document.document_type else False,
                },
                'business': {
                    'affects_inventory': getattr(document, 'affects_inventory', lambda: False)(),
                    'inventory_direction': getattr(document, 'get_inventory_direction', lambda: 'none')(),
                    'editable': getattr(document, 'is_editable', lambda: False)(),
                    'has_lines': getattr(document, 'has_lines', lambda: False)(),
                    'lines_count': getattr(document, 'get_lines_count', lambda: 0)(),
                }
            }

        except Exception as e:
            logger.error(f"Error getting document info: {e}")
            return {}

    # =====================
    # PRIVATE HELPER METHODS
    # =====================

    @staticmethod
    def _get_document_type_for_model(model_class: Type[models.Model]):
        """Get DocumentType for model class"""
        try:
            from ..models.documents import get_document_type_by_key

            # Get from model instance methods
            instance = model_class()
            app_name = instance.get_app_name() if hasattr(instance, 'get_app_name') else model_class._meta.app_label
            type_key = instance.get_document_type_key() if hasattr(instance,
                                                                   'get_document_type_key') else model_class.__name__.lower()

            return get_document_type_by_key(app_name, type_key)

        except Exception as e:
            logger.warning(f"No DocumentType found for {model_class.__name__}: {e}")
            return None

    @staticmethod
    def _generate_document_number(document_type, location, user: User) -> str:
        """Generate document number using NumberingConfiguration"""
        try:
            # Try to use NumberingConfiguration
            try:
                from ..models.numbering import generate_document_number
                return generate_document_number(document_type, location, user)
            except ImportError:
                pass  # NumberingConfiguration not available yet

            # Fallback: Simple sequential numbering
            prefix = getattr(document_type, 'code', 'DOC')

            # Simple counter (in real implementation use proper sequence)
            import uuid
            return f"{prefix}{str(uuid.uuid4())[:8].upper()}"

        except Exception as e:
            logger.error(f"Error generating document number: {e}")
            import uuid
            return f"DOC{str(uuid.uuid4())[:8].upper()}"

    @staticmethod
    def _get_initial_status(document_type) -> str:
        """Get initial status from DocumentType"""
        # From DocumentType configuration
        if hasattr(document_type, 'initial_status'):
            return getattr(document_type, 'initial_status', 'draft')

        # Fallback
        return 'draft'

    @staticmethod
    def _validate_transition(document, to_status: str) -> Dict:
        """Validate if transition is allowed by DocumentType"""
        try:
            if not document.document_type:
                return {'valid': False, 'message': 'Document has no DocumentType'}

            # Check with ApprovalRule/DocumentType
            next_statuses = DocumentService._get_next_statuses(document)

            if to_status not in next_statuses:
                return {
                    'valid': False,
                    'message': f'Transition to "{to_status}" not allowed. Allowed: {next_statuses}'
                }

            return {'valid': True}

        except Exception as e:
            return {'valid': False, 'message': str(e)}

    @staticmethod
    def _requires_approval(document, to_status: str) -> bool:
        """Check if transition requires approval"""
        if not document.document_type or not getattr(document.document_type, 'requires_approval', False):
            return False

        # Check ApprovalRule
        try:
            from ..models.approvals import ApprovalRule
            return ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status=document.status,
                to_status=to_status,
                is_active=True
            ).exists()
        except ImportError:
            return False

    @staticmethod
    def _get_next_statuses(document) -> List[str]:
        """Get next possible statuses - DYNAMIC from ApprovalRule"""
        if not document.document_type:
            return []

        try:
            from ..models.approvals import ApprovalRule
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status=document.status,
                is_active=True
            )

            return list(rules.values_list('to_status', flat=True).distinct())
        except ImportError:
            return []

    @staticmethod
    def _validate_business_rules(document, to_status: str, user: User, **kwargs) -> Dict:
        """Validate business-specific rules"""
        try:
            # Dynamic: Call model-specific validation if exists
            model_name = document.__class__.__name__.lower()

            validation_method = getattr(
                DocumentService,
                f'_validate_{model_name}_rules',
                None
            )

            if validation_method:
                return validation_method(document, to_status, user, **kwargs)

            # Default: Basic validation
            return {'valid': True, 'message': 'No specific business rules'}

        except Exception as e:
            return {'valid': False, 'message': str(e)}

    @staticmethod
    def _validate_purchaserequest_rules(document, to_status: str, user: User, **kwargs) -> Dict:
        """Purchase Request specific validation"""
        # Get submission statuses dynamically
        submission_statuses = DocumentService._get_submission_statuses(document.document_type)

        if to_status in submission_statuses:
            lines_attr = getattr(document, 'lines', None)
            if not lines_attr or not lines_attr.exists():
                return {'valid': False, 'message': 'Cannot submit request without lines'}

        return {'valid': True}

    @staticmethod
    def _execute_post_transition_actions(document, from_status: str, to_status: str,
                                         user: User, **kwargs):
        """Execute actions after successful transition"""
        try:
            # Inventory movements (if document affects inventory)
            if getattr(document, 'affects_inventory', lambda: False)():
                DocumentService._handle_inventory_movements(document, to_status)

            # Notifications
            DocumentService._send_transition_notifications(document, from_status, to_status, user)

        except Exception as e:
            logger.error(f"Error in post-transition actions: {e}")

    @staticmethod
    def _handle_inventory_movements(document, status: str):
        """Handle inventory movements based on document status"""
        try:
            # Integration with inventory service if available
            inventory_timing = getattr(document.document_type, 'inventory_timing', None)

            if inventory_timing == 'on_status_change':
                try:
                    from inventory.services.movement_service import MovementService
                    MovementService.create_movements_from_document(document, status)
                except ImportError:
                    logger.warning("InventoryService not available")

        except Exception as e:
            logger.error(f"Error handling inventory movements: {e}")

    @staticmethod
    def _send_transition_notifications(document, from_status: str, to_status: str, user: User):
        """Send notifications for status transition"""
        try:
            # Integration with notification service if available
            try:
                from notifications.services import NotificationService
                NotificationService.send_status_change_notification(
                    document, from_status, to_status, user
                )
            except ImportError:
                logger.info(f"Notification: {document.document_number} {from_status}→{to_status} by {user.username}")

        except Exception as e:
            logger.error(f"Error sending notifications: {e}")

    # =====================
    # DYNAMIC STATUS HELPERS (NO HARDCODING)
    # =====================

    @staticmethod
    def _get_submission_statuses(document_type) -> List[str]:
        """Get statuses that represent submission"""
        try:
            from ..models.approvals import ApprovalRule
            return list(ApprovalRule.objects.filter(
                document_type=document_type,
                is_active=True
            ).values_list('from_status', flat=True).distinct())
        except ImportError:
            return ['submitted']

    @staticmethod
    def _get_submission_status(document_type) -> str:
        """Get the submission status"""
        statuses = DocumentService._get_submission_statuses(document_type)
        return statuses[0] if statuses else 'submitted'

    @staticmethod
    def _get_approval_statuses(document) -> List[str]:
        """Get statuses that represent approval"""
        if not document.document_type:
            return []

        try:
            from ..models.approvals import ApprovalRule
            return list(ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status=document.status,
                is_active=True
            ).values_list('to_status', flat=True).distinct())
        except ImportError:
            return []

    @staticmethod
    def _get_rejection_status(document_type) -> str:
        """Get rejection status"""
        return 'rejected'

    @staticmethod
    def _get_conversion_status(document_type) -> Optional[str]:
        """Get conversion status for requests"""
        return 'converted'

    @staticmethod
    def _is_final_status(document) -> bool:
        """Check if current status is final"""
        if not document.document_type:
            return False

        # Check if no transitions from current status
        next_statuses = DocumentService._get_next_statuses(document)
        return len(next_statuses) == 0

    @staticmethod
    def _can_convert_request(request) -> bool:
        """Check if request can be converted to order"""
        # Business logic: Must be approved and have lines
        approval_statuses = DocumentService._get_approval_statuses(request)

        lines_attr = getattr(request, 'lines', None)
        has_lines = lines_attr and lines_attr.exists()

        return (
                request.status in approval_statuses and
                has_lines
        )

    @staticmethod
    def _copy_request_lines_to_order(request, order):
        """Copy lines from request to order"""
        try:
            PurchaseOrderLine = apps.get_model('purchases', 'PurchaseOrderLine')

            lines_attr = getattr(request, 'lines', None)
            if not lines_attr:
                return

            for req_line in lines_attr.all():
                order_line = PurchaseOrderLine(
                    document=order,
                    product=req_line.product,
                    ordered_quantity=getattr(req_line, 'requested_quantity', req_line.quantity),
                    unit=req_line.unit,
                    notes=getattr(req_line, 'notes', ''),
                )
                order_line.save()

        except Exception as e:
            logger.error(f"Error copying request lines: {e}")
            raise

    @staticmethod
    def _can_user_perform_transition(document, to_status: str, user: User) -> Dict:
        """Check if user can perform transition"""
        try:
            # Delegate to ApprovalService for approval checks
            if DocumentService._requires_approval(document, to_status):
                from .approval_service import ApprovalService
                return ApprovalService.can_user_approve(document, to_status, user)

            # Basic permission check for non-approval transitions
            return {'allowed': True, 'reason': ''}

        except Exception as e:
            return {'allowed': False, 'reason': str(e)}

    @staticmethod
    def _get_transition_info(document, to_status: str) -> Dict:
        """Get UI information for transition"""
        # Configurable transition info
        default_info = {
            'submit': {'label': 'Submit for Approval', 'button_style': 'primary', 'icon': 'fas fa-paper-plane'},
            'approve': {'label': 'Approve', 'button_style': 'success', 'icon': 'fas fa-check'},
            'reject': {'label': 'Reject', 'button_style': 'danger', 'icon': 'fas fa-times'},
            'convert': {'label': 'Convert to Order', 'button_style': 'info', 'icon': 'fas fa-exchange-alt'},
        }

        # Map status to action type
        for action, info in default_info.items():
            if action in to_status.lower():
                return info

        # Default
        return {
            'label': to_status.replace('_', ' ').title(),
            'button_style': 'secondary',
            'icon': 'fas fa-arrow-right'
        }

    # nomenclatures/services/document_service.py - ДОБАВИ САМО ТЕЗИ РЕДОВЕ

    @staticmethod
    def generate_number_for(instance):
        """Generate number for existing model instance (for admin save())"""
        try:
            from nomenclatures.models.numbering import generate_document_number

            # Намери DocumentType
            document_type = DocumentService._get_document_type_for_model(instance.__class__)

            if document_type:
                # ЗАДАЙ СТАТУС АКО НЯМА
                if hasattr(instance, 'status') and not instance.status:
                    instance.status = DocumentService._get_initial_status(document_type)

                return generate_document_number(
                    document_type=document_type,
                    location=getattr(instance, 'location', None),
                    user=getattr(instance, 'created_by', None)
                )
        except:
            pass

        # Fallback
        from datetime import datetime
        prefix = instance.__class__.__name__[:3].upper()
        timestamp = datetime.now().strftime("%y%m%d%H%M%S")

        # ЗАДАЙ СТАТУС И ТУК
        if hasattr(instance, 'status') and not instance.status:
            instance.status = 'draft'

        return f"{prefix}{timestamp}"