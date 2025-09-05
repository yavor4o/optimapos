# nomenclatures/services/document_service.py - UNIFIED FACADE
"""
DocumentService - Unified Facade for All Document Operations

ARCHITECTURAL PRINCIPLE:
- SINGLE PUBLIC API for all document operations
- Hides configuration system complexity
- Centralizes business logic
- Optimized for POS operations

USAGE:
    # Instance-based API
    service = DocumentService(document, user)
    service.create()
    service.add_line(product, quantity=5)
    service.transition_to('approved')
    
    # Static API  
    DocumentService.bulk_status_transition(documents, 'approved', user)
"""

from typing import Dict, List, Optional
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction
import logging

from core.utils.result import Result

# Internal collaborators (not exposed externally)
from .creator import DocumentCreator
from .validator import DocumentValidator
from .status_manager import StatusManager
from .query import DocumentQuery
from .numbering_service import NumberingService
from .document_line_service import DocumentLineService
from .vat_calculation_service import VATCalculationService

# Approval service with fallback
try:
    from .approval_service import ApprovalService
    HAS_APPROVAL_SERVICE = True
except ImportError:
    ApprovalService = None
    HAS_APPROVAL_SERVICE = False

User = get_user_model()
logger = logging.getLogger(__name__)


# =================================================================
# UNIFIED DOCUMENT SERVICE - FACADE PATTERN
# =================================================================

