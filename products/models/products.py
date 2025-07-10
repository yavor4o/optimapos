from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone
from .base import ProductType, ProductGroup, Brand


class ProductManager(models.Manager):
    """Custom manager for products"""

    def active(self):
        return self.filter(is_active=True)

    def by_type(self, product_type):
        return self.filter(product_type=product_type, is_active=True)

    def by_group(self, group):
        return self.filter(product_group=group, is_active=True)

    def weight_based(self):
        return self.filter(unit_type=Product.WEIGHT, is_active=True)

    def with_plu(self):
        return self.filter(
            models.Q(primary_plu__isnull=False) |
            models.Q(plu_codes__isnull=False),
            is_active=True
        ).distinct()


class Product(models.Model):
    """Core product model - clean data only, NO business logic"""

    # Unit types
    PIECE = 'PIECE'
    WEIGHT = 'WEIGHT'
    VOLUME = 'VOLUME'
    LENGTH = 'LENGTH'

    UNIT_TYPE_CHOICES = [
        (PIECE, _('Piece/Count')),
        (WEIGHT, _('Weight (kg, g)')),
        (VOLUME, _('Volume (l, ml)')),
        (LENGTH, _('Length (m, cm)')),
    ]

    # Basic identification
    code = models.CharField(
        _('Product Code'),
        max_length=50,
        unique=True,
        help_text=_('Unique internal product code')
    )
    name = models.CharField(_('Product Name'), max_length=255)

    # Classification
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Brand')
    )
    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Product Group')
    )


    # Unit configuration
    base_unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Base Unit')
    )
    unit_type = models.CharField(
        _('Unit Type'),
        max_length=10,
        choices=UNIT_TYPE_CHOICES,
        default=PIECE,
        help_text=_('Defines how this product is measured/sold')
    )

    # Tax configuration
    tax_group = models.ForeignKey(
        'nomenclatures.TaxGroup',
        on_delete=models.PROTECT,
        verbose_name=_('Tax Group')
    )

    # PLU codes (for weight-based products)
    primary_plu = models.CharField(
        _('Primary PLU Code'),
        max_length=10,
        blank=True,
        help_text=_('Main PLU code for weight-based products')
    )

    # Inventory tracking
    track_batches = models.BooleanField(
        _('Track Batches'),
        default=False,
        help_text=_('Enable batch/lot tracking for this product')
    )

    # Moving Average Cost fields
    current_avg_cost = models.DecimalField(
        _('Current Average Cost'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Weighted average purchase cost')
    )
    current_stock_qty = models.DecimalField(
        _('Current Stock Quantity'),
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Total quantity across all locations')
    )

    # Last purchase tracking
    last_purchase_cost = models.DecimalField(
        _('Last Purchase Cost'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Cost from most recent purchase')
    )
    last_purchase_date = models.DateField(
        _('Last Purchase Date'),
        null=True,
        blank=True
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = ProductManager()

    class Meta:
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active', 'product_group']),
            models.Index(fields=['unit_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        super().clean()

        # Code validation
        if self.code:
            self.code = self.code.upper().strip()

        # Name validation
        if self.name:
            self.name = self.name.strip()

        # Negative values validation
        if self.current_avg_cost < 0:
            raise ValidationError({
                'current_avg_cost': _('Average cost cannot be negative')
            })

        if self.current_stock_qty < 0:
            self.current_stock_qty = Decimal('0.000')  # Auto-correct

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ONLY simple properties, NO business logic
    @property
    def is_weight_based(self):
        """Check if product is sold by weight"""
        return self.unit_type == self.WEIGHT

    @property
    def has_stock(self):
        """Check if product has available stock"""
        return self.current_stock_qty > 0

    @property
    def primary_plu_code(self):
        """Get primary PLU code from ProductPLU model"""
        primary_plu = self.plu_codes.filter(is_primary=True).first()
        return primary_plu.plu_code if primary_plu else None


class ProductPLU(models.Model):
    """Multiple PLU codes per product"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='plu_codes',
        verbose_name=_('Product')
    )
    plu_code = models.CharField(
        _('PLU Code'),
        max_length=10,
        help_text=_('PLU code for weight-based products')
    )
    is_primary = models.BooleanField(
        _('Is Primary'),
        default=False,
        help_text=_('Primary PLU code for this product')
    )
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Higher priority = preferred when conflicts')
    )
    description = models.CharField(
        _('Description'),
        max_length=100,
        blank=True
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Product PLU Code')
        verbose_name_plural = _('Product PLU Codes')
        unique_together = ('product', 'plu_code')
        ordering = ['-priority', '-is_primary', 'plu_code']
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_primary=True),
                name='unique_primary_plu_per_product'
            )
        ]

    def __str__(self):
        primary_indicator = " (Primary)" if self.is_primary else ""
        return f"{self.product.code} - PLU: {self.plu_code}{primary_indicator}"

    def clean(self):
        super().clean()
        if self.plu_code:
            self.plu_code = self.plu_code.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)