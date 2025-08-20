# =====================================================
# ФАЙЛ 2: nomenclatures/mixins/__init__.py
# =====================================================

# nomenclatures/mixins/__init__.py
"""
Document Mixins Package - EXTRACTED FROM purchases.models.base

Provides composable functionality for document models:
- FinancialMixin: Financial calculations and totals
- PaymentMixin: Payment tracking and status
- DeliveryMixin: Delivery information and tracking
- FinancialLineMixin: Line-level financial calculations
"""

from .financial import FinancialMixin, FinancialLineMixin
from .payment import PaymentMixin
from .delivery import DeliveryMixin

__all__ = [
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'

# =====================================================
# ФАЙЛ 3: nomenclatures/mixins/financial.py
# =====================================================

# nomenclatures/mixins/financial.py
"""
Financial Mixins - EXTRACTED FROM purchases.models.base

Provides financial calculation functionality for documents and lines
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class FinancialMixin(models.Model):
    """
    Mixin за документи с финансови данни

    Използва се от PurchaseOrder, DeliveryReceipt, SalesInvoice
    НЕ се използва от PurchaseRequest (само заявка без цени)
    """

    # =====================
    # FINANCIAL TOTALS
    # =====================
    total_amount = models.DecimalField(
        _('Total Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total amount before tax')
    )

    tax_amount = models.DecimalField(
        _('Tax Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total tax amount')
    )

    grand_total = models.DecimalField(
        _('Grand Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total amount including tax')
    )

    # =====================
    # CURRENCY
    # =====================
    currency = models.ForeignKey(
        'nomenclatures.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Currency'),
        help_text=_('Document currency')
    )

    exchange_rate = models.DecimalField(
        _('Exchange Rate'),
        max_digits=10,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text=_('Exchange rate to base currency')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Financial validation"""
        super().clean()

        # Basic financial validation
        if self.total_amount < 0:
            raise ValidationError({'total_amount': _('Total amount cannot be negative')})

        if self.tax_amount < 0:
            raise ValidationError({'tax_amount': _('Tax amount cannot be negative')})

        if self.grand_total < 0:
            raise ValidationError({'grand_total': _('Grand total cannot be negative')})

    def recalculate_totals(self):
        """
        Recalculate document totals from lines

        NOTE: This will be moved to services layer
        """
        if not hasattr(self, 'lines'):
            return

        lines_total = Decimal('0.00')
        lines_tax = Decimal('0.00')

        for line in self.lines.all():
            if hasattr(line, 'line_total'):
                lines_total += line.line_total or Decimal('0.00')
            if hasattr(line, 'vat_amount'):
                lines_tax += line.vat_amount or Decimal('0.00')

        self.total_amount = lines_total
        self.tax_amount = lines_tax
        self.grand_total = lines_total + lines_tax

    @property
    def total_in_base_currency(self):
        """Calculate total in base currency"""
        return self.grand_total * self.exchange_rate

    @property
    def has_tax(self):
        """Check if document has tax"""
        return self.tax_amount > 0


class FinancialLineMixin(models.Model):
    """
    Mixin за редове с финансови данни

    Използва се от PurchaseOrderLine, DeliveryLine, SalesInvoiceLine
    НЕ се използва от PurchaseRequestLine (само заявка без цени)
    """

    # =====================
    # PRICING
    # =====================
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price per unit')
    )

    discount_percentage = models.DecimalField(
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
    # LINE TOTALS
    # =====================
    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total for this line before tax')
    )

    # =====================
    # VAT/TAX
    # =====================
    vat_rate = models.DecimalField(
        _('VAT Rate %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        help_text=_('VAT rate percentage')
    )

    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Calculated VAT amount')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Financial line validation"""
        super().clean()

        if self.unit_price < 0:
            raise ValidationError({'unit_price': _('Unit price cannot be negative')})

        if self.discount_percentage < 0 or self.discount_percentage > 100:
            raise ValidationError({'discount_percentage': _('Discount percentage must be between 0 and 100')})

    def calculate_line_total(self):
        """
        Calculate line total with discounts

        NOTE: This will be moved to services layer
        """
        if not hasattr(self, 'quantity'):
            return Decimal('0.00')

        base_total = self.unit_price * self.quantity

        # Apply percentage discount
        if self.discount_percentage > 0:
            discount = base_total * (self.discount_percentage / 100)
            self.discount_amount = discount

        # Apply fixed discount
        total_discount = self.discount_amount

        self.line_total = base_total - total_discount
        return self.line_total

    def calculate_vat(self):
        """
        Calculate VAT amount

        NOTE: This will be moved to services layer
        """
        if self.vat_rate > 0:
            self.vat_amount = self.line_total * (self.vat_rate / 100)
        else:
            self.vat_amount = Decimal('0.00')
        return self.vat_amount

    @property
    def total_including_vat(self):
        """Line total including VAT"""
        return self.line_total + self.vat_amount


# =====================================================
# ФАЙЛ 4: nomenclatures/mixins/payment.py
# =====================================================

# nomenclatures/mixins/payment.py
"""
Payment Mixin - EXTRACTED FROM purchases.models.base

Provides payment tracking functionality
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone


class PaymentMixin(models.Model):
    """
    Mixin за документи с плащания

    Използва се главно от DeliveryReceipt и понякога от PurchaseOrder.
    НЕ се използва от PurchaseRequest.
    """

    # =====================
    # PAYMENT STATUS
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

    # =====================
    # PAYMENT DETAILS
    # =====================
    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        blank=True,
        help_text=_('How payment was made')
    )

    payment_reference = models.CharField(
        _('Payment Reference'),
        max_length=100,
        blank=True,
        help_text=_('Bank reference, transaction ID, etc.')
    )

    # =====================
    # PAYMENT TERMS
    # =====================
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=100,
        blank=True,
        help_text=_('Payment terms and conditions')
    )

    due_date = models.DateField(
        _('Due Date'),
        null=True,
        blank=True,
        help_text=_('When payment is due')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Payment validation"""
        super().clean()

        # Payment validation
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()

    @property
    def is_overdue(self):
        """Check if payment is overdue"""
        if not self.due_date or self.is_paid:
            return False
        return timezone.now().date() > self.due_date

    @property
    def days_until_due(self):
        """Days until payment is due"""
        if not self.due_date or self.is_paid:
            return None

        delta = self.due_date - timezone.now().date()
        return delta.days


# =====================================================
# ФАЙЛ 5: nomenclatures/mixins/delivery.py
# =====================================================

# nomenclatures/mixins/delivery.py
"""
Delivery Mixin - EXTRACTED FROM purchases.models.base

Provides delivery information and tracking
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone


class DeliveryMixin(models.Model):
    """
    Mixin за документи с delivery информация

    Използва се от DeliveryReceipt.
    НЕ се използва от PurchaseRequest или PurchaseOrder.
    """

    # =====================
    # DELIVERY TIMING
    # =====================
    delivery_date = models.DateField(
        _('Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When delivery was made')
    )

    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When delivery is expected')
    )

    # =====================
    # DELIVERY ADDRESS
    # =====================
    delivery_address = models.TextField(
        _('Delivery Address'),
        blank=True,
        help_text=_('Full delivery address')
    )

    delivery_contact = models.CharField(
        _('Delivery Contact'),
        max_length=100,
        blank=True,
        help_text=_('Contact person for delivery')
    )

    delivery_phone = models.CharField(
        _('Delivery Phone'),
        max_length=20,
        blank=True,
        help_text=_('Phone number for delivery contact')
    )

    # =====================
    # DELIVERY TRACKING
    # =====================
    tracking_number = models.CharField(
        _('Tracking Number'),
        max_length=100,
        blank=True,
        help_text=_('Courier tracking number')
    )

    carrier = models.CharField(
        _('Carrier'),
        max_length=100,
        blank=True,
        help_text=_('Delivery company/carrier')
    )

    # =====================
    # DELIVERY STATUS
    # =====================
    delivery_notes = models.TextField(
        _('Delivery Notes'),
        blank=True,
        help_text=_('Notes about the delivery')
    )

    received_by = models.CharField(
        _('Received By'),
        max_length=100,
        blank=True,
        help_text=_('Who received the delivery')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Delivery validation"""
        super().clean()

        # Date validation
        if self.delivery_date and self.expected_delivery_date:
            if self.delivery_date < self.expected_delivery_date:
                # Early delivery is usually OK, just log
                pass

    @property
    def is_delivered(self):
        """Check if delivery has been made"""
        return bool(self.delivery_date)

    @property
    def is_late(self):
        """Check if delivery is late"""
        if not self.expected_delivery_date:
            return False

        compare_date = self.delivery_date or timezone.now().date()
        return compare_date > self.expected_delivery_date

    @property
    def delivery_delay_days(self):
        """Calculate delivery delay in days"""
        if not self.expected_delivery_date:
            return None

        compare_date = self.delivery_date or timezone.now().date()
        if compare_date <= self.expected_delivery_date:
            return 0

        delta = compare_date - self.expected_delivery_date
        return delta.days