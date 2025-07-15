# purchases/models/base.py - FIXED CLEAN ARCHITECTURE

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
            models.Q(supplier__name__icontains=query) |
            models.Q(external_reference__icontains=query) |
            models.Q(notes__icontains=query)
        )


class LineManager(models.Manager):
    """Base manager for document lines"""

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)


# =================================================================
# MINIMAL BASE DOCUMENT - САМО ОБЩИТЕ ПОЛЕТА
# =================================================================

class BaseDocument(models.Model):
    """
    Минимален базов клас с САМО наистина общите полета

    Съдържа само полетата които се ползват от ВСИЧКИ документи.
    Всичко останало е в mixin-ите или конкретните модели.
    """

    # =====================
    # CORE FIELDS - задължителни за всички
    # =====================
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True,
        help_text=_('Auto-generated unique document number')
    )

    document_date = models.DateField(
        _('Document Date'),
        default=timezone.now,
        help_text=_('Date when document was created')
    )

    status = models.CharField(
        _('Status'),
        max_length=20,
        help_text=_('Current document status')
        # NOTE: Choices ще се дефинират в конкретните модели
    )

    # =====================
    # BUSINESS RELATIONSHIPS - общи за всички
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
        help_text=_('Business location')
    )

    # =====================
    # REFERENCE FIELDS - опционални но общи
    # =====================
    external_reference = models.CharField(
        _('External Reference'),
        max_length=100,
        blank=True,
        help_text=_('PO number, contract reference, etc.')
    )

    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes and comments')
    )

    # =====================
    # AUDIT FIELDS - задължителни за всички
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
    # MINIMAL VALIDATION - само основните неща
    # =====================
    def clean(self):
        """Минимална валидация - БЕЗ business-specific правила"""
        super().clean()

        # Само основни проверки
        if self.document_date and self.document_date > timezone.now().date():
            raise ValidationError({
                'document_date': _('Document date cannot be in the future')
            })

        # ПРЕМАХНАТО: delivery_date validation
        # ПРЕМАХНАТО: payment validation
        # Тези ще са в mixin-ите!

    def save(self, *args, **kwargs):
        """Enhanced save with document number generation"""
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
        """
        prefix = self.get_document_prefix()
        year = timezone.now().year

        # Find last number for this year and prefix
        last_doc = self.__class__.objects.filter(
            document_number__startswith=f"{prefix}-{year}-"
        ).order_by('-document_number').first()

        if last_doc:
            try:
                last_number = int(last_doc.document_number.split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}-{year}-{new_number:04d}"

    def get_document_prefix(self):
        """Override in subclasses"""
        return "DOC"

    # =====================
    # BASIC BUSINESS LOGIC
    # =====================
    def can_be_edited(self):
        """Override in subclasses with specific logic"""
        return True

    def can_be_cancelled(self):
        """Override in subclasses with specific logic"""
        return True


# =================================================================
# MIXIN CLASSES - ЗА СПЕЦИФИЧНИ ФУНКЦИОНАЛНОСТИ
# =================================================================

class FinancialMixin(models.Model):
    """
    Mixin за документи с финансови данни

    Използва се от PurchaseOrder и DeliveryReceipt.
    НЕ се използва от PurchaseRequest (заявките нямат финансови данни).
    """

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

    class Meta:
        abstract = True

    def recalculate_totals(self):
        """Recalculate all financial totals from lines"""
        if not hasattr(self, 'lines'):
            return

        lines = self.lines.all()
        subtotal = sum(getattr(line, 'line_total', 0) for line in lines)
        discount_total = sum(getattr(line, 'discount_amount', 0) for line in lines)
        vat_total = sum(getattr(line, 'vat_amount', 0) for line in lines)

        self.subtotal = subtotal
        self.discount_total = discount_total
        self.vat_total = vat_total
        self.grand_total = subtotal + vat_total

        self.save(update_fields=[
            'subtotal', 'discount_total', 'vat_total', 'grand_total'
        ])


class PaymentMixin(models.Model):
    """
    Mixin за документи с плащания

    Използва се главно от DeliveryReceipt и понякога от PurchaseOrder.
    НЕ се използва от PurchaseRequest.
    """

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

    class Meta:
        abstract = True

    def clean(self):
        """Payment-specific validation"""
        super().clean()

        # Payment validation - само за документи с този mixin
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()


class DeliveryMixin(models.Model):
    """
    Mixin за документи с delivery информация

    Използва се от DeliveryReceipt.
    НЕ се използва от PurchaseRequest или PurchaseOrder.
    """

    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were delivered')
    )

    delivery_instructions = models.TextField(
        _('Delivery Instructions'),
        blank=True,
        help_text=_('Special instructions for delivery')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Delivery-specific validation"""
        super().clean()

        # НЕ ПРАВИМ date validation тук - delivery_date може да е във всякакво време
        # Това е реалната дата на доставка, не планирана


# =================================================================
# MINIMAL BASE DOCUMENT LINE
# =================================================================

class BaseDocumentLine(models.Model):
    """
    Минимален базов клас за редове - САМО общите полета
    """

    # =====================
    # CORE FIELDS
    # =====================
    line_number = models.PositiveIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product'),
        help_text=_('Product being purchased')
    )

    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity in specified unit')
    )

    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit'),
        help_text=_('Unit of measure for this line')
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
    # MINIMAL VALIDATION
    # =====================
    def clean(self):
        """Основна валидация - БЕЗ financial проверки"""
        super().clean()

        # Quantity must be positive
        if self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be greater than zero')
            })

    def save(self, *args, **kwargs):
        """Basic save"""
        self.full_clean()
        super().save(*args, **kwargs)


# =================================================================
# FINANCIAL LINE MIXIN
# =================================================================

class FinancialLineMixin(models.Model):
    """
    Mixin за редове с финансови данни

    Използва се от PurchaseOrderLine и DeliveryLine.
    НЕ се използва от PurchaseRequestLine.
    """

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price per unit')
    )

    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Discount percentage')
    )

    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total amount for this line')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Financial validation"""
        super().clean()

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

    def save(self, *args, **kwargs):
        """Save with financial calculations"""
        self.calculate_line_total()
        super().save(*args, **kwargs)

    def calculate_line_total(self):
        """Calculate line total with discount"""
        if self.quantity and self.unit_price:
            subtotal = self.quantity * self.unit_price
            discount_amount = subtotal * (self.discount_percent / 100)
            self.line_total = subtotal - discount_amount
        else:
            self.line_total = Decimal('0.00')

    @property
    def discount_amount(self):
        """Calculate discount amount"""
        if self.quantity and self.unit_price:
            return (self.quantity * self.unit_price) * (self.discount_percent / 100)
        return Decimal('0.00')