# purchases/signals.py - ПЪЛЕН ФУНКЦИОНАЛЕН ФАЙЛ С ПОПРАВКА
from decimal import Decimal

from django.db.models.signals import post_save, post_delete, pre_delete, m2m_changed, pre_save
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

@receiver(post_save, sender=PurchaseRequestLine)
def update_request_totals_on_line_save(sender, instance, **kwargs):
    """Recalculate request totals when line is saved"""
    if instance.document_id:
        try:
            instance.document.recalculate_totals()
            logger.debug(f"Recalculated totals for request {instance.document.document_number}")
        except Exception as e:
            logger.error(f"Error recalculating request totals: {e}")


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
        if hasattr(instance, 'source_request') and instance.source_request:
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
# DELIVERY SIGNALS - ПОПРАВЕНИ НО ПЪЛНИ
# =================================================================

@receiver(post_save, sender=DeliveryReceipt)
def handle_delivery_status_changes(sender, instance, created, **kwargs):
    """Handle delivery status changes and workflow transitions"""

    if created:
        logger.info(f"New delivery receipt created: {instance.document_number}")
        _log_document_action(instance, 'created')

        # ✅ ПОПРАВЕНО: Логваме creation_type БЕЗ достъп до ManyToMany при създаване
        if instance.creation_type == 'from_orders':
            logger.info(f"Delivery {instance.document_number} created from orders (count will be available after save)")
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
        try:
            order_numbers = [
                PurchaseOrder.objects.get(pk=pk).document_number
                for pk in pk_set if pk
            ]
            logger.info(f"Added source orders to delivery {instance.document_number}: {', '.join(order_numbers)}")

            # Update creation type if needed
            if instance.creation_type == 'direct' and instance.source_orders.exists():
                instance.creation_type = 'from_orders'
                instance.save(update_fields=['creation_type'])
        except Exception as e:
            logger.error(f"Error handling source orders addition: {e}")

    elif action == 'post_remove':
        try:
            order_numbers = [
                PurchaseOrder.objects.get(pk=pk).document_number
                for pk in pk_set if pk
            ]
            logger.info(f"Removed source orders from delivery {instance.document_number}: {', '.join(order_numbers)}")
        except Exception as e:
            logger.error(f"Error handling source orders removal: {e}")


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
# WORKFLOW EVENT HANDLERS - ПЪЛНА ФУНКЦИОНАЛНОСТ
# =================================================================

def _handle_request_approved(request):
    """Handle request approval workflow"""
    try:
        approved_by = getattr(request, 'approved_by', None)
        approved_at = getattr(request, 'approved_at', None)

        _log_document_action(request, 'approved', {
            'approved_by': approved_by.username if approved_by else None,
            'approval_time': approved_at.isoformat() if approved_at else None
        })

        # Notify stakeholders about approval
        # TODO: Implement notification system

    except Exception as e:
        logger.error(f"Error handling request approval for {request.document_number}: {e}")


def _handle_request_converted(request):
    """Handle request conversion to order"""
    try:
        converted_to_order = getattr(request, 'converted_to_order', None)
        order_number = converted_to_order.document_number if converted_to_order else 'Unknown'

        _log_document_action(request, 'converted_to_order', {
            'order_number': order_number,
            'converted_by': getattr(request, 'converted_by', None),
            'conversion_time': getattr(request, 'converted_at', None)
        })

    except Exception as e:
        logger.error(f"Error handling request conversion for {request.document_number}: {e}")


def _handle_order_sent(order):
    """Handle order sent to supplier"""
    try:
        _log_document_action(order, 'sent_to_supplier', {
            'sent_by': getattr(order, 'sent_by', None),
            'sent_time': getattr(order, 'sent_to_supplier_at', None),
            'supplier': order.supplier.name
        })

        # TODO: Integrate with supplier notification system

    except Exception as e:
        logger.error(f"Error handling order sent for {order.document_number}: {e}")


def _handle_order_confirmed(order):
    """
    Handle order confirmation by supplier

    ОБНОВЕНО: Добавена проверка за auto-receive
    """
    try:
        _log_document_action(order, 'confirmed_by_supplier', {
            'supplier_confirmed': getattr(order, 'supplier_confirmed', None),
            'supplier_reference': getattr(order, 'supplier_order_reference', None),
            'expected_delivery': getattr(order, 'expected_delivery_date', None)
        })

        # НОВО: Проверка за auto-receive
        if (hasattr(order.document_type, 'auto_receive') and
                order.document_type.auto_receive and
                order.document_type.affects_inventory):

            try:
                from inventory.services import MovementService

                movements = MovementService.create_from_document(order)

                if movements:
                    logger.info(
                        f"Auto-receive: Created {len(movements)} inventory movements "
                        f"for confirmed order {order.document_number}"
                    )

                    # Маркираме поръчката като доставена
                    order.delivery_status = 'completed'
                    order.save(update_fields=['delivery_status'])

            except Exception as e:
                logger.error(
                    f"Error in auto-receive for order {order.document_number}: {e}"
                )

        # Update delivery planning
        # TODO: Integrate with delivery scheduling system

    except Exception as e:
        logger.error(f"Error handling order confirmation for {order.document_number}: {e}")





