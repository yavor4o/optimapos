from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base import PartnerBase, PartnerScheduleBase, Weekday


class SupplierManager(models.Manager):
    """Мениджър за доставчици"""

    def active(self):
        return self.filter(is_active=True)

    def by_division(self, division):
        return self.filter(divisions__name=division, is_active=True)

    def with_delivery_today(self):
        """Доставчици които правят доставки днес"""
        from django.utils import timezone
        today = timezone.now().strftime('%a').lower()[:3]  # mon, tue, etc.

        return self.filter(
            day_schedules__day=today,
            day_schedules__makes_delivery=True,
            is_active=True
        ).distinct()


class Supplier(PartnerBase):
    """Доставчик - подобрена версия"""

    # Банкови данни
    bank = models.CharField(_('Bank'), max_length=100, blank=True)
    bank_account = models.CharField(_('Bank Account'), max_length=100, blank=True)

    # Бизнес информация
    division = models.CharField(
        _('Main Division'),
        max_length=100,
        blank=True,
        help_text=_('Primary business division')
    )
    is_internal = models.BooleanField(
        _('Internal Supplier'),
        default=False,
        help_text=_('Internal company supplier')
    )

    # Търговски условия
    payment_days = models.PositiveSmallIntegerField(
        _('Payment Terms (days)'),
        default=30,
        help_text=_('Standard payment terms in days')
    )

    # Настройки и ограничения
    delivery_blocked = models.BooleanField(
        _('Delivery Blocked'),
        default=False,
        help_text=_('Temporarily block deliveries from this supplier')
    )
    credit_limit = models.DecimalField(
        _('Credit Limit'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Maximum unpaid amount allowed')
    )

    objects = SupplierManager()

    class Meta:
        verbose_name = _('Supplier')
        verbose_name_plural = _('Suppliers')
        ordering = ['name']

    def clean(self):
        super().clean()

        # Допълнителни валидации за доставчик
        if self.payment_days < 0:
            raise ValidationError({'payment_days': _('Payment days cannot be negative')})

        if self.credit_limit < 0:
            raise ValidationError({'credit_limit': _('Credit limit cannot be negative')})

    def can_deliver(self):
        """Проверява дали доставчикът може да прави доставки"""
        return self.is_active and not self.delivery_blocked

    def get_active_divisions(self):
        """Връща активните дивизии на доставчика"""
        return self.divisions.filter(is_active=True)

    def get_delivery_days(self):
        """Връща дните в които прави доставки"""
        return self.day_schedules.filter(makes_delivery=True)

    def get_order_days(self):
        """Връща дните в които очаква заявки"""
        return self.day_schedules.filter(expects_order=True)


class SupplierDivision(models.Model):
    """Дивизии на доставчик (крафт, алкохол, храни и т.н.)"""

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='divisions',
        verbose_name=_('Supplier')
    )
    name = models.CharField(_('Division Name'), max_length=100)
    code = models.CharField(_('Division Code'), max_length=20, blank=True)
    description = models.TextField(_('Description'), blank=True)

    # Специфични настройки за дивизията
    contact_person = models.CharField(_('Contact Person'), max_length=100, blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)

    # Търговски условия специфични за дивизията
    payment_days = models.PositiveSmallIntegerField(
        _('Payment Terms (days)'),
        null=True,
        blank=True,
        help_text=_('Override supplier payment terms for this division')
    )

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Supplier Division')
        verbose_name_plural = _('Supplier Divisions')
        unique_together = ('supplier', 'name')
        ordering = ['supplier', 'name']

    def __str__(self):
        return f"{self.supplier.name} - {self.name}"

    def get_effective_payment_days(self):
        """Връща платежните дни - от дивизията или от доставчика"""
        return self.payment_days or self.supplier.payment_days


class SupplierDaySchedule(PartnerScheduleBase):
    """График на доставчика за заявки и доставки по дни"""

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='day_schedules',
        verbose_name=_('Supplier')
    )
    expects_order = models.BooleanField(
        _('Expects Order'),
        default=False,
        help_text=_('Does supplier expect orders on this day?')
    )
    makes_delivery = models.BooleanField(
        _('Makes Delivery'),
        default=False,
        help_text=_('Does supplier make deliveries on this day?')
    )

    # Допълнителни настройки
    order_deadline_time = models.TimeField(
        _('Order Deadline'),
        null=True,
        blank=True,
        help_text=_('Latest time to place orders for this day')
    )
    delivery_time_from = models.TimeField(
        _('Delivery From'),
        null=True,
        blank=True
    )
    delivery_time_to = models.TimeField(
        _('Delivery To'),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _('Supplier Day Schedule')
        verbose_name_plural = _('Supplier Day Schedules')
        unique_together = ('supplier', 'day')
        ordering = ['supplier', 'day']

    def __str__(self):
        return f"{self.supplier.name} - {self.get_day_display()}"

    def clean(self):
        super().clean()

        # Валидация на времената
        if (self.delivery_time_from and self.delivery_time_to and
                self.delivery_time_from >= self.delivery_time_to):
            raise ValidationError({
                'delivery_time_to': _('Delivery end time must be after start time')
            })