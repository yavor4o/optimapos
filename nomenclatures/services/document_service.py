# nomenclatures/services/document_service.py - ЦЯЛОСТЕН КОД
"""
Document Service - COMPLETE VERSION

ЛОГИКА:
1. Ако DocumentType.requires_approval=True → използва ApprovalRule workflow
2. Ако DocumentType.requires_approval=False → използва само DocumentTypeStatus настройки
3. Поддържа малки магазини без сложни одобрения
4. Поддържа едитиране на completed документи (allow_edit_completed)
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any, Type, Union, Tuple, TYPE_CHECKING

from nomenclatures.models import DocumentTypeStatus

if TYPE_CHECKING:
    from django.db import models as django_models
from dataclasses import dataclass, field
from django.db import transaction, models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.apps import apps
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


# =====================
# RESULT TYPES (Унифицирани с ApprovalService)
# =====================

@dataclass
class Result:
    """Унифициран резултат за всички services"""
    ok: bool
    code: Optional[str] = None
    msg: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, data: Dict = None, msg: str = None) -> 'Result':
        return cls(ok=True, data=data or {}, msg=msg)

    @classmethod
    def error(cls, code: str, msg: str, data: Dict = None) -> 'Result':
        return cls(ok=False, code=code, msg=msg, data=data or {})


class DocumentService:
    """
    Document Service - CENTRAL ORCHESTRATOR

    Поддържа и сложни approval workflows и прости status transitions.
    """

    # =====================
    # DOCUMENT CREATION
    # =====================

    @staticmethod
    @transaction.atomic
    def create_document(model_class,
                        data: Dict[str, Any],
                        user: User,
                        location: Optional[Any] = None) -> Result:
        """
        Create document with automatic numbering and initial status
        """
        try:
            # 1. Get DocumentType
            document_type = DocumentService._get_document_type_for_model(model_class)
            if not document_type:
                return Result.error(
                    'DOCUMENT_TYPE_NOT_FOUND',
                    f'No DocumentType found for {model_class.__name__}'
                )

            # 2. Extract location
            location = location or data.get('location')
            if not location:
                return Result.error('LOCATION_REQUIRED', 'Location is required for document creation')

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
            document.save()

            logger.info(f"Created {model_class.__name__} {document_number} by {user.username}")

            return Result.success(
                data={'document': document},
                msg=f'Document {document_number} created successfully'
            )

        except Exception as e:
            logger.error(f"Error creating {model_class.__name__}: {e}")
            return Result.error('DOCUMENT_CREATION_FAILED', str(e))

    @staticmethod
    def create_purchase_request(supplier, location, user, lines_data=None, **kwargs) -> Result:
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

                result = DocumentService.create_document(PurchaseRequest, data, user, location)
                if not result.ok:
                    return result

                request = result.data['document']

                # Create lines if provided
                if lines_data:
                    for line_data in lines_data:
                        line = PurchaseRequestLine(
                            document=request,
                            **line_data
                        )
                        line.full_clean()
                        line.save()

                return Result.success(
                    data={'document': request},
                    msg=f'Purchase Request {request.document_number} created with {len(lines_data) if lines_data else 0} lines'
                )

        except Exception as e:
            return Result.error('REQUEST_CREATION_FAILED', str(e))

    # =====================
    # STATUS TRANSITIONS - ГЛАВНАТА ЛОГИКА
    # =====================

    @staticmethod
    @transaction.atomic
    def transition_document(document, to_status: str, user: User,
                            comments: str = '', **kwargs) -> Result:
        """
        Execute document status transition - COMPLETE FIXED VERSION

        ЛОГИКА:
        1. Ако requires_approval=True → ApprovalService authorization + ApprovalRule
        2. Ако requires_approval=False → DocumentTypeStatus validation САМО
        3. Винаги business validation
        4. State change + conditional logging
        """
        try:
            from_status = document.status

            logger.info(f"🔄 Transitioning {document.document_number}: {from_status} → {to_status}")

            # Lock document за race condition protection
            document = document.__class__.objects.select_for_update().get(pk=document.pk)

            # Идемпотентност
            if document.status == to_status:
                return Result.success(
                    data={'status': to_status},
                    msg=f'Document already in status {to_status}'
                )

            # 1. ОСНОВНА ВАЛИДАЦИЯ
            if not document.document_type:
                logger.error(f"❌ Document {document.document_number} has no document_type")
                return Result.error('NO_DOCUMENT_TYPE', 'Document has no type configured')

            # 2. СТАТУС ВАЛИДАЦИЯ (винаги се прави)
            logger.debug(f"🔍 Validating status transition for {document.document_number}")
            status_result = DocumentService._validate_status_transition(document, to_status)
            if not status_result.ok:
                logger.error(f"❌ Status validation failed: {status_result.msg}")
                return status_result

            # 3. APPROVAL vs SIMPLE TRANSITION ЛОГИКА
            approval_data = {}

            if document.document_type.requires_approval:
                # === APPROVAL WORKFLOW ===
                logger.debug(f"🔒 Document requires approval - checking ApprovalService")
                try:
                    from .approval_service import ApprovalService

                    decision = ApprovalService.authorize_transition(document, user, to_status)
                    if not decision.allowed:
                        logger.warning(f"🚫 Approval denied: {decision.reason}")
                        return Result.error(
                            'AUTHORIZATION_DENIED',
                            decision.reason,
                            data={'rule_id': decision.rule_id, 'level': decision.level}
                        )

                    logger.info(f"✅ Approval authorized by rule {decision.rule_id}")
                    approval_data = {
                        'rule_id': decision.rule_id,
                        'level': decision.level
                    }

                except ImportError:
                    logger.error("❌ ApprovalService not available but document requires approval")
                    return Result.error('APPROVAL_SERVICE_UNAVAILABLE', 'Approval system not available')

            else:
                # === SIMPLE TRANSITION (малки магазини) ===
                logger.debug(f"🟢 Simple transition - no approval required")
                simple_result = DocumentService._validate_simple_transition(document, to_status, user)
                if not simple_result.ok:
                    logger.error(f"❌ Simple validation failed: {simple_result.msg}")
                    return simple_result

            # 4. BUSINESS VALIDATION
            logger.debug(f"🔧 Validating business rules")
            business_result = DocumentService._validate_business_rules(
                document, to_status, user, **kwargs
            )
            if not business_result.ok:
                logger.error(f"❌ Business validation failed: {business_result.msg}")
                return business_result

            # 5. 🚀 EXECUTE TRANSITION
            logger.info(f"🚀 Executing transition: {from_status} → {to_status}")

            old_status = document.status
            document.status = to_status

            # Update audit fields
            if hasattr(document, 'updated_by'):
                document.updated_by = user
            if hasattr(document, 'approved_by') and 'approv' in to_status.lower():
                document.approved_by = user
            if hasattr(document, 'approved_at') and 'approv' in to_status.lower():
                document.approved_at = timezone.now()

            # 🔥 CRITICAL FIX: Save document immediately
            try:
                document.save()
                logger.info(f"💾 Document saved with new status: {to_status}")
            except Exception as save_error:
                logger.error(f"❌ Failed to save document: {save_error}")
                return Result.error('SAVE_FAILED', f'Failed to save document: {save_error}')

            # 6. 🔥 CONDITIONAL LOGGING (fixed)
            try:
                if document.document_type.requires_approval:
                    # Log to ApprovalLog for approval workflows
                    logger.debug(f"📝 Logging to ApprovalLog")
                    DocumentService._log_transition(
                        document, approval_data.get('rule_id'), old_status, to_status, user, comments
                    )
                else:
                    # Log to Django admin log for simple transitions
                    logger.debug(f"📝 Logging to Admin log (simple transition)")
                    DocumentService._log_simple_transition(
                        document, old_status, to_status, user, comments
                    )
            except Exception as log_error:
                # Logging failure should NOT break the transition
                logger.warning(f"⚠️ Logging failed but transition succeeded: {log_error}")

            # 7. POST-TRANSITION EFFECTS
            try:
                logger.debug(f"🔄 Executing post-transition actions")
                DocumentService._execute_post_transition_actions(
                    document, old_status, to_status, user, **kwargs
                )
            except Exception as post_error:
                logger.warning(f"⚠️ Post-transition actions failed: {post_error}")

            logger.info(f"✅ Successfully transitioned {document.document_number} to {to_status}")

            return Result.success(
                data={
                    'document': document,
                    'from_status': old_status,
                    'to_status': to_status,
                    **approval_data
                },
                msg=f'Document transitioned from {old_status} to {to_status}'
            )

        except Exception as e:
            logger.error(f"💥 Error transitioning {document.document_number}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Result.error('TRANSITION_FAILED', str(e))

    # =====================
    # SMART CONVENIENCE METHODS
    # =====================

    # nomenclatures/services/document_service.py - ЛИПСВАЩИЯ МЕТОД

    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """
        Get documents ready for next processing step - КОМПЕТИРАЛ ЛИПСВАЩИЯ МЕТОД

        ЛОГИКА:
        - Documents които са ОДОБРЕНИ но още НЕ СА започнали следващата стъпка
        - За PurchaseRequest: approved но не converted
        - За PurchaseOrder: confirmed но не delivered
        - За DeliveryReceipt: received но не completed

        ИЗПОЛЗВА:
        - ApprovalRule.to_status_obj за статуси които са резултат от approval
        - DocumentTypeStatus с can_be_processed=True (ако има такова поле)
        - Fallback логика за всеки document type
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ..models.approvals import ApprovalRule
            from ..models.statuses import DocumentTypeStatus

            processing_statuses = set()

            # Get document type за този модел
            doc_type = DocumentService._get_document_type_for_model(queryset.model)

            if doc_type and doc_type.requires_approval:
                # === APPROVAL WORKFLOW ЛОГИКА ===
                # Намери статуси които са резултат от successful approval
                rules = ApprovalRule.objects.filter(
                    document_type=doc_type,
                    is_active=True
                )
                # Вземи to_status от approval rules (това са одобрените статуси)
                processing_statuses.update(rules.values_list('to_status_obj__code', flat=True))

            else:
                # === SIMPLE WORKFLOW ЛОГИКА ===
                # Използвай DocumentTypeStatus за "processing ready" статуси
                type_statuses = DocumentTypeStatus.objects.filter(
                    document_type=doc_type,
                    is_active=True,
                    is_final=False,  # Не са финални
                    # can_be_processed=True  # Ако има такова поле
                )
                processing_statuses.update(type_statuses.values_list('status__code', flat=True))

            # === FALLBACK ПО MODEL TYPE ===
            if not processing_statuses:
                model_name = queryset.model.__name__.lower()

                if 'request' in model_name:
                    # PurchaseRequest: approved = готов за conversion в order
                    processing_statuses = {'approved'}

                elif 'order' in model_name:
                    # PurchaseOrder: confirmed = готов за delivery creation
                    processing_statuses = {'confirmed', 'sent'}

                elif 'delivery' in model_name or 'receipt' in model_name:
                    # DeliveryReceipt: received = готов за completion
                    processing_statuses = {'received', 'partial'}

                elif 'invoice' in model_name:
                    # Invoice: approved = готов за payment
                    processing_statuses = {'approved', 'sent'}

                else:
                    # Generic fallback
                    processing_statuses = {'approved', 'confirmed', 'ready'}

            return queryset.filter(status__in=processing_statuses)

        except ImportError:
            # === COMPLETE FALLBACK БЕЗ NOMENCLATURES ===
            model_name = queryset.model.__name__.lower()

            if 'request' in model_name:
                return queryset.filter(status='approved')
            elif 'order' in model_name:
                return queryset.filter(status='confirmed')
            elif 'delivery' in model_name:
                return queryset.filter(status='received')
            else:
                return queryset.filter(status__in=['approved', 'confirmed', 'ready'])

    @staticmethod
    def submit_for_approval(document, user: User, comments: str = '') -> Result:
        """Submit document for approval - SMART VERSION"""
        try:
            if not document.document_type.requires_approval:
                return Result.error(
                    'NO_APPROVAL_REQUIRED',
                    'This document type does not require approval'
                )

            from .approval_service import ApprovalService
            target_status = ApprovalService.find_submission_status(document)

            if not target_status:
                return Result.error(
                    'NO_SUBMISSION_STATUS',
                    'No submission status found for current state'
                )

            return DocumentService.transition_document(document, target_status, user, comments)

        except Exception as e:
            return Result.error('SUBMISSION_FAILED', str(e))

    @staticmethod
    def approve_document(document, user: User, comments: str = '') -> Result:
        """Approve document - SMART VERSION"""
        try:
            from .approval_service import ApprovalService

            target_status = ApprovalService.find_next_approval_status(document)
            if not target_status:
                return Result.error(
                    'NO_APPROVAL_STATUS',
                    'No approval status found for current state'
                )

            return DocumentService.transition_document(document, target_status, user, comments)

        except Exception as e:
            return Result.error('APPROVAL_FAILED', str(e))

    @staticmethod
    def reject_document(document, user: User, reason: str) -> Result:
        """Reject document - SMART VERSION"""
        try:
            from .approval_service import ApprovalService

            target_status = ApprovalService.find_rejection_status(document)
            if not target_status:
                return Result.error(
                    'NO_REJECTION_STATUS',
                    'No rejection status found for current state'
                )

            return DocumentService.transition_document(
                document, target_status, user, reason
            )

        except Exception as e:
            return Result.error('REJECTION_FAILED', str(e))

    # =====================
    # EDITING PERMISSIONS - ЗА КОРЕКЦИИ
    # =====================

    # nomenclatures/services/document_service.py - Замени метода can_edit_document

    @staticmethod
    def can_edit_document(document, user) -> Tuple[bool, str]:
        """
        FIXED: Check if document can be edited - използва правилната йерархия на permissions
        """
        try:
            # 1. Провери дали има DocumentStatus
            from nomenclatures.models import DocumentStatus
            status_obj = DocumentStatus.objects.filter(code=document.status).first()

            if not status_obj:
                return False, f"Unknown status: {document.status}"

            # 2. ПЪРВО - провери DocumentStatus базовото правило (global constraint)
            if not status_obj.allow_edit:
                return False, f"Status '{status_obj.name}' doesn't allow editing globally"

            # 3. ВТОРО - провери DocumentTypeStatus override (type-specific constraint)
            from nomenclatures.models import DocumentTypeStatus
            type_status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status=status_obj,
                is_active=True
            ).first()

            if type_status_config and not type_status_config.allows_editing:
                return False, f"Cannot edit {document.document_type.name} in '{status_obj.name}' status"

            # 4. ТРЕТО - провери user permissions (Django permissions)
            if user and hasattr(user, 'has_perm'):
                edit_permission = f"{document._meta.app_label}.change_{document._meta.model_name}"
                if not user.has_perm(edit_permission):
                    return False, f"User doesn't have permission to edit {document._meta.model_name}"

            return True, "Editing allowed"

        except Exception as e:
            logger.error(f"Error checking edit permissions: {e}")
            return False, f"Error checking permissions: {e}"

    @staticmethod
    def _check_completed_edit_permissions(document, user: User) -> Dict:
        """Провери permissions за editing на completed документи"""
        try:
            # 1. Creator винаги може (ако няма restrictions)
            if hasattr(document, 'created_by') and document.created_by == user:
                return {'allowed': True, 'reason': 'Document creator'}

            # 2. Admin permissions
            if user.is_superuser:
                return {'allowed': True, 'reason': 'Superuser permissions'}

            # 3. Specific permissions за editing completed
            perm_name = f'{document._meta.app_label}.edit_completed_{document._meta.model_name}'
            if user.has_perm(perm_name):
                return {'allowed': True, 'reason': 'Has edit_completed permission'}

            # 4. Manager role check
            if user.groups.filter(name__icontains='manager').exists():
                return {'allowed': True, 'reason': 'Manager role'}

            return {'allowed': False, 'reason': 'Insufficient permissions to edit completed document'}

        except Exception as e:
            return {'allowed': False, 'reason': f'Error checking permissions: {e}'}

    # =====================
    # STATUS VALIDATION METHODS
    # =====================

    @staticmethod
    def _validate_status_transition(document, to_status: str) -> Result:
        """Провери дали to_status е валиден за document_type"""
        try:
            # Провери дали to_status съществува в DocumentTypeStatus
            from ..models.statuses import DocumentTypeStatus

            status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=to_status,
                is_active=True
            ).first()

            if not status_config:
                # Намери какви статуси са конфигурирани
                configured = list(
                    DocumentTypeStatus.objects.filter(
                        document_type=document.document_type,
                        is_active=True
                    ).values_list('status__code', flat=True)
                )

                return Result.error(
                    'INVALID_STATUS',
                    f"Status '{to_status}' is not configured for document type "
                    f"'{document.document_type.type_key}'. Available: {configured}"
                )

            # Провери transition rules
            current_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            # Не може FROM final статус
            if current_config and current_config.is_final:
                return Result.error(
                    'FROM_FINAL_STATUS',
                    f"Cannot transition from final status '{document.status}'"
                )

            # Не може TO initial статус
            if status_config.is_initial:
                return Result.error(
                    'TO_INITIAL_STATUS',
                    f"Cannot transition to initial status '{to_status}'"
                )

            return Result.success()

        except Exception as e:
            return Result.error('STATUS_VALIDATION_ERROR', str(e))

    @staticmethod
    def _validate_simple_transition(document, to_status: str, user: User) -> Result:
        """
        Валидация за документи БЕЗ approval workflow

        Проверява само основни business rules и permissions
        """
        try:
            # 1. Basic permissions - всеки може да прави transitions (освен restrictions)

            # 2. Специални business rules за common transitions
            if 'complet' in to_status.lower():
                # Към completed статус - провери lines
                if hasattr(document, 'lines'):
                    if not document.lines.exists():
                        return Result.error(
                            'NO_LINES',
                            'Cannot complete document without lines'
                        )

            # 3. Cancel transition - винаги позволен (освен от final)
            if 'cancel' in to_status.lower():
                return Result.success(msg="Cancellation allowed")

            # 4. Default - позволено
            return Result.success(msg="Simple transition allowed")

        except Exception as e:
            return Result.error('SIMPLE_TRANSITION_ERROR', str(e))

    @staticmethod
    def _validate_business_rules(document, to_status: str, user: User, **kwargs) -> Result:
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
                result = validation_method(document, to_status, user, **kwargs)
                if isinstance(result, dict):
                    # Legacy format conversion
                    if result.get('valid'):
                        return Result.success(msg=result.get('message', 'Business rules passed'))
                    else:
                        return Result.error('BUSINESS_RULE_VIOLATION', result.get('message', 'Business rule failed'))
                return result

            # Default: Basic validation
            return Result.success(msg='No specific business rules')

        except Exception as e:
            return Result.error('BUSINESS_VALIDATION_ERROR', str(e))

    @staticmethod
    def _validate_purchaserequest_rules(document, to_status: str, user: User, **kwargs) -> Result:
        """Purchase Request specific validation"""
        try:
            # Submission validation
            if any(word in to_status.lower() for word in ['submit', 'pending', 'review']):
                if not document.lines.exists():
                    return Result.error(
                        'NO_LINES',
                        'Cannot submit request without lines'
                    )

            # Completion validation
            if 'complet' in to_status.lower():
                if not document.lines.exists():
                    return Result.error(
                        'NO_LINES',
                        'Cannot complete request without lines'
                    )

                # Check all lines have required data
                incomplete_lines = document.lines.filter(
                    models.Q(quantity__isnull=True) | models.Q(quantity__lte=0)
                )
                if incomplete_lines.exists():
                    return Result.error(
                        'INCOMPLETE_LINES',
                        f'Lines with missing quantities: {incomplete_lines.count()}'
                    )

            return Result.success()

        except Exception as e:
            return Result.error('PURCHASE_REQUEST_VALIDATION_ERROR', str(e))

    # =====================
    # INFORMATION & QUERY METHODS
    # =====================

    @staticmethod
    def get_available_actions(document, user: User) -> List[Dict]:
        """Get available actions for document and user"""
        try:
            actions = []

            if not document.document_type:
                return actions

            if document.document_type.requires_approval:
                # === APPROVAL WORKFLOW ACTIONS ===
                from .approval_service import ApprovalService
                transitions = ApprovalService.get_available_transitions(document, user)

                for trans in transitions:
                    actions.append({
                        'action': 'transition',
                        'status': trans['to_status'],
                        'label': trans['label'],
                        'can_perform': True,
                        'requires_approval': True,
                        'button_style': DocumentService._get_button_style(trans['to_status']),
                        'icon': trans.get('icon', 'fas fa-arrow-right'),
                        'rule_id': trans.get('rule_id')
                    })
            else:
                # === SIMPLE WORKFLOW ACTIONS ===
                available_statuses = DocumentService._get_simple_next_statuses(document)

                for status in available_statuses:
                    actions.append({
                        'action': 'transition',
                        'status': status,
                        'label': status.replace('_', ' ').title(),
                        'can_perform': True,
                        'requires_approval': False,
                        'button_style': DocumentService._get_button_style(status),
                        'icon': DocumentService._get_status_icon(status)
                    })

            # === EDIT ACTION ===
            can_edit, edit_reason = DocumentService.can_edit_document(document, user)
            if can_edit:
                actions.append({
                    'action': 'edit',
                    'label': 'Edit Document',
                    'can_perform': True,
                    'button_style': 'outline-primary',
                    'icon': 'fas fa-edit',
                    'reason': edit_reason
                })

            return actions

        except Exception as e:
            logger.error(f"Error getting available actions: {e}")
            return []

    @staticmethod
    def _get_simple_next_statuses(document) -> List[str]:
        """Намери следващи статуси за simple workflow"""
        try:
            from ..models.statuses import DocumentTypeStatus

            # Намери всички non-initial статуси за този document type
            all_statuses = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                is_initial=False,
                is_active=True
            ).exclude(
                status__code=document.status
            ).order_by('sort_order')

            # Филтрирай според current status
            available = []

            for config in all_statuses:
                status_code = config.status.code

                # Основни правила:
                # - От draft може към всички
                # - От in-progress може към completed или cancelled
                # - От completed може само към cancelled (ако allow_edit_completed)

                if document.status == 'draft':
                    available.append(status_code)
                elif 'cancel' in status_code:
                    # Cancellation винаги е възможна
                    available.append(status_code)
                elif not config.is_final:
                    # Към non-final статуси
                    available.append(status_code)

            return available

        except Exception as e:
            logger.error(f"Error getting simple next statuses: {e}")
            return []

    @staticmethod
    def _get_status_info(document) -> Dict:
        """Информация за текущия статус"""
        try:
            from ..models.statuses import DocumentTypeStatus

            config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).select_related('status').first()

            if config:
                return {
                    'code': config.status.code,
                    'name': config.custom_name or config.status.name,
                    'color': config.status.color,
                    'icon': config.status.icon,
                    'is_initial': config.is_initial,
                    'is_final': config.is_final,
                    'is_cancellation': config.is_cancellation,
                    'allow_edit': config.status.allow_edit,
                    'allow_delete': config.status.allow_delete
                }

            # Fallback
            return {
                'code': document.status,
                'name': document.status.replace('_', ' ').title(),
                'color': '#6c757d',
                'is_initial': document.status == 'draft',
                'is_final': document.status in ['completed', 'cancelled'],
                'is_cancellation': 'cancel' in document.status.lower(),
                'allow_edit': True,
                'allow_delete': False
            }

        except Exception as e:
            logger.error(f"Error getting status info: {e}")
            return {'code': document.status}

    # =====================
    # HELPER METHODS
    # =====================

    @staticmethod
    def _get_button_style(status: str) -> str:
        """UI button style за статуси"""
        status_lower = status.lower()

        if any(word in status_lower for word in ['approv', 'accept', 'confirm']):
            return 'success'
        elif any(word in status_lower for word in ['reject', 'deny', 'cancel']):
            return 'danger'
        elif any(word in status_lower for word in ['submit', 'send']):
            return 'primary'
        elif any(word in status_lower for word in ['complet', 'finish']):
            return 'info'
        else:
            return 'secondary'

    @staticmethod
    def _get_status_icon(status: str) -> str:
        """Icon за статуси"""
        status_lower = status.lower()

        if any(word in status_lower for word in ['approv', 'accept']):
            return 'fas fa-check'
        elif any(word in status_lower for word in ['reject', 'deny']):
            return 'fas fa-times'
        elif 'cancel' in status_lower:
            return 'fas fa-ban'
        elif any(word in status_lower for word in ['submit', 'send']):
            return 'fas fa-paper-plane'
        elif any(word in status_lower for word in ['complet', 'finish']):
            return 'fas fa-check-circle'
        elif 'draft' in status_lower:
            return 'fas fa-edit'
        else:
            return 'fas fa-arrow-right'

    @staticmethod
    def _log_transition(document, rule_id: Optional[int], from_status: str,
                        to_status: str, user: User, comments: str = ''):
        """
        🔥 FIXED: Log approval transition - SKIP for simple transitions
        """
        try:
            # 🔥 FIX: Skip logging for documents that don't require approval
            if not document.document_type.requires_approval:
                logger.debug(f"Skipping ApprovalLog for simple transition: {from_status} → {to_status}")
                return

            # 🔥 FIX: Skip logging if no rule_id (shouldn't happen for approval docs, but safety check)
            if not rule_id:
                logger.warning(f"No rule_id for approval document {document.document_number}, skipping log")
                return

            from ..models.approvals import ApprovalLog, ApprovalRule
            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get_for_model(document.__class__)

            # Determine action based on to_status
            if any(word in to_status.lower() for word in ['approv', 'accept', 'confirm']):
                action = 'approved'
            elif any(word in to_status.lower() for word in ['reject', 'deny']):
                action = 'rejected'
            elif any(word in to_status.lower() for word in ['cancel']):
                action = 'cancelled'
            else:
                action = 'submitted'

            # Get rule
            try:
                rule = ApprovalRule.objects.get(id=rule_id)
            except ApprovalRule.DoesNotExist:
                logger.error(f"ApprovalRule {rule_id} not found for logging")
                return

            # Create log entry
            ApprovalLog.objects.create(
                content_type=content_type,
                object_id=document.pk,
                rule=rule,  # Now guaranteed to exist
                action=action,
                from_status=from_status,
                to_status=to_status,
                actor=user,
                comments=comments or ''
            )

            logger.debug(f"✅ Logged approval transition: {from_status} → {to_status}")

        except Exception as e:
            logger.error(f"❌ Error logging approval transition: {e}")
            # 🔥 IMPORTANT: Don't re-raise - logging failure shouldn't break transition

    # 🔥 ALSO ADD: Alternative logging for simple transitions (optional)
    @staticmethod
    def _log_simple_transition(document, from_status: str, to_status: str, user: User, comments: str = ''):
        """
        Log simple transition without ApprovalRule (optional alternative logging)
        Could save to Django admin log or custom SimpleTransitionLog model
        """
        try:
            from django.contrib.admin.models import LogEntry, CHANGE
            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get_for_model(document.__class__)

            LogEntry.objects.log_action(
                user_id=user.id,
                content_type_id=content_type.id,
                object_id=document.pk,
                object_repr=str(document),
                action_flag=CHANGE,
                change_message=f"Status changed from {from_status} to {to_status}" +
                               (f" - {comments}" if comments else "")
            )

            logger.debug(f"✅ Logged simple transition to admin log: {from_status} → {to_status}")

        except Exception as e:
            logger.debug(f"⚠️ Failed to log simple transition: {e}")

    @staticmethod
    def _execute_post_transition_actions(document, from_status: str, to_status: str,
                                         user: User, **kwargs):
        """Execute actions after successful transition"""
        try:
            # 1. Inventory movements (if document affects inventory)
            if document.document_type.affects_inventory:
                DocumentService._handle_inventory_movements(document, from_status, to_status)

            # 2. Notifications
            DocumentService._send_transition_notifications(document, from_status, to_status, user)

            # 3. Auto-calculations (VAT, totals, etc.)
            DocumentService._update_document_calculations(document, to_status)

        except Exception as e:
            logger.error(f"Error in post-transition actions: {e}")

    @staticmethod
    def _handle_inventory_movements(document, from_status: str, to_status: str):
        """Handle inventory movements based on DocumentTypeStatus configuration"""
        try:
            to_status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=to_status,
                is_active=True
            ).first()

            if not to_status_config or not document.document_type.affects_inventory:
                return

            # 1. ОТМЕНИ движения ако новия статус изисква
            if to_status_config.reverses_inventory_movements:
                try:
                    from inventory.services.movement_service import MovementService
                    reversed_count = MovementService.reverse_document_movements(
                        document, f"Status changed to {to_status}"
                    )
                    logger.info(f"Reversed {reversed_count} movements for {document.document_number}")
                except Exception as e:
                    logger.error(f"Error reversing movements: {e}")

            # 2. ✅ СЪЗДАЙ движения САМО ако трябва И ги няма
            if to_status_config.creates_inventory_movements:
                # ✅ ПРОВЕРИ ДАЛИ ВЕЧЕ ИМА ПРАВИЛНИ ДВИЖЕНИЯ
                if not DocumentService._has_correct_movements_for_status(document, to_status):
                    try:
                        from inventory.services.movement_service import MovementService
                        new_movements = MovementService.create_from_document(document)
                        logger.info(f"Created {len(new_movements)} movements for {document.document_number}")
                    except Exception as e:
                        logger.error(f"Error creating movements: {e}")
                else:
                    logger.info(f"Document {document.document_number} already has correct movements for {to_status}")

        except Exception as e:
            logger.error(f"Error handling inventory movements: {e}")

    @staticmethod
    def _has_correct_movements_for_status(document, status: str) -> bool:
        """
        ✅ NEW: Check if document already has correct movements for given status
        """
        try:
            from inventory.models import InventoryMovement

            # За approved статус - провери дали има IN движения които отговарят на текущите линии
            if status == 'approved':
                current_movements = InventoryMovement.objects.filter(
                    source_document_type__in=['PURCHASE_REQUEST', 'PURCHASEREQUEST'],
                    source_document_number=document.document_number,
                    movement_type='IN'
                )

                expected_total = sum(
                    line.requested_quantity for line in document.lines.all()
                    if line.requested_quantity
                )

                actual_total = sum(mov.quantity for mov in current_movements)

                # Ако totals-ите съвпадат - има правилни движения
                return abs(expected_total - actual_total) < 0.001

            # За други статуси - assume че няма правилни движения
            return False

        except Exception as e:
            logger.error(f"Error checking movements for status: {e}")
            return False

    @staticmethod
    def _update_document_calculations(document, status: str):
        """Update document calculations (VAT, totals)"""
        try:
            # Trigger recalculation ако документът има финансови полета
            if hasattr(document, 'calculate_totals'):
                document.calculate_totals()
                document.save()
            elif hasattr(document, 'update_totals'):
                document.update_totals()

        except Exception as e:
            logger.error(f"Error updating calculations: {e}")

    @staticmethod
    def _send_transition_notifications(document, from_status: str, to_status: str, user: User):
        """Send notifications for status transition"""
        try:
            try:
                from notifications.services import NotificationService
                NotificationService.send_status_change_notification(
                    document, from_status, to_status, user
                )
            except ImportError:
                # Simple logging fallback
                logger.info(
                    f"Status Change: {document.document_number} "
                    f"{from_status}→{to_status} by {user.username}"
                )

        except Exception as e:
            logger.error(f"Error sending notifications: {e}")

    # =====================
    # LEGACY SUPPORT & UTILITY METHODS
    # =====================

    @staticmethod
    def _get_document_type_for_model(model_class):
        """Get DocumentType for model class"""
        try:
            from ..models.documents import get_document_type_by_key

            app_name = model_class._meta.app_label
            type_key = model_class.__name__.lower()

            # Опитай с model methods ако има
            try:
                instance = model_class()
                if hasattr(instance, 'get_app_name'):
                    app_name = instance.get_app_name()
                if hasattr(instance, 'get_document_type_key'):
                    type_key = instance.get_document_type_key()
            except:
                pass

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
            prefix = getattr(document_type, 'code', document_type.type_key[:3].upper())

            # Simple counter (в реалната имплементация използвай sequence)
            from django.utils import timezone
            timestamp = timezone.now().strftime("%y%m%d%H%M%S")
            return f"{prefix}{timestamp}"

        except Exception as e:
            logger.error(f"Error generating document number: {e}")
            from django.utils import timezone
            timestamp = timezone.now().strftime("%y%m%d%H%M%S")
            return f"DOC{timestamp}"

    @staticmethod
    def _get_initial_status(document_type) -> str:
        """Get initial status from DocumentTypeStatus"""
        try:
            from ..models.statuses import DocumentTypeStatus

            initial_config = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_initial=True,
                is_active=True
            ).first()

            if initial_config:
                return initial_config.status.code

            # Fallback
            return 'draft'

        except Exception as e:
            logger.warning(f"Error getting initial status: {e}")
            return 'draft'

    # =====================
    # DYNAMIC QUERY METHODS (for Managers)
    # =====================

    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """Get documents pending approval - DYNAMIC"""
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ..models.approvals import ApprovalRule

            pending_statuses = set()

            # Get document types за този модел
            doc_type = DocumentService._get_document_type_for_model(queryset.model)
            if doc_type and doc_type.requires_approval:
                # Използвай ApprovalRule
                rules = ApprovalRule.objects.filter(
                    document_type=doc_type,
                    is_active=True
                )
                pending_statuses.update(rules.values_list('from_status_obj__code', flat=True))

            # Fallback ако няма правила
            if not pending_statuses:
                pending_statuses = {'submitted', 'pending_approval', 'pending_review'}

            return queryset.filter(status__in=pending_statuses)

        except ImportError:
            # Fallback без ApprovalRule
            return queryset.filter(status__in=['submitted', 'pending_approval'])

    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """Get active documents - DYNAMIC"""
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ..models.statuses import DocumentTypeStatus

            doc_type = DocumentService._get_document_type_for_model(queryset.model)
            if doc_type:
                # Използвай DocumentTypeStatus за final статуси
                final_statuses = list(
                    DocumentTypeStatus.objects.filter(
                        document_type=doc_type,
                        is_final=True,
                        is_active=True
                    ).values_list('status__code', flat=True)
                )

                if final_statuses:
                    return queryset.exclude(status__in=final_statuses)

            # Fallback
            return queryset.exclude(status__in=['cancelled', 'closed', 'deleted', 'archived'])

        except Exception:
            # Basic fallback
            return queryset.exclude(status__in=['cancelled', 'closed', 'deleted'])

    # В края на nomenclatures/services/document_service.py

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

    @staticmethod
    def handle_document_update(document, user, reason: str = '') -> dict:
        """
        Handle document updates with inventory movement correction
        ✅ FIXED: Only sync if there are actual changes
        """
        try:
            current_config = DocumentService._get_document_type_status_config(document)
            has_movements = DocumentService._document_has_movements(document)

            if has_movements and current_config.allows_movement_correction:

                # ✅ ДОБАВИ CHANGE DETECTION
                if not DocumentService._document_needs_sync(document):
                    return {
                        'success': True,
                        'auto_corrected': False,
                        'message': 'No sync needed - document movements are current'
                    }

                if current_config.auto_correct_movements_on_edit:
                    # АВТОМАТИЧНА корекция САМО ако има промени
                    from inventory.services.movement_service import MovementService
                    correction_result = MovementService.sync_movements_with_document(
                        document=document,
                        user=user,
                        reason=reason or "Document edited"
                    )

                    return {
                        'success': True,
                        'auto_corrected': True,
                        'movements_corrected': correction_result.get('total_corrections', 0)
                    }
                else:
                    return {
                        'success': True,
                        'auto_corrected': False,
                        'needs_manual_correction': True,
                        'message': 'Document has movements that need manual correction'
                    }

            return {'success': True, 'auto_corrected': False}

        except Exception as e:
            logger.error(f"Error handling document update: {e}")
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _document_needs_sync(document) -> bool:
        """
        Сравнява очакваните спрямо реалните движения, разделени на IN и OUT.
        За inventory_direction='both' това предотвратява зануляване на разлики (+/-).
        Толеранси: qty=0.0001, value=0.01.
        """
        try:
            from inventory.models import InventoryMovement
            direction = getattr(getattr(document, 'document_type', None), 'inventory_direction', 'in')

            # 1) Очаквани IN/OUT qty/value от линиите
            exp_in_qty = exp_in_val = Decimal('0')
            exp_out_qty = exp_out_val = Decimal('0')

            lines_qs = getattr(document, 'lines', None)
            if lines_qs:
                for line in lines_qs.all():
                    qty = Decimal(str(getattr(line, 'requested_quantity', getattr(line, 'quantity', 0)) or 0))
                    if qty == 0:
                        continue
                    unit_cost_raw = (
                            getattr(line, 'unit_price', None)
                            or getattr(line, 'entered_price', None)
                            or Decimal('0')
                    )
                    unit_cost = Decimal(str(unit_cost_raw or 0))

                    if direction == 'both':
                        if qty > 0:
                            exp_in_qty += qty
                            exp_in_val += qty * unit_cost
                        else:
                            q = (-qty)  # абсолют
                            exp_out_qty += q
                            exp_out_val += q * unit_cost
                    elif direction == 'out':
                        # целият документ е OUT; qty се очаква положително
                        exp_out_qty += qty
                        exp_out_val += qty * unit_cost
                    else:
                        # по подразбиране IN
                        exp_in_qty += qty
                        exp_in_val += qty * unit_cost

            # 2) Реални IN/OUT qty/value от движенията
            doc_number = getattr(document, 'document_number', None) or getattr(document, 'number', None)
            if not doc_number:
                return True

            movs = InventoryMovement.objects.filter(
                source_document_number=doc_number,
            )

            act_in_qty = act_in_val = Decimal('0')
            act_out_qty = act_out_val = Decimal('0')

            for m in movs:
                q = Decimal(str(getattr(m, 'quantity', 0) or 0))
                p = Decimal(str(getattr(m, 'cost_price', 0) or 0))
                if getattr(m, 'movement_type', None) == 'OUT':
                    act_out_qty += q
                    act_out_val += q * p
                else:
                    act_in_qty += q
                    act_in_val += q * p

            # 3) Сравнение по отделно за IN и OUT
            if (exp_in_qty - act_in_qty).copy_abs() > Decimal('0.0001'):
                return True
            if (exp_in_val - act_in_val).copy_abs() > Decimal('0.01'):
                return True
            if (exp_out_qty - act_out_qty).copy_abs() > Decimal('0.0001'):
                return True
            if (exp_out_val - act_out_val).copy_abs() > Decimal('0.01'):
                return True

            return False

        except Exception as e:
            logger.error(f"_document_needs_sync failed, defaulting to True: {e}")
            return True

    @staticmethod
    def _document_has_movements(document) -> bool:
        """NEW: Check if document has any inventory movements - FIXED"""
        try:
            from inventory.models import InventoryMovement

            # ✅ ИЗПОЛЗВАЙ СЪЩАТА ЛОГИКА КАТО В reverse_document_movements
            possible_types = [
                document._meta.model_name.upper(),  # PURCHASEREQUEST
                document.__class__.__name__.upper(),  # PURCHASEREQUEST
                'PURCHASE_REQUEST',  # Manual mapping
                document._meta.model_name.upper().replace('REQUEST', '_REQUEST'),  # PURCHASE_REQUEST
            ]

            return InventoryMovement.objects.filter(
                source_document_type__in=possible_types,
                source_document_number=document.document_number
            ).exists()

        except ImportError:
            return False

    @staticmethod
    def _get_document_type_status_config(document):
        """NEW: Get DocumentTypeStatus config for current document status"""
        from nomenclatures.models import DocumentTypeStatus
        return DocumentTypeStatus.objects.filter(
            document_type=document.document_type,
            status__code=document.status,
            is_active=True
        ).first()


# =====================
# CONVENIENCE FUNCTIONS
# =====================

def transition_document(document, to_status: str, user: User, comments: str = '') -> Result:
    """Convenience function for document transitions"""
    return DocumentService.transition_document(document, to_status, user, comments)


def can_edit_document(document, user: User) -> bool:
    """Quick check if document can be edited"""
    can_edit, _ = DocumentService.can_edit_document(document, user)
    return can_edit


def get_document_actions(document, user: User) -> List[Dict]:
    """Get available actions for document"""
    return DocumentService.get_available_actions(document, user)


