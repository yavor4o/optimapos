# purchases/signals.py - CLEANED UP VERSION

from django.db.models.signals import post_save, post_delete, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import logging

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)

logger = logging.getLogger(__name__)


# =================================================================
# AUDIT & LOGGING SIGNALS - ЗАПАЗВАМЕ
# =================================================================

@receiver(post_save, sender=PurchaseRequest)
def log_request_changes(sender, instance, created, **kwargs):
    """САМО LOGGING - БЕЗ business logic"""

    if created:
        logger.info(f"📄 New purchase request created: {instance.document_number}")
        _log_document_action(instance, 'created')
        return

    # Log status changes САМО за audit
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"📋 Request {instance.document_number} status: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })


@receiver(post_save, sender=PurchaseOrder)
def log_order_changes(sender, instance, created, **kwargs):
    """САМО LOGGING - БЕЗ business logic"""

    if created:
        logger.info(f"📦 New purchase order created: {instance.document_number}")
        _log_document_action(instance, 'created')

    # Log status changes САМО за audit
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"📋 Order {instance.document_number} status: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })


@receiver(post_save, sender=DeliveryReceipt)
def log_delivery_changes(sender, instance, created, **kwargs):
    """САМО LOGGING - БЕЗ business logic"""

    if created:
        logger.info(f"🚚 New delivery receipt created: {instance.document_number}")
        _log_document_action(instance, 'created')

    # Log status changes САМО за audit
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"📋 Delivery {instance.document_number} status: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })


# =================================================================
# TOTALS RECALCULATION SIGNALS - ЗАПАЗВАМЕ
# =================================================================

@receiver(post_save, sender=PurchaseRequestLine)
def update_request_totals_on_line_save(sender, instance, **kwargs):
    """
    ✅ ПРОФЕСИОНАЛНО: Manual totals update when lines change

    Calls save() which will trigger recalculate_totals() internally
    """
    if instance.document_id:
        try:
            # ✅ PROFESSIONAL: Just save the document,
            # save() method will handle totals calculation
            instance.document.save()
            logger.debug(f"💰 Updated totals for request {instance.document.document_number}")
        except Exception as e:
            logger.error(f"❌ Error updating request totals: {e}")


