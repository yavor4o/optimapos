# purchases/signals.py - REFACTORED FOR NEW STRUCTURE

from django.db.models.signals import post_save, post_delete, pre_delete, m2m_changed
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
# REQUEST SIGNALS
# =================================================================

@receiver(post_save, sender=PurchaseRequest)
def handle_request_status_changes(sender, instance, created, **kwargs):
    """Handle request status changes and workflow transitions"""

    if created:
        logger.info(f"New purchase request created: {instance.document_number}")
        _log_document_action(instance, 'created')
        return

    # Check for status changes
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"Request {instance.document_number} status changed: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })

            # Handle specific status transitions
            if new_status == 'approved':
                _handle_request_approved(instance)
            elif new_status == 'converted':
                _handle_request_converted(instance)


@receiver(pre_delete, sender=PurchaseRequestLine)
def preserve_request_id_before_line_delete(sender, instance, **kwargs):
    """Preserve request ID before line deletion for cleanup"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=PurchaseRequestLine)
def cleanup_request_totals_on_line_delete(sender, instance, **kwargs):
    """Recalculate request totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            request = PurchaseRequest.objects.get(pk=instance._document_id_for_cleanup)
            request.recalculate_totals()
            logger.info(f"Recalculated totals for request {request.document_number} after line deletion")
        except PurchaseRequest.DoesNotExist:
            logger.warning(f"Request with ID {instance._document_id_for_cleanup} not found during cleanup")


# =================================================================
# ORDER SIGNALS
# =================================================================

@receiver(post_save, sender=PurchaseOrder)
def handle_order_status_changes(sender, instance, created, **kwargs):
    """Handle order status changes and workflow transitions"""

    if created:
        logger.info(f"New purchase order created: {instance.document_number}")
        _log_document_action(instance, 'created')

        # Log if created from request
        if instance.source_request:
            logger.info(
                f"Order {instance.document_number} created from request {instance.source_request.document_number}")

        return

    # Check for status changes
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"Order {instance.document_number} status changed: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })

            # Handle specific status transitions
            if new_status == 'sent':
                _handle_order_sent(instance)
            elif new_status == 'confirmed':
                _handle_order_confirmed(instance)


@receiver(pre_delete, sender=PurchaseOrderLine)
def preserve_order_id_before_line_delete(sender, instance, **kwargs):
    """Preserve order ID before line deletion for cleanup"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=PurchaseOrderLine)
def cleanup_order_totals_on_line_delete(sender, instance, **kwargs):
    """Recalculate order totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            order = PurchaseOrder.objects.get(pk=instance._document_id_for_cleanup)
            order.recalculate_totals()
            logger.info(f"Recalculated totals for order {order.document_number} after line deletion")
        except PurchaseOrder.DoesNotExist:
            logger.warning(f"Order with ID {instance._document_id_for_cleanup} not found during cleanup")


# =================================================================
# DELIVERY SIGNALS
# =================================================================

@receiver(post_save, sender=DeliveryReceipt)
def handle_delivery_status_changes(sender, instance, created, **kwargs):
    """Handle delivery status changes and workflow transitions"""

    if created:
        logger.info(f"New delivery receipt created: {instance.document_number}")
        _log_document_action(instance, 'created')

        # Log creation type
        if instance.creation_type == 'from_orders':
            order_count = instance.source_orders.count()
            logger.info(f"Delivery {instance.document_number} created from {order_count} orders")
        elif instance.creation_type == 'direct':
            logger.info(f"Direct delivery {instance.document_number} created")

        return

    # Check for status changes
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"Delivery {instance.document_number} status changed: {old_status} -> {new_status}")
            _log_document_action(instance, f'status_changed_to_{new_status}', {
                'old_status': old_status,
                'new_status': new_status
            })

            # Handle specific status transitions
            if new_status == 'received':
                _handle_delivery_received(instance)
            elif new_status == 'completed':
                _handle_delivery_completed(instance)


@receiver(m2m_changed, sender=DeliveryReceipt.source_orders.through)
def handle_delivery_source_orders_changed(sender, instance, action, pk_set, **kwargs):
    """Handle changes to delivery source orders"""

    if action == 'post_add':
        order_numbers = [
            PurchaseOrder.objects.get(pk=pk).document_number
            for pk in pk_set
        ]
        logger.info(f"Added source orders to delivery {instance.document_number}: {', '.join(order_numbers)}")

        # Update creation type if needed
        if instance.creation_type == 'direct' and instance.source_orders.exists():
            instance.creation_type = 'from_orders'
            instance.save(update_fields=['creation_type'])

    elif action == 'post_remove':
        order_numbers = [
            PurchaseOrder.objects.get(pk=pk).document_number
            for pk in pk_set
        ]
        logger.info(f"Removed source orders from delivery {instance.document_number}: {', '.join(order_numbers)}")


