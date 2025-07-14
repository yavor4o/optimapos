# purchases/models/orders.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocument, BaseDocumentLine
from .document_types import DocumentType


class PurchaseOrderManager(models.Manager):
    """Manager for Purchase Orders with specific queries"""

    def confirmed(self):
        """Confirmed orders ready for delivery"""
        return self.filter(status='confirmed')

    def sent_to_supplier(self):
        """Orders sent to suppliers but not yet confirmed"""
        return self.filter(status='sent')

    def awaiting_delivery(self):
        """Orders confirmed and awaiting delivery"""
        return self.filter(status='confirmed', supplier_confirmed=True)

    def ready_for_delivery_creation(self):
        """Orders that can be used for delivery creation"""
        return self.filter(
            status='confirmed',
            supplier_confirmed=True
        ).exclude(
            # Exclude fully delivered orders (all lines delivered)
            id__in=self._get_fully_delivered_order_ids()
        )

    def _get_fully_delivered_order_ids(self):
        """Helper to get IDs of orders that are fully delivered"""
        # This will be implemented when we have DeliveryLine model
        # For now return empty list
        return []

    def by_supplier(self, supplier):
        """Orders for specific supplier"""
        return self.filter(supplier=supplier)

    def for_delivery_on(self, date):
        """Orders expected for delivery on specific date"""
        return self.filter(expected_delivery_date=date, status='confirmed')

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