@receiver(post_save, sender=PurchaseOrderLine)
def update_order_totals_on_line_save(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Recalculate totals when line is saved"""
    if instance.document_id:
        try:
            instance.document.recalculate_totals()
            logger.debug(f"💰 Recalculated totals for order {instance.document.document_number}")
        except Exception as e:
            logger.error(f"❌ Error recalculating order totals: {e}")


@receiver(post_save, sender=DeliveryLine)
def update_delivery_totals_on_line_save(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Recalculate totals when line is saved"""
    if instance.document_id:
        try:
            instance.document.recalculate_totals()
            logger.debug(f"💰 Recalculated totals for delivery {instance.document.document_number}")
        except Exception as e:
            logger.error(f"❌ Error recalculating delivery totals: {e}")


# =================================================================
# CLEANUP SIGNALS - ЗАПАЗВАМЕ
# =================================================================

@receiver(pre_delete, sender=PurchaseRequestLine)
def preserve_request_id_before_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Preserve request ID before line deletion"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=PurchaseRequestLine)
def cleanup_request_totals_on_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Recalculate totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            request = PurchaseRequest.objects.get(pk=instance._document_id_for_cleanup)
            request.recalculate_totals()
            logger.info(f"💰 Recalculated totals for request {request.document_number} after line deletion")
        except PurchaseRequest.DoesNotExist:
            logger.warning(f"⚠️ Request with ID {instance._document_id_for_cleanup} not found during cleanup")


@receiver(pre_delete, sender=PurchaseOrderLine)
def preserve_order_id_before_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Preserve order ID before line deletion"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=PurchaseOrderLine)
def cleanup_order_totals_on_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Recalculate totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            order = PurchaseOrder.objects.get(pk=instance._document_id_for_cleanup)
            order.recalculate_totals()
            logger.info(f"💰 Recalculated totals for order {order.document_number} after line deletion")
        except PurchaseOrder.DoesNotExist:
            logger.warning(f"⚠️ Order with ID {instance._document_id_for_cleanup} not found during cleanup")


@receiver(pre_delete, sender=DeliveryLine)
def preserve_delivery_id_before_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Preserve delivery ID before line deletion"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=DeliveryLine)
def cleanup_delivery_totals_on_line_delete(sender, instance, **kwargs):
    """ЗАПАЗВАМЕ - Recalculate totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            delivery = DeliveryReceipt.objects.get(pk=instance._document_id_for_cleanup)
            delivery.recalculate_totals()
            logger.info(f"💰 Recalculated totals for delivery {delivery.document_number} after line deletion")
        except DeliveryReceipt.DoesNotExist:
            logger.warning(f"⚠️ Delivery with ID {instance._document_id_for_cleanup} not found during cleanup")


# =================================================================
# STATUS TRACKING SIGNALS - ЗАПАЗВАМЕ ЗА LOGGING
# =================================================================

@receiver(pre_save, sender=PurchaseRequest)
def track_request_status_changes(sender, instance, **kwargs):
    """Track status changes САМО за logging purposes"""
    if instance.pk:
        try:
            original = PurchaseRequest.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except PurchaseRequest.DoesNotExist:
            instance._original_status = None


@receiver(pre_save, sender=PurchaseOrder)
def track_order_status_changes(sender, instance, **kwargs):
    """Track status changes САМО за logging purposes"""
    if instance.pk:
        try:
            original = PurchaseOrder.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except PurchaseOrder.DoesNotExist:
            instance._original_status = None


@receiver(pre_save, sender=DeliveryReceipt)
def track_delivery_status_changes(sender, instance, **kwargs):
    """Track status changes САМО за logging purposes"""
    if instance.pk:
        try:
            original = DeliveryReceipt.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except DeliveryReceipt.DoesNotExist:
            instance._original_status = None


# =================================================================
# HELPER FUNCTIONS - ЗАПАЗВАМЕ
# =================================================================

def _log_document_action(document, action, extra_data=None):
    """Helper function за audit logging"""
    try:
        # Simplified logging - можем да интегрираме с audit система
        log_data = {
            'document_type': document.__class__.__name__,
            'document_number': document.document_number,
            'action': action,
            'timestamp': timezone.now().isoformat(),
            'user': getattr(document, 'updated_by', None),
        }

        if extra_data:
            log_data.update(extra_data)

        # За сега само logging, но можем да добавим persistent audit trail
        logger.info(f"📋 Document action: {log_data}")

    except Exception as e:
        logger.error(f"❌ Error logging document action: {e}")


# =================================================================
# ПРЕМАХНАТИ SIGNALS - СЕГА СА В WorkflowService
# =================================================================

# ПРЕМАХНАТО: handle_request_status_changes - business logic
# ПРЕМАХНАТО: _handle_request_approved - business logic
# ПРЕМАХНАТО: _handle_request_converted - business logic
# ПРЕМАХНАТО: _handle_order_sent - business logic
# ПРЕМАХНАТО: _handle_order_confirmed - business logic
# ПРЕМАХНАТО: _handle_delivery_completed - business logic
# ПРЕМАХНАТО: handle_delivery_source_orders_changed - business logic
# ПРЕМАХНАТО: MovementService calls - сега в WorkflowService
# ПРЕМАХНАТО: Workflow transitions - сега в WorkflowService
# ПРЕМАХНАТО: Auto-conversions - сега в WorkflowService

# ВСЯ BUSINESS LOGIC Е ПРЕМЕСТЕНА В WorkflowService!


# =================================================================
# DEPRECATED COMMENT - INFORMATION ABOUT MIGRATION
# =================================================================

"""
MIGRATION NOTES:

Премахнати business logic signals:
- handle_request_status_changes() → WorkflowService
- _handle_request_approved() → WorkflowService._execute_post_transition_actions() 
- _handle_request_converted() → WorkflowService._handle_document_conversions()
- _handle_order_sent() → WorkflowService
- _handle_order_confirmed() → WorkflowService
- _handle_delivery_completed() → WorkflowService + MovementService

Запазени signals:
✅ Audit logging (post_save document signals)
✅ Totals recalculation (post_save line signals)  
✅ Cleanup operations (pre_delete/post_delete line signals)
✅ Status tracking (pre_save for logging)

Новото место за business logic:
🎯 WorkflowService.transition_document()
🎯 WorkflowService._execute_post_transition_actions()
🎯 WorkflowService._handle_inventory_movements()
🎯 WorkflowService._handle_document_conversions()
"""