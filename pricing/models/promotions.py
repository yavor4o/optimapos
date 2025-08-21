# pricing/models/promotions.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.interfaces import ILocation


class PromotionalPriceManager(models.Manager):
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

    def current_promotions(self, date=None):
        """Get currently active promotions"""
        if date is None:
            date = timezone.now().date()

        return self.filter(
            start_date__lte=date,
            end_date__gte=date,
            is_active=True
        )

    def for_product(self, product, location=None, date=None):
        """Get promotions for specific product"""
        qs = self.filter(product=product, is_active=True)

        if location:
            content_type = ContentType.objects.get_for_model(location.__class__)
            qs = qs.filter(content_type=content_type, object_id=location.pk)

        if date:
            qs = qs.filter(start_date__lte=date, end_date__gte=date)

        return qs.order_by('-priority', 'start_date')


class PromotionalPrice(models.Model):
    """Promotional pricing per location with date ranges"""

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
        related_name='promotional_prices',
        verbose_name=_('Product')
    )

    # =====================
    # PROMOTION DETAILS
    # =====================
    name = models.CharField(
        _('Promotion Name'),
        max_length=100,
        help_text=_('Descriptive name for this promotion')
    )

    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of the promotion')
    )

    promotional_price = models.DecimalField(
        _('Promotional Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Special promotional price')
    )

    # =====================
    # DATE RANGE
    # =====================
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('When the promotion becomes active')
    )
    end_date = models.DateField(
        _('End Date'),
        help_text=_('When the promotion expires')
    )

    # =====================
    # QUANTITY RESTRICTIONS
    # =====================
    min_quantity = models.DecimalField(
        _('Minimum Quantity'),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_('Minimum quantity to get promotional price')
    )

    max_quantity = models.DecimalField(
        _('Maximum Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Maximum quantity per transaction (optional)')
    )

    # =====================
    # CUSTOMER RESTRICTIONS
    # =====================
    customer_groups = models.ManyToManyField(
        'nomenclatures.PriceGroup',
        blank=True,
        related_name='promotions',
        verbose_name=_('Customer Groups'),
        help_text=_('Limit promotion to specific customer groups (leave empty for all)')
    )

    # =====================
    # PRIORITY & STATUS
    # =====================
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Higher priority takes precedence when promotions overlap')
    )

    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = PromotionalPriceManager()

    class Meta:
        verbose_name = _('Promotional Price')
        verbose_name_plural = _('Promotional Prices')
        ordering = ['-priority', 'start_date']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['product', 'start_date']),
        ]

    def __str__(self):
        location_str = str(self.priceable_location) if self.priceable_location else 'Unknown'
        return f"{self.name} - {self.product.code} @ {location_str}: {self.promotional_price}"



    # =====================
    # BUSINESS LOGIC
    # =====================
    def is_valid_for_date(self, date=None):
        """Check if promotion is valid for given date"""
        if date is None:
            date = timezone.now().date()
        return self.start_date <= date <= self.end_date

    def is_valid_for_quantity(self, quantity):
        """Check if promotion is valid for given quantity"""
        if quantity < self.min_quantity:
            return False
        if self.max_quantity and quantity > self.max_quantity:
            return False
        return True