class PurchaseOrder(BaseDocument):
    """
    Purchase Order - Поръчки към доставчици

    Workflow: draft → sent → confirmed → (in_delivery) → completed

    Can be created from:
    1. PurchaseRequest (approved request conversion)
    2. Direct creation (verbal orders, phone orders, urgent purchases)

    Can be used for:
    1. Single delivery (1 order = 1 delivery)
    2. Multiple deliveries (partial deliveries)
    3. Multi-order delivery (multiple orders = 1 delivery)
    """

    # =====================
    # SOURCE TRACKING
    # =====================
    source_request = models.ForeignKey(
        'purchases.PurchaseRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name=_('Source Request'),
        help_text=_('Request this order was created from (if any)')
    )

    # =====================
    # ORDER CLASSIFICATION
    # =====================
    is_urgent = models.BooleanField(
        _('Urgent Order'),
        default=False,
        help_text=_('Whether this is an urgent/emergency order')
    )

    order_method = models.CharField(
        _('Order Method'),
        max_length=50,
        blank=True,
        help_text=_('How this order was placed (phone, email, system, etc.)')
    )

    # =====================
    # SUPPLIER INTERACTION
    # =====================
    order_reference = models.CharField(
        _('Order Reference'),
        max_length=100,
        blank=True,
        help_text=_('Internal reference number for this order')
    )

    supplier_confirmed = models.BooleanField(
        _('Supplier Confirmed'),
        default=False,
        help_text=_('Whether supplier has confirmed this order')
    )

    supplier_confirmed_date = models.DateField(
        _('Supplier Confirmed Date'),
        null=True,
        blank=True,
        help_text=_('When supplier confirmed the order')
    )

    supplier_order_reference = models.CharField(
        _('Supplier Order Reference'),
        max_length=100,
        blank=True,
        help_text=_('Supplier\'s reference number for this order')
    )

    # =====================
    # DELIVERY PLANNING
    # =====================
    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        help_text=_('When we expect to receive this order')
    )

    requested_delivery_date = models.DateField(
        _('Requested Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When we requested delivery from supplier')
    )

    delivery_instructions = models.TextField(
        _('Delivery Instructions'),
        blank=True,
        help_text=_('Special instructions for delivery')
    )

    # =====================
    # CONTACT INFORMATION
    # =====================
    supplier_contact_person = models.CharField(
        _('Supplier Contact Person'),
        max_length=100,
        blank=True,
        help_text=_('Contact person at supplier for this order')
    )

    supplier_contact_phone = models.CharField(
        _('Supplier Contact Phone'),
        max_length=20,
        blank=True,
        help_text=_('Phone number for order-related contact')
    )

    supplier_contact_email = models.EmailField(
        _('Supplier Contact Email'),
        blank=True,
        help_text=_('Email for order-related contact')
    )

    # =====================
    # TERMS AND CONDITIONS
    # =====================
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=100,
        blank=True,
        help_text=_('Payment terms for this order')
    )

    delivery_terms = models.CharField(
        _('Delivery Terms'),
        max_length=100,
        blank=True,
        help_text=_('Delivery terms (FOB, CIF, etc.)')
    )

    special_conditions = models.TextField(
        _('Special Conditions'),
        blank=True,
        help_text=_('Any special conditions or requirements')
    )

    # =====================
    # ORDER TRACKING
    # =====================
    sent_to_supplier_at = models.DateTimeField(
        _('Sent to Supplier At'),
        null=True,
        blank=True,
        help_text=_('When order was sent to supplier')
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
    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=[
            ('pending', _('Pending')),
            ('partial', _('Partially Delivered')),
            ('completed', _('Fully Delivered')),
            ('cancelled', _('Cancelled')),
        ],
        default='pending',
        help_text=_('Current delivery status of this order')
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

    # =====================
    # DOCUMENT TYPE SETUP
    # =====================
    def save(self, *args, **kwargs):
        # Auto-set document type to ORD if not set
        if not hasattr(self, 'document_type') or not self.document_type:
            self.document_type = DocumentType.get_by_code('ORD')

        super().save(*args, **kwargs)

    def get_document_prefix(self):
        """Override to return ORD prefix"""
        return "ORD"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation for orders"""
        super().clean()

        # Supplier confirmation validation
        if self.supplier_confirmed and not self.supplier_confirmed_date:
            self.supplier_confirmed_date = timezone.now().date()

        # Expected delivery date should be today or future
        if self.expected_delivery_date < timezone.now().date():
            raise ValidationError({
                'expected_delivery_date': _('Expected delivery date cannot be in the past')
            })

        # Order type validation
        if self.source_request and not self.is_from_request:
            # This is automatically handled - no validation needed
            pass

    # =====================
    # WORKFLOW METHODS
    # =====================
    def send_to_supplier(self, user=None):
        """Send order to supplier"""
        if self.status != self.DRAFT:
            raise ValidationError("Can only send draft orders")

        if not self.lines.exists():
            raise ValidationError("Cannot send order without lines")

        self.status = 'sent'
        self.sent_to_supplier_at = timezone.now()
        self.sent_by = user
        self.updated_by = user
        self.save()

        return True

    def confirm_by_supplier(self, user=None, supplier_reference=''):
        """Mark order as confirmed by supplier"""
        if self.status not in ['sent', self.DRAFT]:
            raise ValidationError("Can only confirm sent or draft orders")

        self.status = 'confirmed'
        self.supplier_confirmed = True
        self.supplier_confirmed_date = timezone.now().date()
        if supplier_reference:
            self.supplier_order_reference = supplier_reference
        self.updated_by = user
        self.save()

        return True

    def mark_as_delivered(self, user=None):
        """Mark order as fully delivered"""
        self.delivery_status = 'completed'
        self.status = 'received'  # Final status
        self.updated_by = user
        self.save()

        return True

    def mark_as_partially_delivered(self, user=None):
        """Mark order as partially delivered"""
        self.delivery_status = 'partial'
        self.updated_by = user
        self.save()

        return True

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_sent(self):
        """Check if order can be sent to supplier"""
        return (
                self.status == self.DRAFT and
                self.lines.exists()
        )

    def can_be_confirmed(self):
        """Check if order can be confirmed"""
        return self.status in ['sent', self.DRAFT]

    def can_be_used_for_delivery(self):
        """Check if order can be used for delivery creation"""
        return (
                self.status == 'confirmed' and
                self.supplier_confirmed and
                self.delivery_status in ['pending', 'partial']
        )

    def can_be_edited(self):
        """Override parent method"""
        return self.status in [self.DRAFT]

    def can_be_cancelled(self):
        """Override parent method"""
        return self.status in [self.DRAFT, 'sent']

    # =====================
    # DELIVERY TRACKING
    # =====================
    def get_delivery_summary(self):
        """Get summary of deliveries for this order"""
        # This will be implemented when we have DeliveryLine model
        # For now return basic info
        return {
            'total_lines': self.lines.count(),
            'delivered_lines': 0,  # TODO: Calculate from deliveries
            'pending_lines': self.lines.count(),
            'delivery_percentage': 0,
        }

    def update_delivery_status(self):
        """Update delivery status based on actual deliveries"""
        # TODO: Implement when we have DeliveryLine model
        # This will calculate:
        # - pending: No lines delivered
        # - partial: Some lines delivered
        # - completed: All lines delivered
        pass

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_from_request(self):
        return self.source_request is not None

    @property
    def is_direct_order(self):
        return self.source_request is None

    @property
    def is_confirmed_by_supplier(self):
        return self.supplier_confirmed

    @property
    def is_overdue_delivery(self):
        """Check if delivery is overdue"""
        return (
                self.expected_delivery_date < timezone.now().date() and
                self.delivery_status != 'completed'
        )

    @property
    def days_until_delivery(self):
        """Days until expected delivery"""
        delta = self.expected_delivery_date - timezone.now().date()
        return delta.days

    @property
    def is_fully_delivered(self):
        return self.delivery_status == 'completed'

    @property
    def is_partially_delivered(self):
        return self.delivery_status == 'partial'


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

        return queryset.select_related(
            'document__supplier',
            'product',
            'unit'
        )


class PurchaseOrderLine(BaseDocumentLine):
    """
    Purchase Order Line - Редове на поръчка

    Contains ordered products with confirmed quantities and prices
    """

    # =====================
    # FOREIGN KEY TO PARENT
    # =====================
    document = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Order')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_request_line = models.ForeignKey(
        'purchases.PurchaseRequestLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_lines',
        verbose_name=_('Source Request Line'),
        help_text=_('Request line this order line was created from (if any)')
    )

    # =====================
    # ORDER-SPECIFIC FIELDS
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

    confirmed_price = models.DecimalField(
        _('Confirmed Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Price confirmed by supplier (if different from quoted)')
    )

    confirmed_delivery_date = models.DateField(
        _('Confirmed Delivery Date'),
        null=True,
        blank=True,
        help_text=_('Delivery date confirmed by supplier')
    )

    # =====================
    # SUPPLIER INFORMATION
    # =====================
    supplier_product_code = models.CharField(
        _('Supplier Product Code'),
        max_length=50,
        blank=True,
        help_text=_('Supplier\'s code for this product')
    )

    supplier_product_name = models.CharField(
        _('Supplier Product Name'),
        max_length=200,
        blank=True,
        help_text=_('Supplier\'s name for this product')
    )

    # =====================
    # DELIVERY TRACKING
    # =====================
    delivery_status = models.CharField(
        _('Line Delivery Status'),
        max_length=20,
        choices=[
            ('pending', _('Pending')),
            ('partial', _('Partially Delivered')),
            ('completed', _('Fully Delivered')),
            ('cancelled', _('Cancelled')),
        ],
        default='pending',
        help_text=_('Delivery status of this specific line')
    )

    delivered_quantity = models.DecimalField(
        _('Delivered Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Total quantity delivered so far')
    )

    remaining_quantity = models.DecimalField(
        _('Remaining Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Quantity still pending delivery')
    )

    # =====================
    # SPECIAL REQUIREMENTS
    # =====================
    special_instructions = models.TextField(
        _('Special Instructions'),
        blank=True,
        help_text=_('Special handling or delivery instructions for this line')
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
            models.Index(fields=['source_request_line']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation for order lines"""
        super().clean()

        # Set ordered_quantity from quantity if not set
        if not self.ordered_quantity and self.quantity:
            self.ordered_quantity = self.quantity

        # Ensure ordered_quantity is set
        if not self.ordered_quantity and self.quantity:
            self.ordered_quantity = self.quantity

        # Set quantity from ordered_quantity if not set
        if not self.quantity and self.ordered_quantity:
            self.quantity = self.ordered_quantity

    def save(self, *args, **kwargs):
        """Enhanced save with delivery calculations"""
        # Calculate remaining quantity
        if self.ordered_quantity and self.delivered_quantity:
            self.remaining_quantity = self.ordered_quantity - self.delivered_quantity
        else:
            self.remaining_quantity = self.ordered_quantity or Decimal('0.000')

        # Update delivery status based on quantities
        self._update_delivery_status()

        super().save(*args, **kwargs)

    def _update_delivery_status(self):
        """Update delivery status based on delivered vs ordered quantities"""
        if not self.ordered_quantity:
            return

        if self.delivered_quantity >= self.ordered_quantity:
            self.delivery_status = 'completed'
        elif self.delivered_quantity > 0:
            self.delivery_status = 'partial'
        else:
            self.delivery_status = 'pending'

    # =====================
    # DELIVERY TRACKING METHODS
    # =====================
    def add_delivery(self, quantity, delivery_line=None):
        """Add delivered quantity to this line"""
        if quantity <= 0:
            raise ValidationError("Delivery quantity must be positive")

        if self.delivered_quantity + quantity > self.ordered_quantity:
            raise ValidationError("Cannot deliver more than ordered quantity")

        self.delivered_quantity += quantity
        self.save()

        return True

    def get_deliverable_quantity(self):
        """Get quantity that can still be delivered"""
        return self.remaining_quantity

    def is_fully_delivered(self):
        """Check if this line is fully delivered"""
        return self.delivery_status == 'completed'

    def is_partially_delivered(self):
        """Check if this line is partially delivered"""
        return self.delivery_status == 'partial'

    def can_be_delivered(self):
        """Check if this line can still receive deliveries"""
        return self.remaining_quantity > 0

    # =====================
    # PROPERTIES
    # =====================
    @property
    def delivery_percentage(self):
        """Calculate delivery completion percentage"""
        if not self.ordered_quantity or self.ordered_quantity == 0:
            return 0

        return (self.delivered_quantity / self.ordered_quantity) * 100

    @property
    def is_overdue(self):
        """Check if delivery is overdue"""
        if not self.confirmed_delivery_date:
            return self.document.is_overdue_delivery

        return (
                self.confirmed_delivery_date < timezone.now().date() and
                not self.is_fully_delivered()
        )

    @property
    def effective_quantity(self):
        """Get the effective quantity (confirmed or ordered)"""
        return self.confirmed_quantity or self.ordered_quantity

    @property
    def effective_price(self):
        """Get the effective price (confirmed or original)"""
        return self.confirmed_price or self.unit_price

    @property
    def variance_quantity(self):
        """Calculate quantity variance (confirmed vs ordered)"""
        if self.confirmed_quantity and self.ordered_quantity:
            return self.confirmed_quantity - self.ordered_quantity
        return Decimal('0.000')

    @property
    def variance_price(self):
        """Calculate price variance (confirmed vs original)"""
        if self.confirmed_price and self.unit_price:
            return self.confirmed_price - self.unit_price
        return Decimal('0.0000')