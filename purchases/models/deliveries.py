# purchases/models/deliveries.py - FIXED WITH NEW ARCHITECTURE
from datetime import timedelta

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .base import BaseDocument, BaseDocumentLine, FinancialMixin, PaymentMixin, DeliveryMixin, FinancialLineMixin


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
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return self.filter(
            status='delivered',
            delivery_date__lte=cutoff_date
        )


class DeliveryReceipt(BaseDocument, FinancialMixin, PaymentMixin, DeliveryMixin):
    """
    Delivery Receipt - Доставки и получаване на стоки

    Логика: Използва всички mixin-и защото има:
    - Финансови данни (FinancialMixin)
    - Плащания (PaymentMixin)
    - Delivery информация (DeliveryMixin)
    """



    # =====================
    # ДОСТАВКА-СПЕЦИФИЧНИ ПОЛЕТА
    # =====================


    # CREATION TYPE
    CREATION_TYPE_CHOICES = [
        ('from_orders', _('From Purchase Orders')),
        ('direct', _('Direct Delivery')),
    ]

    creation_type = models.CharField(
        _('Creation Type'),
        max_length=20,
        choices=CREATION_TYPE_CHOICES,
        default='from_orders',
        help_text=_('How this delivery was created')
    )

    # DELIVERY SPECIFIC INFO
    delivery_note_number = models.CharField(
        _('Delivery Note Number'),
        max_length=50,
        blank=True,
        help_text=_('Supplier\'s delivery note number')
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

    vehicle_info = models.CharField(
        _('Vehicle Info'),
        max_length=100,
        blank=True,
        help_text=_('Vehicle license plate, type, etc.')
    )

    # RECEIVING PROCESS
    received_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='received_deliveries',
        verbose_name=_('Received By'),
        help_text=_('Who received this delivery')
    )

    received_at = models.DateTimeField(
        _('Received At'),
        null=True,
        blank=True,
        help_text=_('When delivery was received and checked')
    )

    processed_at = models.DateTimeField(
        _('Processed At'),
        null=True,
        blank=True,
        help_text=_('When delivery was fully processed')
    )

    processed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='processed_deliveries',
        verbose_name=_('Processed By'),
        help_text=_('Who processed this delivery')
    )

    # QUALITY CONTROL
    quality_checked = models.BooleanField(
        _('Quality Checked'),
        default=False,
        help_text=_('Whether quality control was performed')
    )

    quality_inspector = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quality_inspected_deliveries',
        verbose_name=_('Quality Inspector'),
        help_text=_('Who performed quality inspection')
    )

    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Whether delivery passed quality control')
    )

    has_quality_issues = models.BooleanField(
        _('Has Quality Issues'),
        default=False,
        help_text=_('Whether there are quality problems with this delivery')
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Quality control notes and observations')
    )

    # VARIANCES
    has_variances = models.BooleanField(
        _('Has Variances'),
        default=False,
        help_text=_('Whether there are quantity/price variances')
    )

    variance_notes = models.TextField(
        _('Variance Notes'),
        blank=True,
        help_text=_('Notes about variances found')
    )

    # SPECIAL HANDLING
    special_handling_notes = models.TextField(
        _('Special Handling Notes'),
        blank=True,
        help_text=_('Special handling requirements or observations')
    )

    # SOURCE TRACKING
    source_orders = models.ManyToManyField(
        'purchases.PurchaseOrder',
        blank=True,
        related_name='deliveries',
        verbose_name=_('Source Orders'),
        help_text=_('Purchase orders fulfilled by this delivery')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = DeliveryReceiptManager()

    class Meta:
        verbose_name = _('Delivery Receipt')
        verbose_name_plural = _('Delivery Receipts')
        ordering = ['-delivery_date', '-created_at']
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

    def get_document_prefix(self):
        """Override to return DEL prefix"""
        return "DEL"


    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_edited(self):
        return not self.is_final_status()

    def can_be_received(self):
        return 'received' in self.get_next_statuses() and self.lines.exists()

    def can_be_completed(self):
        next_statuses = self.get_next_statuses()
        return 'completed' in next_statuses or 'accepted' in next_statuses

    def can_be_cancelled(self):
        return not self.is_final_status()

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
        return not self.lines.filter(received_quantity=0).exists()

    @property
    def quality_issues_count(self):
        """Count of lines with quality issues"""
        return self.lines.filter(quality_approved=False).count()

    @property
    def variance_lines_count(self):
        """Count of lines with variances"""
        return self.lines.exclude(variance_quantity=0).count()

    def get_variance_summary(self):
        """Get summary of variances"""
        variance_lines = self.lines.exclude(variance_quantity=0)

        positive_variances = variance_lines.filter(variance_quantity__gt=0)
        negative_variances = variance_lines.filter(variance_quantity__lt=0)

        return {
            'total_variance_lines': variance_lines.count(),
            'positive_variances': positive_variances.count(),
            'negative_variances': negative_variances.count(),
            'total_positive_value': sum(
                line.variance_quantity * line.unit_price
                for line in positive_variances
            ),
            'total_negative_value': sum(
                line.variance_quantity * line.unit_price
                for line in negative_variances
            ),
        }


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
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )


