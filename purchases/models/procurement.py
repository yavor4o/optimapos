# purchases/models/procurement.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocument, DocumentManager


class DocumentType(models.Model):
    """Типове документи за purchases - invoices, delivery notes, etc."""

    # Предефинирани типове
    STOCK_IN = 'stock_in'
    STOCK_OUT = 'stock_out'
    INVOICE = 'invoice'
    TRANSFER = 'transfer'
    ADJUSTMENT = 'adjustment'

    TYPE_CHOICES = [
        (STOCK_IN, _('Stock In (+)')),
        (STOCK_OUT, _('Stock Out (-)')),
        (INVOICE, _('Invoice')),
        (TRANSFER, _('Internal Transfer')),
        (ADJUSTMENT, _('Stock Adjustment')),
    ]

    # Основна информация
    code = models.CharField(
        _('Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like INV, DEL, ADJ')
    )
    name = models.CharField(
        _('Document Type Name'),
        max_length=100
    )
    type_key = models.CharField(
        _('Type Key'),
        max_length=20,
        choices=TYPE_CHOICES
    )

    # Влияние върху наличности
    stock_effect = models.IntegerField(
        _('Stock Effect'),
        choices=[
            (1, _('Increases stock')),
            (-1, _('Decreases stock')),
            (0, _('No effect'))
        ],
        default=1,
        help_text=_('How this document type affects inventory levels')
    )

    # Специални настройки
    allow_reverse_operations = models.BooleanField(
        _('Allow Reverse Operations'),
        default=False,
        help_text=_('Allow negative quantities to reverse the stock effect')
    )
    requires_batch = models.BooleanField(
        _('Requires Batch'),
        default=False,
        help_text=_('Whether batch numbers are mandatory')
    )
    requires_expiry = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Whether expiry dates are mandatory')
    )

    # Workflow настройки
    auto_confirm = models.BooleanField(
        _('Auto Confirm'),
        default=False,
        help_text=_('Automatically confirm document on creation')
    )
    auto_receive = models.BooleanField(
        _('Auto Receive'),
        default=False,
        help_text=_('Automatically receive document on confirmation')
    )

    # Статус
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Одит
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['type_key', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """Валидации на document type"""
        super().clean()

        # Проверяваме логиката на auto operations
        if self.auto_receive and not self.auto_confirm:
            raise ValidationError({
                'auto_receive': _('Cannot auto-receive without auto-confirm')
            })

    def get_stock_effect_display_badge(self):
        """Връща HTML badge за stock effect"""
        colors = {
            1: '#28A745',  # Green for increase
            -1: '#DC3545',  # Red for decrease
            0: '#6C757D'  # Gray for no effect
        }

        symbols = {
            1: '+',
            -1: '-',
            0: '='
        }

        color = colors.get(self.stock_effect, '#6C757D')
        symbol = symbols.get(self.stock_effect, '?')

        return f'<span style="background-color: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{symbol} Stock</span>'


class PurchaseDocument(BaseDocument):
    """Основен документ за закупки/доставки - CLEAN MODEL"""

    # Специфична информация за purchase
    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were/will be delivered')
    )

    # Връзки
    supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.PROTECT,
        related_name='purchase_documents',
        verbose_name=_('Supplier')
    )
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        related_name='purchase_documents',
        verbose_name=_('Location')
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        verbose_name=_('Document Type')
    )

    # Референтни номера
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

    # НОВО ПОЛЕ за auto invoice creation
    auto_create_invoice = models.BooleanField(
        _('Auto Create Invoice'),
        default=False,
        help_text=_('Automatically create invoice document when saving')
    )

    # Допълнителна информация
    notes = models.TextField(
        _('Notes'),
        blank=True
    )

    # Managers
    objects = DocumentManager()

    class Meta:
        verbose_name = _('Purchase Document')
        verbose_name_plural = _('Purchase Documents')
        ordering = ['-delivery_date', '-document_date']
        indexes = [
            models.Index(fields=['supplier', 'delivery_date']),
            models.Index(fields=['location', 'document_date']),
            models.Index(fields=['status', 'delivery_date']),
            models.Index(fields=['supplier_document_number']),
        ]

    def __str__(self):
        return f"{self.document_number} - {self.supplier.name} ({self.delivery_date})"

    def clean(self):
        """Валидации на purchase document"""
        super().clean()

        # Delivery date не може да е преди document date
        if self.delivery_date and self.document_date:
            if self.delivery_date < self.document_date:
                raise ValidationError({
                    'delivery_date': _('Delivery date cannot be before document date')
                })

        # Проверяваме дали supplier-а е активен
        if self.supplier and not self.supplier.is_active:
            raise ValidationError({
                'supplier': _('Cannot create documents for inactive suppliers')
            })

        # Проверяваме дали location-а е активен
        if self.location and not self.location.is_active:
            raise ValidationError({
                'location': _('Cannot create documents for inactive locations')
            })

    def save(self, *args, **kwargs):
        """Enhanced save с auto invoice creation"""
        is_new = self.pk is None

        # Flag за auto invoice creation
        should_create_invoice = (
                is_new and
                self.auto_create_invoice and
                self.document_type.code == 'GRN' and
                self.supplier_document_number
        )

        # Запазваме оригиналния статус за change tracking
        if not is_new:
            try:
                original = PurchaseDocument.objects.get(pk=self.pk)
                self._original_status = original.status
            except PurchaseDocument.DoesNotExist:
                self._original_status = None

        # Генериране на номер ако е нов
        if is_new and not self.document_number:
            self.document_number = self.generate_document_number()

        # Auto-operations само от document type settings
        if is_new and self.document_type:
            if self.document_type.auto_confirm:
                self.status = self.CONFIRMED
            if self.document_type.auto_receive:
                self.status = self.RECEIVED

        super().save(*args, **kwargs)

        # Auto-create invoice СЛЕД save
        if should_create_invoice:
            self._trigger_auto_invoice_creation()

    def _trigger_auto_invoice_creation(self):
        """Trigger auto invoice creation via service"""
        try:
            from ..services import DocumentService
            DocumentService.create_invoice_from_grn(self)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Auto invoice creation failed for {self.document_number}: {e}")

    def generate_document_number(self):
        """Генерира уникален номер на документа"""
        prefix = self.document_type.code if self.document_type else 'PUR'
        year = timezone.now().year

        # Намираме последния номер за тази година
        last_doc = PurchaseDocument.objects.filter(
            document_number__startswith=f"{prefix}{year}",
            document_type=self.document_type
        ).order_by('-document_number').first()

        if last_doc:
            try:
                last_number = int(last_doc.document_number[-4:])
                new_number = last_number + 1
            except ValueError:
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}{year}{new_number:04d}"

    def recalculate_totals(self):
        """Преизчислява общите суми на базата на редовете"""
        lines = self.lines.all()
        self.subtotal = sum(line.line_total for line in lines)
        self.vat_amount = sum(line.vat_amount for line in lines)
        self.grand_total = self.subtotal + self.vat_amount - self.discount_amount

    # =====================
    # CORE BUSINESS LOGIC (остава в модела)
    # =====================

    def confirm(self, user=None):
        """Потвърждава документа"""
        if self.status != self.DRAFT:
            raise ValidationError("Can only confirm draft documents")

        self.status = self.CONFIRMED
        if user:
            self.updated_by = user
        self.save()

    def receive(self, user=None):
        """Получава документа"""
        if self.status != self.CONFIRMED:
            raise ValidationError("Can only receive confirmed documents")

        self._status_changed_to_received = True
        self.status = self.RECEIVED
        if user:
            self.updated_by = user
        self.save()

    def cancel(self, user=None):
        """Отказва документа"""
        if not self.can_be_cancelled():
            raise ValidationError("Cannot cancel this document in current status")

        self.status = self.CANCELLED
        if user:
            self.updated_by = user
        self.save()

    # =====================
    # BUSINESS RULES & PROPERTIES (остава в модела)
    # =====================

    def can_be_modified(self):
        """Проверява дали документът може да се модифицира"""
        return self.status in [self.DRAFT]

    def can_be_received(self):
        """Проверява дали документът може да се получи"""
        return self.status == self.CONFIRMED

    def can_be_cancelled(self):
        """Проверява дали документът може да се отмени"""
        return self.status in [self.DRAFT, self.CONFIRMED]

    def is_overdue_payment(self):
        """Проверява дали плащането е просрочено"""
        if self.is_paid:
            return False

        from datetime import timedelta
        due_date = self.delivery_date + timedelta(days=self.supplier.payment_days)
        return timezone.now().date() > due_date

    def get_days_until_payment(self):
        """Връща дни до падеж на плащането"""
        if self.is_paid:
            return 0

        from datetime import timedelta
        due_date = self.delivery_date + timedelta(days=self.supplier.payment_days)
        days_diff = (due_date - timezone.now().date()).days
        return days_diff

    # =====================
    # SIMPLE COMPUTED PROPERTIES (остава в модела)
    # =====================

    def get_total_weight(self):
        """Изчислява общото тегло на документа"""
        total_weight = Decimal('0.00')
        for line in self.lines.all():
            if hasattr(line.product, 'weight_per_unit') and line.product.weight_per_unit:
                total_weight += line.quantity_base_unit * line.product.weight_per_unit
        return total_weight

    def get_lines_count(self):
        """Връща броя редове"""
        return self.lines.count()

    def get_products_count(self):
        """Връща броя уникални продукти"""
        return self.lines.values('product').distinct().count()

    def get_related_invoice(self):
        """Връща свързания INV документ ако съществува"""
        if not self.supplier_document_number:
            return None

        return PurchaseDocument.objects.filter(
            document_type__code='INV',
            supplier_document_number=self.supplier_document_number,
            supplier=self.supplier
        ).exclude(pk=self.pk).first()