# pricing/models/promotions.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class PromotionalPriceManager(models.Manager):
    """Manager for promotional prices"""

    def active(self):
        return self.filter(is_active=True)

    def for_location(self, location):
        return self.filter(location=location, is_active=True)

    def for_product(self, product):
        return self.filter(product=product, is_active=True)

    def current_promotions(self, date=None):
        """Get currently active promotions"""
        if date is None:
            date = timezone.now().date()

        return self.filter(
            start_date__lte=date,
            end_date__gte=date,
            is_active=True
        )

    def upcoming_promotions(self, days_ahead=7):
        """Get promotions starting within specified days"""
        from datetime import timedelta
        today = timezone.now().date()
        future_date = today + timedelta(days=days_ahead)

        return self.filter(
            start_date__gt=today,
            start_date__lte=future_date,
            is_active=True
        )

    def expired_promotions(self):
        """Get expired promotions"""
        today = timezone.now().date()
        return self.filter(
            end_date__lt=today,
            is_active=True
        )


class PromotionalPrice(models.Model):
    """Time-limited promotional prices"""

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='promotional_prices',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='promotional_prices',
        verbose_name=_('Product')
    )

    # Promotion details
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

    # Pricing
    promotional_price = models.DecimalField(
        _('Promotional Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Special promotional price')
    )

    # Date range
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('When the promotion becomes active')
    )
    end_date = models.DateField(
        _('End Date'),
        help_text=_('When the promotion expires')
    )

    # Quantity restrictions
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

    # Customer restrictions
    customer_groups = models.ManyToManyField(
        'nomenclatures.PriceGroup',
        blank=True,
        related_name='promotions',
        verbose_name=_('Customer Groups'),
        help_text=_('Limit promotion to specific customer groups (leave empty for all)')
    )

    # Priority for overlapping promotions
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Higher priority takes precedence when promotions overlap')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = PromotionalPriceManager()

    class Meta:
        verbose_name = _('Promotional Price')
        verbose_name_plural = _('Promotional Prices')
        ordering = ['-priority', 'start_date', 'location', 'product']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['location', 'product', 'start_date']),
        ]

    def __str__(self):
        return f"{self.name} | {self.product.code} @ {self.location.code} → {self.promotional_price}"

    def clean(self):
        # Date validation
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({
                'end_date': _('End date must be after start date')
            })

        # Price validation
        if self.promotional_price < 0:
            raise ValidationError({
                'promotional_price': _('Promotional price cannot be negative')
            })

        # Quantity validation
        if self.min_quantity <= 0:
            raise ValidationError({
                'min_quantity': _('Minimum quantity must be positive')
            })

        if self.max_quantity and self.max_quantity < self.min_quantity:
            raise ValidationError({
                'max_quantity': _('Maximum quantity cannot be less than minimum quantity')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def is_valid_now(self):
        """Check if promotion is currently valid"""
        today = timezone.now().date()
        return (
                self.is_active and
                self.start_date <= today <= self.end_date
        )

    def is_valid_for_date(self, date):
        """Check if promotion is valid for specific date"""
        return (
                self.is_active and
                self.start_date <= date <= self.end_date
        )

    def is_valid_for_quantity(self, quantity):
        """Check if quantity qualifies for promotion"""
        if quantity < self.min_quantity:
            return False

        if self.max_quantity and quantity > self.max_quantity:
            return False

        return True

    def is_valid_for_customer(self, customer):
        """Check if customer qualifies for promotion"""
        # If no customer groups specified, promotion is for everyone
        if not self.customer_groups.exists():
            return True

        # Check if customer belongs to any of the promotion groups
        if customer and hasattr(customer, 'price_group') and customer.price_group:
            return self.customer_groups.filter(id=customer.price_group.id).exists()

        return False

    def get_discount_amount(self):
        """Calculate discount amount from base price"""
        try:
            from .base_prices import ProductPrice
            base_price_obj = ProductPrice.objects.get(
                location=self.location,
                product=self.product,
                is_active=True
            )
            base_price = base_price_obj.effective_price
            return max(Decimal('0'), base_price - self.promotional_price)
        except ProductPrice.DoesNotExist:
            return Decimal('0')

    def get_discount_percentage(self):
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
                return ((base_price - self.promotional_price) / base_price) * 100
        except ProductPrice.DoesNotExist:
            pass

        return Decimal('0')

    @property
    def days_until_start(self):
        """Days until promotion starts"""
        today = timezone.now().date()
        if self.start_date > today:
            return (self.start_date - today).days
        return 0

    @property
    def days_until_end(self):
        """Days until promotion ends"""
        today = timezone.now().date()
        if self.end_date > today:
            return (self.end_date - today).days
        return 0