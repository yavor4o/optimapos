from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from optimapos import settings
from .base import BaseNomenclature, ActiveManager


class Currency(models.Model):
    """Валути за работа в системата"""
    code = models.CharField(
        _('Currency Code'),
        max_length=3,
        unique=True,
        help_text=_('ISO 4217 code like BGN, EUR, USD')
    )
    name = models.CharField(
        _('Currency Name'),
        max_length=50
    )
    symbol = models.CharField(
        _('Symbol'),
        max_length=5,
        blank=True,
        help_text=_('Currency symbol like лв, €, $')
    )
    is_base = models.BooleanField(
        _('Is Base Currency'),
        default=False,
        help_text=_('Only one currency can be base')
    )
    decimal_places = models.PositiveSmallIntegerField(
        _('Decimal Places'),
        default=2,
        help_text=_('Number of decimal places for amounts')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Currency')
        verbose_name_plural = _('Currencies')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        # Само една базова валута
        if self.is_base:
            existing_base = Currency.objects.filter(
                is_base=True
            ).exclude(pk=self.pk)
            if existing_base.exists():
                raise ValidationError({
                    'is_base': _('There can be only one base currency. Current base is %s') % existing_base.first().code
                })

        # Кодът трябва да е с главни букви
        if self.code:
            self.code = self.code.upper()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class ExchangeRateManager(models.Manager):
    """Manager за работа с валутни курсове"""

    def get_rate_for_date(self, currency, date=None):
        """Връща курса за дата или последния наличен"""
        if date is None:
            date = timezone.now().date()

        rate = self.filter(
            currency=currency,
            date__lte=date,
            is_active=True
        ).order_by('-date').first()

        if not rate:
            raise ValueError(f"No exchange rate found for {currency.code} on or before {date}")

        return rate

    def get_latest_rates(self):
        """Връща последните курсове за всички валути"""
        from django.db.models import Max

        latest_dates = self.filter(is_active=True).values('currency').annotate(
            latest_date=Max('date')
        )

        rates = []
        for item in latest_dates:
            rate = self.get(
                currency_id=item['currency'],
                date=item['latest_date']
            )
            rates.append(rate)

        return rates


class ExchangeRate(models.Model):
    """Валутни курсове"""
    currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name='rates',
        verbose_name=_('Currency')
    )
    date = models.DateField(
        _('Date'),
        db_index=True
    )

    # БНБ обикновено дава курс за 1, 100 или други единици
    units = models.DecimalField(
        _('Currency Units'),
        max_digits=10,
        decimal_places=0,
        default=1,
        help_text=_('Number of currency units (e.g., 1, 100, 1000)')
    )

    buy_rate = models.DecimalField(
        _('Buy Rate'),
        max_digits=10,
        decimal_places=6,
        help_text=_('Rate when we buy this currency')
    )
    sell_rate = models.DecimalField(
        _('Sell Rate'),
        max_digits=10,
        decimal_places=6,
        help_text=_('Rate when we sell this currency')
    )
    central_rate = models.DecimalField(
        _('Central Bank Rate'),
        max_digits=10,
        decimal_places=6,
        help_text=_('Official rate from central bank')
    )

    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_exchange_rates',
        null=True,
        blank=True
    )

    # Manager
    objects = ExchangeRateManager()

    class Meta:
        verbose_name = _('Exchange Rate')
        verbose_name_plural = _('Exchange Rates')
        unique_together = ('currency', 'date')
        ordering = ['-date', 'currency']
        indexes = [
            models.Index(fields=['-date', 'currency']),
            models.Index(fields=['currency', '-date']),
        ]

    def __str__(self):
        return f"{self.currency.code} on {self.date}: {self.central_rate}"

    def clean(self):
        # Валидация на курсовете
        if any([self.buy_rate <= 0, self.sell_rate <= 0, self.central_rate <= 0]):
            raise ValidationError(_('All rates must be positive numbers'))

        # Buy rate обикновено е по-нисък от sell rate
        if self.buy_rate > self.sell_rate:
            raise ValidationError(_('Buy rate cannot be higher than sell rate'))

        # Не може курс за базова валута
        if self.currency.is_base:
            raise ValidationError(_('Cannot set exchange rate for base currency'))

        # Не може курс за бъдеща дата
        if self.date > timezone.now().date():
            raise ValidationError(_('Cannot set exchange rate for future date'))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def rate_per_unit(self):
        """Курс за 1 единица валута"""
        return self.central_rate / self.units

    def convert_to_base(self, amount, use_rate='central'):
        """Конвертира сума към базовата валута"""
        rate_map = {
            'buy': self.buy_rate,
            'sell': self.sell_rate,
            'central': self.central_rate
        }
        rate = rate_map.get(use_rate, self.central_rate)
        return (amount * rate) / self.units

    def convert_from_base(self, amount, use_rate='central'):
        """Конвертира от базовата валута"""
        rate_map = {
            'buy': self.buy_rate,
            'sell': self.sell_rate,
            'central': self.central_rate
        }
        rate = rate_map.get(use_rate, self.central_rate)
        return (amount * self.units) / rate


class TaxGroup(BaseNomenclature):
    """Данъчни групи - ДДС ставки"""
    rate = models.DecimalField(
        _('Rate (%)'),
        max_digits=5,
        decimal_places=2,
        help_text=_('Tax rate as percentage')
    )
    tax_type = models.CharField(
        _('Tax Type'),
        max_length=20,
        choices=[
            ('VAT', _('VAT/ДДС')),
            ('EXCISE', _('Excise/Акциз')),
            ('OTHER', _('Other')),
        ],
        default='VAT'
    )
    is_default = models.BooleanField(
        _('Is Default'),
        default=False,
        help_text=_('Default tax group for new products')
    )

    # За специални случаи
    is_reverse_charge = models.BooleanField(
        _('Reverse Charge'),
        default=False,
        help_text=_('For EU reverse charge mechanism')
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Tax Group')
        verbose_name_plural = _('Tax Groups')
        ordering = ['tax_type', 'rate']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'rate'],
                name='unique_tax_group_name_rate'
            ),
            models.UniqueConstraint(
                fields=['is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_tax_group'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

    def clean(self):
        # Проверка за отрицателни ставки
        if self.rate < 0:
            raise ValidationError(_('Tax rate cannot be negative'))

        # Проверка за разумни стойности
        if self.rate > 100:
            raise ValidationError(_('Tax rate cannot exceed 100%'))

    def calculate_tax(self, amount, prices_include_tax=True):
        """Изчислява данъка за дадена сума"""
        if prices_include_tax:
            # Цената включва данък - изваждаме го
            tax = amount * self.rate / (100 + self.rate)
        else:
            # Цената е без данък - добавяме го
            tax = amount * self.rate / 100

        return round(Decimal(str(tax)), 2)

    def get_amount_without_tax(self, amount_with_tax):
        """Връща сумата без данък"""
        return amount_with_tax / (1 + self.rate / 100)

    def get_amount_with_tax(self, amount_without_tax):
        """Връща сумата с данък"""
        return amount_without_tax * (1 + self.rate / 100)