def _handle_delivery_received(delivery):
    """Handle delivery received and processed"""
    try:
        # Safe access to variance summary
        variance_summary = None
        if hasattr(delivery, 'get_variance_summary'):
            try:
                variance_summary = delivery.get_variance_summary()
            except:
                pass

        _log_document_action(delivery, 'received', {
            'received_by': delivery.received_by.username if delivery.received_by else None,
            'quality_checked': getattr(delivery, 'quality_checked', False),
            'has_variances': getattr(delivery, 'has_variances', False),
            'variance_summary': variance_summary
        })

        # Update source orders delivery status - SAFE ACCESS
        if hasattr(delivery, 'source_orders') and delivery.pk:
            try:
                for order in delivery.source_orders.all():
                    if hasattr(order, 'update_delivery_status'):
                        order.update_delivery_status()
            except:
                pass

        # TODO: Integrate with inventory system
        # TODO: Update product costs

    except Exception as e:
        logger.error(f"Error handling delivery received for {delivery.document_number}: {e}")


def _handle_delivery_completed(delivery):
    """
    Handle delivery completion and inventory updates

    ОБНОВЕНО: Добавена интеграция с inventory система
    """
    try:
        # Логване на действието
        _log_document_action(delivery, 'completed', {
            'completed_by': getattr(delivery, 'processed_by', None),
            'completion_time': timezone.now().isoformat(),
            'lines_count': delivery.lines.count(),
            'has_variances': delivery.has_variances,
            'has_quality_issues': delivery.has_quality_issues
        })

        # НОВО: Създаване на inventory движения
        try:
            from inventory.services import MovementService

            # MovementService.create_from_document проверява:
            # - affects_inventory
            # - inventory_timing
            # - текущия статус
            movements = MovementService.create_from_document(delivery)

            if movements:
                logger.info(
                    f"Successfully created {len(movements)} inventory movements "
                    f"for delivery {delivery.document_number}"
                )

                # Логване на детайли за движенията
                movement_summary = {}
                for movement in movements:
                    key = f"{movement.product.code}_{movement.movement_type}"
                    if key not in movement_summary:
                        movement_summary[key] = {
                            'product': movement.product.name,
                            'type': movement.movement_type,
                            'total_qty': Decimal('0'),
                            'locations': set()
                        }
                    movement_summary[key]['total_qty'] += movement.quantity
                    movement_summary[key]['locations'].add(movement.location.code)

                for key, data in movement_summary.items():
                    logger.info(
                        f"  - {data['product']}: {data['total_qty']} units "
                        f"({data['type']}) in {', '.join(data['locations'])}"
                    )

            else:
                logger.debug(
                    f"No inventory movements created for delivery {delivery.document_number} "
                    f"(may not affect inventory or wrong timing)"
                )

        except ImportError:
            logger.error(
                "Could not import MovementService. "
                "Is the inventory app installed and configured?"
            )
        except Exception as e:
            # Логваме грешката, но не спираме целия процес
            logger.error(
                f"Error creating inventory movements for delivery "
                f"{delivery.document_number}: {e}",
                exc_info=True
            )

            # Може да искаме да известим админите
            _notify_inventory_error(delivery, str(e))

        # Актуализация на свързаните поръчки
        if hasattr(delivery, 'update_source_orders'):
            try:
                delivery.update_source_orders()
                logger.info(
                    f"Updated delivery status for source orders of "
                    f"delivery {delivery.document_number}"
                )
            except Exception as e:
                logger.error(
                    f"Error updating source orders for delivery "
                    f"{delivery.document_number}: {e}"
                )

        # Известяване на заинтересованите страни
        _notify_delivery_completed(delivery)

    except Exception as e:
        logger.error(
            f"Error handling delivery completion for {delivery.document_number}: {e}",
            exc_info=True
        )


def _notify_inventory_error(delivery, error_message):
    """
    Известява админите за грешки при създаване на inventory движения

    НОВО: Helper функция за error notifications
    """
    try:
        # TODO: Implement actual notification
        # За сега само логваме
        logger.critical(
            f"INVENTORY ERROR for delivery {delivery.document_number}: {error_message}"
        )

        # Може да добавим:
        # - Email до админи
        # - Slack notification
        # - Създаване на error ticket

    except Exception as e:
        logger.error(f"Could not send inventory error notification: {e}")


def _notify_delivery_completed(delivery):
    """
    Известява заинтересованите страни за завършена доставка

    Съществуваща функция - може да се разшири
    """
    try:
        # TODO: Implement notifications
        # - Email до warehouse manager
        # - Update на dashboard
        # - Trigger за следващи процеси
        pass

    except Exception as e:
        logger.error(f"Error sending delivery notifications: {e}")


# =================================================================
# AUDIT LOGGING HELPER - ENHANCED
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
        log_data = {
            'document_type': document.__class__.__name__,
            'document_number': document.document_number,
            'action': action,
            'timestamp': timezone.now().isoformat()
        }

        if additional_data:
            log_data.update(additional_data)

        logger.info(f"Document action: {log_data}")
    except Exception as e:
        logger.error(f"Error logging action for {document.document_number}: {e}")


# =================================================================
# STATUS TRACKING - STORE ORIGINAL STATUS
# =================================================================

@receiver(pre_save, sender=PurchaseRequest)
def store_request_original_status(sender, instance, **kwargs):
    """Store original status before save"""
    if instance.pk:
        try:
            original = PurchaseRequest.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except PurchaseRequest.DoesNotExist:
            pass


@receiver(pre_save, sender=PurchaseOrder)
def store_order_original_status(sender, instance, **kwargs):
    """Store original status before save"""
    if instance.pk:
        try:
            original = PurchaseOrder.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except PurchaseOrder.DoesNotExist:
            pass


@receiver(pre_save, sender=DeliveryReceipt)
def store_delivery_original_status(sender, instance, **kwargs):
    """Store original status before save"""
    if instance.pk:
        try:
            original = DeliveryReceipt.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except DeliveryReceipt.DoesNotExist:
            pass


# =================================================================
# STATUS TRACKING - POST SAVE
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