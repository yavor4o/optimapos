# pricing/models/group_prices.py - REFACTORED

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.interfaces import ILocation

class ProductPriceByGroupManager(models.Manager):
    """Updated manager с GenericForeignKey support"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location: ILocation):
        """Get prices for any ILocation"""
        content_type = ContentType.objects.get_for_model(location.__class__)
        return self.filter(
            content_type=content_type,
            object_id=location.pk,
            is_active=True
        )

    def for_group(self, price_group):
        return self.filter(price_group=price_group, is_active=True)

    def for_product(self, product):
        return self.filter(product=product, is_active=True)


class ProductPriceByGroup(models.Model):
    """Special prices for customer groups per location"""

    # =====================
    # GENERIC LOCATION RELATIONSHIP
    # =====================
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_('Location Type')
    )
    object_id = models.PositiveIntegerField(verbose_name=_('Location ID'))
    priceable_location = GenericForeignKey('content_type', 'object_id')

    # =====================
    # RELATIONSHIPS
    # =====================
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

    # =====================
    # PRICING DATA
    # =====================
    price = models.DecimalField(
        _('Group Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Special price for this group')
    )

    min_quantity = models.DecimalField(
        _('Minimum Quantity'),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_('Minimum quantity to get this price')
    )

    # Status & Audit
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = ProductPriceByGroupManager()

    class Meta:
        verbose_name = _('Product Price by Group')
        verbose_name_plural = _('Product Prices by Group')
        unique_together = [('content_type', 'object_id', 'product', 'price_group', 'min_quantity')]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['product', 'price_group']),
        ]

    def __str__(self):
        location_str = str(self.priceable_location) if self.priceable_location else 'Unknown'
        return f"{self.product.code} @ {location_str} ({self.price_group.name}): {self.price}"

    # =====================
    # BACKWARD COMPATIBILITY
    # =====================
    @property
    def location(self) -> ILocation:
        return self.priceable_location

    @location.setter
    def location(self, value: ILocation):
        self.content_type = ContentType.objects.get_for_model(value.__class__)
        self.object_id = value.pk