# purchases/services/workflow_service.py
"""
WorkflowService - Централизиран управител на workflow transitions

Заменя разпръснатата логика от:
- Model methods (submit_for_approval, approve, convert_to_order)
- Signal handlers (_handle_request_approved, _handle_request_converted)
- Scattered business logic

Интегрира с:
- ApprovalService (за approval transitions)
- DocumentType (за allowed transitions)
- InventoryService (за inventory movements)
"""

from typing import Dict, List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

from nomenclatures.models import ApprovalRule

User = get_user_model()
logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Централизиран workflow управител

    ЕДИНСТВЕН entry point за всички status transitions
    """

    # ВРЕМЕННО: Добави debug logging в WorkflowService.transition_document()

    @staticmethod
    @transaction.atomic
    def transition_document(document, to_status: str, user: User = None, **kwargs) -> Dict:
        """
        DEBUG VERSION - Намира infinite recursion
        """
        try:
            from_status = document.status
            print(f"🔄 DEBUG: Starting transition: {document.document_number} {from_status} -> {to_status}")

            # СТЪПКА 1: DocumentType validation
            print(f"🔍 DEBUG: Step 1 - DocumentType validation")
            validation_result = WorkflowService._validate_document_type_transition(document, to_status)
            if not validation_result['valid']:
                print(f"❌ DEBUG: DocumentType validation failed: {validation_result['message']}")
                return {
                    'success': False,
                    'message': validation_result['message'],
                    'error_code': 'DOCUMENT_TYPE_VALIDATION_FAILED'
                }
            print(f"✅ DEBUG: DocumentType validation passed")

            # СТЪПКА 2: Business rules validation
            print(f"🔍 DEBUG: Step 2 - Business rules validation")
            business_validation = WorkflowService._validate_business_rules(document, to_status, user, **kwargs)
            if not business_validation['valid']:
                print(f"❌ DEBUG: Business validation failed: {business_validation['message']}")
                return {
                    'success': False,
                    'message': business_validation['message'],
                    'error_code': 'BUSINESS_RULES_VALIDATION_FAILED'
                }
            print(f"✅ DEBUG: Business validation passed")

            # СТЪПКА 3: Approval handling (ако се изисква)
            print(f"🔍 DEBUG: Step 3 - Checking if approval needed")
            if WorkflowService._needs_approval(document, to_status):
                print(f"🔍 DEBUG: Approval needed - calling ApprovalService")
                approval_result = WorkflowService._handle_approval_transition(document, to_status, user, **kwargs)
                if not approval_result['success']:
                    print(f"❌ DEBUG: Approval failed: {approval_result['message']}")
                    return approval_result
                print(f"✅ DEBUG: Approval successful")
                # ApprovalService вече е update-нал document.status, затова return
                return approval_result

            print(f"🔍 DEBUG: No approval needed - executing direct transition")

            # СТЪПКА 4: Execute non-approval transition
            with transaction.atomic():
                print(f"🔍 DEBUG: Step 4a - Updating status from {document.status} to {to_status}")
                # Update status
                document.status = to_status

                print(f"🔍 DEBUG: Step 4b - Updating document fields")
                # Update related fields
                WorkflowService._update_document_fields(document, to_status, user)

                print(f"🔍 DEBUG: Step 4c - Saving document")
                # Save document
                document.save()

                print(f"🔍 DEBUG: Step 4d - Post-transition actions")
                # СТЪПКА 5: Post-transition actions
                WorkflowService._execute_post_transition_actions(
                    document, from_status, to_status, user, **kwargs
                )

            print(f"✅ DEBUG: Transition completed successfully")

            return {
                'success': True,
                'message': f'Document transitioned from {from_status} to {to_status}',
                'from_status': from_status,
                'to_status': to_status
            }

        except Exception as e:
            print(f"❌ DEBUG: Exception in transition_document: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Transition failed: {str(e)}',
                'error_code': 'UNEXPECTED_ERROR'
            }

    @staticmethod
    def get_available_transitions(document, user: User = None) -> List[Dict]:
        """
        Връща възможните transitions за документ

        Returns:
            List[Dict]: [{'to_status': str, 'can_transition': bool, 'reason': str}, ...]
        """
        try:
            available = []

            # От DocumentType
            if document.document_type:
                next_statuses = document.document_type.get_next_statuses(document.status)

                for next_status in next_statuses:
                    can_transition = True
                    reason = ""

                    # Проверка за approval
                    if WorkflowService._needs_approval(document, next_status):
                        # Използваме ApprovalService за проверка
                        from nomenclatures.services.approval_service import ApprovalService
                        approval_transitions = ApprovalService.get_available_transitions(document, user)
                        can_transition = any(t['to_status'] == next_status for t in approval_transitions)
                        if not can_transition:
                            reason = "Requires approval permissions"

                    # Business rules проверка
                    if can_transition:
                        business_check = WorkflowService._validate_business_rules(
                            document, next_status, user, check_only=True
                        )
                        can_transition = business_check['valid']
                        if not can_transition:
                            reason = business_check['message']

                    available.append({
                        'to_status': next_status,
                        'can_transition': can_transition,
                        'reason': reason,
                        'requires_approval': WorkflowService._needs_approval(document, next_status)
                    })

            return available

        except Exception as e:
            logger.error(f"Error getting available transitions: {e}")
            return []

    # =====================
    # PRIVATE HELPER METHODS
    # =====================

    @staticmethod
    def _validate_document_type_transition(document, to_status: str) -> Dict:
        """Валидация според DocumentType rules"""
        try:
            if not document.document_type:
                return {
                    'valid': False,
                    'message': 'Document has no DocumentType configured'
                }

            # Проверка дали transition е позволен
            if not document.document_type.can_transition_to(document.status, to_status):
                allowed = document.document_type.get_next_statuses(document.status)
                return {
                    'valid': False,
                    'message': f'Transition from "{document.status}" to "{to_status}" not allowed. Allowed: {allowed}'
                }

            return {'valid': True, 'message': 'DocumentType validation passed'}

        except Exception as e:
            return {
                'valid': False,
                'message': f'DocumentType validation error: {str(e)}'
            }

    @staticmethod
    def _needs_approval(document, to_status: str) -> bool:  # ← ТУК ТРЯБВА ДА Е!
        if not document.document_type:
            return False

        has_rules = ApprovalRule.objects.for_document(document).filter(
            from_status=document.status,
            to_status=to_status
        ).exists()

        requires_approval = document.document_type.requires_approval

        # CONSISTENCY CHECKS
        if requires_approval and not has_rules:
            raise ValidationError(
                f"DocumentType '{document.document_type.name}' requires approval "
                f"for transition '{document.status}' → '{to_status}' "
                f"but no ApprovalRule configured."
            )

        if not requires_approval and has_rules:
            raise ValidationError(
                f"ApprovalRule exists for transition '{document.status}' → '{to_status}' "
                f"but DocumentType '{document.document_type.name}' has requires_approval=False. "
                f"Either remove the rule or enable requires_approval."
            )

        return requires_approval and has_rules

    def _handle_approval_transition(document, to_status, user=None, **kwargs):
        from nomenclatures.services.approval_service import ApprovalService

        if to_status == 'submitted':
            return ApprovalService.submit_document_with_auto_approve(document, user)

        if to_status == 'rejected':
            reason = kwargs.get('reason') or kwargs.get('comments', 'Rejected')
            return ApprovalService.reject_document(document, user, reason)

        # Всичко останало мине през execute_transition
        comments = kwargs.get('comments', '')
        return ApprovalService.execute_transition(document, to_status, user, comments)

    @staticmethod
    def _validate_business_rules(document, to_status: str, user: User = None,
                                 check_only: bool = False, **kwargs) -> Dict:
        """Валидация на business-specific rules"""
        try:
            model_name = document.__class__.__name__

            if model_name == 'PurchaseRequest':
                return WorkflowService._validate_request_rules(document, to_status, user, **kwargs)
            elif model_name == 'PurchaseOrder':
                return WorkflowService._validate_order_rules(document, to_status, user, **kwargs)
            elif model_name == 'DeliveryReceipt':
                return WorkflowService._validate_delivery_rules(document, to_status, user, **kwargs)

            # Default validation
            return {'valid': True, 'message': 'No specific business rules'}

        except Exception as e:
            return {
                'valid': False,
                'message': f'Business validation error: {str(e)}'
            }

    @staticmethod
    def _validate_request_rules(document, to_status: str, user: User = None, **kwargs) -> Dict:
        """Purchase Request specific validation"""

        if to_status == 'submitted':
            if not document.lines.exists():
                return {'valid': False, 'message': 'Cannot submit request without lines'}

        elif to_status == 'converted':
            if document.status != 'approved':
                return {'valid': False, 'message': 'Can only convert approved requests'}

        return {'valid': True, 'message': 'Request validation passed'}

    @staticmethod
    def _validate_order_rules(document, to_status: str, user: User = None, **kwargs) -> Dict:
        """Purchase Order specific validation"""

        if to_status == 'confirmed':
            if not document.lines.exists():
                return {'valid': False, 'message': 'Cannot confirm order without lines'}

        return {'valid': True, 'message': 'Order validation passed'}

    @staticmethod
    def _validate_delivery_rules(document, to_status: str, user: User = None, **kwargs) -> Dict:
        """Delivery Receipt specific validation"""

        if to_status == 'received':
            if not document.lines.exists():
                return {'valid': False, 'message': 'Cannot receive delivery without lines'}

        return {'valid': True, 'message': 'Delivery validation passed'}

    @staticmethod
    def _update_document_fields(document, to_status: str, user: User = None):
        """Updates related document fields based on new status"""

        # Standard tracking fields
        if hasattr(document, 'updated_by') and user:
            document.updated_by = user

        # Status-specific field updates
        if to_status == 'converted':
            if hasattr(document, 'converted_at'):
                document.converted_at = timezone.now()
            if hasattr(document, 'converted_by') and user:
                document.converted_by = user

        elif to_status == 'received':
            if hasattr(document, 'received_at'):
                document.received_at = timezone.now()
            if hasattr(document, 'received_by') and user:
                document.received_by = user

    @staticmethod
    def _execute_post_transition_actions(document, from_status: str, to_status: str,
                                         user: User = None, **kwargs):
        """Executes actions after successful transition"""

        # 1. Inventory movements
        WorkflowService._handle_inventory_movements(document, to_status)

        # 2. Document conversions
        WorkflowService._handle_document_conversions(document, from_status, to_status, user, **kwargs)

        # 3. Notifications (placeholder)
        logger.info(f"📧 Notification: {document.document_number} changed to {to_status}")

        # 4. Audit logging (the old _log_document_action functionality)
        logger.info(f"📋 Audit: {document.document_number} {from_status} -> {to_status} by {user}")

    @staticmethod
    def _handle_inventory_movements(document, to_status: str):
        """Handles inventory movements based on DocumentType configuration"""
        print(f"\n📦 === INVENTORY MOVEMENTS DEBUG ===")
        print(f"📦 Document: {document.document_number}")
        print(f"📦 To status: {to_status}")
        print(f"📦 Document type: {document.document_type}")
        print(
            f"📦 Affects inventory: {document.document_type.affects_inventory if document.document_type else 'No DocumentType'}")
        try:
            if not document.document_type or not document.document_type.affects_inventory:
                print(f"📦 SKIPPING: Document does not affect inventory")
                return

            # Check timing according to DocumentType
            should_create = document.document_type.should_affect_inventory(to_status)
            print(f"📦 Should create movement for '{to_status}': {should_create}")

            if should_create:
                print(f"📦 CREATING MOVEMENTS...")
                from inventory.services import MovementService
                movements = MovementService.create_from_document(document)
                print(f"📦 CREATED {len(movements)} movements!")

                for movement in movements:
                    print(f"📦   - {movement.movement_type}: {movement.product.code} x {movement.quantity}")
                else:
                    print(f"📦 NOT CREATING: Timing condition not met")

                if movements:
                    logger.info(f"📦 Created {len(movements)} inventory movements for {document.document_number}")

        except Exception as e:
            print(f"❌ INVENTORY ERROR: {e}")
            logger.error(f"❌ Error handling inventory movements: {e}")
            # НЕ re-raise - inventory errors не трябва да спират workflow

    @staticmethod
    def _handle_document_conversions(document, from_status: str, to_status: str, user: User = None, **kwargs):
        """Handles automatic document conversions"""

        # PLACEHOLDER за auto-conversion rules
        # Например: approved request -> auto-create order (ако е конфигурирано)

        if to_status == 'converted' and document.__class__.__name__ == 'PurchaseRequest':
            logger.info(f"🔄 Request {document.document_number} marked as converted")
            # Actual conversion logic ще се добави по-късно

        pass


# =====================
# CONVENIENCE FUNCTIONS за лесно използване
# =====================

def transition_document(document, to_status: str, user: User = None, **kwargs) -> Dict:
    """Convenience function за document transitions"""
    return WorkflowService.transition_document(document, to_status, user, **kwargs)


def get_available_actions(document, user: User = None) -> List[Dict]:
    """Convenience function за available transitions"""
    return WorkflowService.get_available_transitions(document, user)