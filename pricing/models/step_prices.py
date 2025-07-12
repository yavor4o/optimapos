# pricing/models/step_prices.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class ProductStepPriceManager(models.Manager):
    """Manager for step prices"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location):
        return self.filter(location=location, is_active=True)

    def for_product(self, product):
        return self.filter(product=product, is_active=True)

    def for_quantity(self, location, product, quantity):
        """Get applicable step price for quantity"""
        return self.filter(
            location=location,
            product=product,
            min_quantity__lte=quantity,
            is_active=True
        ).order_by('-min_quantity').first()


class ProductStepPrice(models.Model):
    """Quantity-based step pricing"""

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='step_prices',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='step_prices',
        verbose_name=_('Product')
    )

    # Step definition
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

    # Optional description for the step
    description = models.CharField(
        _('Description'),
        max_length=100,
        blank=True,
        help_text=_('Optional description for this price step')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = ProductStepPriceManager()

    class Meta:
        unique_together = ('location', 'product', 'min_quantity')
        verbose_name = _('Product Step Price')
        verbose_name_plural = _('Product Step Prices')
        ordering = ['location', 'product', 'min_quantity']

    def __str__(self):
        return f"{self.product.code} @ {self.location.code} ≥ {self.min_quantity} = {self.price}"

    def clean(self):
        if self.min_quantity <= 0:
            raise ValidationError({
                'min_quantity': _('Minimum quantity must be positive')
            })

        if self.price < 0:
            raise ValidationError({
                'price': _('Price cannot be negative')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def discount_from_base(self):
        """Calculate discount percentage from base price"""
        try:
            from .base_prices import ProductPrice
            base_price_obj = ProductPrice.objects.get(
                location=self.location,
                product=self.product,
                is_active=True
            )
            base_price = base_price_obj.effective_price

            if base_price > 0:
                return ((base_price - self.price) / base_price) * 100
        except ProductPrice.DoesNotExist:
            pass

        return Decimal('0')