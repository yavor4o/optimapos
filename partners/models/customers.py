from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base import PartnerBase, PartnerScheduleBase


class CustomerManager(models.Manager):
    """Мениджър за клиенти"""

    def active(self):
        return self.filter(is_active=True)

    def companies(self):
        return self.filter(type=Customer.COMPANY, is_active=True)

    def individuals(self):
        return self.filter(type=Customer.PERSON, is_active=True)

    def with_credit(self):
        return self.filter(credit_limit__gt=0, is_active=True)

    def by_price_group(self, price_group):
        return self.filter(price_group=price_group, is_active=True)


class Customer(PartnerBase):
    """Клиент - подобрена версия"""

    # Тип клиент
    COMPANY = 'company'
    PERSON = 'person'

    CUSTOMER_TYPE_CHOICES = [
        (COMPANY, _('Company')),
        (PERSON, _('Individual')),
    ]

    type = models.CharField(
        _('Customer Type'),
        max_length=10,
        choices=CUSTOMER_TYPE_CHOICES,
        default=COMPANY
    )

    # Кредитен мениджмънт
    credit_limit = models.DecimalField(
        _('Credit Limit'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Maximum credit allowed')
    )
    payment_delay_days = models.PositiveSmallIntegerField(
        _('Payment Delay (days)'),
        default=0,
        help_text=_('Days of deferred payment allowed')
    )

   # Ценообразуване
    price_group = models.ForeignKey(
        'nomenclatures.PriceGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers',
        verbose_name=_('Price Group')
    )
    discount_percent = models.DecimalField(
        _('Default Discount %'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Applied when no price group is set')
    )

    # Категоризация
    CATEGORY_REGULAR = 'regular'
    CATEGORY_VIP = 'vip'
    CATEGORY_PROBLEMATIC = 'problematic'

    CATEGORY_CHOICES = [
        (CATEGORY_REGULAR, _('Regular')),
        (CATEGORY_VIP, _('VIP')),
        (CATEGORY_PROBLEMATIC, _('Problematic')),
    ]

    category = models.CharField(
        _('Category'),
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_REGULAR
    )

    # Блокировки и ограничения
    sales_blocked = models.BooleanField(
        _('Sales Blocked'),
        default=False,
        help_text=_('Block all sales to this customer')
    )
    credit_blocked = models.BooleanField(
        _('Credit Blocked'),
        default=False,
        help_text=_('Block credit sales, cash only')
    )

    objects = CustomerManager()

    class Meta:
        verbose_name = _('Customer')
        verbose_name_plural = _('Customers')
        ordering = ['name']

    def clean(self):
        super().clean()

        # Валидации
        if self.credit_limit < 0:
            raise ValidationError({'credit_limit': _('Credit limit cannot be negative')})

        if self.payment_delay_days < 0:
            raise ValidationError({'payment_delay_days': _('Payment delay cannot be negative')})

        if self.discount_percent and (self.discount_percent < 0 or self.discount_percent > 100):
            raise ValidationError({'discount_percent': _('Discount must be between 0 and 100%')})

    def can_buy(self):
        """Проверява дали клиентът може да купува"""
        return self.is_active and not self.sales_blocked

    def can_buy_on_credit(self):
        """Проверява дали клиентът може да купува на кредит"""
        return self.can_buy() and not self.credit_blocked and self.credit_limit > 0

    def get_effective_discount(self):
        """Връща ефективната отстъпка - от група или директна"""
        if self.price_group and hasattr(self.price_group, 'discount_percentage'):
            return self.price_group.discount_percentage
        return self.discount_percent or 0

    def get_delivery_days(self):
        """Връща дните в които очаква доставки"""
        return self.day_schedules.filter(expects_delivery=True)

    def get_order_days(self):
        """Връща дните в които дава заявки"""
        return self.day_schedules.filter(expects_order=True)


class CustomerSite(models.Model):
    """Обекти/адреси на клиент"""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='sites',
        verbose_name=_('Customer')
    )
    name = models.CharField(_('Site Name'), max_length=100)

    # Адресна информация
    city = models.CharField(_('City'), max_length=100, blank=True)
    address = models.TextField(_('Address'), blank=True)

    # Контакти за този обект
    contact_person = models.CharField(_('Contact Person'), max_length=100, blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)

    # Настройки специфични за обекта
    is_delivery_address = models.BooleanField(_('Delivery Address'), default=True)
    is_billing_address = models.BooleanField(_('Billing Address'), default=False)
    is_primary = models.BooleanField(_('Primary Site'), default=False)

    # Специални условия за този обект
    special_discount = models.DecimalField(
        _('Special Discount %'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Customer Site')
        verbose_name_plural = _('Customer Sites')
        unique_together = ('customer', 'name')
        ordering = ['customer', 'name']

    def __str__(self):
        return f"{self.customer.name} - {self.name}"

    def clean(self):
        super().clean()

        # Само един primary site на клиент
        if self.is_primary:
            existing_primary = CustomerSite.objects.filter(
                customer=self.customer,
                is_primary=True
            ).exclude(pk=self.pk)

            if existing_primary.exists():
                raise ValidationError({
                    'is_primary': _('Customer can have only one primary site')
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CustomerDaySchedule(PartnerScheduleBase):
    """График на клиента за получаване на заявки и доставки"""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='day_schedules',
        verbose_name=_('Customer')
    )
    expects_order = models.BooleanField(
        _('Places Orders'),
        default=False,
        help_text=_('Does customer place orders on this day?')
    )
    expects_delivery = models.BooleanField(
        _('Expects Delivery'),
        default=False,
        help_text=_('Does customer expect deliveries on this day?')
    )

    # Допълнителни настройки
    preferred_delivery_time_from = models.TimeField(
        _('Preferred Delivery From'),
        null=True,
        blank=True
    )
    preferred_delivery_time_to = models.TimeField(
        _('Preferred Delivery To'),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _('Customer Day Schedule')
        verbose_name_plural = _('Customer Day Schedules')
        unique_together = ('customer', 'day')
        ordering = ['customer', 'day']

    def __str__(self):
        return f"{self.customer.name} - {self.get_day_display()}"

    def clean(self):
        super().clean()

        # Валидация на времената
        if (self.preferred_delivery_time_from and self.preferred_delivery_time_to and
                self.preferred_delivery_time_from >= self.preferred_delivery_time_to):
            raise ValidationError({
                'preferred_delivery_time_to': _('End time must be after start time')
            })