class DocumentService:
    """
    UNIFIED FACADE for all document operations
    
    Centralizes access to all document services and hides
    configuration system complexity.
    """
    
    def __init__(self, document=None, user: User = None):
        """
        Initialize service for specific document and user
        
        Args:
            document: Document instance (optional for static methods)
            user: User performing operations (optional)
        """
        self.document = document
        self.user = user
        
        # Internal collaborators - NOT exposed
        self._creator = DocumentCreator()
        self._validator = DocumentValidator()
        self._status_manager = StatusManager()
        self._query = DocumentQuery()
        self._numbering = NumberingService()
        self._line_service = DocumentLineService()
        self._vat_service = VATCalculationService()
        
        # Approval service if available
        self._approval_service = ApprovalService if HAS_APPROVAL_SERVICE else None
        
        # Configuration cache for performance
        self._config_cache = {}
    
    # =====================================================
    # DOCUMENT LIFECYCLE METHODS
    # =====================================================
    
    def create(self, **kwargs) -> Result:
        """
        Create document with automatic numbering and initial status
        
        Returns:
            Result: Success with document data or error
        """
        try:
            if not self.document:
                return Result.error('NO_DOCUMENT', 'Document instance required')
                
            success = self._creator.create_document(
                self.document, 
                self.user, 
                **kwargs
            )
            
            if success:
                return Result.success(
                    data={'document': self.document},
                    msg=f'Document {self.document.document_number} created successfully'
                )
            else:
                return Result.error('CREATION_FAILED', 'Document creation failed')
                
        except Exception as e:
            logger.error(f"Error creating document: {e}")
            return Result.error('CREATION_ERROR', str(e))
    
    def transition_to(self, status: str, comments: str = '') -> Result:
        """
        Transition document to new status
        
        Args:
            status: Target status code
            comments: Optional transition comments
            
        Returns:
            Result: Transition result with data
        """
        if not self.document:
            return Result.error('NO_DOCUMENT', 'Document instance required')
            
        if not self.user:
            return Result.error('NO_USER', 'User required for status transitions')
        
        return self._status_manager.transition_document(
            self.document, 
            status, 
            self.user, 
            comments
        )
    
    def add_line(self, product, quantity: Decimal, **kwargs) -> Result:
        """
        Add line to document
        
        Args:
            product: Product instance
            quantity: Line quantity
            **kwargs: Additional line fields
            
        Returns:
            Result: Added line result
        """
        if not self.document:
            return Result.error('NO_DOCUMENT', 'Document instance required')
            
        return self._line_service.add_line(
            self.document, 
            product, 
            quantity, 
            **kwargs
        )
    
    def remove_line(self, line_number: int) -> Result:
        """
        Remove line from document
        
        Args:
            line_number: Line number to remove
            
        Returns:
            Result: Removal result
        """
        if not self.document:
            return Result.error('NO_DOCUMENT', 'Document instance required')
            
        return self._line_service.remove_line(self.document, line_number)
    
    def calculate_totals(self) -> Result:
        """
        Calculate document totals including VAT
        
        Returns:
            Result: Calculation results with totals
        """
        if not self.document:
            return Result.error('NO_DOCUMENT', 'Document instance required')
            
        return self._vat_service.calculate_document_vat(self.document)
    
    # =====================================================
    # PERMISSIONS AND VALIDATION
    # =====================================================
    
    def can_edit(self) -> bool:
        """Check if document can be edited"""
        if not self.document:
            return False
            
        can_edit, _ = self._validator.can_edit_document(self.document, self.user)
        return can_edit
    
    def can_delete(self) -> bool:
        """Check if document can be deleted"""
        if not self.document:
            return False
            
        can_delete, _ = self._validator.can_delete_document(self.document, self.user)
        return can_delete
    
    def get_permissions(self) -> Dict:
        """
        Get comprehensive permissions summary
        
        Returns:
            Dict: Complete permissions data
        """
        if not self.document:
            return {'error': 'No document instance'}
            
        return self._validator.get_effective_permissions(self.document, self.user)
    
    def get_available_actions(self) -> List[Dict]:
        """
        Get available actions for current user
        
        Returns:
            List[Dict]: Available actions with metadata
        """
        if not self.document:
            return []
            
        if self._approval_service:
            return self._query.get_available_actions(self.document, self.user)
        else:
            # Simplified actions without approval
            actions = []
            if self.can_edit():
                actions.append({
                    'action': 'edit',
                    'label': 'Edit',
                    'can_perform': True,
                    'button_style': 'btn-secondary',
                    'icon': 'ki-filled ki-notepad-edit'
                })
            if self.can_delete():
                actions.append({
                    'action': 'delete',
                    'label': 'Delete', 
                    'can_perform': True,
                    'button_style': 'btn-danger',
                    'icon': 'fas fa-trash'
                })
            return actions
    
    # =====================================================
    # VALIDATION INTEGRATION METHODS 
    # =====================================================
    
    def validate_for_purchase_creation(self, partner, location, lines_data: List[dict], expected_amount: Decimal = None) -> Result:
        """
        Integrated validation for purchase document creation
        Uses all relevant validation services
        """
        errors = []
        warnings = []
        
        # 1. Partner/Supplier validation
        if partner:
            try:
                from partners.services import SupplierService
                partner_result = SupplierService.validate_supplier_operation(
                    partner, 
                    expected_amount or Decimal('0')
                )
                if not partner_result.ok:
                    errors.append(f"Supplier validation failed: {partner_result.msg}")
            except ImportError:
                # Fallback basic validation
                if not partner.is_active:
                    errors.append("Partner is not active")
                if getattr(partner, 'delivery_blocked', False):
                    errors.append("Partner delivery is blocked")
        
        # 2. Location validation (basic)
        if location and not location.is_active:
            errors.append(f"Location '{location.name}' is not active")
        
        # 3. Products validation
        if lines_data:
            try:
                from products.services import ProductValidationService
                for line_data in lines_data:
                    product = line_data.get('product')
                    quantity = line_data.get('quantity', Decimal('1'))
                    
                    if not product:
                        errors.append("Product is required for all lines")
                        continue
                        
                    product_result = ProductValidationService.validate_purchase(
                        product, quantity, partner
                    )
                    if not product_result.ok:
                        errors.append(f"Product {product.code}: {product_result.msg}")
                    elif 'warning' in product_result.data:
                        warnings.append(f"Product {product.code}: {product_result.data['warning']}")
            except ImportError:
                # Fallback basic product validation
                for line_data in lines_data:
                    product = line_data.get('product')
                    if product and hasattr(product, 'lifecycle_status'):
                        if product.lifecycle_status != 'ACTIVE':
                            errors.append(f"Product {product.code} is not active")
        
        # Return result
        validation_data = {
            'errors': errors,
            'warnings': warnings,
            'partner_validated': bool(partner),
            'location_validated': bool(location), 
            'products_count': len(lines_data) if lines_data else 0
        }
        
        if errors:
            return Result.error(
                'VALIDATION_FAILED',
                f"Document validation failed: {len(errors)} errors",
                data=validation_data
            )
        else:
            msg = f"Validation passed for {len(lines_data)} lines"
            if warnings:
                msg += f" with {len(warnings)} warnings"
            return Result.success(data=validation_data, msg=msg)
    
    def validate_partner_for_purchase(self, partner, amount: Decimal = None) -> Result:
        """Integration point for partner validations"""
        try:
            from partners.services import SupplierService
            return SupplierService.validate_supplier_operation(partner, amount or Decimal('0'))
        except ImportError:
            # Fallback basic validation
            if not partner.is_active:
                return Result.error('PARTNER_INACTIVE', 'Partner is not active')
            if getattr(partner, 'delivery_blocked', False):
                return Result.error('DELIVERY_BLOCKED', 'Partner delivery is blocked')
            return Result.success(msg='Partner validated (basic)')

    def validate_products_for_purchase(self, lines_data: List[dict], partner=None) -> Result:
        """Integration point for product validations"""
        try:
            from products.services import ProductValidationService
            errors = []
            warnings = []
            
            for line_data in lines_data:
                product = line_data.get('product')
                quantity = line_data.get('quantity', Decimal('1'))
                
                if not product:
                    errors.append("Product is required")
                    continue
                    
                result = ProductValidationService.validate_purchase(
                    product, quantity, partner
                )
                if not result.ok:
                    errors.append(f"{product.code}: {result.msg}")
                elif 'warning' in result.data:
                    warnings.append(f"{product.code}: {result.data['warning']}")
            
            validation_data = {'errors': errors, 'warnings': warnings}
            
            if errors:
                return Result.error('PRODUCT_VALIDATION_FAILED', "; ".join(errors), data=validation_data)
            else:
                msg = f"{len(lines_data)} products validated"
                if warnings:
                    msg += f" with {len(warnings)} warnings"
                return Result.success(data=validation_data, msg=msg)
                
        except ImportError:
            # Fallback basic validation  
            errors = []
            for line_data in lines_data:
                product = line_data.get('product')
                if product and hasattr(product, 'lifecycle_status'):
                    if product.lifecycle_status != 'ACTIVE':
                        errors.append(f"{product.code}: Not active")
            
            if errors:
                return Result.error('BASIC_VALIDATION_FAILED', "; ".join(errors))
            return Result.success(msg=f'{len(lines_data)} products validated (basic)')

    def validate_location_for_operation(self, location, operation_type='purchase') -> Result:
        """Integration point for location validations"""
        if not location:
            return Result.error('LOCATION_REQUIRED', 'Location is required')
            
        if not location.is_active:
            return Result.error('LOCATION_INACTIVE', f'Location {location.name} is not active')
            
        # Additional location-specific validations could go here
        # E.g., InventoryLocationService.validate_for_purchase(location)
        
        return Result.success(data={'location_code': location.code}, msg=f'Location {location.name} validated')

    # =====================================================
    # CONFIGURATION UTILITIES
    # =====================================================
    
    def get_document_config(self) -> Dict:
        """
        Get complete configuration summary for document
        
        Returns:
            Dict: Document type and status configuration
        """
        if not self.document or not self.document.document_type:
            return {'error': 'No document type configured'}
            
        cache_key = f"config_{self.document.document_type.id}_{self.document.status}"
        
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]
            
        try:
            from ..models import DocumentTypeStatus
            
            status_config = DocumentTypeStatus.objects.filter(
                document_type=self.document.document_type,
                status__code=self.document.status,
                is_active=True
            ).select_related('status').first()
            
            config = {
                'document_type': {
                    'name': self.document.document_type.name,
                    'type_key': self.document.document_type.type_key,
                    'affects_inventory': self.document.document_type.affects_inventory,
                    'inventory_direction': self.document.document_type.inventory_direction,
                    'requires_approval': self.document.document_type.requires_approval,
                    'is_fiscal': self.document.document_type.is_fiscal,
                    'auto_receive': getattr(self.document.document_type, 'auto_receive', False),
                },
                'current_status': {
                    'code': self.document.status,
                    'name': status_config.status.name if status_config else self.document.status,
                    'is_initial': status_config.is_initial if status_config else False,
                    'is_final': status_config.is_final if status_config else False,
                    'allows_editing': status_config.allows_editing if status_config else True,
                    'allows_deletion': status_config.allows_deletion if status_config else False,
                    'creates_inventory_movements': status_config.creates_inventory_movements if status_config else False,
                },
                'permissions': self.get_permissions()
            }
            
            # Cache result
            self._config_cache[cache_key] = config
            return config
            
        except Exception as e:
            logger.error(f"Error getting document config: {e}")
            return {'error': str(e)}
    
    def preview_next_number(self) -> str:
        """
        Preview what the next document number would be
        
        Returns:
            str: Preview of next number
        """
        if not self.document:
            return "NO_DOCUMENT"
            
        return self._creator.preview_next_number(
            self.document.__class__,
            getattr(self.document, 'location', None),
            self.user
        )
    
    # =====================================================
    # STATIC UTILITY METHODS
    # =====================================================
    
    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """Get active documents using configuration-driven filtering"""
        return DocumentQuery.get_active_documents(model_class, queryset)
    
    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """Get documents pending approval"""
        return DocumentQuery.get_pending_approval_documents(model_class, queryset)
    
    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """Get documents ready for processing"""
        return DocumentQuery.get_ready_for_processing_documents(model_class, queryset)
    
    # =====================================================
    # BULK OPERATIONS
    # =====================================================
    
    @staticmethod
    @transaction.atomic
    def bulk_status_transition(documents: List, target_status: str, user: User, comments: str = '') -> Result:
        """
        Bulk transition multiple documents to same status
        
        Args:
            documents: List of document instances
            target_status: Target status for all documents
            user: User performing transitions
            comments: Optional comments
            
        Returns:
            Result: Bulk operation result with success/failure counts
        """
        try:
            logger.info(f"Bulk transitioning {len(documents)} documents to {target_status}")
            
            results = {
                'successful': [],
                'failed': [],
                'total': len(documents)
            }
            
            for doc in documents:
                service = DocumentService(doc, user)
                result = service.transition_to(target_status, comments)
                
                if result.ok:
                    results['successful'].append({
                        'document_number': doc.document_number,
                        'old_status': result.data.get('old_status'),
                        'new_status': result.data.get('new_status')
                    })
                else:
                    results['failed'].append({
                        'document_number': doc.document_number,
                        'error': result.msg
                    })
            
            success_count = len(results['successful'])
            fail_count = len(results['failed'])
            
            logger.info(f"Bulk transition complete: {success_count} success, {fail_count} failed")
            
            return Result.success(
                data=results,
                msg=f'Bulk transition: {success_count}/{len(documents)} successful'
            )
            
        except Exception as e:
            logger.error(f"Bulk transition failed: {e}")
            return Result.error('BULK_TRANSITION_FAILED', str(e))
    
    def __str__(self):
        doc_info = f"{self.document.document_number}" if self.document else "No document"
        user_info = f"{self.user.username}" if self.user else "No user"
        return f"DocumentService({doc_info}, {user_info})"

        # =================================================
        # SEMANTIC ACTION METHODS - NEW ADDITION
        # =================================================

    def approve(self, comments: str = '') -> Result:
        """
        🎯 SEMANTIC ACTION: Approve document

        ✅ FIXED: Uses configuration-driven available actions instead of helper methods

        Args:
            comments: Optional approval comments

        Returns:
            Result with transition details or error
        """
        try:
            logger.info(f"Approving document {self.document.document_number}")

            if not self.document.document_type:
                return Result.error('NO_DOCUMENT_TYPE', 'Document has no document type configured')

            # ✅ FIXED: Find approve action from available actions (configuration-driven)
            available_actions = self.get_available_actions()
            target_status = None
            
            for action in available_actions:
                if action.get('action') == 'transition' and action.get('semantic_type') == 'approve':
                    if action.get('can_perform', False):
                        target_status = action.get('status')
                        break
            
            if not target_status:
                return Result.error(
                    'NO_APPROVE_ACTION',
                    'No approve action available for current document state'
                )

            # Perform the transition
            return self.transition_to(target_status, comments)

        except Exception as e:
            logger.error(f"Document approval failed: {e}")
            return Result.error('APPROVAL_FAILED', f'Approval failed: {str(e)}')

    def submit_for_approval(self, comments: str = '') -> Result:
        """
        🎯 SEMANTIC ACTION: Submit document for approval

        ✅ FIXED: Uses configuration-driven available actions instead of helper methods

        Args:
            comments: Optional submission comments

        Returns:
            Result with transition details or error
        """
        try:
            logger.info(f"Submitting document {self.document.document_number} for approval")

            if not self.document.document_type:
                return Result.error('NO_DOCUMENT_TYPE', 'Document has no document type configured')

            # ✅ FIXED: Find submit action from available actions (configuration-driven)
            available_actions = self.get_available_actions()
            target_status = None
            
            for action in available_actions:
                if action.get('action') == 'transition' and action.get('semantic_type') == 'submit':
                    if action.get('can_perform', False):
                        target_status = action.get('status')
                        break
            
            if not target_status:
                return Result.error(
                    'NO_SUBMIT_ACTION',
                    'No submit action available for current document state'
                )

            # Perform the transition
            return self.transition_to(target_status, comments)

        except Exception as e:
            logger.error(f"Document submission failed: {e}")
            return Result.error('SUBMISSION_FAILED', f'Submission failed: {str(e)}')

    def reject(self, comments: str = '') -> Result:
        """
        🎯 SEMANTIC ACTION: Reject document

        ✅ FIXED: Uses configuration-driven available actions instead of helper methods

        Args:
            comments: Optional rejection reason (usually required)

        Returns:
            Result with transition details or error
        """
        try:
            logger.info(f"Rejecting document {self.document.document_number}")

            if not self.document.document_type:
                return Result.error('NO_DOCUMENT_TYPE', 'Document has no document type configured')

            if not comments:
                return Result.error('REJECTION_REASON_REQUIRED', 'Rejection reason is required')

            # ✅ FIXED: Find reject action from available actions (configuration-driven)
            available_actions = self.get_available_actions()
            target_status = None
            
            for action in available_actions:
                if action.get('action') == 'transition' and action.get('semantic_type') == 'reject':
                    if action.get('can_perform', False):
                        target_status = action.get('status')
                        break
            
            if not target_status:
                return Result.error(
                    'NO_REJECT_ACTION',
                    'No reject action available for current document state'
                )

            # Perform the transition
            return self.transition_to(target_status, comments)

        except Exception as e:
            logger.error(f"Document rejection failed: {e}")
            return Result.error('REJECTION_FAILED', f'Rejection failed: {str(e)}')

    def return_to_draft(self, comments: str = '') -> Result:
        """
        🎯 SEMANTIC ACTION: Return document to draft status

        ✅ FIXED: Uses configuration-driven available actions instead of helper methods

        Args:
            comments: Optional reason for returning to draft

        Returns:
            Result with transition details or error
        """
        try:
            logger.info(f"Returning document {self.document.document_number} to draft")

            # ✅ FIXED: Find return_draft action from available actions
            available_actions = self.get_available_actions()
            logger.info(f"🐛 DEBUG available_actions: {available_actions}")
            target_status = None
            
            for action in available_actions:
                logger.info(f"🐛 DEBUG action: {action}")
                if action.get('action') == 'transition' and action.get('semantic_type') == 'return_draft':
                    if action.get('can_perform', False):
                        target_status = action.get('status')
                        logger.info(f"🐛 DEBUG Found return_draft action: {target_status}")
                        break
            
            if not target_status:
                # Fallback: try to find initial status
                target_status = self._find_initial_status()
                if not target_status:
                    return Result.error(
                        'NO_RETURN_DRAFT_ACTION',
                        'No return to draft action available for current document state'
                    )
                logger.info(f"Using fallback initial status: {target_status}")

            # Perform the transition
            return self.transition_to(target_status, comments)

        except Exception as e:
            logger.error(f"Return to draft failed: {e}")
            return Result.error('DRAFT_RETURN_FAILED', f'Return to draft failed: {str(e)}')

    def cancel(self, comments: str = '') -> Result:
        """
        🎯 SEMANTIC ACTION: Cancel document

        Automatically finds appropriate cancellation status for the document type
        and performs the transition with proper validation.

        Args:
            comments: Optional cancellation reason (usually required)

        Returns:
            Result with transition details or error
        """
        try:
            logger.info(f"Cancelling document {self.document.document_number}")

            if not self.document.document_type:
                return Result.error('NO_DOCUMENT_TYPE', 'Document has no document type configured')

            if not comments:
                return Result.error('CANCELLATION_REASON_REQUIRED', 'Cancellation reason is required')

            # Find appropriate cancellation status using StatusResolver
            target_status = self._find_cancellation_status()
            if not target_status:
                return Result.error(
                    'NO_CANCELLATION_STATUS',
                    'No suitable cancellation status configured for this document type'
                )

            # Perform the transition
            return self.transition_to(target_status, comments)

        except Exception as e:
            logger.error(f"Document cancellation failed: {e}")
            return Result.error('CANCELLATION_FAILED', f'Cancellation failed: {str(e)}')

    # =================================================
    # PRIVATE HELPER METHODS FOR STATUS RESOLUTION
    # =================================================

    def _find_completion_status(self) -> Optional[str]:
        """Find appropriate completion status for document type"""
        try:
            from ._status_resolver import StatusResolver

            # Look in final statuses for completion-like names
            final_statuses = StatusResolver.get_final_statuses(self.document.document_type)
            for status in final_statuses:
                status_lower = status.lower()
                if any(word in status_lower for word in ['complet', 'finish', 'done', 'approved', 'received']):
                    return status

            # Fallback: Get any final status
            if final_statuses:
                return list(final_statuses)[0]

            # Fallback
            return 'completed'

        except Exception as e:
            logger.warning(f"Failed to find completion status: {e}")
            return 'completed'

    def _find_approval_status(self) -> Optional[str]:
        """Find appropriate approval status for document type"""
        try:
            from ._status_resolver import StatusResolver
            return StatusResolver.get_approval_status(self.document.document_type)
        except Exception as e:
            logger.warning(f"Failed to find approval status: {e}")
            return 'approved'

    def _find_rejection_status(self) -> Optional[str]:
        """Find appropriate rejection/cancellation status for document type"""
        try:
            from ._status_resolver import StatusResolver
            return StatusResolver.get_rejection_status(self.document.document_type)
        except Exception as e:
            logger.warning(f"Failed to find rejection status: {e}")
            return 'rejected'

    def _find_initial_status(self) -> Optional[str]:
        """Find initial status for document type"""
        try:
            from ._status_resolver import StatusResolver
            return StatusResolver.get_initial_status(self.document.document_type)
        except Exception as e:
            logger.warning(f"Failed to find initial status: {e}")
            return 'draft'

    def _find_cancellation_status(self) -> Optional[str]:
        """Find appropriate cancellation status for document type"""
        try:
            from ._status_resolver import StatusResolver
            return StatusResolver.get_cancellation_status(self.document.document_type)
        except Exception as e:
            logger.warning(f"Failed to find cancellation status: {e}")
            return 'cancelled'

    # =================================================
    # STATUS INQUIRY METHODS
    # =================================================

    # ❌ REMOVED: get_available_semantic_actions() - Use get_available_actions() with semantic_type filtering
    
    def get_available_semantic_actions_LEGACY(self) -> Dict[str, bool]:
        """
        Get available semantic actions for current document state

        Returns:
            Dict with action availability: {
                'can_approve': bool,
                'can_submit': bool,
                'can_reject': bool,
                'can_return_to_draft': bool,
                'can_cancel': bool
            }
        """
        try:
            from ._status_resolver import StatusResolver

            current_status = self.document.status
            doc_type = self.document.document_type

            if not doc_type:
                return {'can_approve': False, 'can_submit': False, 'can_reject': False,
                        'can_return_to_draft': False, 'can_cancel': False}

            # Get available transitions from current status
            available_statuses = StatusResolver.get_next_possible_statuses(doc_type, current_status)

            # Check what semantic actions are possible
            completion_status = self._find_completion_status()
            approval_status = self._find_approval_status()
            rejection_status = self._find_rejection_status()
            initial_status = self._find_initial_status()
            cancellation_status = self._find_cancellation_status()

            # ✅ FIXED: Use get_available_actions and map by semantic meaning of target statuses
            available_actions_list = self.get_available_actions()
            
            # Map raw actions to semantic actions
            actions = {
                'can_approve': False,
                'can_submit': False, 
                'can_reject': False,
                'can_return_to_draft': False,
                'can_cancel': False
            }
            
            for action in available_actions_list:
                if action.get('action') == 'transition':
                    target_status = action.get('status', '')
                    can_perform = action.get('can_perform', False) or action.get('can_execute', False)
                    
                    if can_perform:
                        target_lower = target_status.lower()
                        # Map based on semantic meaning of target status names (not helper methods)
                        if any(word in target_lower for word in ['complet', 'approved', 'finished', 'done', 'received']):
                            actions['can_approve'] = True
                        elif any(word in target_lower for word in ['submit', 'pending', 'review', 'approval']):
                            actions['can_submit'] = True  
                        elif any(word in target_lower for word in ['reject', 'declined', 'refused']):
                            actions['can_reject'] = True
                        elif any(word in target_lower for word in ['draft', 'initial']) or target_status == initial_status:
                            actions['can_return_to_draft'] = True
                        elif any(word in target_lower for word in ['cancel', 'cancelled', 'abort']):
                            actions['can_cancel'] = True
            
            return actions

        except Exception as e:
            logger.error(f"Failed to get semantic actions: {e}")
            return {'can_approve': False, 'can_submit': False, 'can_reject': False, 'can_return_to_draft': False, 'can_cancel': False}

    # ❌ REMOVED: get_semantic_action_labels() - Use action.label from get_available_actions()
    
    def get_semantic_action_labels_LEGACY(self) -> Dict[str, str]:
        """
        Get user-friendly labels for semantic actions

        Returns:
            Dict with action labels: {
                'approve': 'Complete Delivery',
                'submit': 'Submit for Review',
                'reject': 'Cancel Delivery',
                'return_to_draft': 'Return to Draft'
            }
        """
        try:
            doc_type = self.document.document_type

            if not doc_type:
                return {}

            # Get status configurations via DocumentType methods (which exist)
            completion_status = self._find_completion_status()
            approval_status = self._find_approval_status()
            rejection_status = self._find_rejection_status()
            initial_status = self._find_initial_status()
            cancellation_status = self._find_cancellation_status()

            # Build labels from status codes (simple approach since we can't get status names easily)
            labels = {}

            if completion_status:
                labels['approve'] = completion_status.replace('_', ' ').title()

            if approval_status:
                labels['submit'] = approval_status.replace('_', ' ').title()

            if rejection_status:
                labels['reject'] = rejection_status.replace('_', ' ').title()

            if initial_status:
                labels['return_to_draft'] = f"Return to {initial_status.replace('_', ' ').title()}"

            if cancellation_status:
                labels['cancel'] = cancellation_status.replace('_', ' ').title()

            return labels

        except Exception as e:
            logger.error(f"Failed to get action labels: {e}")
            return {
                'approve': 'Approve',
                'submit': 'Submit for Approval',
                'reject': 'Reject',
                'return_to_draft': 'Return to Draft'
            }
