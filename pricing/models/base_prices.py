# pricing/models/base_prices.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class ProductPriceManager(models.Manager):
    """Manager for product base prices"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location):
        return self.filter(location=location, is_active=True)

    def for_product(self, product):
        return self.filter(product=product, is_active=True)

    def with_markup_above(self, percentage):
        """Products with markup above specified percentage"""
        return self.filter(
            markup_percentage__gte=percentage,
            is_active=True
        )


class ProductPrice(models.Model):
    """Base selling prices for products per location"""

    # Core relationship
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='product_prices',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='location_prices',
        verbose_name=_('Product')
    )

    # Pricing methods (choose one)
    base_price = models.DecimalField(
        _('Base Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Fixed base selling price')
    )

    markup_percentage = models.DecimalField(
        _('Markup Percentage'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Markup % over cost price')
    )

    # Calculated field (auto-updated)
    effective_price = models.DecimalField(
        _('Effective Price'),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_('Calculated effective selling price')
    )

    # Metadata
    pricing_method = models.CharField(
        _('Pricing Method'),
        max_length=20,
        choices=[
            ('FIXED', _('Fixed Price')),
            ('MARKUP', _('Markup on Cost')),
            ('AUTO', _('Auto (Location Default)')),
        ],
        default='FIXED'
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    last_cost_update = models.DateTimeField(
        _('Last Cost Update'),
        null=True,
        blank=True
    )

    objects = ProductPriceManager()

    class Meta:
        unique_together = ('location', 'product')
        verbose_name = _('Product Price')
        verbose_name_plural = _('Product Prices')
        ordering = ['location', 'product']

    def __str__(self):
        return f"{self.product.code} @ {self.location.code}: {self.effective_price}"

    def clean(self):
        # Validate pricing method consistency
        if self.pricing_method == 'FIXED' and not self.base_price:
            raise ValidationError({
                'base_price': _('Base price is required for fixed pricing')
            })

        if self.pricing_method == 'MARKUP' and not self.markup_percentage:
            raise ValidationError({
                'markup_percentage': _('Markup percentage is required for markup pricing')
            })

        # Validate positive values
        if self.base_price and self.base_price < 0:
            raise ValidationError({
                'base_price': _('Base price cannot be negative')
            })

        if self.markup_percentage and self.markup_percentage < 0:
            raise ValidationError({
                'markup_percentage': _('Markup percentage cannot be negative')
            })

    def save(self, *args, **kwargs):
        # Calculate effective price before saving
        self.calculate_effective_price()
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate_effective_price(self):
        """Calculate effective selling price based on pricing method"""
        if self.pricing_method == 'FIXED' and self.base_price:
            self.effective_price = self.base_price

        elif self.pricing_method == 'MARKUP' and self.markup_percentage:
            # Get current cost from inventory
            cost_price = self.get_current_cost_price()
            if cost_price > 0:
                self.effective_price = cost_price * (1 + self.markup_percentage / 100)
            else:
                self.effective_price = Decimal('0')

        elif self.pricing_method == 'AUTO':
            # Use location's default markup
            cost_price = self.get_current_cost_price()
            if cost_price > 0 and hasattr(self.location, 'default_markup_percentage'):
                default_markup = getattr(self.location, 'default_markup_percentage', 30)
                self.effective_price = cost_price * (1 + default_markup / 100)
            else:
                self.effective_price = Decimal('0')

        # Round to 2 decimal places
        self.effective_price = round(self.effective_price, 2)

    def get_current_cost_price(self):
        """Get current cost price from inventory"""
        try:
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(
                location=self.location,
                product=self.product
            )
            return item.avg_cost
        except:
            # Fallback to product's average cost
            return self.product.current_avg_cost or Decimal('0')

    def get_profit_margin(self):
        """Calculate profit margin percentage"""
        cost_price = self.get_current_cost_price()
        if cost_price > 0 and self.effective_price > 0:
            return ((self.effective_price - cost_price) / self.effective_price) * 100
        return Decimal('0')

    def get_markup_amount(self):
        """Calculate markup amount in currency"""
        cost_price = self.get_current_cost_price()
        return max(Decimal('0'), self.effective_price - cost_price)