# inventory/models/groups.py

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class InventoryLocationManager(models.Manager):
    """Manager for inventory locations"""

    def active(self):
        return self.filter(is_active=True)

    def shops(self):
        return self.filter(location_type='SHOP', is_active=True)

    def warehouses(self):
        return self.filter(location_type='WAREHOUSE', is_active=True)

    def storage_areas(self):
        return self.filter(location_type='STORAGE', is_active=True)


class InventoryLocation(models.Model):
    """Physical locations where inventory is held"""

    WAREHOUSE = 'WAREHOUSE'
    SHOP = 'SHOP'
    STORAGE = 'STORAGE'
    VIRTUAL = 'VIRTUAL'

    LOCATION_TYPE_CHOICES = [
        (WAREHOUSE, _('Main Warehouse')),
        (SHOP, _('Shop Floor')),
        (STORAGE, _('Storage Area')),
        (VIRTUAL, _('Virtual Location')),
    ]

    # Basic info
    code = models.CharField(
        _('Location Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like WH01, SHOP1, STOR1')
    )
    name = models.CharField(_('Location Name'), max_length=100)
    location_type = models.CharField(
        _('Location Type'),
        max_length=10,
        choices=LOCATION_TYPE_CHOICES,
        default=WAREHOUSE
    )

    default_markup_percentage = models.DecimalField(
        _('Default Markup Percentage'),
        max_digits=5,
        decimal_places=2,
        default=30,
        help_text=_('Default markup when no specific price is set')
    )

    purchase_prices_include_vat = models.BooleanField(default=False)
    sales_prices_include_vat = models.BooleanField(default=True)

    # Address and contact
    address = models.TextField(_('Address'), blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)

    # Manager
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Manager')
    )

    # Settings
    allow_negative_stock = models.BooleanField(
        _('Allow Negative Stock'),
        default=False,
        help_text=_('Allow sales when insufficient stock')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = InventoryLocationManager()

    class Meta:
        verbose_name = _('Inventory Location')
        verbose_name_plural = _('Inventory Locations')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.upper().strip()
        if self.name:
            self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_total_stock_value(self):
        """Calculate total inventory value for this location"""
        from .items import InventoryItem
        from django.db.models import Sum, F

        total = self.inventory_items.aggregate(
            total_value=Sum(F('current_qty') * F('avg_cost'))
        )['total_value']
        return total or 0

    def get_product_count(self):
        """Get number of different products in this location"""
        return self.inventory_items.filter(current_qty__gt=0).count()

    def can_sell(self, product, quantity):
        """Check if location can sell specified quantity of product"""
        try:
            from .items import InventoryItem
            item = self.inventory_items.get(product=product)
            return item.available_qty >= quantity or self.allow_negative_stock
        except InventoryItem.DoesNotExist:
            return self.allow_negative_stock


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

    # Връзка със склад
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        related_name='pos_locations',
        verbose_name=_('Location')
    )

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

    default_customer = models.ForeignKey(
        'partners.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_('Default customer for anonymous sales')
    )

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
        return f"{self.code} - {self.name} "

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