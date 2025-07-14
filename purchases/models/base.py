# purchases/models/base.py - NEW CLEAN ARCHITECTURE

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta


class DocumentManager(models.Manager):
    """Base manager for all purchase documents"""

    def active(self):
        """Return only active documents (not cancelled/closed)"""
        return self.exclude(status__in=['cancelled', 'closed'])

    def confirmed(self):
        """Return confirmed documents"""
        return self.filter(status='confirmed')

    def received(self):
        """Return received documents"""
        return self.filter(status='received')

    def for_supplier(self, supplier):
        """Filter by supplier with optimizations"""
        return self.filter(supplier=supplier).select_related(
            'supplier', 'location'
        ).prefetch_related('lines__product')

    def for_location(self, location):
        """Filter by location"""
        return self.filter(location=location)

    def search(self, query):
        """Search documents by various fields"""
        return self.filter(
            models.Q(document_number__icontains=query) |
            models.Q(supplier_document_number__icontains=query) |
            models.Q(supplier__name__icontains=query) |
            models.Q(external_reference__icontains=query) |
            models.Q(notes__icontains=query)
        )

    def dashboard_summary(self):
        """Get summary data for dashboard"""
        return self.aggregate(
            total_documents=models.Count('id'),
            total_amount=models.Sum('grand_total'),
            confirmed_amount=models.Sum(
                'grand_total',
                filter=models.Q(status='confirmed')
            ),
            unpaid_amount=models.Sum(
                'grand_total',
                filter=models.Q(is_paid=False)
            )
        )

    def today_deliveries(self):
        """Documents scheduled for delivery today"""
        today = timezone.now().date()
        return self.filter(delivery_date=today, status='confirmed')

    def overdue_payment(self):
        """Documents with overdue payments"""
        return self.filter(is_paid=False, status='received')

    def due_soon(self, days=7):
        """Documents due for delivery soon"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            delivery_date__lte=cutoff_date,
            status='confirmed'
        )


class LineManager(models.Manager):
    """Base manager for document lines"""

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)

    def expiring_soon(self, days=30):
        """Lines with products expiring soon"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )

    def quality_issues(self):
        """Lines with quality problems"""
        return self.filter(quality_approved=False)

    def by_batch(self, batch_number):
        """Lines with specific batch"""
        return self.filter(batch_number=batch_number)

    def with_price_analysis(self):
        """Lines with optimized queries for price analysis"""
        return self.select_related(
            'product',
            'unit',
            'document__supplier'
        ).prefetch_related(
            'product__packagings'
        )

    def recent_purchases(self, days=30):
        """Recent purchase lines for price analysis"""
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return self.filter(
            document__delivery_date__gte=cutoff_date,
            document__status='received'
        ).select_related('product', 'document__supplier')


