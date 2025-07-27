# purchases/models/deliveries.py - FIXED WITH NEW ARCHITECTURE
from datetime import timedelta

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .base import BaseDocument, BaseDocumentLine, FinancialMixin, PaymentMixin, DeliveryMixin, FinancialLineMixin, \
    SmartDocumentTypeMixin


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


class DeliveryReceipt(SmartDocumentTypeMixin,BaseDocument, FinancialMixin, PaymentMixin, DeliveryMixin):
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
        cutoff_date = timezone.now().date() + timezone.timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )


class DeliveryLine(BaseDocumentLine, FinancialLineMixin):
    """
    Delivery Line - Ред на доставка

    Логика: Използва FinancialLineMixin защото има финансови данни.
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
        help_text=_('Order line this delivery line fulfills (if any)')
    )

    # =====================
    # DELIVERY-SPECIFIC FIELDS
    # =====================
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Quantity that was originally ordered')
    )

    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity actually received')
    )

    variance_quantity = models.DecimalField(
        _('Variance Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Difference between ordered and received (received - ordered)')
    )

    # QUALITY CONTROL
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
        ('packaging_issue', _('Packaging Issue')),
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
        help_text=_('Quality control notes for this item')
    )

    # BATCH/LOT TRACKING
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        blank=True,
        help_text=_('Batch/lot number from supplier')
    )

    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Product expiry date')
    )

    production_date = models.DateField(
        _('Production Date'),
        null=True,
        blank=True,
        help_text=_('Product production date')
    )

    # SPECIAL HANDLING
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
            models.Index(fields=['product']),
            models.Index(fields=['source_order_line']),
            models.Index(fields=['quality_approved', 'batch_number']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['variance_quantity']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # ДОСТАВКА LINE ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Delivery line specific validation"""
        super().clean()

        # Set quantity from received_quantity for base validation
        if self.received_quantity and not self.received_quantity:
            self.quantity = self.received_quantity

        # НОВ КОД (правилен):
        if self.document and self.document.document_type:
            direction = self.document.document_type.inventory_direction

            if direction == 'both':
                # За "both" direction позволяваме negative values
                if self.received_quantity == 0:
                    raise ValidationError({
                        'received_quantity': _('Received quantity cannot be zero')
                    })
            else:
                # За "in"/"out" direction винаги positive
                if self.received_quantity <= 0:
                    raise ValidationError({
                        'received_quantity': _('Received quantity must be greater than zero')
                    })

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

        # Expiry date validation
        if self.expiry_date and self.expiry_date <= timezone.now().date():
            # Just warn, don't prevent saving - might be receiving expired goods for disposal
            pass

        # Unit validation
        if self.product and self.unit:
            valid_units = self.product.get_valid_purchase_units()
            if self.unit not in valid_units:
                unit_names = [u.name for u in valid_units]
                raise ValidationError({
                    'unit': f'Invalid unit. Valid units: {", ".join(unit_names)}'
                })

    def save(self, *args, **kwargs):
        """Enhanced save with variance calculation"""


        # Calculate variance if we have both quantities
        if self.ordered_quantity and self.received_quantity:
            self.variance_quantity = self.received_quantity - self.ordered_quantity

        super().save(*args, **kwargs)

    def get_quantity(self):
        """Get quantity for financial calculations"""
        return self.received_quantity or Decimal('0')

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
    def is_positive_variance(self):
        """More received than ordered"""
        return self.variance_quantity > 0

    @property
    def is_negative_variance(self):
        """Less received than ordered"""
        return self.variance_quantity < 0

    @property
    def variance_percentage(self):
        """Variance as percentage of ordered quantity"""
        if not self.ordered_quantity:
            return None
        return (self.variance_quantity / self.ordered_quantity) * 100

    @property
    def variance_value(self):
        """Monetary value of variance"""
        if self.unit_price:
            return self.variance_quantity * self.unit_price
        return Decimal('0.00')

    @property
    def is_expired(self):
        """Is the product expired?"""
        if not self.expiry_date:
            return False
        return self.expiry_date <= timezone.now().date()

    @property
    def expires_soon(self, days=30):
        """Does the product expire soon?"""
        if not self.expiry_date:
            return False
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.expiry_date <= cutoff_date

    @property
    def has_quality_issues(self):
        return not self.quality_approved

    @property
    def effective_received_quantity(self):
        """Received quantity minus any quality issues"""
        if self.quality_approved:
            return self.received_quantity
        return Decimal('0.000')  # If quality not approved, consider as not usable