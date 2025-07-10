from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base import BaseNomenclature, ActiveManager


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


class POSLocation(models.Model):
    """POS локации/каси"""
    code = models.CharField(
        _('POS Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like POS01, CASH1')
    )
    name = models.CharField(
        _('POS Location Name'),
        max_length=100
    )

    # # Връзка със склад
    # warehouse = models.ForeignKey(
    #     'warehouse.Warehouse',
    #     on_delete=models.PROTECT,
    #     related_name='pos_locations',
    #     verbose_name=_('Warehouse')
    # )

    # Адрес (ако е различен от склада)
    address = models.TextField(
        _('Address'),
        blank=True
    )

    # Фискално устройство
    fiscal_device_serial = models.CharField(
        _('Fiscal Device Serial'),
        max_length=50,
        blank=True,
        unique=True,
        null=True
    )
    fiscal_device_number = models.CharField(
        _('Fiscal Device Number'),
        max_length=20,
        blank=True,
        help_text=_('Official registration number')
    )

    # Настройки
    allow_negative_stock = models.BooleanField(
        _('Allow Negative Stock Sales'),
        default=False,
        help_text=_('Whether to allow sales when stock is insufficient')
    )

    require_customer = models.BooleanField(
        _('Require Customer'),
        default=False,
        help_text=_('Whether customer selection is mandatory')
    )

    # default_customer = models.ForeignKey(
    #     'partners.Customer',
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     help_text=_('Default customer for anonymous sales')
    # )

    # Принтери
    receipt_printer = models.CharField(
        _('Receipt Printer'),
        max_length=100,
        blank=True,
        help_text=_('Receipt printer name/address')
    )

    # Работно време
    opens_at = models.TimeField(
        _('Opens At'),
        null=True,
        blank=True
    )
    closes_at = models.TimeField(
        _('Closes At'),
        null=True,
        blank=True
    )

    # Статус
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    # Одит
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Last Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('POS Location')
        verbose_name_plural = _('POS Locations')
        # ordering = ['warehouse', 'code']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.warehouse.code})"

    def clean(self):
        # Проверка на работното време
        if self.opens_at and self.closes_at:
            if self.opens_at >= self.closes_at:
                raise ValidationError({
                    'closes_at': _('Closing time must be after opening time')
                })

    def is_open_now(self):
        """Проверява дали касата работи в момента"""
        if not self.opens_at or not self.closes_at:
            return True  # Ако няма работно време - винаги отворена

        from django.utils import timezone
        now = timezone.now().time()

        if self.opens_at < self.closes_at:
            # Нормално работно време (09:00 - 18:00)
            return self.opens_at <= now <= self.closes_at
        else:
            # През полунощ (22:00 - 02:00)
            return now >= self.opens_at or now <= self.closes_at

    def get_active_session(self):
        """Връща активната касова сесия ако има такава"""
        # Това ще се имплементира в sales модула
        return None

    def can_open_session(self, user):
        """Проверява дали потребител може да отвори сесия"""
        if not self.is_active:
            return False, "POS location is not active"

        if not self.is_open_now():
            return False, "POS location is closed"

        active_session = self.get_active_session()
        if active_session:
            return False, f"Session already open by {active_session.cashier}"

        return True, None