# =================================================================
# CONVENIENCE FUNCTIONS FOR BACKWARD COMPATIBILITY
# =================================================================

def create_document(instance, user=None, **kwargs) -> bool:
    """Backward compatibility wrapper"""
    service = DocumentService(instance, user)
    result = service.create(**kwargs)
    return result.ok

def can_edit_document(document, user) -> Result:
    """Check if document can be edited - Returns Result object"""
    try:
        service = DocumentService(document, user)
        can_edit = service.can_edit()
        return Result.success(
            data={'can_edit': can_edit},
            msg='Edit allowed' if can_edit else 'Edit not allowed'
        )
    except Exception as e:
        return Result.error('PERMISSION_CHECK_FAILED', f'Failed to check edit permission: {str(e)}')

def can_delete_document(document, user) -> Result:
    """Check if document can be deleted - Returns Result object"""
    try:
        service = DocumentService(document, user)
        can_delete = service.can_delete()
        return Result.success(
            data={'can_delete': can_delete},
            msg='Delete allowed' if can_delete else 'Delete not allowed'
        )
    except Exception as e:
        return Result.error('PERMISSION_CHECK_FAILED', f'Failed to check delete permission: {str(e)}')

def get_document_permissions(document, user) -> Result:
    """Get comprehensive document permissions - Returns Result object"""
    try:
        service = DocumentService(document, user)
        permissions = service.get_permissions()
        
        return Result.success(
            data=permissions,
            msg='Document permissions retrieved'
        )
    except Exception as e:
        return Result.error('PERMISSION_CHECK_FAILED', f'Failed to get document permissions: {str(e)}')

