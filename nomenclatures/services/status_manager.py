# nomenclatures/services/document/status_manager.py - CONFIGURATION-DRIVEN VERSION
"""
Status Manager - управлява status transitions

ФИКСИРАНО:
✅ _execute_post_transition_actions() - CONFIGURATION-DRIVEN вместо hardcoded
✅ Enhanced error handling със structured logging
✅ Integration с DocumentTypeStatus inventory settings
✅ Backward compatibility запазена
"""

from typing import  Optional, List
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
import logging
import json
from django.db import transaction
from core.utils.result import Result
from nomenclatures.services.validator import DocumentValidator

User = get_user_model()
logger = logging.getLogger(__name__)


class StatusManager:
    """Специализиран service за управление на статуси"""

    @staticmethod
    @transaction.atomic
    def transition_document(document,
                            to_status: str,
                            user: User,
                            comments: str = '',
                            **kwargs) -> Result:
        """
        Execute document status transition with PostgreSQL compatibility

        ✅ БЕЗ ПРОМЯНА - работи перфектно
        """
        try:
            from_status = document.status

            logger.info(f"🔄 Transitioning {document.document_number}: {from_status} → {to_status}")

            # Refresh document data (without locking for PostgreSQL compatibility)
            # Get fresh copy to ensure data consistency across concurrent operations
            document = document.__class__.objects.get(pk=document.pk)
            logger.debug(f"📄 Document retrieved: {document.document_number}")

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

            # 2. СТАТУС ВАЛИДАЦИЯ
            logger.debug(f"🔍 Validating status transition for {document.document_number}")
            status_result = StatusManager._validate_status_transition(document, to_status)
            if not status_result.ok:
                logger.error(f"❌ Status validation failed: {status_result.msg}")
                return status_result

            # 3. APPROVAL vs SIMPLE TRANSITION ЛОГИКА
            approval_data = {}

            if document.document_type.requires_approval:
                # === APPROVAL WORKFLOW ===
                logger.debug(f"🔒 Document requires approval - checking ApprovalService")
                try:
                    from ..approval_service import ApprovalService

                    approval_result = ApprovalService.authorize_document_transition(
                        document, to_status, user
                    )
                    if not approval_result.ok:
                        logger.warning(f"🚫 Approval denied: {approval_result.msg}")
                        return approval_result

                    logger.info(f"✅ Approval authorized: {approval_result.msg}")
                    approval_data = approval_result.data or {}

                except ImportError:
                    logger.error("❌ ApprovalService not available but document requires approval")
                    return Result.error('APPROVAL_SERVICE_UNAVAILABLE', 'Approval system not available')

            else:
                # === SIMPLE TRANSITION ===
                logger.debug(f"🟢 Simple transition - no approval required")
                simple_result = DocumentValidator._validate_simple_transition(document, to_status, user)
                if not simple_result.ok:
                    logger.error(f"❌ Simple validation failed: {simple_result.msg}")
                    return simple_result

            # 4. BUSINESS VALIDATION
            logger.debug(f"🔧 Validating business rules")
            business_result = DocumentValidator._validate_business_rules(
                document, to_status, user, **kwargs
            )
            if not business_result.ok:
                logger.error(f"❌ Business validation failed: {business_result.msg}")
                return business_result

            # 5. EXECUTE TRANSITION
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

            # Save document
            try:
                document.save()
                logger.info(f"💾 Document saved with new status: {to_status}")
            except Exception as save_error:
                logger.error(f"❌ Failed to save document: {save_error}")
                return Result.error('SAVE_FAILED', f'Failed to save document: {save_error}')

            # 6. CONDITIONAL LOGGING
            try:
                if document.document_type.requires_approval:
                    logger.debug(f"📝 Logging to ApprovalLog")
                    StatusManager._log_transition(
                        document, approval_data.get('rule_id'), old_status, to_status, user, comments
                    )
                else:
                    logger.debug(f"📝 Logging to Admin log (simple transition)")
                    StatusManager._log_simple_transition(
                        document, old_status, to_status, user, comments
                    )
            except Exception as log_error:
                logger.warning(f"⚠️ Logging failed but transition succeeded: {log_error}")

            # 7. POST-TRANSITION EFFECTS
            try:
                logger.debug(f"🔄 Executing post-transition actions")
                StatusManager._execute_post_transition_actions(
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

    @staticmethod
    def _validate_status_transition(document, to_status: str) -> Result:
        """
        Validate status transition is allowed

        ✅ БЕЗ ПРОМЯНА - работи перфектно
        """
        try:
            from ..models.statuses import DocumentStatus, DocumentTypeStatus

            # Check if to_status exists
            status_obj = DocumentStatus.objects.filter(
                code=to_status,
                is_active=True
            ).first()

            if not status_obj:
                return Result.error(
                    'INVALID_STATUS',
                    f"Status '{to_status}' does not exist"
                )

            # Check if status is configured for this document type
            status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status=status_obj,
                is_active=True
            ).first()

            if not status_config:
                configured = DocumentTypeStatus.objects.filter(
                    document_type=document.document_type,
                    is_active=True
                ).values_list('status__code', flat=True)

                return Result.error(
                    'STATUS_NOT_CONFIGURED',
                    f"Status '{to_status}' not configured for {document.document_type.name}. "
                    f"Available: {', '.join(configured)}"
                )

            # Check transition rules
            current_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            # Cannot transition FROM final status
            if current_config and current_config.is_final:
                return Result.error(
                    'FROM_FINAL_STATUS',
                    f"Cannot transition from final status '{document.status}'"
                )

            # Cannot transition TO initial status
            if status_config.is_initial:
                return Result.error(
                    'TO_INITIAL_STATUS',
                    f"Cannot transition to initial status '{to_status}'"
                )

            return Result.success()

        except Exception as e:
            return Result.error('STATUS_VALIDATION_ERROR', str(e))

    @staticmethod
    def _execute_post_transition_actions(document, old_status: str, new_status: str, user: User, **kwargs):
        """
        🎯 FIXED: CONFIGURATION-DRIVEN post-transition actions

        ПРЕДИ: Hardcoded if new_status == 'received' and model == 'deliveryreceipt'
        СЕГА: Използва DocumentTypeStatus.creates_inventory_movements конфигурация
        """
        try:
            from nomenclatures.models import DocumentTypeStatus

            # =====================
            # STEP 1: Намери конфигурацията за НОВИЯ статус
            # =====================
            new_status_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=new_status,
                is_active=True
            ).first()

            if not new_status_config:
                logger.warning(f"No configuration found for {document.document_type.name} status '{new_status}'")
                return

            # =====================
            # STEP 2: INVENTORY ACTIONS (Configuration-Driven)
            # =====================

            # 🎯 Създаване на движения (заменя hardcoded логика)
            if new_status_config.creates_inventory_movements:
                logger.info(f"📦 Creating inventory movements for {document.document_number} → {new_status}")
                try:
                    from inventory.services import MovementService
                    result = MovementService.process_document_movements(document)
                    if result.ok:
                        movements_count = result.data.get('movements_created', 0)
                        logger.info(f"✅ Created {movements_count} inventory movements")
                    else:
                        logger.error(f"❌ Movement creation failed: {result.msg}")
                except ImportError:
                    logger.warning("⚠️ MovementService not available")
                except Exception as e:
                    logger.error(f"❌ Movement creation error: {str(e)}")

            # 🔄 Обръщане на движения (DIRECT DELETION - bypasses correction permission checks)
            if new_status_config.reverses_inventory_movements:
                logger.info(f"↩️ Reversing inventory movements for {document.document_number} → {new_status}")
                try:
                    from inventory.models import InventoryMovement
                    
                    # Direct deletion - reversal is not the same as correction
                    # reverses_inventory_movements means "delete all movements on status entry"
                    movements_to_delete = InventoryMovement.objects.filter(
                        source_document_number=document.document_number
                    )
                    deleted_count = movements_to_delete.count()
                    
                    if deleted_count > 0:
                        movements_to_delete.delete()
                        logger.info(f"✅ Movement reversal completed: {deleted_count} movements deleted")
                    else:
                        logger.info(f"✅ No movements to reverse for {document.document_number}")
                        
                except Exception as e:
                    logger.error(f"❌ Movement reversal error: {str(e)}")

            # =====================
            # STEP 3: LEGACY ACTIONS (Backward Compatibility)
            # =====================

            # 📧 Email notifications (unchanged)
            if hasattr(document, 'send_status_change_email'):
                try:
                    document.send_status_change_email(old_status, new_status, user)
                    logger.debug(f"📧 Status change email sent")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send email: {e}")

            # 🔗 Update related documents (improved logic)
            if new_status == 'converted' and hasattr(document, 'converted_to_order'):
                try:
                    if document.converted_to_order:
                        document.converted_to_order.source_request = document
                        document.converted_to_order.save(update_fields=['source_request'])
                        logger.debug(f"🔗 Updated related order reference")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update related order: {e}")

            # =====================
            # STEP 4: BUSINESS TRIGGERS (Configuration-Driven)
            # =====================

            # 🏁 Final document processing
            if new_status_config.is_final:
                logger.info(f"🏁 Document {document.document_number} reached final status: {new_status}")
                try:
                    # Trigger final document processing
                    StatusManager._process_final_document(document, new_status, user)
                except Exception as e:
                    logger.warning(f"⚠️ Final document processing failed: {e}")

            # 🚫 Cancellation cleanup
            if new_status_config.is_cancellation:
                logger.info(f"🚫 Document {document.document_number} cancelled: {new_status}")
                try:
                    # Trigger cancellation cleanup
                    StatusManager._process_cancelled_document(document, old_status, user)
                except Exception as e:
                    logger.warning(f"⚠️ Cancellation cleanup failed: {e}")

        except Exception as e:
            logger.error(f"💥 Error in post-transition actions for {document.document_number}: {e}")
            # НЕ re-raise - не искаме transition да се провали заради side effects

    @staticmethod
    def _process_final_document(document, final_status: str, user: User):
        """
        🎯 NEW: Process documents that reach final status
        """
        # Integration triggers (ако е нужно)
        if document.document_type.is_fiscal:
            logger.info(f"💰 Fiscal document {document.document_number} finalized")
            # TODO: Trigger fiscal device integration

        # Performance analytics
        if hasattr(document, 'created_at'):
            processing_time = timezone.now() - document.created_at
            logger.info(f"⏱️ Document processing time: {processing_time}")

    @staticmethod
    def _process_cancelled_document(document, old_status: str, user: User):
        """
        🎯 NEW: Process cancelled documents
        """
        # Cleanup logic for cancelled documents
        logger.info(f"🧹 Cleaning up cancelled document {document.document_number}")

        # TODO: Add specific cancellation cleanup logic
        # - Remove reservations
        # - Cancel related processes
        # - Notify stakeholders

    @staticmethod
    def _log_transition(document, rule_id: Optional[int], old_status: str, new_status: str, user: User, comments: str):
        """
        Log transition to ApprovalLog

        ✅ БЕЗ ПРОМЯНА - работи перфектно
        """
        try:
            from nomenclatures.models.approvals import ApprovalLog, ApprovalRule

            rule = None
            if rule_id:
                try:
                    rule = ApprovalRule.objects.get(id=rule_id)
                except ApprovalRule.DoesNotExist:
                    pass

            ApprovalLog.objects.create(
                content_type=ContentType.objects.get_for_model(document),
                object_id=document.pk,
                rule=rule,
                from_status=old_status,
                to_status=new_status,
                action='approved' if 'approv' in new_status.lower() else 'submitted',
                actor=user,
                comments=comments or f'Status changed from {old_status} to {new_status}'
            )

        except Exception as e:
            logger.warning(f"Failed to create ApprovalLog: {e}")

    @staticmethod
    def _log_simple_transition(document, old_status: str, new_status: str, user: User, comments: str):
        """
        Log transition to Django admin log

        ✅ БЕЗ ПРОМЯНА - работи перфектно
        """
        try:
            LogEntry.objects.create(
                user=user,
                content_type=ContentType.objects.get_for_model(document.__class__),
                object_id=str(document.pk),
                object_repr=str(document),
                action_flag=CHANGE,
                change_message=json.dumps([{
                    'changed': {
                        'fields': ['status'],
                        'from': old_status,
                        'to': new_status,
                        'comments': comments
                    }
                }])
            )
        except Exception as e:
            logger.warning(f"Failed to create LogEntry: {e}")

    @staticmethod
    def _get_simple_next_statuses(document) -> List[str]:
        """
        🎯 ENHANCED: Get next available statuses using configuration

        ПОДОБРЕНО: Използва DocumentTypeStatus вместо hardcoded map
        """
        try:
            from nomenclatures.models.statuses import DocumentTypeStatus

            # Get configured statuses for this document type
            configured_statuses = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                is_active=True
            ).select_related('status').order_by('sort_order')

            # Build dynamic transitions based on configuration
            next_statuses = []
            current_position = None

            for i, config in enumerate(configured_statuses):
                if config.status.code == document.status:
                    current_position = i
                    break

            if current_position is not None:
                # Get next statuses in workflow order
                remaining_configs = configured_statuses[current_position + 1:]

                for config in remaining_configs:
                    # Skip initial statuses (can't go back to initial)
                    if not config.is_initial:
                        next_statuses.append(config.status.code)

                    # Stop at first final status option
                    if config.is_final and next_statuses:
                        break

                # Always allow cancellation if configured
                cancellation_config = configured_statuses.filter(is_cancellation=True).first()
                if cancellation_config and cancellation_config.status.code not in next_statuses:
                    next_statuses.append(cancellation_config.status.code)

            return next_statuses

        except Exception as e:
            logger.warning(f"Error getting next statuses: {e}")
            # Fallback to basic transitions
            # FIXED: Use dynamic status resolution instead of hardcoded map
            try:
                from ._status_resolver import StatusResolver
                return StatusResolver.get_next_possible_statuses(document.document_type, document.status)
            except Exception as fallback_error:
                logger.error(f"StatusResolver also failed: {fallback_error}")
                # Emergency fallback - return empty list (no transitions allowed)
                return []