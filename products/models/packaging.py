from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from .products import Product


class ProductPackaging(models.Model):
    """Product packaging/unit conversions - NO PRICING"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='packagings',
        verbose_name=_('Product')
    )
    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Packaging Unit')
    )
    conversion_factor = models.DecimalField(
        _('Conversion Factor'),
        max_digits=10,
        decimal_places=4,
        help_text=_('How many base units in this packaging')
    )
    is_default_sale_unit = models.BooleanField(
        _('Default Sale Unit'),
        default=False,
        help_text=_('Default unit for POS sales')
    )
    is_default_purchase_unit = models.BooleanField(
        _('Default Purchase Unit'),
        default=False,
        help_text=_('Default unit for purchases')
    )

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Product Packaging')
        verbose_name_plural = _('Product Packagings')
        unique_together = ('product', 'unit')
        ordering = ['product', '-is_default_sale_unit', 'unit']
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_default_sale_unit=True),
                name='unique_default_sale_unit_per_product'
            ),
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_default_purchase_unit=True),
                name='unique_default_purchase_unit_per_product'
            )
        ]

    def __str__(self):
        return f"{self.product.code} - {self.unit.code} x{self.conversion_factor}"

    def clean(self):
        super().clean()

        if self.conversion_factor <= 0:
            raise ValidationError({
                'conversion_factor': _('Conversion factor must be positive')
            })

        if self.unit == self.product.base_unit:
            raise ValidationError({
                'unit': _('Packaging unit cannot be the same as base unit')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductBarcode(models.Model):
    """Product barcodes"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='barcodes',
        verbose_name=_('Product')
    )
    barcode = models.CharField(
        _('Barcode'),
        max_length=50,
        unique=True,
        help_text=_('EAN13, UPC, or internal barcode')
    )
    packaging = models.ForeignKey(
        ProductPackaging,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Packaging')
    )
    is_primary = models.BooleanField(
        _('Is Primary'),
        default=False,
        help_text=_('Primary barcode for this product')
    )

    # Barcode type detection
    STANDARD = 'STANDARD'
    WEIGHT = 'WEIGHT'
    INTERNAL = 'INTERNAL'

    BARCODE_TYPE_CHOICES = [
        (STANDARD, _('Standard EAN/UPC')),
        (WEIGHT, _('Weight-based (28xxx)')),
        (INTERNAL, _('Internal Code')),
    ]

    barcode_type = models.CharField(
        _('Barcode Type'),
        max_length=10,
        choices=BARCODE_TYPE_CHOICES,
        default=STANDARD
    )

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Product Barcode')
        verbose_name_plural = _('Product Barcodes')
        ordering = ['product', '-is_primary', 'barcode']
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_primary=True),
                name='unique_primary_barcode_per_product'
            )
        ]

    def __str__(self):
        packaging_info = f" ({self.packaging.unit.code})" if self.packaging else ""
        primary_info = " (Primary)" if self.is_primary else ""
        return f"{self.barcode}{packaging_info}{primary_info}"

    def clean(self):
        super().clean()

        if self.barcode:
            self.barcode = self.barcode.strip()

        if self.packaging and self.packaging.product != self.product:
            raise ValidationError({
                'packaging': _('Packaging must belong to the same product')
            })

        # Auto-detect barcode type
        if self.barcode.startswith('28') and len(self.barcode) == 13:
            self.barcode_type = self.WEIGHT
        elif len(self.barcode) in [8, 12, 13, 14]:
            self.barcode_type = self.STANDARD
        else:
            self.barcode_type = self.INTERNAL

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def quantity_in_base_units(self):
        """Get quantity in base units this barcode represents"""
        if self.packaging:
            return self.packaging.conversion_factor
        return Decimal('1.000')