def transition_document(document, new_status, user, comments='') -> Result:
    """Transition document to new status - Returns Result object"""
    try:
        service = DocumentService(document, user)
        return service.transition_to(new_status, comments)
    except Exception as e:
        return Result.error('TRANSITION_FAILED', f'Failed to transition document: {str(e)}')
        
# Additional convenience methods for common operations
def get_document_actions(document, user) -> Result:
    """Get available actions for document - Returns Result with action list"""
    try:
        permissions_result = get_document_permissions(document, user)
        if not permissions_result.ok:
            return permissions_result
            
        permissions = permissions_result.data
        actions = []
        
        if permissions.get('can_edit', False):
            actions.append({
                'key': 'edit',
                'name': 'Edit',
                'icon': 'edit',
                'reason': permissions.get('edit_reason', '')
            })
            
        if permissions.get('can_delete', False):
            actions.append({
                'key': 'delete', 
                'name': 'Delete',
                'icon': 'trash',
                'reason': permissions.get('delete_reason', '')
            })
            
        if permissions.get('can_transition', False):
            actions.append({
                'key': 'change_status',
                'name': 'Change Status', 
                'icon': 'arrow-right',
                'reason': 'Status transition available'
            })
            
        return Result.success(
            data={'actions': actions},
            msg=f'Found {len(actions)} available actions'
        )
        
    except Exception as e:
        return Result.error('ACTION_CHECK_FAILED', f'Failed to get document actions: {str(e)}')


