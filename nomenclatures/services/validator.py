# nomenclatures/services/document/validator.py
"""
Document Validator - валидира бизнес правила

МЕТОДИ ПРЕМЕСТЕНИ ОТ DocumentService:
- _validate_business_rules()
- _validate_purchaserequest_rules()
- _validate_simple_transition()
- can_edit_document()
"""

from typing import Tuple, Dict, Any
from django.contrib.auth import get_user_model
from django.db import models
import logging

from core.utils.result import Result
from nomenclatures.models import DocumentTypeStatus

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentValidator:
    """Специализиран service за валидации"""

    @staticmethod
    def _validate_business_rules(document, to_status: str, user: User, **kwargs) -> Result:
        """
        Validate business-specific rules

        КОПИРАНО от старата версия за backward compatibility
        """
        try:
            # Dynamic: Call model-specific validation if exists
            model_name = document.__class__.__name__.lower()

            validation_method = getattr(
                DocumentValidator,
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
    def _validate_simple_transition(document, to_status: str, user: User) -> Result:
        """
        Minimal validation for simple transitions - DON'T duplicate existing validations!
        """
        try:

            target_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=to_status,
                is_active=True
            ).first()

            if target_config and target_config.is_cancellation:
                return Result.success(msg="Cancellation allowed")

            return Result.success(msg="Simple transition allowed")

        except Exception as e:
            return Result.error('SIMPLE_VALIDATION_ERROR', str(e))

    @staticmethod
    def can_edit_document(document, user: User) -> Tuple[bool, str]:
        """
        ✅ FINAL: CONFIGURATION-DRIVEN document editing validation

        Hierarchy:
        1. DocumentTypeStatus.allows_editing (status-specific) ← ГЛАВНОТО!
        2. DocumentType.allow_edit_completed (for final documents)
        3. User permissions

        Returns:
            Tuple[bool, str]: (can_edit, reason)
        """
        try:
            # No document type - fallback
            if not document.document_type:
                return False, "Document has no type configured"

            # =====================
            # STEP 1: Find Status Configuration
            # =====================
            from ...models import DocumentTypeStatus

            status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            if not status_config:
                # Fallback - no configuration found
                logger.warning(f"No status configuration for {document.document_type.name}.{document.status}")
                return True, "No configuration found - allowing edit (fallback)"

            # =====================
            # STEP 2: Status-Level Check (ГЛАВНАТА КОНФИГУРАЦИЯ!)
            # =====================
            if not status_config.allows_editing:
                return False, f"Editing disabled for status '{document.status}'"

            # =====================
            # STEP 3: Document-Type-Level Check (Final Documents)
            # =====================
            if status_config.is_final:
                if not document.document_type.allow_edit_completed:
                    return False, (
                        f"Cannot edit documents in final status '{document.status}' "
                        f"- document type '{document.document_type.name}' does not allow "
                        f"editing completed documents"
                    )
                else:
                    logger.info(
                        f"Allowing edit of final document {getattr(document, 'document_number', 'Unknown')} "
                        f"due to document type allow_edit_completed=True"
                    )

            # =====================
            # STEP 4: User-Specific Validation
            # =====================
            if user:
                # Check document ownership (if applicable)
                if hasattr(document, 'created_by') and document.created_by:
                    if document.created_by != user and not user.is_superuser:
                        # Check if user has elevated permissions
                        if not user.has_perm('nomenclatures.change_document_others'):
                            return False, (
                                f"Only the document creator ({document.created_by.username}) "
                                f"or users with special permissions can edit this document"
                            )

                # Check if user has basic edit permission
                perm_name = f"{document._meta.app_label}.change_{document._meta.model_name}"
                if not user.has_perm(perm_name):
                    return False, "User does not have permission to edit documents"

            # =====================
            # STEP 5: Success
            # =====================
            return True, "Document can be edited"

        except Exception as e:
            logger.error(f"Error validating document edit permissions: {e}")
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def can_delete_document(document, user: User) -> Tuple[bool, str]:
        """
        ✅ FINAL: CONFIGURATION-DRIVEN document deletion validation
        """
        try:
            from ...models import DocumentTypeStatus

            # Find status configuration
            status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            if not status_config:
                return False, f"No active configuration found for status '{document.status}'"

            # ✅ Status-level check (ГЛАВНАТА КОНФИГУРАЦИЯ!)
            if not status_config.allows_deletion:
                return False, f"Deletion disabled for status '{document.status}'"

            # Final documents generally shouldn't be deletable
            if status_config.is_final:
                return False, f"Cannot delete documents in final status '{document.status}'"

            # User permissions
            if user:
                if hasattr(document, 'created_by') and document.created_by:
                    if document.created_by != user and not user.is_superuser:
                        if not user.has_perm('nomenclatures.delete_document_others'):
                            return False, "Only the document creator or elevated users can delete this document"

                if not user.has_perm('nomenclatures.delete_document'):
                    return False, "User does not have permission to delete documents"

            # Check for dependent data
            if hasattr(document, 'lines') and document.lines.exists():
                line_count = document.lines.count()
                return False, f"Cannot delete document with {line_count} existing lines"

            return True, "Document can be deleted"

        except Exception as e:
            logger.error(f"Error validating document deletion permissions: {e}")
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def get_effective_permissions(document, user: User) -> Dict[str, Any]:
        """
        ✅ NEW: Get comprehensive permission summary for a document

        Returns all computed permissions in one place for UI/API use
        """
        try:
            from ...models import DocumentTypeStatus

            status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            if not status_config:
                return {
                    'error': f"No configuration found for status '{document.status}'",
                    'can_edit': False,
                    'can_delete': False,
                    'can_transition': False
                }

            can_edit, edit_reason = DocumentValidator.can_edit_document(document, user)
            can_delete, delete_reason = DocumentValidator.can_delete_document(document, user)

            return {
                'document_number': getattr(document, 'document_number', 'Unknown'),
                'current_status': document.status,
                'document_type': document.document_type.name,

                # Computed permissions
                'can_edit': can_edit,
                'can_delete': can_delete,
                'can_transition': not status_config.is_final,  # Final statuses can't transition

                # Reasons
                'edit_reason': edit_reason,
                'delete_reason': delete_reason,

                # Configuration details
                'status_config': {
                    'allows_editing': status_config.allows_editing,
                    'allows_deletion': status_config.allows_deletion,
                    'is_initial': status_config.is_initial,
                    'is_final': status_config.is_final,
                    'is_cancellation': status_config.is_cancellation,
                },

                'document_type_config': {
                    'allow_edit_completed': document.document_type.allow_edit_completed,
                    'requires_approval': document.document_type.requires_approval,
                    'affects_inventory': document.document_type.affects_inventory,
                }
            }

        except Exception as e:
            logger.error(f"Error getting effective permissions: {e}")
            return {
                'error': f"Permission calculation failed: {str(e)}",
                'can_edit': False,
                'can_delete': False,
                'can_transition': False
            }

    @staticmethod
    def _validate_purchaserequest_rules(document, to_status: str, user: User, **kwargs) -> Result:
        """
        Purchase Request specific validation

        КОПИРАНО от старата версия за backward compatibility
        """
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

    @staticmethod
    def _validate_purchaseorder_rules(document, to_status: str, user: User, **kwargs) -> Result:
        """
        Purchase Order specific validation

        НОВИ правила за PurchaseOrder
        """
        try:
            # Confirmation validation
            if 'confirm' in to_status.lower():
                if not document.supplier_confirmed:
                    return Result.error(
                        'NOT_CONFIRMED',
                        'Supplier confirmation required'
                    )

            # Delivery validation
            if 'deliver' in to_status.lower() or 'receiv' in to_status.lower():
                if not hasattr(document, 'expected_delivery_date'):
                    return Result.error(
                        'NO_DELIVERY_DATE',
                        'Expected delivery date required'
                    )

            return Result.success()

        except Exception as e:
            return Result.error('PURCHASE_ORDER_VALIDATION_ERROR', str(e))

    @staticmethod
    def _validate_deliveryreceipt_rules(document, to_status: str, user: User, **kwargs) -> Result:
        """
        Delivery Receipt specific validation

        НОВИ правила за DeliveryReceipt
        """
        try:
            # Receiving validation
            if 'receiv' in to_status.lower() or 'complet' in to_status.lower():
                # Check all lines have received quantities
                if hasattr(document, 'lines'):
                    lines_without_qty = document.lines.filter(
                        models.Q(received_quantity__isnull=True) |
                        models.Q(received_quantity=0)
                    )
                    if lines_without_qty.exists():
                        return Result.error(
                            'NO_RECEIVED_QTY',
                            f'{lines_without_qty.count()} lines without received quantity'
                        )

            return Result.success()

        except Exception as e:
            return Result.error('DELIVERY_VALIDATION_ERROR', str(e))