# nomenclatures/mixins/financial.py
"""
Financial Mixins - EXTRACTED FROM purchases.models.base
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class FinancialMixin(models.Model):
    """
    Mixin за документи с финансови данни
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
        """Calculate line total with discounts"""
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
        """Calculate VAT amount"""
        if self.vat_rate > 0:
            self.vat_amount = self.line_total * (self.vat_rate / 100)
        else:
            self.vat_amount = Decimal('0.00')
        return self.vat_amount

    @property
    def total_including_vat(self):
        """Line total including VAT"""
        return self.line_total + self.vat_amount