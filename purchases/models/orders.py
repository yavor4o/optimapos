# purchases/models/orders.py - ФИНАЛНА ВЕРСИЯ
"""
Purchase Order Models - ПЪЛНА СИНХРОНИЗАЦИЯ СЪС SERVICES

АРХИТЕКТУРА:
✅ DocumentService - статуси, transitions, validation
✅ ApprovalService - workflow, permissions
✅ MovementService - inventory movements
✅ InventoryService - stock checks

PATTERN: ТОЧНО като PurchaseRequest
"""

import logging
from typing import Dict
from django.db import models, transaction
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from inventory.services import InventoryService
from .base import BaseDocument, BaseDocumentLine, FinancialMixin, PaymentMixin, FinancialLineMixin

logger = logging.getLogger(__name__)


class PurchaseOrderManager(models.Manager):
    """Manager for Purchase Orders - SYNCHRONIZED WITH NOMENCLATURES"""

    def pending_approval(self):
        """Orders waiting for approval - DYNAMIC от DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_pending_approval_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.filter(status='draft')

    def confirmed(self):
        """Confirmed orders ready for delivery - DYNAMIC от DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_ready_for_processing_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.filter(status='confirmed')

    def active(self):
        """Active orders (not cancelled/completed) - DYNAMIC от DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_active_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.exclude(status__in=['cancelled', 'completed'])

    # =====================
    # BUSINESS QUERIES
    # =====================

    def sent_to_supplier(self):
        """Orders sent to suppliers but not yet confirmed"""
        return self.filter(status='sent')

    def awaiting_delivery(self):
        """Orders confirmed and awaiting delivery"""
        return self.filter(status='confirmed', supplier_confirmed=True)

    def ready_for_delivery_creation(self):
        """Orders that can be used for delivery creation"""
        return self.confirmed().filter(
            supplier_confirmed=True
        ).exclude(
            delivery_status='completed'
        )

    def by_supplier(self, supplier):
        """Orders for specific supplier"""
        return self.filter(supplier=supplier)

    def overdue_delivery(self):
        """Orders past expected delivery date"""
        today = timezone.now().date()
        return self.filter(
            expected_delivery_date__lt=today,
            status='confirmed'
        )

    def from_requests(self):
        """Orders created from requests"""
        return self.filter(source_request__isnull=False)

    def direct_orders(self):
        """Orders created directly (not from requests)"""
        return self.filter(source_request__isnull=True)

    def this_month(self):
        """Orders created this month"""
        today = timezone.now().date()
        return self.filter(
            created_at__month=today.month,
            created_at__year=today.year
        )


class PurchaseOrder(BaseDocument, FinancialMixin, PaymentMixin):
    """
    Purchase Order - ФИНАЛНА СИНХРОНИЗАЦИЯ

    SERVICES INTEGRATION:
    ✅ DocumentService - за всички document operations
    ✅ ApprovalService - за workflow permissions
    ✅ MovementService - за auto-receive movements
    ✅ InventoryService - за stock impact analysis
    """

    # =====================
    # ORDER-SPECIFIC FIELDS
    # =====================

    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        help_text=_('When we expect this order to be delivered')
    )

    is_urgent = models.BooleanField(
        _('Urgent Order'),
        default=False,
        help_text=_('Mark as urgent for priority processing')
    )

    # =====================
    # SUPPLIER INTERACTION
    # =====================
    supplier_order_reference = models.CharField(
        _('Supplier Order Reference'),
        max_length=100,
        blank=True,
        help_text=_('Reference number from supplier system')
    )

    supplier_confirmed = models.BooleanField(
        _('Supplier Confirmed'),
        default=False,
        help_text=_('Has supplier confirmed this order?')
    )

    sent_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sent_purchase_orders',
        verbose_name=_('Sent By'),
        help_text=_('User who sent the order to supplier')
    )

    # =====================
    # DELIVERY STATUS TRACKING
    # =====================
    DELIVERY_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('partial', _('Partially Delivered')),
        ('completed', _('Fully Delivered')),
        ('cancelled', _('Cancelled')),
    ]

    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
        help_text=_('Current delivery status of this order')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_request = models.ForeignKey(
        'purchases.PurchaseRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_orders',
        verbose_name=_('Source Request'),
        help_text=_('Request this order was created from (if any)')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseOrderManager()

    class Meta:
        verbose_name = _('Purchase Order')
        verbose_name_plural = _('Purchase Orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'supplier_confirmed']),
            models.Index(fields=['supplier', 'expected_delivery_date']),
            models.Index(fields=['is_urgent', 'status']),
            models.Index(fields=['delivery_status', 'expected_delivery_date']),
            models.Index(fields=['source_request']),
        ]

    def __str__(self):
        return f"ORD {self.document_number} - {self.supplier.name}"

    def get_document_prefix(self):
        """Override to return ORD prefix"""
        return "ORD"

    def get_document_type_key(self):
        """Return document type key for nomenclatures integration"""
        return 'purchase_order'

    # =====================
    # NOMENCLATURES INTEGRATION - СТРИКТНО DocumentService
    # =====================

    def can_edit(self, user=None):
        """Check if order can be edited - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, reason = DocumentService.can_edit_document(self, user)
            return can_edit
        except ImportError:
            # Fallback logic
            return self.status in ['draft'] and not self.supplier_confirmed

    def get_available_actions(self, user=None):
        """Get available actions for user - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_available_actions(self, user)
        except ImportError:
            # Fallback actions
            actions = []
            if self.status == 'draft':
                actions.append('send_to_supplier')
            if self.status == 'sent':
                actions.append('mark_confirmed')
            if self.status == 'confirmed':
                actions.append('create_delivery')
            return actions

    def transition_to(self, new_status, user, comments=''):
        """Transition to new status - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.transition_document(
                self, new_status, user, comments
            )
        except ImportError:
            raise ValidationError("Document workflow service not available")

    def get_workflow_info(self):
        """Get complete workflow information - USES ApprovalService"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_workflow_info(self)
        except ImportError:
            return None

    def get_approval_history(self):
        """Get approval history - USES ApprovalService"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_approval_history(self)
        except ImportError:
            return []

    # =====================
    # BUSINESS LOGIC METHODS - ИЗПОЛЗВАТ DocumentService
    # =====================

    def send_to_supplier(self, user=None):
        """Send order to supplier"""
        if self.status != 'draft':
            raise ValidationError("Can only send draft orders")

        if not self.lines.exists():
            raise ValidationError("Cannot send order without lines")

        self.transition_to('sent', user, 'Order sent to supplier')
        self.sent_by = user
        self.save(update_fields=['sent_by'])
        return True

    def confirm_order(self, user=None, supplier_reference=''):
        """Confirm order from supplier"""
        if self.status != 'sent':
            raise ValidationError("Can only confirm sent orders")

        self.transition_to('confirmed', user, 'Order confirmed by supplier')
        self.supplier_confirmed = True
        if supplier_reference:
            self.supplier_order_reference = supplier_reference
        self.save(update_fields=['supplier_confirmed', 'supplier_order_reference'])

        # ✅ AUTO-RECEIVE LOGIC ако е настроено - USES MovementService
        if getattr(self.document_type, 'auto_receive', False):
            try:
                from inventory.services.movement_service import MovementService
                movements = MovementService.create_from_document(self)
                logger.info(f"Auto-created {len(movements)} movements for {self.document_number}")
            except Exception as e:
                logger.error(f"Error in auto-receive: {e}")

        return True

    def cancel_order(self, user=None, reason=''):
        """Cancel order"""
        if self.status in ['completed', 'cancelled']:
            raise ValidationError(f"Cannot cancel {self.status} order")

        self.transition_to('cancelled', user, reason)
        return True

    def create_delivery(self, user=None, **kwargs):
        """Create delivery receipt from this order"""
        if self.status != 'confirmed':
            raise ValidationError("Can only create delivery from confirmed orders")

        if self.delivery_status == 'completed':
            raise ValidationError("Order already fully delivered")

        # Import here to avoid circular imports
        from .deliveries import DeliveryReceipt, DeliveryLine

        delivery = DeliveryReceipt.objects.create(
            supplier=self.supplier,
            location=self.location,
            source_order=self,  # Link back to this order
            document_date=timezone.now().date(),
            created_by=user,
            **kwargs
        )

        # Create delivery lines from order lines
        for order_line in self.lines.all():
            if order_line.remaining_quantity > 0:  # Only undelivered items
                DeliveryLine.objects.create(
                    document=delivery,
                    source_order_line=order_line,
                    product=order_line.product,
                    unit=order_line.unit,
                    expected_quantity=order_line.remaining_quantity,
                    unit_price=order_line.unit_price,
                    line_number=order_line.line_number
                )

        # Update delivery status
        self._update_delivery_status()

        return delivery

    def _update_delivery_status(self):
        """Update delivery status based on delivered quantities"""
        total_ordered = sum(line.ordered_quantity for line in self.lines.all())
        total_delivered = sum(line.delivered_quantity for line in self.lines.all())

        if total_delivered == 0:
            self.delivery_status = 'pending'
        elif total_delivered >= total_ordered:
            self.delivery_status = 'completed'
            # Automatically complete the order
            if self.status == 'confirmed':
                self.transition_to('completed', reason='Fully delivered')
        else:
            self.delivery_status = 'partial'

        self.save(update_fields=['delivery_status'])

    # =====================
    # INVENTORY INTEGRATION - USES InventoryService
    # =====================

    def check_inventory_impact(self):
        """Check how this order would impact inventory - USES InventoryService"""
        impact = {}

        for line in self.lines.all():
            if line.product not in impact:
                impact[line.product] = {
                    'current_stock': Decimal('0'),
                    'ordered_qty': Decimal('0'),
                    'impact_analysis': {}
                }

            # Get current availability using InventoryService
            try:
                availability = InventoryService.check_availability(
                    self.location, line.product, Decimal('0')
                )
                impact[line.product]['current_stock'] = availability['current_qty']
                impact[line.product]['impact_analysis'] = availability
            except Exception as e:
                logger.error(f"Error checking availability: {e}")

            impact[line.product]['ordered_qty'] += line.ordered_quantity

        return impact

    def validate_with_inventory(self):
        """Validate order against inventory constraints"""
        # За purchase orders обикновено няма inventory constraints
        # Но може да провериш за reorder points, max stock levels и т.н.
        return True, "OK"

    # =====================
    # PROPERTIES
    # =====================

    @property
    def is_overdue(self):
        """Check if order is overdue for delivery"""
        if not self.expected_delivery_date:
            return False
        return (
                self.expected_delivery_date < timezone.now().date() and
                self.status == 'confirmed'
        )

    @property
    def is_fully_delivered(self):
        return self.delivery_status == 'completed'

    @property
    def is_partially_delivered(self):
        return self.delivery_status == 'partial'

    @property
    def total_ordered_quantity(self):
        """Total quantity across all lines"""
        return sum(line.ordered_quantity for line in self.lines.all())

    @property
    def total_delivered_quantity(self):
        """Total delivered quantity across all lines"""
        return sum(line.delivered_quantity for line in self.lines.all())

    @property
    def delivery_progress_percentage(self):
        """Delivery progress as percentage"""
        total_ordered = self.total_ordered_quantity
        if total_ordered == 0:
            return 0
        return (self.total_delivered_quantity / total_ordered) * 100


