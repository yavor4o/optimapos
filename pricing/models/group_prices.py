# pricing/models/group_prices.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class ProductPriceByGroupManager(models.Manager):
    """Manager for group-specific prices"""

    def active(self):
        return self.filter(is_active=True)

    def for_group(self, price_group):
        return self.filter(price_group=price_group, is_active=True)

    def for_location(self, location):
        return self.filter(location=location, is_active=True)

    def for_product(self, product):
        return self.filter(product=product, is_active=True)


class ProductPriceByGroup(models.Model):
    """Specific prices for customer groups per location"""

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='group_prices',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='group_prices',
        verbose_name=_('Product')
    )
    price_group = models.ForeignKey(
        'nomenclatures.PriceGroup',
        on_delete=models.CASCADE,
        related_name='product_group_prices',
        verbose_name=_('Price Group')
    )

    # Price
    price = models.DecimalField(
        _('Group Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Special price for this group')
    )

    # Optional minimum quantity
    min_quantity = models.DecimalField(
        _('Minimum Quantity'),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_('Minimum quantity to get this price')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = ProductPriceByGroupManager()

    class Meta:
        unique_together = ('location', 'product', 'price_group', 'min_quantity')
        verbose_name = _('Product Price by Group')
        verbose_name_plural = _('Product Prices by Group')
        ordering = ['location', 'product', 'price_group']

    def __str__(self):
        return f"{self.product.code} @ {self.location.code} / {self.price_group.name} = {self.price}"

    def clean(self):
        if self.price < 0:
            raise ValidationError({
                'price': _('Price cannot be negative')
            })

        if self.min_quantity <= 0:
            raise ValidationError({
                'min_quantity': _('Minimum quantity must be positive')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)