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