class DeliveryLine(BaseDocumentLine, FinancialLineMixin):
    """
    Delivery Line - CLEAN VERSION

    ✅ received_quantity като primary
    ✅ expected_quantity (от order) за сравнение
    ✅ variance_quantity auto-calculated
    ✅ Quality control fields
    ✅ Batch tracking
    """

    # =====================
    # DOCUMENT RELATIONSHIP
    # =====================
    document = models.ForeignKey(
        'DeliveryReceipt',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Delivery Receipt')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_order_line = models.ForeignKey(
        'PurchaseOrderLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_lines',
        verbose_name=_('Source Order Line'),
        help_text=_('Order line this delivery fulfills')
    )

    # =====================
    # QUANTITIES
    # =====================
    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity actually received')
    )

    expected_quantity = models.DecimalField(
        _('Expected Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Expected quantity (from order or manual)')
    )

    # AUTO-CALCULATED
    variance_quantity = models.DecimalField(
        _('Variance'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        editable=False,  # Auto-calculated!
        help_text=_('received - expected (auto-calculated)')
    )

    # =====================
    # QUALITY CONTROL
    # =====================
    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Whether this item passed quality control')
    )

    QUALITY_ISSUE_CHOICES = [
        ('damaged', _('Damaged')),
        ('expired', _('Expired')),
        ('wrong_product', _('Wrong Product')),
        ('poor_quality', _('Poor Quality')),
        ('contaminated', _('Contaminated')),
        ('packaging', _('Packaging Issue')),
        ('temperature', _('Temperature Issue')),
        ('other', _('Other')),
    ]

    quality_issue_type = models.CharField(
        _('Quality Issue Type'),
        max_length=20,
        choices=QUALITY_ISSUE_CHOICES,
        blank=True,
        help_text=_('Type of quality issue (if any)')
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Quality control notes')
    )

    # =====================
    # BATCH/LOT TRACKING
    # =====================
    batch_number = models.CharField(
        _('Batch/Lot Number'),
        max_length=50,
        blank=True,
        db_index=True,  # Important for tracking
        help_text=_('Batch or lot number from supplier')
    )

    production_date = models.DateField(
        _('Production Date'),
        null=True,
        blank=True,
        help_text=_('When product was manufactured')
    )

    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        db_index=True,  # Important for queries
        help_text=_('Product expiry date')
    )

    # =====================
    # SPECIAL HANDLING
    # =====================
    temperature_at_receipt = models.DecimalField(
        _('Temperature (°C)'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Temperature when received (for cold chain)')
    )

    requires_special_storage = models.BooleanField(
        _('Requires Special Storage'),
        default=False,
        help_text=_('Needs special storage conditions')
    )

    storage_location = models.CharField(
        _('Storage Location'),
        max_length=50,
        blank=True,
        help_text=_('Where item was stored (rack/bin/zone)')
    )

    class Meta:
        verbose_name = _('Delivery Line')
        verbose_name_plural = _('Delivery Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['source_order_line']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['quality_approved']),
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.received_quantity}"

    # =====================
    # IMPLEMENT ABSTRACT METHOD
    # =====================

    def get_quantity_for_display(self):
        """Return received quantity for display"""
        return self.received_quantity

    # =====================
    # VALIDATION
    # =====================

    def clean(self):
        """Delivery line validation"""
        super().clean()

        # Received quantity validation
        if self.received_quantity <= 0:
            # Check if document allows negative (returns/corrections)
            if self.document and self.document.document_type:
                direction = getattr(self.document.document_type, 'inventory_direction', 'in')
                if direction == 'both':
                    # Allow negative for corrections
                    if self.received_quantity == 0:
                        raise ValidationError({
                            'received_quantity': _('Quantity cannot be zero')
                        })
                else:
                    # Normal deliveries - positive only
                    raise ValidationError({
                        'received_quantity': _('Received quantity must be greater than zero')
                    })

        # Quality validation
        if not self.quality_approved and not self.quality_issue_type:
            raise ValidationError({
                'quality_issue_type': _('Please specify quality issue type')
            })

        # Expiry validation
        if self.expiry_date and self.production_date:
            if self.expiry_date <= self.production_date:
                raise ValidationError({
                    'expiry_date': _('Expiry date must be after production date')
                })

        # Temperature validation for cold chain
        if self.temperature_at_receipt is not None:
            # Check product requirements
            if hasattr(self.product, 'max_temperature'):
                if self.temperature_at_receipt > self.product.max_temperature:
                    # Just warning, still allow saving
                    import warnings
                    warnings.warn(
                        f"Temperature {self.temperature_at_receipt}°C exceeds product max {self.product.max_temperature}°C"
                    )

    # =====================
    # SAVE WITH AUTO-CALCULATIONS
    # =====================

    def save(self, *args, **kwargs):
        """Enhanced save with auto-calculations"""

        # 1. Auto-populate expected from order line
        if self.source_order_line and not self.expected_quantity:
            self.expected_quantity = self.source_order_line.remaining_quantity

        # 2. Calculate variance
        if self.expected_quantity:
            self.variance_quantity = self.received_quantity - self.expected_quantity
        else:
            self.variance_quantity = Decimal('0.000')

        # 3. For FinancialLineMixin
        self.quantity = self.received_quantity

        # 4. Save
        is_new = not self.pk
        super().save(*args, **kwargs)

        # 5. After save - update order line delivery tracking
        if self.source_order_line:
            self.source_order_line.update_delivery_status()

    # =====================
    # PROPERTIES
    # =====================

    @property
    def is_from_order(self):
        """Check if line is from order"""
        return self.source_order_line is not None

    @property
    def is_direct_delivery(self):
        """Check if direct delivery (not from order)"""
        return self.source_order_line is None

    @property
    def has_variance(self):
        """Check if has variance"""
        return self.variance_quantity != 0

    @property
    def variance_type(self):
        """Get variance type"""
        if self.variance_quantity > 0:
            return 'over'
        elif self.variance_quantity < 0:
            return 'under'
        return 'exact'

    @property
    def variance_percentage(self):
        """Calculate variance percentage"""
        if not self.expected_quantity or self.expected_quantity == 0:
            return None
        return (self.variance_quantity / self.expected_quantity) * 100

    @property
    def variance_value(self):
        """Calculate monetary value of variance"""
        if hasattr(self, 'unit_price') and self.unit_price:
            return self.variance_quantity * self.unit_price
        return Decimal('0.00')

    @property
    def is_expired(self):
        """Check if expired"""
        if not self.expiry_date:
            return False
        return self.expiry_date <= timezone.now().date()

    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - timezone.now().date()
        return delta.days

    @property
    def expires_soon(self):
        """Check if expires within 30 days"""
        days = self.days_until_expiry
        return days is not None and days <= 30

    @property
    def effective_quantity(self):
        """Get usable quantity (considering quality)"""
        if self.quality_approved:
            return self.received_quantity
        return Decimal('0.000')

    @property
    def storage_info(self):
        """Get storage information summary"""
        info = []
        if self.storage_location:
            info.append(f"Location: {self.storage_location}")
        if self.temperature_at_receipt is not None:
            info.append(f"Temp: {self.temperature_at_receipt}°C")
        if self.requires_special_storage:
            info.append("Special storage required")
        return " | ".join(info) if info else "Standard storage"

    # =====================
    # METHODS
    # =====================

    def can_be_used(self):
        """Check if line can be used for inventory"""
        return (
                self.quality_approved and
                not self.is_expired and
                self.received_quantity > 0
        )

    def get_inventory_impact(self):
        """
        Get inventory impact of this line
        Returns: tuple (product, quantity, batch)
        """
        if not self.can_be_used():
            return None

        return {
            'product': self.product,
            'quantity': self.effective_quantity,
            'batch_number': self.batch_number,
            'expiry_date': self.expiry_date,
            'location': self.storage_location
        }

    def create_quality_issue(self, issue_type, notes=''):
        """Mark line with quality issue"""
        self.quality_approved = False
        self.quality_issue_type = issue_type
        self.quality_notes = notes
        self.save()

