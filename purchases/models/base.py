# purchases/models/base.py - ОБНОВИ САМО DocumentManager И LineManager

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.conf import settings
from django.db.models import Q, Sum, Count, Avg
from datetime import timedelta


class DocumentManager(models.Manager):
    """Manager за purchase документи - ОБНОВЕН"""

    def draft(self):
        return self.filter(status='draft')

    def confirmed(self):
        return self.filter(status='confirmed')

    def received(self):
        return self.filter(status='received')

    def paid(self):
        return self.filter(is_paid=True)

    def unpaid(self):
        return self.filter(is_paid=False)

    def active(self):
        """Активни (не отменени) документи"""
        return self.exclude(status='cancelled')

    def pending_receipt(self):
        """Потвърдени но неполучени до днес"""
        return self.filter(
            status='confirmed',
            delivery_date__lte=timezone.now().date()
        )

    def pending_payment(self):
        """Получени но неплатени"""
        return self.filter(
            status__in=['received', 'closed'],
            is_paid=False
        )

    def overdue_payment(self, days_threshold: int = 0):
        """Просрочени плащания"""
        cutoff_date = timezone.now().date() - timedelta(days=days_threshold)
        return self.filter(
            is_paid=False,
            delivery_date__lt=cutoff_date
        ).exclude(status='cancelled')

    def due_soon(self, days_ahead: int = 7):
        """Падеж скоро"""
        future_date = timezone.now().date() + timedelta(days=days_ahead)
        return self.filter(
            is_paid=False,
            delivery_date__lte=future_date,
            delivery_date__gte=timezone.now().date()
        )

    def today_deliveries(self):
        """Доставки днес"""
        today = timezone.now().date()
        return self.filter(delivery_date=today)

    def this_week_deliveries(self):
        """Доставки тази седмица"""
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return self.filter(delivery_date__range=[week_start, week_end])

    def this_month(self):
        """Документи този месец"""
        today = timezone.now().date()
        month_start = today.replace(day=1)
        return self.filter(created_at__date__gte=month_start)

    def for_supplier(self, supplier):
        return self.filter(supplier=supplier)

    def for_location(self, location):
        return self.filter(location=location)

    def large_orders(self, threshold: Decimal = Decimal('1000.00')):
        """Големи поръчки"""
        return self.filter(grand_total__gte=threshold)

    def with_discounts(self):
        """С отстъпки"""
        return self.filter(discount_amount__gt=0)

    def with_quality_issues(self):
        """Документи с качествени проблеми"""
        return self.filter(lines__quality_approved=False).distinct()

    def expiring_soon(self, days: int = 30):
        """Документи с продукти изтичащи скоро"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            lines__expiry_date__isnull=False,
            lines__expiry_date__lte=cutoff_date
        ).distinct()

    def search(self, query: str):
        """Търсене в документи"""
        return self.filter(
            Q(document_number__icontains=query) |
            Q(supplier__name__icontains=query) |
            Q(supplier__company_name__icontains=query) |
            Q(supplier_document_number__icontains=query) |
            Q(external_reference__icontains=query) |
            Q(notes__icontains=query)
        )

    def summary_stats(self):
        """Статистики"""
        return self.aggregate(
            total_count=Count('id'),
            total_amount=Sum('grand_total'),
            avg_amount=Avg('grand_total'),
            draft_count=Count('id', filter=Q(status='draft')),
            confirmed_count=Count('id', filter=Q(status='confirmed')),
            received_count=Count('id', filter=Q(status='received')),
            paid_count=Count('id', filter=Q(is_paid=True)),
            unpaid_count=Count('id', filter=Q(is_paid=False)),
        )

    def get_dashboard_summary(self):
        """Dashboard данни"""
        today = timezone.now().date()

        basic_stats = self.summary_stats()
        urgent_deliveries = self.today_deliveries().count()
        overdue_payments = self.overdue_payment().count()
        due_soon_payments = self.due_soon().count()

        recent_docs = self.filter(
            created_at__date__gte=today - timedelta(days=7)
        ).order_by('-created_at')[:5]

        return {
            'basic_stats': basic_stats,
            'urgent': {
                'deliveries_today': urgent_deliveries,
                'overdue_payments': overdue_payments,
                'due_soon_payments': due_soon_payments,
            },
            'recent_activity': list(recent_docs.values(
                'document_number', 'supplier__name', 'grand_total',
                'status', 'delivery_date', 'created_at'
            ))
        }

    def overdue(self, supplier=None):
        """Просрочени документи - стария метод за съвместимост"""
        from datetime import timedelta

        queryset = self.filter(is_paid=False, status__in=['received', 'closed'])

        if supplier:
            overdue_date = timezone.now().date() - timedelta(days=supplier.payment_days)
            queryset = queryset.filter(
                supplier=supplier,
                delivery_date__lt=overdue_date
            )

        return queryset

    def in_date_range(self, date_from, date_to):
        """Документи в период - стария метод"""
        queryset = self.all()
        if date_from:
            queryset = queryset.filter(document_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(document_date__lte=date_to)
        return queryset

    def with_totals(self):
        """Анотира с общи суми - стария метод"""
        return self.annotate(
            lines_count=models.Count('lines'),
            total_quantity=models.Sum('lines__quantity'),
            calculated_total=models.Sum('lines__line_total')
        )


class LineManager(models.Manager):
    """Manager за редове в документи - ОБНОВЕН"""

    def for_product(self, product):
        return self.filter(product=product)

    def with_discount(self):
        return self.filter(discount_percent__gt=0)

    def expired_soon(self, days=30):
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )

    def quality_issues(self):
        """Редове с качествени проблеми"""
        return self.filter(quality_approved=False)

    def over_received(self):
        """Редове с повече получено от поръчано"""
        return self.filter(received_quantity__gt=models.F('quantity'))

    def under_received(self):
        """Редове с по-малко получено от поръчано"""
        return self.filter(received_quantity__lt=models.F('quantity'))

    def with_variance(self):
        """Редове с разлика между поръчано и получено"""
        return self.exclude(received_quantity=models.F('quantity'))

    def by_batch(self, batch_number):
        """Редове с конкретен batch"""
        return self.filter(batch_number=batch_number)

    def with_price_analysis(self):
        return self.select_related(
            'product',
            'unit',
            'document__supplier'
        ).prefetch_related(
            'product__packagings'
        )


# ОСТАНАЛИТЕ КЛАСОВЕ ОСТАВАТ СЪЩИТЕ (BaseDocument, BaseDocumentLine)...
# Просто добавям imports ако липсват

class BaseDocument(models.Model):
    """Базов абстрактен клас за всички purchase документи"""

    # Статуси - общи за всички документи
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'
    RECEIVED = 'received'
    CANCELLED = 'cancelled'
    PAID = 'paid'
    CLOSED = 'closed'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (CONFIRMED, _('Confirmed')),
        (RECEIVED, _('Received')),
        (CANCELLED, _('Cancelled')),
        (PAID, _('Paid')),
        (CLOSED, _('Closed')),
    ]

    # Общи полета за всички документи
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True
    )
    document_date = models.DateField(_('Document Date'))
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=DRAFT
    )

    # Финансови полета
    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    grand_total = models.DecimalField(
        _('Grand Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Плащане
    is_paid = models.BooleanField(_('Is Paid'), default=False)
    payment_date = models.DateField(_('Payment Date'), null=True, blank=True)

    # Одит полета
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_%(class)s_documents',
        verbose_name=_('Created By'),
        null=True,
        blank=True
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_%(class)s_documents',
        verbose_name=_('Updated By'),
        null=True,
        blank=True
    )

    class Meta:
        abstract = True
        ordering = ['-document_date', '-created_at']

    def __str__(self):
        return f"{self.document_number} - {self.document_date}"

    def can_be_modified(self):
        return self.status in [self.DRAFT, self.CONFIRMED]

    def can_be_received(self):
        return self.status in [self.CONFIRMED]

    def can_be_cancelled(self):
        return self.status in [self.DRAFT, self.CONFIRMED]



    def get_status_display_badge(self):
        colors = {
            self.DRAFT: '#6C757D',
            self.CONFIRMED: '#0D6EFD',
            self.RECEIVED: '#198754',
            self.CANCELLED: '#DC3545',
            self.PAID: '#6F42C1',
            self.CLOSED: '#495057'
        }
        color = colors.get(self.status, '#6C757D')
        display = self.get_status_display()
        return f'<span style="background-color: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{display}</span>'


class BaseDocumentLine(models.Model):
    """Базов абстрактен клас за редове в документи"""

    line_number = models.PositiveSmallIntegerField(_('Line Number'))

    # Продукт и количества
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )
    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=10,
        decimal_places=3
    )
    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit')
    )

    # Количество в базова единица
    quantity_base_unit = models.DecimalField(
        _('Quantity (Base Unit)'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Automatically calculated')
    )

    # Цени
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4
    )
    unit_price_base = models.DecimalField(
        _('Unit Price (Base)'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Price per base unit - automatically calculated')
    )

    # Отстъпки
    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Изчислени полета
    final_unit_price = models.DecimalField(
        _('Final Unit Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Unit price after discount')
    )
    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2
    )
    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Batch information
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        blank=True
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True
    )

    class Meta:
        abstract = True
        ordering = ['line_number']

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({'quantity': _('Quantity must be positive')})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': _('Unit price cannot be negative')})

    def save(self, *args, **kwargs):
        # Изчисляваме количеството в базова единица
        if self.product and self.unit:
            conversion_factor = self.get_conversion_factor()
            self.quantity_base_unit = self.quantity * conversion_factor
            self.unit_price_base = self.unit_price / conversion_factor

        # Изчисляваме финалната цена след отстъпка
        if self.discount_percent > 0:
            self.discount_amount = (self.unit_price * self.quantity * self.discount_percent) / 100
            self.final_unit_price = self.unit_price * (1 - self.discount_percent / 100)
        else:
            self.discount_amount = Decimal('0.00')
            self.final_unit_price = self.unit_price

        # Изчисляваме общата сума на реда
        self.line_total = self.final_unit_price * self.quantity

        # VAT изчисления
        if hasattr(self.product, 'tax_group') and self.product.tax_group:
            self.vat_amount = self.line_total * (self.product.tax_group.rate / 100)

        super().save(*args, **kwargs)

    def get_conversion_factor(self):
        if not self.product or not self.unit:
            return Decimal('1.00')
        if self.unit == self.product.base_unit:
            return Decimal('1.00')
        try:
            packaging = self.product.packagings.get(unit=self.unit)
            return packaging.conversion_factor
        except:
            return Decimal('1.00')

    def get_markup_percentage(self, current_sale_price=None):
        if not current_sale_price or self.final_unit_price == 0:
            return None
        markup = ((current_sale_price - self.final_unit_price) / self.final_unit_price) * 100
        return markup

    def suggest_sale_price(self, markup_percentage=None):
        if not markup_percentage:
            markup_percentage = getattr(self, '_default_markup', 30)
        suggested_price = self.final_unit_price * (1 + markup_percentage / 100)
        return suggested_price