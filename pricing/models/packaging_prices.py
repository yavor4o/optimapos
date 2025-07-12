# pricing/models/packaging_prices.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class PackagingPriceManager(models.Manager):
    """Manager for packaging-specific prices"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location):
        return self.filter(location=location, is_active=True)

    def for_product(self, product):
        return self.filter(
            packaging__product=product,
            is_active=True
        )

    def for_packaging(self, packaging):
        return self.filter(packaging=packaging, is_active=True)


class PackagingPrice(models.Model):
    """Specific prices for product packagings per location"""

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='packaging_prices',
        verbose_name=_('Location')
    )
    packaging = models.ForeignKey(
        'products.ProductPackaging',
        on_delete=models.CASCADE,
        related_name='location_prices',
        verbose_name=_('Packaging')
    )

    # Price for the entire packaging
    price = models.DecimalField(
        _('Packaging Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price for the entire packaging unit')
    )

    # Pricing method
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

    # Markup percentage (if using MARKUP method)
    markup_percentage = models.DecimalField(
        _('Markup Percentage'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Markup % over base unit price')
    )

    # Discount percentage (if using AUTO method)
    discount_percentage = models.DecimalField(
        _('Discount Percentage'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Discount % from calculated base price')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = PackagingPriceManager()

    class Meta:
        unique_together = ('location', 'packaging')
        verbose_name = _('Packaging Price')
        verbose_name_plural = _('Packaging Prices')
        ordering = ['location', 'packaging__product', 'packaging__unit']

    def __str__(self):
        return f"{self.packaging} @ {self.location.code}: {self.price:.2f}"

    def clean(self):
        # Validate pricing method consistency
        if self.pricing_method == 'MARKUP' and not self.markup_percentage:
            raise ValidationError({
                'markup_percentage': _('Markup percentage is required for markup pricing')
            })

        # Validate positive values
        if self.price < 0:
            raise ValidationError({
                'price': _('Price cannot be negative')
            })

        if self.markup_percentage and self.markup_percentage < 0:
            raise ValidationError({
                'markup_percentage': _('Markup percentage cannot be negative')
            })

        if self.discount_percentage < 0 or self.discount_percentage > 100:
            raise ValidationError({
                'discount_percentage': _('Discount must be between 0 and 100%')
            })

    def save(self, *args, **kwargs):
        # Calculate effective price before saving
        if self.pricing_method != 'FIXED':
            self.calculate_effective_price()

        self.full_clean()
        super().save(*args, **kwargs)

    def calculate_effective_price(self):
        """Calculate effective packaging price based on pricing method"""
        if self.pricing_method == 'FIXED':
            # Price is already set manually
            return

        # Get base unit price for this product
        try:
            from .base_prices import ProductPrice
            base_price_obj = ProductPrice.objects.get(
                location=self.location,
                product=self.packaging.product,
                is_active=True
            )
            base_unit_price = base_price_obj.effective_price
        except ProductPrice.DoesNotExist:
            # Fallback to product's average cost + default markup
            base_unit_price = self.get_fallback_base_price()

        if base_unit_price <= 0:
            self.price = Decimal('0')
            return

        # Calculate packaging price based on conversion factor
        packaging_base_price = base_unit_price * self.packaging.conversion_factor

        if self.pricing_method == 'MARKUP':
            # Apply markup
            if self.markup_percentage:
                self.price = packaging_base_price * (1 + self.markup_percentage / 100)
            else:
                self.price = packaging_base_price

        elif self.pricing_method == 'AUTO':
            # Apply discount
            self.price = packaging_base_price * (1 - self.discount_percentage / 100)

        # Round to 2 decimal places
        self.price = round(self.price, 2)

    def get_fallback_base_price(self):
        """Get fallback base unit price"""
        try:
            # Try to get cost from inventory
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(
                location=self.location,
                product=self.packaging.product
            )
            cost_price = item.avg_cost
        except:
            cost_price = self.packaging.product.current_avg_cost or Decimal('0')

        if cost_price > 0:
            # Apply default markup (30%)
            return cost_price * Decimal('1.30')

        return Decimal('0')

    def get_unit_price(self):
        """Calculate price per base unit"""
        if self.packaging.conversion_factor > 0:
            return self.price / self.packaging.conversion_factor
        return Decimal('0')

    def get_savings_from_base(self):
        """Calculate savings compared to buying individual base units"""
        try:
            from .base_prices import ProductPrice
            base_price_obj = ProductPrice.objects.get(
                location=self.location,
                product=self.packaging.product,
                is_active=True
            )
            individual_total = base_price_obj.effective_price * self.packaging.conversion_factor

            if individual_total > self.price:
                savings_amount = individual_total - self.price
                savings_percentage = (savings_amount / individual_total) * 100
                return {
                    'amount': savings_amount,
                    'percentage': savings_percentage,
                    'individual_total': individual_total
                }
        except ProductPrice.DoesNotExist:
            pass

        return {
            'amount': Decimal('0'),
            'percentage': Decimal('0'),
            'individual_total': Decimal('0')
        }

    @property
    def packaging_info(self):
        """Get packaging information"""
        return {
            'product_code': self.packaging.product.code,
            'product_name': self.packaging.product.name,
            'unit_name': self.packaging.unit.name,
            'conversion_factor': self.packaging.conversion_factor,
            'base_unit': self.packaging.product.base_unit.code
        }