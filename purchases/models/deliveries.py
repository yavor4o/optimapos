# purchases/models/deliveries.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocument, BaseDocumentLine
from .document_types import DocumentType


class DeliveryReceiptManager(models.Manager):
    """Manager for Delivery Receipts with specific queries"""

    def received(self):
        """Deliveries that have been received and processed"""
        return self.filter(status='received')

    def pending_processing(self):
        """Deliveries received but not yet processed"""
        return self.filter(status='delivered')

    def with_quality_issues(self):
        """Deliveries with quality control issues"""
        return self.filter(has_quality_issues=True)

    def from_orders(self):
        """Deliveries created from purchase orders"""
        return self.filter(source_orders__isnull=False).distinct()

    def direct_deliveries(self):
        """Direct deliveries (not from orders)"""
        return self.filter(source_orders__isnull=True)

    def for_supplier(self, supplier):
        """Deliveries from specific supplier"""
        return self.filter(supplier=supplier)

    def today(self):
        """Deliveries for today"""
        today = timezone.now().date()
        return self.filter(delivery_date=today)

    def overdue_processing(self, days=1):
        """Deliveries received but not processed within timeframe"""
        cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
        return self.filter(
            status='delivered',
            delivery_date__lte=cutoff_date
        )


class DeliveryReceipt(BaseDocument):
    """
    Delivery Receipt - Доставки и получаване на стоки

    Workflow: draft → delivered → received → completed

    Can be created from:
    1. Purchase Orders (single or multiple)
    2. Direct delivery (no orders - if allowed in settings)

    Handles:
    - Multi-order consolidation (one delivery from multiple orders)
    - Direct deliveries (supplier brings goods without prior order)
    - Quality control and inspection
    - Batch tracking and expiry dates
    - Variance reporting (ordered vs received)
    """

    # =====================
    # SOURCE TRACKING
    # =====================
    source_orders = models.ManyToManyField(
        'purchases.PurchaseOrder',
        blank=True,
        related_name='deliveries',
        verbose_name=_('Source Orders'),
        help_text=_('Orders this delivery is based on (if any)')
    )

    # =====================
    # DELIVERY CLASSIFICATION
    # =====================
    CREATION_TYPE_CHOICES = [
        ('from_orders', _('From Orders')),  # Created from one or more orders
        ('direct', _('Direct Delivery')),  # Direct delivery without orders
        ('mixed', _('Mixed')),  # Orders + additional items
    ]

    creation_type = models.CharField(
        _('Creation Type'),
        max_length=20,
        choices=CREATION_TYPE_CHOICES,
        help_text=_('How this delivery was created')
    )

    # =====================
    # DELIVERY INFORMATION
    # =====================
    delivery_note_number = models.CharField(
        _('Delivery Note Number'),
        max_length=100,
        blank=True,
        help_text=_('Supplier\'s delivery note/dispatch number')
    )

    vehicle_info = models.CharField(
        _('Vehicle Information'),
        max_length=100,
        blank=True,
        help_text=_('Delivery vehicle details (license plate, etc.)')
    )

    driver_name = models.CharField(
        _('Driver Name'),
        max_length=100,
        blank=True,
        help_text=_('Name of delivery driver')
    )

    driver_phone = models.CharField(
        _('Driver Phone'),
        max_length=20,
        blank=True,
        help_text=_('Driver contact number')
    )

    # =====================
    # RECEIVING PROCESS
    # =====================
    received_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='received_deliveries',
        verbose_name=_('Received By'),
        help_text=_('User who received and processed this delivery')
    )

    received_at = models.DateTimeField(
        _('Received At'),
        null=True,
        blank=True,
        help_text=_('When the delivery was physically received')
    )

    processed_at = models.DateTimeField(
        _('Processed At'),
        null=True,
        blank=True,
        help_text=_('When the delivery was fully processed in system')
    )

    # =====================
    # QUALITY CONTROL
    # =====================
    quality_checked = models.BooleanField(
        _('Quality Checked'),
        default=False,
        help_text=_('Whether quality control has been performed')
    )

    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Overall quality approval status')
    )

    has_quality_issues = models.BooleanField(
        _('Has Quality Issues'),
        default=False,
        help_text=_('Whether any items failed quality control')
    )

    quality_inspector = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inspected_deliveries',
        verbose_name=_('Quality Inspector'),
        help_text=_('User who performed quality inspection')
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Quality control notes and observations')
    )

    # =====================
    # VARIANCE TRACKING
    # =====================
    has_variances = models.BooleanField(
        _('Has Variances'),
        default=False,
        help_text=_('Whether there are differences between ordered and received')
    )

    variance_notes = models.TextField(
        _('Variance Notes'),
        blank=True,
        help_text=_('Explanation of variances between ordered and received')
    )

    # =====================
    # FINANCIAL TRACKING
    # =====================
    supplier_invoice_reference = models.CharField(
        _('Supplier Invoice Reference'),
        max_length=100,
        blank=True,
        help_text=_('Reference to supplier invoice (for finance app integration)')
    )

    has_supplier_invoice = models.BooleanField(
        _('Has Supplier Invoice'),
        default=False,
        help_text=_('Whether this delivery came with supplier invoice')
    )

    # =====================
    # SPECIAL HANDLING
    # =====================
    requires_cold_storage = models.BooleanField(
        _('Requires Cold Storage'),
        default=False,
        help_text=_('Whether items require refrigerated storage')
    )

    is_urgent_delivery = models.BooleanField(
        _('Urgent Delivery'),
        default=False,
        help_text=_('Whether this is an urgent/priority delivery')
    )

    special_handling_notes = models.TextField(
        _('Special Handling Notes'),
        blank=True,
        help_text=_('Special handling requirements or notes')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = DeliveryReceiptManager()

    class Meta:
        verbose_name = _('Delivery Receipt')
        verbose_name_plural = _('Delivery Receipts')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'delivery_date']),
            models.Index(fields=['supplier', 'delivery_date']),
            models.Index(fields=['creation_type', 'status']),
            models.Index(fields=['has_quality_issues', 'quality_checked']),
            models.Index(fields=['has_variances', 'status']),
            models.Index(fields=['received_by', '-received_at']),
        ]

    def __str__(self):
        return f"DEL {self.document_number} - {self.supplier.name}"

    # =====================
    # DOCUMENT TYPE SETUP
    # =====================
    def save(self, *args, **kwargs):
        # Auto-set document type to DEL if not set
        if not hasattr(self, 'document_type') or not self.document_type:
            self.document_type = DocumentType.get_by_code('DEL')

        # Auto-determine creation type if not set
        if not self.pk and not self.creation_type:
            self.creation_type = 'direct'  # Default for new deliveries

        super().save(*args, **kwargs)

    def get_document_prefix(self):
        """Override to return DEL prefix"""
        return "DEL"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation for deliveries"""
        super().clean()

        # Creation type validation based on source orders
        if self.creation_type == 'from_orders':
            if not self.source_orders.exists():
                raise ValidationError({
                    'source_orders': _('Source orders are required for deliveries created from orders')
                })

        elif self.creation_type == 'direct':
            # Check if direct deliveries are allowed (this will integrate with core settings)
            # For now, we'll allow them
            pass

        # Quality control validation
        if self.quality_checked and not self.quality_inspector:
            raise ValidationError({
                'quality_inspector': _('Quality inspector is required when quality check is performed')
            })

        # Received validation
        if self.status == 'received':
            if not self.received_at:
                self.received_at = timezone.now()
            if not self.received_by:
                raise ValidationError({
                    'received_by': _('Received by is required when status is received')
                })

    # =====================
    # WORKFLOW METHODS
    # =====================
    def mark_as_delivered(self, user=None):
        """Mark delivery as delivered (arrived at location)"""
        if self.status not in [self.DRAFT]:
            raise ValidationError("Can only mark draft deliveries as delivered")

        self.status = 'delivered'
        self.delivery_date = timezone.now().date()
        self.updated_by = user
        self.save()

        return True

    def receive_delivery(self, user, quality_check=True):
        """Receive and process the delivery"""
        if self.status != 'delivered':
            raise ValidationError("Can only receive delivered items")

        if not self.lines.exists():
            raise ValidationError("Cannot receive delivery without lines")

        self.status = 'received'
        self.received_by = user
        self.received_at = timezone.now()

        if quality_check:
            self.quality_checked = True
            self.quality_inspector = user
            # Check if any lines have quality issues
            self.has_quality_issues = self.lines.filter(quality_approved=False).exists()
            self.quality_approved = not self.has_quality_issues

        # Check for variances
        self.has_variances = self.lines.filter(
            models.Q(variance_quantity__gt=0) | models.Q(variance_quantity__lt=0)
        ).exists()

        self.updated_by = user
        self.save()

        # Update stock levels and product costs
        self._update_inventory()
        self._update_product_costs()

        # Update source order delivery status
        self._update_source_orders()

        return True

    def complete_processing(self, user=None):
        """Complete the delivery processing"""
        if self.status != 'received':
            raise ValidationError("Can only complete received deliveries")

        self.status = 'completed'
        self.processed_at = timezone.now()
        self.updated_by = user
        self.save()

        return True

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_received(self):
        """Check if delivery can be received"""
        return (
                self.status == 'delivered' and
                self.lines.exists()
        )

    def can_be_completed(self):
        """Check if delivery processing can be completed"""
        return self.status == 'received'

    def can_be_edited(self):
        """Override parent method"""
        return self.status in [self.DRAFT, 'delivered']

    def can_be_cancelled(self):
        """Override parent method"""
        return self.status in [self.DRAFT, 'delivered']

    # =====================
    # SOURCE ORDER MANAGEMENT
    # =====================
    def add_source_orders(self, orders):
        """Add orders as sources for this delivery"""
        if not isinstance(orders, list):
            orders = [orders]

        for order in orders:
            if not order.can_be_used_for_delivery():
                raise ValidationError(f"Order {order.document_number} cannot be used for delivery")

        self.source_orders.add(*orders)

        # Update creation type
        if self.source_orders.exists() and self.creation_type == 'direct':
            self.creation_type = 'from_orders'
            self.save()

    def copy_lines_from_orders(self):
        """Copy lines from source orders to this delivery"""
        if not self.source_orders.exists():
            return

        line_number = 1
        for order in self.source_orders.all():
            for order_line in order.lines.all():
                if order_line.can_be_delivered():
                    DeliveryLine.objects.create(
                        document=self,
                        line_number=line_number,
                        source_order_line=order_line,
                        product=order_line.product,
                        quantity=order_line.get_deliverable_quantity(),
                        ordered_quantity=order_line.effective_quantity,
                        unit=order_line.unit,
                        unit_price=order_line.effective_price,
                        discount_percent=order_line.discount_percent,
                        # Copy other relevant fields
                    )
                    line_number += 1

        # Recalculate totals
        self.recalculate_totals()

    # =====================
    # VARIANCE ANALYSIS
    # =====================
    def get_variance_summary(self):
        """Get summary of variances in this delivery"""
        if not self.lines.exists():
            return None

        lines_with_variances = self.lines.exclude(variance_quantity=0)

        return {
            'total_lines': self.lines.count(),
            'lines_with_variances': lines_with_variances.count(),
            'variance_percentage': (lines_with_variances.count() / self.lines.count()) * 100,
            'total_variance_value': sum(
                line.variance_quantity * line.unit_price
                for line in lines_with_variances
            ),
            'positive_variances': lines_with_variances.filter(variance_quantity__gt=0).count(),
            'negative_variances': lines_with_variances.filter(variance_quantity__lt=0).count(),
        }

    # =====================
    # INTEGRATION METHODS
    # =====================
    def _update_inventory(self):
        """Update inventory levels based on received quantities"""
        # This will integrate with inventory app
        # For now, placeholder
        for line in self.lines.filter(quality_approved=True):
            # Create inventory movement
            # Update product stock levels
            pass

    def _update_product_costs(self):
        """Update product costs based on received prices"""
        # This will update product.last_purchase_cost and current_avg_cost
        for line in self.lines.filter(quality_approved=True):
            product = line.product
            if line.unit_price > 0:
                product.last_purchase_cost = line.unit_price
                # Update average cost calculation
                # product.update_average_cost(line.unit_price, line.quantity)
                product.save()

    def _update_source_orders(self):
        """Update delivery status of source orders"""
        for order in self.source_orders.all():
            # Update order line delivery quantities
            for order_line in order.lines.all():
                delivery_lines = self.lines.filter(source_order_line=order_line)
                total_delivered = sum(dl.quantity for dl in delivery_lines)
                order_line.add_delivery(total_delivered)

            # Update order delivery status
            order.update_delivery_status()

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_from_orders(self):
        return self.source_orders.exists()

    @property
    def is_direct_delivery(self):
        return not self.source_orders.exists()

    @property
    def source_orders_count(self):
        return self.source_orders.count()

    @property
    def has_received_all_lines(self):
        """Check if all lines have been received"""
        return not self.lines.filter(quantity=0).exists()

    @property
    def quality_issues_count(self):
        """Count of lines with quality issues"""
        return self.lines.filter(quality_approved=False).count()

    @property
    def variance_lines_count(self):
        """Count of lines with variances"""
        return self.lines.exclude(variance_quantity=0).count()


class DeliveryLineManager(models.Manager):
    """Manager for Delivery Lines"""

    def with_variances(self):
        """Lines with quantity variances"""
        return self.exclude(variance_quantity=0)

    def with_quality_issues(self):
        """Lines that failed quality control"""
        return self.filter(quality_approved=False)

    def from_orders(self):
        """Lines that came from order lines"""
        return self.filter(source_order_line__isnull=False)

    def direct_items(self):
        """Lines that are direct additions (not from orders)"""
        return self.filter(source_order_line__isnull=True)

    def expiring_soon(self, days=30):
        """Lines with products expiring soon"""
        cutoff_date = timezone.now().date() + timezone.timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )


class DeliveryLine(BaseDocumentLine):
    """
    Delivery Line - Редове на доставка

    Contains received products with actual quantities, quality status, and variance tracking
    """

    # =====================
    # FOREIGN KEY TO PARENT
    # =====================
    document = models.ForeignKey(
        DeliveryReceipt,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Delivery Receipt')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_order_line = models.ForeignKey(
        'purchases.PurchaseOrderLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_lines',
        verbose_name=_('Source Order Line'),
        help_text=_('Order line this delivery line was created from (if any)')
    )

    # =====================
    # QUANTITY TRACKING
    # =====================
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Original ordered quantity (if from order)')
    )

    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Actually received quantity')
    )

    variance_quantity = models.DecimalField(
        _('Variance Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Difference between ordered and received (received - ordered)')
    )

    # =====================
    # QUALITY CONTROL
    # =====================
    quality_checked_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quality_checked_lines',
        verbose_name=_('Quality Checked By'),
        help_text=_('User who performed quality check on this line')
    )

    quality_issue_type = models.CharField(
        _('Quality Issue Type'),
        max_length=50,
        blank=True,
        choices=[
            ('damaged', _('Damaged')),
            ('expired', _('Expired')),
            ('wrong_product', _('Wrong Product')),
            ('poor_quality', _('Poor Quality')),
            ('packaging_issue', _('Packaging Issue')),
            ('contaminated', _('Contaminated')),
            ('other', _('Other')),
        ],
        help_text=_('Type of quality issue if any')
    )

    rejection_reason = models.TextField(
        _('Rejection Reason'),
        blank=True,
        help_text=_('Detailed reason for rejecting this line')
    )

    # =====================
    # STORAGE AND HANDLING
    # =====================
    storage_location = models.CharField(
        _('Storage Location'),
        max_length=100,
        blank=True,
        help_text=_('Where this item was stored after receiving')
    )

    requires_special_handling = models.BooleanField(
        _('Requires Special Handling'),
        default=False,
        help_text=_('Whether this item needs special handling')
    )

    temperature_at_receipt = models.DecimalField(
        _('Temperature at Receipt'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Temperature when received (for cold chain tracking)')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = DeliveryLineManager()

    class Meta:
        verbose_name = _('Delivery Line')
        verbose_name_plural = _('Delivery Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product', 'quality_approved']),
            models.Index(fields=['source_order_line']),
            models.Index(fields=['quality_approved', 'batch_number']),
            models.Index(fields=['expiry_date', 'quality_approved']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation for delivery lines"""
        super().clean()

        # Set quantity from received_quantity
        if self.received_quantity and not self.quantity:
            self.quantity = self.received_quantity

        # Quality issue validation
        if not self.quality_approved and not self.quality_issue_type:
            raise ValidationError({
                'quality_issue_type': _('Quality issue type is required when quality is not approved')
            })

        # Variance validation
        if self.ordered_quantity and self.received_quantity:
            calculated_variance = self.received_quantity - self.ordered_quantity
            if abs(self.variance_quantity - calculated_variance) > Decimal('0.001'):
                self.variance_quantity = calculated_variance

    def save(self, *args, **kwargs):
        """Enhanced save with variance calculation"""
        # Calculate variance if we have both quantities
        if self.ordered_quantity and self.received_quantity:
            self.variance_quantity = self.received_quantity - self.ordered_quantity

        # Set quantity to received_quantity for base calculations
        if self.received_quantity and not self.quantity:
            self.quantity = self.received_quantity

        super().save(*args, **kwargs)

    # =====================
    # QUALITY CONTROL METHODS
    # =====================
    def approve_quality(self, user, notes=''):
        """Approve quality for this line"""
        self.quality_approved = True
        self.quality_checked_by = user
        if notes:
            self.quality_notes = notes
        self.save()

    def reject_quality(self, user, issue_type, reason):
        """Reject quality for this line"""
        self.quality_approved = False
        self.quality_checked_by = user
        self.quality_issue_type = issue_type
        self.rejection_reason = reason
        self.save()

    # =====================
    # VARIANCE ANALYSIS
    # =====================
    def get_variance_percentage(self):
        """Calculate variance as percentage of ordered quantity"""
        if not self.ordered_quantity or self.ordered_quantity == 0:
            return None

        return (self.variance_quantity / self.ordered_quantity) * 100

    def is_over_received(self):
        """Check if more was received than ordered"""
        return self.variance_quantity > 0

    def is_under_received(self):
        """Check if less was received than ordered"""
        return self.variance_quantity < 0

    def has_significant_variance(self, tolerance_percent=5):
        """Check if variance exceeds tolerance threshold"""
        variance_percent = self.get_variance_percentage()
        if variance_percent is None:
            return False

        return abs(variance_percent) > tolerance_percent

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_from_order(self):
        return self.source_order_line is not None

    @property
    def is_direct_item(self):
        return self.source_order_line is None

    @property
    def has_variance(self):
        return self.variance_quantity != 0

    @property
    def variance_value(self):
        """Calculate monetary value of variance"""
        if self.variance_quantity and self.unit_price:
            return self.variance_quantity * self.unit_price
        return Decimal('0.00')

    @property
    def is_cold_chain_item(self):
        """Check if this is a cold chain item"""
        return self.temperature_at_receipt is not None

    @property
    def current_stock_display(self):
        """Override to show current stock after this delivery"""
        base_stock = super().current_stock_display
        if self.quality_approved and self.received_quantity:
            return base_stock + self.received_quantity
        return base_stock