# =====================================================================
# MISSING METHODS THAT MODELS ARE CALLING
# =====================================================================

def recalculate_document_lines(document, user=None, recalc_vat=True, update_pricing=False) -> Result:
    """Recalculate all document lines - financial totals, VAT, etc."""
    try:
        # Basic line validation first
        if not hasattr(document, 'lines'):
            return Result.error('NO_LINES_SUPPORT', 'Document does not support lines')
            
        lines = document.lines.all()
        if not lines.exists():
            return Result.success(data={'recalculated_lines': 0}, msg='No lines to recalculate')
            
        recalculated_count = 0
        errors = []
        
        # Recalculate each line
        for line in lines:
            try:
                # Update pricing if requested and line has pricing methods
                if update_pricing and hasattr(line, 'update_pricing'):
                    line.update_pricing()
                    
                # Recalculate line totals if FinancialLineMixin
                if hasattr(line, 'recalculate_totals'):
                    line.recalculate_totals()
                elif hasattr(line, 'line_total'):
                    # Force recalculation by accessing property
                    _ = line.line_total
                    
                line.save()
                recalculated_count += 1
                
            except Exception as e:
                errors.append(f'Line {line.line_number}: {str(e)}')
                
        # VAT recalculation if requested (handles document totals via VATCalculationService)
        if recalc_vat:
            try:
                from .vat_calculation_service import VATCalculationService
                vat_result = VATCalculationService.calculate_document_vat(document, save=True)
                if not vat_result.ok:
                    errors.append(f'VAT calculation: {vat_result.msg}')
            except ImportError:
                # VAT service not available - not an error
                pass
            except Exception as e:
                errors.append(f'VAT calculation: {str(e)}')
                
        if errors:
            return Result.error(
                'PARTIAL_RECALCULATION',
                f'Recalculated {recalculated_count} lines with errors: {"; ".join(errors)}',
                data={'recalculated_lines': recalculated_count, 'errors': errors}
            )
            
        return Result.success(
            data={'recalculated_lines': recalculated_count},
            msg=f'Successfully recalculated {recalculated_count} lines'
        )
        
    except Exception as e:
        return Result.error('RECALCULATION_FAILED', f'Failed to recalculate document lines: {str(e)}')