@receiver(pre_delete, sender=DeliveryLine)
def preserve_delivery_id_before_line_delete(sender, instance, **kwargs):
    """Preserve delivery ID before line deletion for cleanup"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=DeliveryLine)
def cleanup_delivery_totals_on_line_delete(sender, instance, **kwargs):
    """Recalculate delivery totals when line is deleted"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            delivery = DeliveryReceipt.objects.get(pk=instance._document_id_for_cleanup)
            delivery.recalculate_totals()
            logger.info(f"Recalculated totals for delivery {delivery.document_number} after line deletion")
        except DeliveryReceipt.DoesNotExist:
            logger.warning(f"Delivery with ID {instance._document_id_for_cleanup} not found during cleanup")


# =================================================================
# WORKFLOW EVENT HANDLERS
# =================================================================

def _handle_request_approved(request):
    """Handle request approval workflow"""
    try:
        _log_document_action(request, 'approved', {
            'approved_by': request.approved_by.username if request.approved_by else None,
            'approval_time': request.approved_at.isoformat() if request.approved_at else None
        })

        # Notify stakeholders about approval
        # TODO: Implement notification system

    except Exception as e:
        logger.error(f"Error handling request approval for {request.document_number}: {e}")


def _handle_request_converted(request):
    """Handle request conversion to order"""
    try:
        order_number = request.converted_to_order.document_number if request.converted_to_order else 'Unknown'

        _log_document_action(request, 'converted_to_order', {
            'order_number': order_number,
            'converted_by': request.converted_by.username if request.converted_by else None,
            'conversion_time': request.converted_at.isoformat() if request.converted_at else None
        })

    except Exception as e:
        logger.error(f"Error handling request conversion for {request.document_number}: {e}")


def _handle_order_sent(order):
    """Handle order sent to supplier"""
    try:
        _log_document_action(order, 'sent_to_supplier', {
            'sent_by': order.sent_by.username if order.sent_by else None,
            'sent_time': order.sent_to_supplier_at.isoformat() if order.sent_to_supplier_at else None,
            'supplier': order.supplier.name
        })

        # TODO: Integrate with supplier notification system

    except Exception as e:
        logger.error(f"Error handling order sent for {order.document_number}: {e}")


def _handle_order_confirmed(order):
    """Handle order confirmation by supplier"""
    try:
        _log_document_action(order, 'confirmed_by_supplier', {
            'supplier_confirmed': order.supplier_confirmed,
            'supplier_reference': order.supplier_order_reference,
            'expected_delivery': order.expected_delivery_date.isoformat() if order.expected_delivery_date else None
        })

        # Update delivery planning
        # TODO: Integrate with delivery scheduling system

    except Exception as e:
        logger.error(f"Error handling order confirmation for {order.document_number}: {e}")


def _handle_delivery_received(delivery):
    """Handle delivery received and processed"""
    try:
        variance_summary = delivery.get_variance_summary()

        _log_document_action(delivery, 'received', {
            'received_by': delivery.received_by.username if delivery.received_by else None,
            'quality_checked': delivery.quality_checked,
            'has_variances': delivery.has_variances,
            'variance_summary': variance_summary
        })

        # Update source orders delivery status
        for order in delivery.source_orders.all():
            order.update_delivery_status()

        # TODO: Integrate with inventory system
        # TODO: Update product costs

    except Exception as e:
        logger.error(f"Error handling delivery received for {delivery.document_number}: {e}")


def _handle_delivery_completed(delivery):
    """Handle delivery processing completion"""
    try:
        _log_document_action(delivery, 'completed', {
            'processed_by': delivery.updated_by.username if delivery.updated_by else None,
            'processing_time': delivery.processed_at.isoformat() if delivery.processed_at else None,
            'total_amount': str(delivery.grand_total)
        })

        # Final integrations
        # TODO: Update financial records
        # TODO: Supplier performance tracking

    except Exception as e:
        logger.error(f"Error handling delivery completion for {delivery.document_number}: {e}")


# =================================================================
# AUDIT LOGGING HELPER
# =================================================================

def _log_document_action(document, action, additional_data=None):
    """Log document action to audit system"""
    try:
        # Use core audit system instead of old PurchaseAuditLog
        from core.services import AuditService

        AuditService.log_action(
            obj=document,
            action=action,
            user=getattr(document, 'updated_by', None),
            description=f"{document.__class__.__name__} {action}",
            additional_data=additional_data or {}
        )

    except ImportError:
        # Fallback if core audit is not available yet
        logger.info(f"Document {document.document_number}: {action}")
    except Exception as e:
        logger.error(f"Error logging action for {document.document_number}: {e}")


# =================================================================
# STATUS TRACKING
# =================================================================

@receiver(post_save, sender=PurchaseRequest)
def track_request_changes(sender, instance, **kwargs):
    """Track changes for next signal call"""
    instance._original_status = instance.status


@receiver(post_save, sender=PurchaseOrder)
def track_order_changes(sender, instance, **kwargs):
    """Track changes for next signal call"""
    instance._original_status = instance.status


@receiver(post_save, sender=DeliveryReceipt)
def track_delivery_changes(sender, instance, **kwargs):
    """Track changes for next signal call"""
    instance._original_status = instance.status