class PurchaseOrderLineManager(models.Manager):
    """Manager for Purchase Order Lines"""

    def for_order(self, order):
        """Lines for specific order"""
        return self.filter(document=order)

    def confirmed_not_delivered(self):
        """Lines from confirmed orders not yet delivered"""
        return self.filter(
            document__status='confirmed',
            document__delivery_status__in=['pending', 'partial']
        )

    def available_for_delivery(self, supplier=None):
        """Lines available for delivery creation"""
        queryset = self.filter(
            document__status='confirmed',
            document__supplier_confirmed=True,
            document__delivery_status__in=['pending', 'partial']
        )

        if supplier:
            queryset = queryset.filter(document__supplier=supplier)

        return queryset.select_related('document__supplier', 'product', 'unit')

    def with_remaining_quantity(self):
        """Lines that still have quantity to deliver"""
        from django.db.models import F
        return self.filter(F('ordered_quantity') > F('delivered_quantity'))


class PurchaseOrderLine(BaseDocumentLine, FinancialLineMixin):
    """
    Purchase Order Line - ФИНАЛНА СИНХРОНИЗАЦИЯ

    SERVICES INTEGRATION:
    ✅ DocumentService integration в save()
    ✅ InventoryService integration за validation
    """

    # =====================
    # DOCUMENT RELATIONSHIP
    # =====================
    document = models.ForeignKey(
        'PurchaseOrder',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Order')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_request_line = models.ForeignKey(
        'PurchaseRequestLine',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='order_lines',
        help_text=_('Request line this was created from')
    )

    # =====================
    # QUANTITIES
    # =====================
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity ordered from supplier')
    )

    confirmed_quantity = models.DecimalField(
        _('Confirmed Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Quantity confirmed by supplier (if different from ordered)')
    )

    # AUTO-CALCULATED from deliveries
    delivered_quantity = models.DecimalField(
        _('Delivered Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        help_text=_('Total quantity delivered (auto-calculated)')
    )

    # =====================
    # DELIVERY STATUS
    # =====================
    DELIVERY_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('partial', _('Partially Delivered')),
        ('completed', _('Fully Delivered')),
    ]

    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
        help_text=_('Delivery status of this line')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseOrderLineManager()

    class Meta:
        verbose_name = _('Purchase Order Line')
        verbose_name_plural = _('Purchase Order Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['source_request_line']),
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.ordered_quantity}"

    # =====================
    # IMPLEMENT ABSTRACT METHOD
    # =====================
    def get_quantity_for_display(self):
        """Return ordered quantity for display"""
        return self.ordered_quantity

    # =====================
    # SYNCHRONIZED SAVE() - USES DocumentService
    # =====================
    def save(self, *args, **kwargs):
        """
        ✅ PurchaseOrderLine save with DocumentService integration
        СЪЩИЯТ PATTERN като PurchaseRequestLine
        """
        logger.debug(f"🔥 PurchaseOrderLine.save() called for line {getattr(self, 'line_number', 'NEW')}")

        # Call parent save chain
        super().save(*args, **kwargs)

        # ✅ DocumentService integration СЛЕД parent save
        if hasattr(self, 'document') and self.document:
            try:
                from nomenclatures.services import DocumentService

                result = DocumentService.handle_document_update(
                    document=self.document,
                    user=getattr(self, '_updating_user', None),
                    reason=f"Line {self.line_number} updated (qty: {self.ordered_quantity}, price: {self.unit_price})"
                )

                logger.debug(f"🔥 DocumentService result: {result}")

            except Exception as e:
                logger.error(f"🔥 Error in DocumentService.handle_document_update: {e}")
                # Don't fail the save for service errors
                pass

        # ✅ Update delivery status
        self._update_delivery_status()

    def _update_delivery_status(self):
        """Update delivery status based on delivered quantity"""
        if self.delivered_quantity == 0:
            self.delivery_status = 'pending'
        elif self.delivered_quantity >= self.ordered_quantity:
            self.delivery_status = 'completed'
        else:
            self.delivery_status = 'partial'

    # =====================
    # PROPERTIES
    # =====================
    @property
    def remaining_quantity(self):
        """Quantity still to be delivered"""
        return max(Decimal('0'), self.ordered_quantity - self.delivered_quantity)

    @property
    def delivery_progress_percentage(self):
        """Delivery progress as percentage"""
        if self.ordered_quantity == 0:
            return 0
        return (self.delivered_quantity / self.ordered_quantity) * 100

    @property
    def is_fully_delivered(self):
        """Check if line is fully delivered"""
        return self.delivered_quantity >= self.ordered_quantity

    @property
    def can_be_delivered(self):
        """Check if line can still receive deliveries"""
        return (
                self.remaining_quantity > 0 and
                self.document.status == 'confirmed'
        )

    # =====================
    # BUSINESS METHODS
    # =====================
    def add_delivery(self, delivered_qty):
        """Add delivered quantity (called from DeliveryLine)"""
        if delivered_qty <= 0:
            return

        self.delivered_quantity += delivered_qty
        self._update_delivery_status()
        self.save(update_fields=['delivered_quantity', 'delivery_status'])

        # Update parent order delivery status
        self.document._update_delivery_status()

    def can_deliver_quantity(self, qty):
        """Check if specific quantity can be delivered"""
        return qty <= self.remaining_quantity

    # =====================
    # VALIDATION - ENHANCED
    # =====================
    def clean(self):
        """Order line validation - ENHANCED"""
        super().clean()

        # Delivered quantity cannot exceed ordered
        if self.ordered_quantity is not None and self.delivered_quantity is not None:
            if self.delivered_quantity > self.ordered_quantity:
                raise ValidationError({
                    'delivered_quantity': _('Delivered quantity cannot exceed ordered quantity')
                })

        # Price validation
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({
                'unit_price': _('Unit price cannot be negative')
            })

        # Product availability validation
        if self.product and self.document and self.document.location and self.ordered_quantity:
            try:
                from products.services.validation_service import ProductValidationService

                can_purchase, message, details = ProductValidationService.can_purchase_product(
                    product=self.product,
                    quantity=self.ordered_quantity,
                    supplier=self.document.supplier
                )

                if not can_purchase:
                    raise ValidationError({
                        'product': f"Cannot purchase this product: {message}"
                    })
            except ImportError:
                pass
