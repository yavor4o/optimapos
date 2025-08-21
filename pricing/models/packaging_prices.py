# pricing/models/packaging_prices.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.interfaces import ILocation

class PackagingPriceManager(models.Manager):
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
        return self.filter(
            packaging__product=product,
            is_active=True
        )

    def for_packaging(self, packaging):
        return self.filter(packaging=packaging, is_active=True)


class PackagingPrice(models.Model):
    """Specific prices for product packagings per location"""

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
    packaging = models.ForeignKey(
        'products.ProductPackaging',
        on_delete=models.CASCADE,
        related_name='location_prices',
        verbose_name=_('Packaging')
    )

    # =====================
    # PRICING DATA
    # =====================
    price = models.DecimalField(
        _('Packaging Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price for the entire packaging unit')
    )

    pricing_method = models.CharField(
        _('Pricing Method'),
        max_length=20,
        choices=[
            ('FIXED', _('Fixed Price')),
            ('MARKUP', _('Markup on Base Unit')),
            ('AUTO', _('Auto (from base unit price)')),
        ],
        default='FIXED'
    )

    markup_percentage = models.DecimalField(
        _('Markup Percentage'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Markup % over base unit price')
    )

    discount_percentage = models.DecimalField(
        _('Discount Percentage'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Discount % from calculated base price')
    )

    # Status & Audit
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = PackagingPriceManager()

    class Meta:
        verbose_name = _('Packaging Price')
        verbose_name_plural = _('Packaging Prices')
        unique_together = [('content_type', 'object_id', 'packaging')]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['packaging', 'is_active']),
        ]

    def __str__(self):
        location_str = str(self.priceable_location) if self.priceable_location else 'Unknown'
        return f"{self.packaging} @ {location_str}: {self.price}"

