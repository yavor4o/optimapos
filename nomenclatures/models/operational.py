from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base_nomenclature import BaseNomenclature, ActiveManager


class UnitOfMeasure(BaseNomenclature):
    """Мерни единици"""
    # Типове единици
    PIECE = 'PIECE'
    WEIGHT = 'WEIGHT'
    VOLUME = 'VOLUME'
    LENGTH = 'LENGTH'
    AREA = 'AREA'

    UNIT_TYPE_CHOICES = [
        (PIECE, _('Piece/Count')),
        (WEIGHT, _('Weight')),
        (VOLUME, _('Volume')),
        (LENGTH, _('Length')),
        (AREA, _('Area')),
    ]

    unit_type = models.CharField(
        _('Unit Type'),
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default=PIECE
    )



    allow_decimals = models.BooleanField(
        _('Allow Decimals'),
        default=True,
        help_text=_('Whether fractional quantities are allowed')
    )

    decimal_places = models.PositiveSmallIntegerField(
        _('Decimal Places'),
        default=3,
        help_text=_('Number of decimal places to display')
    )

    # Символ за показване
    symbol = models.CharField(
        _('Symbol'),
        max_length=10,
        blank=True,
        help_text=_('Display symbol (e.g., kg, л, м²)')
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Unit of Measure')
        verbose_name_plural = _('Units of Measure')
        ordering = ['unit_type', 'name']

    def __str__(self):
        if self.symbol:
            return f"{self.code} - {self.name} ({self.symbol})"
        return f"{self.code} - {self.name}"

    def clean(self):
        # Проверка за decimal places
        if not self.allow_decimals and self.decimal_places > 0:
            raise ValidationError({
                'decimal_places': _('Decimal places must be 0 when decimals are not allowed')
            })





class PaymentType(BaseNomenclature):
    """Типове плащания"""
    # Системни ключове
    CASH = 'CASH'
    CARD = 'CARD'
    BANK_TRANSFER = 'BANK'
    VOUCHER = 'VOUCHER'
    CREDIT = 'CREDIT'

    PAYMENT_KEY_CHOICES = [
        (CASH, _('Cash')),
        (CARD, _('Card')),
        (BANK_TRANSFER, _('Bank Transfer')),
        (VOUCHER, _('Voucher/Coupon')),
        (CREDIT, _('On Credit')),
    ]

    key = models.CharField(
        _('System Key'),
        max_length=20,
        unique=True,
        choices=PAYMENT_KEY_CHOICES,
        help_text=_('Internal system key for payment type')
    )

    # Характеристики
    is_cash = models.BooleanField(
        _('Is Cash Payment'),
        default=False,
        help_text=_('Whether this is a cash-based payment')
    )

    requires_reference = models.BooleanField(
        _('Requires Reference'),
        default=False,
        help_text=_('Whether reference number is required (e.g., card auth)')
    )

    allows_change = models.BooleanField(
        _('Allows Change'),
        default=False,
        help_text=_('Whether change can be given (only for cash)')
    )

    requires_approval = models.BooleanField(
        _('Requires Approval'),
        default=False,
        help_text=_('Whether manager approval is required')
    )

    # За отчети
    is_fiscal = models.BooleanField(
        _('Is Fiscal'),
        default=True,
        help_text=_('Whether to include in fiscal reports')
    )

    # Лимити
    min_amount = models.DecimalField(
        _('Minimum Amount'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Minimum allowed amount for this payment type')
    )

    max_amount = models.DecimalField(
        _('Maximum Amount'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Maximum allowed amount for this payment type')
    )

    # Подредба в POS
    sort_order = models.IntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('Display order in POS')
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Payment Type')
        verbose_name_plural = _('Payment Types')
        ordering = ['sort_order', 'code']

    def clean(self):
        # Само cash може да дава ресто
        if self.allows_change and not self.is_cash:
            raise ValidationError({
                'allows_change': _('Only cash payments can give change')
            })

        # Проверка на лимитите
        if self.min_amount and self.max_amount:
            if self.min_amount > self.max_amount:
                raise ValidationError({
                    'min_amount': _('Minimum amount cannot be greater than maximum')
                })

    def validate_amount(self, amount):
        """Проверява дали сумата е валидна за този тип плащане"""
        if self.min_amount and amount < self.min_amount:
            return False, f"Amount must be at least {self.min_amount}"

        if self.max_amount and amount > self.max_amount:
            return False, f"Amount cannot exceed {self.max_amount}"

        return True, None


