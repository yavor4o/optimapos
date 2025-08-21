# pricing/models/step_prices.py - REFACTORED

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.interfaces import ILocation

class ProductStepPriceManager(models.Manager):
    """Updated manager с GenericForeignKey support"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location: ILocation):
        """Get prices for any ILocation"""
        from django.db import models

        if not isinstance(location, models.Model):
            raise ValueError(f"Location must be a Django Model, got {type(location)}")

        content_type = ContentType.objects.get_for_model(location)
        return self.filter(
            content_type=content_type,
            object_id=location.pk,
            is_active=True
        )

    def for_product(self, product):
        return self.filter(product=product, is_active=True)

    def for_quantity(self, product, location, quantity):
        """Get best step price for quantity"""
        content_type = ContentType.objects.get_for_model(location.__class__)
        return self.filter(
            content_type=content_type,
            object_id=location.pk,
            product=product,
            min_quantity__lte=quantity,
            is_active=True
        ).order_by('-min_quantity').first()


class ProductStepPrice(models.Model):
    """Volume-based pricing per location"""

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
        related_name='step_prices',
        verbose_name=_('Product')
    )

    # =====================
    # STEP PRICING DATA
    # =====================
    min_quantity = models.DecimalField(
        _('Minimum Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Minimum quantity to get this price')
    )

    price = models.DecimalField(
        _('Step Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price for this quantity step')
    )

    description = models.CharField(
        _('Description'),
        max_length=100,
        blank=True,
        help_text=_('Optional description for this price step')
    )

    # Status & Audit
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = ProductStepPriceManager()

    class Meta:
        verbose_name = _('Product Step Price')
        verbose_name_plural = _('Product Step Prices')
        unique_together = [('content_type', 'object_id', 'product', 'min_quantity')]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['product', 'min_quantity']),
        ]

    def __str__(self):
        location_str = str(self.priceable_location) if self.priceable_location else 'Unknown'
        return f"{self.product.code} @ {location_str} (≥{self.min_quantity}): {self.price}"

