# pricing/models/groups.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class PriceGroupManager(models.Manager):
    """Manager for price groups"""

    def active(self):
        return self.filter(is_active=True)

    def with_customers(self):
        return self.filter(
            customers__isnull=False,
            is_active=True
        ).distinct()

    def by_discount_range(self, min_discount=0, max_discount=100):
        return self.filter(
            default_discount_percentage__gte=min_discount,
            default_discount_percentage__lte=max_discount,
            is_active=True
        )


class PriceGroup(models.Model):
    """Customer price groups for differential pricing"""

    name = models.CharField(
        _('Price Group Name'),
        max_length=100,
        unique=True
    )
    code = models.CharField(
        _('Code'),
        max_length=20,
        unique=True,
        help_text=_('Short code for quick reference')
    )
    description = models.TextField(
        _('Description'),
        blank=True
    )

    # Default discount for this group
    default_discount_percentage = models.DecimalField(
        _('Default Discount %'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Default discount percentage for this group')
    )

    # Priority for overlapping rules
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Higher priority = takes precedence in conflicts')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = PriceGroupManager()

    class Meta:
        verbose_name = _('Price Group')
        verbose_name_plural = _('Price Groups')
        ordering = ['-priority', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.upper().strip()

        if self.default_discount_percentage < 0 or self.default_discount_percentage > 100:
            raise ValidationError({
                'default_discount_percentage': _('Discount must be between 0 and 100%')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_customer_count(self):
        """Get number of customers in this price group"""
        return self.customers.filter(is_active=True).count()

    def get_product_count(self):
        """Get number of products with specific prices for this group"""
        return self.product_group_prices.filter(is_active=True).count()