class BaseDocument(models.Model):
    """
    Abstract base class for all purchase documents

    This is the foundation for:
    - PurchaseRequest (заявки)
    - PurchaseOrder (поръчки)
    - DeliveryReceipt (доставки)

    Contains all common fields and behaviors.
    """

    # =====================
    # STATUS CHOICES - UNIVERSAL
    # =====================
    DRAFT = 'draft'
    SUBMITTED = 'submitted'  # For requests
    APPROVED = 'approved'  # For requests
    CONFIRMED = 'confirmed'  # For orders
    SENT = 'sent'  # For orders
    RECEIVED = 'received'  # For deliveries
    CANCELLED = 'cancelled'
    CLOSED = 'closed'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (SUBMITTED, _('Submitted')),
        (APPROVED, _('Approved')),
        (CONFIRMED, _('Confirmed')),
        (SENT, _('Sent')),
        (RECEIVED, _('Received')),
        (CANCELLED, _('Cancelled')),
        (CLOSED, _('Closed')),
    ]

    # =====================
    # CORE DOCUMENT FIELDS
    # =====================
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True,
        help_text=_('Auto-generated unique document number')
    )
    document_date = models.DateField(
        _('Document Date'),
        default=timezone.now
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=DRAFT
    )

    # =====================
    # BUSINESS RELATIONSHIPS
    # =====================
    supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.PROTECT,
        verbose_name=_('Supplier'),
        help_text=_('The supplier for this document')
    )
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        verbose_name=_('Location'),
        help_text=_('Delivery/receiving location')
    )

    # =====================
    # DATES
    # =====================
    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were/will be delivered')
    )

    # =====================
    # REFERENCE NUMBERS
    # =====================
    supplier_document_number = models.CharField(
        _('Supplier Document Number'),
        max_length=50,
        blank=True,
        help_text=_('Supplier\'s invoice/delivery note number')
    )
    external_reference = models.CharField(
        _('External Reference'),
        max_length=100,
        blank=True,
        help_text=_('PO number, contract reference, etc.')
    )

    # =====================
    # FINANCIAL FIELDS
    # =====================
    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Sum of all line totals before VAT')
    )
    discount_total = models.DecimalField(
        _('Total Discount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total discount amount')
    )
    vat_total = models.DecimalField(
        _('VAT Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total VAT amount')
    )
    grand_total = models.DecimalField(
        _('Grand Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Final total including VAT')
    )

    # =====================
    # PAYMENT TRACKING
    # =====================
    is_paid = models.BooleanField(
        _('Is Paid'),
        default=False,
        help_text=_('Whether this document has been paid')
    )
    payment_date = models.DateField(
        _('Payment Date'),
        null=True,
        blank=True,
        help_text=_('When payment was made')
    )
    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        blank=True,
        help_text=_('How payment was made')
    )

    # =====================
    # NOTES AND COMMENTS
    # =====================
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes and comments')
    )

    # =====================
    # AUDIT FIELDS
    # =====================
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_%(class)s_documents',
        verbose_name=_('Created By')
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='updated_%(class)s_documents',
        verbose_name=_('Updated By')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = DocumentManager()

    class Meta:
        abstract = True
        get_latest_by = 'created_at'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document_number} - {self.supplier.name}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Base validation for all documents"""
        super().clean()

        # Document date cannot be in the future
        if self.document_date > timezone.now().date():
            raise ValidationError({
                'document_date': _('Document date cannot be in the future')
            })

        # Delivery date should be today or future
        if self.delivery_date < timezone.now().date():
            raise ValidationError({
                'delivery_date': _('Delivery date cannot be in the past')
            })

        # Payment validation
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()  # Auto-set to today

    def save(self, *args, **kwargs):
        """Enhanced save with business logic"""
        # Generate document number if new
        if not self.document_number:
            self.document_number = self.generate_document_number()

        # Full clean before saving
        self.full_clean()

        super().save(*args, **kwargs)

    # =====================
    # DOCUMENT NUMBER GENERATION
    # =====================
    def generate_document_number(self):
        """
        Generate unique document number
        Override in subclasses for specific prefixes
        Format: PREFIX-YYYY-NNNN
        """
        prefix = self.get_document_prefix()
        year = timezone.now().year

        # Find last number for this year and prefix
        last_doc = self.__class__.objects.filter(
            document_number__startswith=f"{prefix}-{year}-"
        ).order_by('-document_number').first()

        if last_doc:
            try:
                # Extract number: "REQ-2024-0001" -> "0001" -> 1
                last_number = int(last_doc.document_number.split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}-{year}-{new_number:04d}"

    def get_document_prefix(self):
        """
        Return document prefix for number generation
        Override in subclasses
        """
        return "DOC"

    # =====================
    # FINANCIAL CALCULATIONS
    # =====================
    def recalculate_totals(self):
        """Recalculate all financial totals from lines"""
        if not hasattr(self, 'lines'):
            return

        lines = self.lines.all()

        subtotal = sum(line.line_total for line in lines)
        discount_total = sum(line.discount_amount for line in lines)
        vat_total = sum(line.vat_amount for line in lines)

        self.subtotal = subtotal
        self.discount_total = discount_total
        self.vat_total = vat_total
        self.grand_total = subtotal + vat_total

        self.save(update_fields=[
            'subtotal', 'discount_total', 'vat_total', 'grand_total'
        ])

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_edited(self):
        """Check if document can be edited"""
        return self.status in [self.DRAFT, self.SUBMITTED]

    def can_be_confirmed(self):
        """Check if document can be confirmed"""
        return (
                self.status in [self.DRAFT, self.APPROVED] and
                hasattr(self, 'lines') and
                self.lines.exists()
        )

    def can_be_cancelled(self):
        """Check if document can be cancelled"""
        return self.status not in [self.RECEIVED, self.CANCELLED, self.CLOSED]

    # =====================
    # STATUS TRANSITIONS
    # =====================
    def confirm(self, user=None):
        """Confirm the document"""
        if not self.can_be_confirmed():
            raise ValidationError("Document cannot be confirmed in current state")

        self.status = self.CONFIRMED
        self.updated_by = user
        self.save()

    def cancel(self, user=None):
        """Cancel the document"""
        if not self.can_be_cancelled():
            raise ValidationError("Document cannot be cancelled in current state")

        self.status = self.CANCELLED
        self.updated_by = user
        self.save()

    def close(self, user=None):
        """Close the document"""
        self.status = self.CLOSED
        self.updated_by = user
        self.save()


class BaseDocumentLine(models.Model):
    """
    Abstract base class for document lines

    This is the foundation for:
    - PurchaseRequestLine
    - PurchaseOrderLine
    - DeliveryLine

    Contains all common line fields and calculations.
    """

    # =====================
    # LINE IDENTIFICATION
    # =====================
    line_number = models.PositiveSmallIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    # =====================
    # PRODUCT AND QUANTITIES
    # =====================
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )
    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity in the specified unit')
    )
    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit'),
        help_text=_('Unit of measure for this line')
    )

    # =====================
    # BASE UNIT CALCULATIONS
    # =====================
    quantity_base_unit = models.DecimalField(
        _('Quantity (Base Unit)'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Automatically calculated quantity in product base unit')
    )

    # =====================
    # PRICING
    # =====================
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Price per unit')
    )
    unit_price_base = models.DecimalField(
        _('Unit Price (Base)'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price per base unit - automatically calculated')
    )

    # =====================
    # DISCOUNTS
    # =====================
    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Discount percentage')
    )
    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Calculated discount amount')
    )

    # =====================
    # CALCULATED FIELDS
    # =====================
    final_unit_price = models.DecimalField(
        _('Final Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Unit price after discount')
    )
    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total for this line after discount')
    )
    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('VAT amount for this line')
    )

    # =====================
    # BATCH/LOT TRACKING
    # =====================
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        blank=True,
        help_text=_('Batch/lot number for traceability')
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Product expiry date')
    )

    # =====================
    # QUALITY CONTROL
    # =====================
    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Whether this line passed quality control')
    )
    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Notes about quality issues or inspections')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = LineManager()

    class Meta:
        abstract = True
        ordering = ['line_number']

    def __str__(self):
        return f"Line {self.line_number}: {self.product.code} x {self.quantity}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Base validation for all lines"""
        super().clean()

        # Quantity must be positive
        if self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be greater than zero')
            })

        # Unit price must be non-negative
        if self.unit_price < 0:
            raise ValidationError({
                'unit_price': _('Unit price cannot be negative')
            })

        # Discount validation
        if self.discount_percent < 0 or self.discount_percent > 100:
            raise ValidationError({
                'discount_percent': _('Discount percentage must be between 0 and 100')
            })

        # Unit compatibility validation
        if self.product and self.unit:
            if not self._is_unit_compatible():
                raise ValidationError({
                    'unit': _('This unit is not valid for the selected product')
                })

    def save(self, *args, **kwargs):
        """Enhanced save with calculations"""
        # Perform all calculations before saving
        self.calculate_base_quantities()
        self.calculate_prices()
        self.calculate_totals()

        super().save(*args, **kwargs)

    # =====================
    # CALCULATIONS
    # =====================
    def calculate_base_quantities(self):
        """Calculate quantities in base units"""
        if self.product and self.unit:
            conversion_factor = self.get_unit_conversion_factor()
            self.quantity_base_unit = self.quantity * conversion_factor

    def calculate_prices(self):
        """Calculate base unit prices"""
        if self.product and self.unit:
            conversion_factor = self.get_unit_conversion_factor()
            if conversion_factor > 0:
                self.unit_price_base = self.unit_price / conversion_factor
            else:
                self.unit_price_base = self.unit_price

    def calculate_totals(self):
        """Calculate line totals and discounts"""
        # Calculate discount amount if percentage is used
        if self.discount_percent > 0:
            gross_total = self.quantity * self.unit_price
            self.discount_amount = (gross_total * self.discount_percent) / 100

        # Calculate final unit price after discount
        if self.quantity > 0:
            discount_per_unit = self.discount_amount / self.quantity
            self.final_unit_price = self.unit_price - discount_per_unit

        # Calculate line total
        self.line_total = (self.quantity * self.unit_price) - self.discount_amount

        # Calculate VAT if applicable
        self._calculate_vat()

    def _calculate_vat(self):
        """Calculate VAT amount based on product tax group"""
        # This will be implemented based on product tax configuration
        # For now, default to 0
        self.vat_amount = Decimal('0.00')

    # =====================
    # UTILITY METHODS
    # =====================
    def get_unit_conversion_factor(self):
        """Get conversion factor from line unit to product base unit"""
        if not self.product or not self.unit:
            return Decimal('1.0')

        # If unit is the same as base unit, factor is 1
        if self.unit == self.product.base_unit:
            return Decimal('1.0')

        # Look for packaging conversion
        if hasattr(self.product, 'packagings'):
            packaging = self.product.packagings.filter(unit=self.unit).first()
            if packaging:
                return packaging.conversion_factor

        # Default to 1 if no conversion found
        return Decimal('1.0')

    def _is_unit_compatible(self):
        """Check if selected unit is compatible with product"""
        if not self.product or not self.unit:
            return True

        # Base unit is always compatible
        if self.unit == self.product.base_unit:
            return True

        # Check if unit exists in product packagings
        if hasattr(self.product, 'packagings'):
            return self.product.packagings.filter(unit=self.unit).exists()

        return False

    # =====================
    # PROPERTIES FOR CONVENIENCE
    # =====================
    @property
    def current_stock_display(self):
        """Display current stock from product"""
        return self.product.current_stock_qty if self.product else Decimal('0.000')

    @property
    def last_purchase_price_display(self):
        """Display last purchase price from product"""
        return self.product.last_purchase_cost if self.product else Decimal('0.0000')

    @property
    def profit_margin_display(self):
        """Calculate and display profit margin if sale price exists"""
        if (self.product and hasattr(self.product, 'current_sale_price') and
                self.product.current_sale_price and self.unit_price > 0):
            profit = self.product.current_sale_price - self.unit_price
            margin = (profit / self.product.current_sale_price) * 100
            return f"{margin:.1f}%"

        return "N/A"