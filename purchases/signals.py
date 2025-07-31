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
def handle_delivery_line_processing(sender, instance, created, **kwargs):
    """
    Enhanced DeliveryLine processing with immediate inventory support

    Handles:
    1. Document totals recalculation (existing functionality)
    2. Immediate inventory movements (NEW for immediate timing)
    """

    # 1. EXISTING: Recalculate document totals
    if instance.document_id:
        try:
            instance.document.recalculate_totals()
            logger.debug(f"💰 Recalculated totals for delivery {instance.document.document_number}")
        except Exception as e:
            logger.error(f"❌ Error recalculating delivery totals: {e}")

    # 2. NEW: Handle immediate inventory movements for new lines
    if created:  # Only for newly created lines
        try:
            _handle_immediate_inventory_for_line(instance)
        except Exception as e:
            logger.error(f"❌ Error processing immediate inventory for line {instance.pk}: {e}")
            # Don't re-raise - inventory errors shouldn't break line creation


def _should_process_immediate_inventory(line) -> bool:
    """Check if immediate inventory processing should be performed"""
    if not (line.document and line.document.document_type):
        return False
    if not line.document.document_type.affects_inventory:
        return False
    if not line.received_quantity:
        return False
    if line.document.document_type.inventory_timing == 'immediate':
        return True
    return False


# В purchases/signals.py

@receiver(post_save, sender=DeliveryLine)
def handle_delivery_line_processing(sender, instance, created, **kwargs):
    """
    Basic processing on DeliveryLine save:
    - Totals recalculation
    - Logging
    """

    if instance.document_id:
        try:
            instance.document.recalculate_totals()
        except Exception as e:
            logger.error(f"❌ Error recalculating delivery totals: {e}")




def _should_process_immediate_inventory(line) -> bool:
    """Check if immediate inventory processing should be performed"""
    if not (line.document and line.document.document_type):
        return False
    if not line.document.document_type.affects_inventory:
        return False
    if not line.received_quantity:
        return False
    if line.document.document_type.inventory_timing == 'immediate':
        return True
    return False


def _handle_immediate_inventory_for_line(line):
    """Handle immediate inventory processing for a delivery line"""
    if not _should_process_immediate_inventory(line):
        return

    from inventory.services.movement_service import MovementService
    from django.utils import timezone
    from decimal import Decimal

    logger.info(
        f"🔄 Processing immediate inventory for line {line.line_number}: {line.product.code} qty={line.received_quantity}")

    direction = line.document.document_type.inventory_direction

    # Провери и ограничи cost_price
    cost_price = line.unit_price or Decimal('0.00')

    # Ограничи до максимум 8 цифри преди десетичната запетая
    if cost_price > Decimal('99999999.99'):
        cost_price = Decimal('99999999.99')
        logger.warning(f"Cost price truncated for line {line.line_number}: {line.unit_price} → {cost_price}")

    try:
        # ========== IN DIRECTION ==========
        if direction == 'in':
            if line.received_quantity <= 0:
                logger.warning(f"Skipping IN movement - quantity {line.received_quantity} <= 0")
                return

            movement = MovementService.create_incoming_movement(
                location=line.document.location,
                product=line.product,
                quantity=abs(line.received_quantity),
                cost_price=cost_price,
                source_document_type='PURCHASE',
                source_document_number=line.document.document_number,
                movement_date=getattr(line.document, 'delivery_date', None) or timezone.now().date(),
                batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                reason=f"Immediate IN - line {line.line_number}",
                created_by=getattr(line.document, 'updated_by', None) or getattr(line.document, 'created_by', None)
            )
            logger.info(f"✅ Created IN movement: +{movement.quantity}")

        # ========== OUT DIRECTION ==========
        elif direction == 'out':
            if line.received_quantity <= 0:
                logger.warning(f"Skipping OUT movement - quantity {line.received_quantity} <= 0")
                return

            movements = MovementService.create_outgoing_movement(
                location=line.document.location,
                product=line.product,
                quantity=abs(line.received_quantity),
                source_document_type='PURCHASE',
                source_document_number=line.document.document_number,
                movement_date=getattr(line.document, 'delivery_date', None) or timezone.now().date(),
                reason=f"Immediate OUT - line {line.line_number}",
                created_by=getattr(line.document, 'updated_by', None) or getattr(line.document, 'created_by', None)
            )
            logger.info(f"✅ Created OUT movement(s): -{abs(line.received_quantity)}")

        # ========== BOTH DIRECTION ==========
        elif direction == 'both':
            if line.received_quantity == 0:
                logger.warning("Skipping BOTH movement - quantity is 0")
                return

            if line.received_quantity > 0:
                # Positive = incoming
                movement = MovementService.create_incoming_movement(
                    location=line.document.location,
                    product=line.product,
                    quantity=abs(line.received_quantity),
                    cost_price=cost_price,
                    source_document_type='PURCHASE',
                    source_document_number=line.document.document_number,
                    movement_date=getattr(line.document, 'delivery_date', None) or timezone.now().date(),
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    reason=f"Immediate IN (both) - line {line.line_number}",
                    created_by=getattr(line.document, 'updated_by', None) or getattr(line.document, 'created_by', None)
                )
                logger.info(f"✅ Created IN movement (both): +{movement.quantity}")

            else:  # line.received_quantity < 0
                # Negative = outgoing/return
                movements = MovementService.create_outgoing_movement(
                    location=line.document.location,
                    product=line.product,
                    quantity=abs(line.received_quantity),
                    source_document_type='PURCHASE',
                    source_document_number=line.document.document_number,
                    movement_date=getattr(line.document, 'delivery_date', None) or timezone.now().date(),
                    reason=f"Immediate OUT (both) - line {line.line_number}",
                    created_by=getattr(line.document, 'updated_by', None) or getattr(line.document, 'created_by', None)
                )
                logger.info(f"✅ Created OUT movement (both): -{abs(line.received_quantity)}")

        else:
            logger.error(f"❌ Unknown inventory direction: {direction}")

    except Exception as e:
        logger.error(f"❌ Failed to create immediate inventory movement: {e}")
        raise  # Re-raise за да видиш грешката
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


