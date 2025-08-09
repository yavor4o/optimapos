# inventory/models/locations.py - REFACTORED

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class InventoryLocationManager(models.Manager):
    """Manager for inventory locations"""

    def active(self):
        return self.filter(is_active=True)

    def warehouses(self):
        return self.filter(location_type='WAREHOUSE')

    def shops(self):
        return self.filter(location_type='SHOP')

    def with_negative_stock_allowed(self):
        return self.filter(allow_negative_stock=True)


class InventoryLocation(models.Model):
    """
    Inventory locations (warehouses, shops, storage areas)
    REFACTORED: Added batch tracking settings for flexible batch control
    """

    # Location types
    WAREHOUSE = 'WAREHOUSE'
    SHOP = 'SHOP'
    STORAGE = 'STORAGE'
    VIRTUAL = 'VIRTUAL'

    LOCATION_TYPE_CHOICES = [
        (WAREHOUSE, _('Main Warehouse')),
        (SHOP, _('Shop Floor')),
        (STORAGE, _('Storage Area')),
        (VIRTUAL, _('Virtual Location'))
    ]

    # === NEW: Batch tracking modes ===
    BATCH_DISABLED = 'DISABLED'
    BATCH_OPTIONAL = 'OPTIONAL'
    BATCH_ENFORCED = 'ENFORCED'

    BATCH_TRACKING_CHOICES = [
        (BATCH_DISABLED, _('Disabled - Never use batches')),
        (BATCH_OPTIONAL, _('Optional - Follow product settings')),
        (BATCH_ENFORCED, _('Enforced - Always require batches')),
    ]

    # === CORE FIELDS ===
    code = models.CharField(
        _('Location Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like WH01, SHOP1, STOR1')
    )

    name = models.CharField(
        _('Location Name'),
        max_length=100
    )

    location_type = models.CharField(
        _('Location Type'),
        max_length=10,
        choices=LOCATION_TYPE_CHOICES,
        default=WAREHOUSE
    )

    # === BATCH TRACKING SETTINGS (NEW) ===
    batch_tracking_mode = models.CharField(
        _('Batch Tracking Mode'),
        max_length=10,
        choices=BATCH_TRACKING_CHOICES,
        default=BATCH_OPTIONAL,
        help_text=_('How this location handles batch tracking')
    )

    force_batch_on_receive = models.BooleanField(
        _('Force Batch on Receive'),
        default=False,
        help_text=_('Force batch assignment even for non-batch products')
    )

    allow_mixed_batches = models.BooleanField(
        _('Allow Mixed Batches'),
        default=True,
        help_text=_('Allow FIFO from different batches in one operation')
    )

    default_expiry_days = models.PositiveIntegerField(
        _('Default Expiry Days'),
        null=True,
        blank=True,
        help_text=_('Default expiry period for products without explicit expiry')
    )

    # === PRICING ===
    default_markup_percentage = models.DecimalField(
        _('Default Markup Percentage'),
        max_digits=5,
        decimal_places=2,
        default=30,
        help_text=_('Default markup when no specific price is set')
    )

    # === CONTACT INFO ===
    address = models.TextField(
        _('Address'),
        blank=True
    )

    phone = models.CharField(
        _('Phone'),
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        _('Email'),
        blank=True
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Manager')
    )

    # === INVENTORY SETTINGS ===
    allow_negative_stock = models.BooleanField(
        _('Allow Negative Stock'),
        default=False,
        help_text=_('Allow sales when insufficient stock')
    )

    # === STATUS ===
    is_active = models.BooleanField(_('Is Active'), default=True)

    # === AUDIT ===
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

    # === BUSINESS LOGIC METHODS ===

    def should_track_batches(self, product) -> bool:
        """
        Determine if this location should track batches for a product
        NEW METHOD: Implements flexible batch tracking logic
        """
        if self.batch_tracking_mode == self.BATCH_DISABLED:
            return False
        elif self.batch_tracking_mode == self.BATCH_ENFORCED:
            return True
        else:  # BATCH_OPTIONAL
            return product.track_batches

    def requires_batch_on_receive(self, product) -> bool:
        """
        Check if batch is required when receiving this product
        NEW METHOD: For purchase/delivery validation
        """
        if self.force_batch_on_receive:
            return True
        return self.should_track_batches(product)

    def get_batch_requirements(self, product) -> dict:
        """
        Get comprehensive batch requirements for a product at this location
        NEW METHOD: Returns detailed batch handling rules
        """
        return {
            'track_batches': self.should_track_batches(product),
            'require_on_receive': self.requires_batch_on_receive(product),
            'allow_mixed_batches': self.allow_mixed_batches,
            'force_batch_assignment': self.force_batch_on_receive,
            'default_expiry_days': self.default_expiry_days,
            'location_mode': self.batch_tracking_mode,
            'product_supports_batches': product.track_batches
        }

    def can_sell(self, product, quantity):
        """
        ENHANCED: Check if location can sell specified quantity
        Now integrates with ProductValidationService
        """
        try:
            from .items import InventoryItem
            from products.services import ProductValidationService

            # Use Products app validation service
            can_sell, message, details = ProductValidationService.can_sell_product(
                product=product,
                quantity=quantity,
                location=self
            )

            return can_sell

        except ImportError:
            # Fallback to simple check if Products app not available
            try:
                item = self.inventory_items.get(product=product)
                return item.available_qty >= quantity or self.allow_negative_stock
            except:
                return self.allow_negative_stock

    # === ANALYTICS METHODS ===

    def get_total_stock_value(self):
        """Calculate total inventory value for this location"""
        from .items import InventoryItem
        from django.db.models import Sum, F

        total = self.inventory_items.aggregate(
            total_value=Sum(F('current_qty') * F('avg_cost'))
        )['total_value']
        return total or Decimal('0')

    def get_product_count(self):
        """Get number of different products in this location"""
        return self.inventory_items.filter(current_qty__gt=0).count()

    def get_batch_statistics(self):
        """
        Get batch tracking statistics for this location
        NEW METHOD: Provides insights into batch usage
        """
        from .items import InventoryBatch

        if not hasattr(self, '_batch_stats'):
            stats = {
                'total_batches': 0,
                'unknown_batches': 0,
                'expired_batches': 0,
                'expiring_soon': 0,  # Within 30 days
                'products_with_batches': 0
            }

            try:
                from django.utils import timezone
                from datetime import timedelta

                batches = self.inventory_batches.filter(remaining_qty__gt=0)
                stats['total_batches'] = batches.count()
                stats['unknown_batches'] = batches.filter(is_unknown_batch=True).count()

                # Expiry analysis
                today = timezone.now().date()
                thirty_days = today + timedelta(days=30)

                stats['expired_batches'] = batches.filter(
                    expiry_date__lt=today
                ).count()

                stats['expiring_soon'] = batches.filter(
                    expiry_date__gte=today,
                    expiry_date__lte=thirty_days
                ).count()

                stats['products_with_batches'] = batches.values('product').distinct().count()

            except Exception as e:
                pass  # Return default stats if error

            self._batch_stats = stats

        return self._batch_stats

    def get_negative_stock_items(self):
        """
        Get products with negative stock at this location
        ENHANCED: More detailed negative stock analysis
        """
        from .items import InventoryItem

        negative_items = self.inventory_items.filter(current_qty__lt=0)

        return [
            {
                'product_code': item.product.code,
                'product_name': item.product.name,
                'current_qty': item.current_qty,
                'shortage': abs(item.current_qty),
                'value_impact': abs(item.current_qty * item.avg_cost),
                'days_negative': (
                            timezone.now().date() - item.last_movement_date).days if item.last_movement_date else 0
            }
            for item in negative_items
        ]


class POSLocation(models.Model):
    """
    POS locations/cash registers
    UNCHANGED: No modifications needed for refactoring
    """
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

    # Link to inventory location
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        related_name='pos_locations',
        verbose_name=_('Location')
    )

    # Address (if different from warehouse)
    address = models.TextField(
        _('Address'),
        blank=True
    )

    # Fiscal device
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

    # Settings
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

    # Printers
    receipt_printer = models.CharField(
        _('Receipt Printer'),
        max_length=100,
        blank=True,
        help_text=_('Receipt printer name/address')
    )

    # Working hours
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

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Last Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('POS Location')
        verbose_name_plural = _('POS Locations')

    def __str__(self):
        return f"{self.code} - {self.name}"