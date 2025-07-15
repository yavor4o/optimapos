# products/models/products.py - LIFECYCLE VERSION

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from typing import Tuple


class ProductLifecycleChoices(models.TextChoices):
    """Product lifecycle status choices"""
    DRAFT = 'DRAFT', _('Draft - In Development')
    ACTIVE = 'ACTIVE', _('Active - Normal Sales')
    PHASE_OUT = 'PHASE_OUT', _('Phase Out - Limited Sales')
    DISCONTINUED = 'DISCONTINUED', _('Discontinued - No Sales')


class ProductManager(models.Manager):
    """Enhanced manager with lifecycle filtering"""

    def sellable(self):
        """Products that can be sold"""
        return self.filter(
            lifecycle_status__in=[
                ProductLifecycleChoices.ACTIVE,
                ProductLifecycleChoices.PHASE_OUT
            ],
            sales_blocked=False
        )

    def purchasable(self):
        """Products that can be purchased from suppliers"""
        return self.filter(
            lifecycle_status__in=[
                ProductLifecycleChoices.DRAFT,
                ProductLifecycleChoices.ACTIVE
            ],
            purchase_blocked=False
        )

    def active(self):
        """Only active products"""
        return self.filter(lifecycle_status=ProductLifecycleChoices.ACTIVE)

    def phase_out(self):
        """Products being phased out"""
        return self.filter(lifecycle_status=ProductLifecycleChoices.PHASE_OUT)

    def discontinued(self):
        """Discontinued products"""
        return self.filter(lifecycle_status=ProductLifecycleChoices.DISCONTINUED)

    def draft(self):
        """Products in development"""
        return self.filter(lifecycle_status=ProductLifecycleChoices.DRAFT)

    def search(self, query):
        """Search with lifecycle consideration"""
        if not query:
            return self.none()

        return self.filter(
            models.Q(code__icontains=query) |
            models.Q(name__icontains=query) |
            models.Q(barcodes__barcode=query)
        ).distinct()


class Product(models.Model):
    """Enhanced Product model with lifecycle management"""

    # === UNIT TYPES ===
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

    # === CORE IDENTIFICATION ===
    code = models.CharField(
        _('Product Code'),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_('Unique internal product code')
    )

    name = models.CharField(
        _('Product Name'),
        max_length=255,
        db_index=True
    )

    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed product description')
    )

    # === CLASSIFICATION ===
    brand = models.ForeignKey(
        'nomenclatures.Brand',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Brand')
    )

    product_group = models.ForeignKey(
        'nomenclatures.ProductGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Product Group')
    )

    product_type = models.ForeignKey(
        'nomenclatures.ProductType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Product Type')
    )

    # === UNITS ===
    base_unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Base Unit'),
        help_text=_('Base unit for storage and calculations')
    )

    unit_type = models.CharField(
        _('Unit Type'),
        max_length=10,
        choices=UNIT_TYPE_CHOICES,
        default=PIECE,
        help_text=_('How this product is measured/sold')
    )

    # === TAX ===
    tax_group = models.ForeignKey(
        'nomenclatures.TaxGroup',
        on_delete=models.PROTECT,
        verbose_name=_('Tax Group')
    )

    # === TRACKING SETTINGS ===
    track_batches = models.BooleanField(
        _('Track Batches'),
        default=False,
        help_text=_('Enable batch/lot tracking')
    )

    track_serial_numbers = models.BooleanField(
        _('Track Serial Numbers'),
        default=False,
        help_text=_('Enable serial number tracking')
    )

    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Product requires expiry date tracking')
    )

    # === COST & STOCK DATA ===
    current_avg_cost = models.DecimalField(
        _('Current Average Cost'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Moving average cost')
    )

    current_stock_qty = models.DecimalField(
        _('Current Stock Quantity'),
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Total quantity across all locations')
    )

    # === TRANSACTION HISTORY ===
    last_purchase_cost = models.DecimalField(
        _('Last Purchase Cost'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Cost from last purchase')
    )

    last_purchase_date = models.DateTimeField(
        _('Last Purchase Date'),
        null=True,
        blank=True
    )

    last_sale_date = models.DateTimeField(
        _('Last Sale Date'),
        null=True,
        blank=True
    )

    last_sale_price = models.DecimalField(
        _('Last Sale Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    # === NEW LIFECYCLE FIELDS ===

    lifecycle_status = models.CharField(
        _('Lifecycle Status'),
        max_length=20,
        choices=ProductLifecycleChoices.choices,
        default=ProductLifecycleChoices.ACTIVE,
        db_index=True,
        help_text=_('Current product lifecycle stage')
    )

    sales_blocked = models.BooleanField(
        _('Sales Blocked'),
        default=False,
        db_index=True,
        help_text=_('Block all sales for this product')
    )

    purchase_blocked = models.BooleanField(
        _('Purchase Blocked'),
        default=False,
        db_index=True,
        help_text=_('Block all purchases for this product')
    )

    allow_negative_sales = models.BooleanField(
        _('Allow Negative Sales'),
        default=False,
        help_text=_('Allow sales when insufficient stock (overrides location setting)')
    )

    # === METADATA ===
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_products',
        verbose_name=_('Created By')
    )

    # === MANAGERS ===
    objects = ProductManager()

    class Meta:
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['lifecycle_status']),
            models.Index(fields=['sales_blocked', 'purchase_blocked']),
            models.Index(fields=['lifecycle_status', 'sales_blocked']),
            models.Index(fields=['unit_type', 'lifecycle_status']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """Enhanced validation"""
        super().clean()

        # Clean fields
        if self.code:
            self.code = self.code.upper().strip()
        if self.name:
            self.name = self.name.strip()

        # Business validation
        if self.track_serial_numbers and self.unit_type != self.PIECE:
            raise ValidationError({
                'track_serial_numbers': _('Serial numbers only for PIECE unit types')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # === COMPUTED PROPERTIES ===

    @property
    def is_sellable(self) -> bool:
        """Can this product be sold?"""
        return (
                self.lifecycle_status in [
            ProductLifecycleChoices.ACTIVE,
            ProductLifecycleChoices.PHASE_OUT
        ] and
                not self.sales_blocked
        )

    @property
    def is_purchasable(self) -> bool:
        """Can this product be purchased from suppliers?"""
        return (
                self.lifecycle_status in [
            ProductLifecycleChoices.DRAFT,
            ProductLifecycleChoices.ACTIVE
        ] and
                not self.purchase_blocked
        )

    @property
    def lifecycle_badge_class(self) -> str:
        """CSS class for status display"""
        return {
            ProductLifecycleChoices.DRAFT: 'badge-warning',
            ProductLifecycleChoices.ACTIVE: 'badge-success',
            ProductLifecycleChoices.PHASE_OUT: 'badge-info',
            ProductLifecycleChoices.DISCONTINUED: 'badge-danger'
        }.get(self.lifecycle_status, 'badge-secondary')

    @property
    def has_restrictions(self) -> bool:
        """Does this product have any restrictions?"""
        return (
                self.sales_blocked or
                self.purchase_blocked or
                self.lifecycle_status != ProductLifecycleChoices.ACTIVE
        )

    # === EXISTING PROPERTIES (keeping all) ===

    @property
    def full_name(self):
        """Full name with brand"""
        if self.brand:
            return f"{self.brand.name} {self.name}"
        return self.name

    @property
    def has_stock(self):
        """Has any stock"""
        return self.current_stock_qty > 0

    @property
    def stock_value(self):
        """Total stock value"""
        return self.current_stock_qty * self.current_avg_cost

    @property
    def primary_barcode(self):
        """Primary barcode"""
        return self.barcodes.filter(is_primary=True).first()

    @property
    def primary_plu(self):
        """Primary PLU code"""
        return self.plu_codes.filter(is_primary=True).first()

    @property
    def default_sale_packaging(self):
        """Default sale packaging"""
        return self.packagings.filter(is_default_sale_unit=True).first()

    @property
    def default_purchase_packaging(self):
        """Default purchase packaging"""
        return self.packagings.filter(is_default_purchase_unit=True).first()

    # === BUSINESS METHODS ===

    def validate_sale_quantity(self, quantity: Decimal, location=None) -> Tuple[bool, str]:
        """Validate quantity for sale"""
        # Sellability check
        if not self.is_sellable:
            return False, f"Product not sellable: {self.get_lifecycle_status_display()}"

        # Basic quantity validation
        if quantity <= 0:
            return False, "Quantity must be positive"

        # Unit type validation
        if self.unit_type == self.PIECE:
            if quantity != int(quantity):
                return False, "Piece products must be whole numbers"

        return True, "OK"

    def get_restrictions_summary(self) -> str:
        """Human-readable restrictions"""
        restrictions = []

        if not self.is_sellable:
            if self.sales_blocked:
                restrictions.append("Sales blocked")
            else:
                restrictions.append(f"Not sellable ({self.get_lifecycle_status_display()})")

        if not self.is_purchasable:
            if self.purchase_blocked:
                restrictions.append("Purchases blocked")
            else:
                restrictions.append("Not purchasable")

        if self.lifecycle_status == ProductLifecycleChoices.PHASE_OUT:
            restrictions.append("Phase-out: sell existing stock only")

        return "; ".join(restrictions) if restrictions else "No restrictions"

    # === LIFECYCLE MANAGEMENT ===

    def set_lifecycle_status(self, new_status: str, user=None, reason: str = ""):
        """Change lifecycle status with validation"""
        if new_status not in ProductLifecycleChoices.values:
            raise ValueError(f"Invalid lifecycle status: {new_status}")

        old_status = self.lifecycle_status
        self.lifecycle_status = new_status
        self.save()

        # TODO: Add audit logging in Phase 2
        return f"Lifecycle changed: {old_status} → {new_status}"

    def block_sales(self, reason: str = ""):
        """Block all sales"""
        self.sales_blocked = True
        self.save()
        return f"Sales blocked for {self.code}"

    def unblock_sales(self):
        """Unblock sales"""
        self.sales_blocked = False
        self.save()
        return f"Sales unblocked for {self.code}"

    def block_purchases(self, reason: str = ""):
        """Block all purchases"""
        self.purchase_blocked = True
        self.save()
        return f"Purchases blocked for {self.code}"

    def unblock_purchases(self):
        """Unblock purchases"""
        self.purchase_blocked = False
        self.save()
        return f"Purchases unblocked for {self.code}"

    # === EXISTING BUSINESS METHODS (keeping all) ===

    def update_average_cost(self, new_qty, new_cost):
        """Update moving average cost"""
        if new_qty <= 0:
            return

        existing_value = self.current_stock_qty * self.current_avg_cost
        new_value = new_qty * new_cost
        total_qty = self.current_stock_qty + new_qty

        if total_qty > 0:
            self.current_avg_cost = (existing_value + new_value) / total_qty
            self.current_stock_qty = total_qty

        self.last_purchase_cost = new_cost
        self.last_purchase_date = timezone.now()
        self.save(update_fields=[
            'current_avg_cost', 'current_stock_qty',
            'last_purchase_cost', 'last_purchase_date'
        ])

    def add_stock(self, quantity, cost_per_unit=None):
        """Add stock quantity"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if cost_per_unit:
            self.update_average_cost(quantity, cost_per_unit)
        else:
            self.current_stock_qty += quantity
            self.save(update_fields=['current_stock_qty'])

    def remove_stock(self, quantity):
        """Remove stock quantity"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if quantity > self.current_stock_qty:
            raise ValueError("Insufficient stock")

        self.current_stock_qty -= quantity
        self.last_sale_date = timezone.now()
        self.save(update_fields=['current_stock_qty', 'last_sale_date'])

    def get_active_barcodes(self):
        """Get all active barcodes"""
        return self.barcodes.filter(is_active=True)

    def get_active_packagings(self):
        """Get all active packagings"""
        return self.packagings.filter(is_active=True)

    def can_be_sold_by_weight(self):
        """Can be sold by weight"""
        return self.unit_type == self.WEIGHT and self.has_plu_codes()

    def has_plu_codes(self):
        """Has any PLU codes"""
        return self.plu_codes.filter(is_active=True).exists()

class ProductPLU(models.Model):
    """PLU кодове за продукти (главно за везни)"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='plu_codes',
        verbose_name=_('Product')
    )
    plu_code = models.CharField(
        _('PLU Code'),
        max_length=10,
        help_text=_('PLU код за везни продукти')
    )
    is_primary = models.BooleanField(
        _('Is Primary'),
        default=False,
        help_text=_('Основен PLU код за този продукт')
    )
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('По-висок приоритет = предпочитан при конфликти')
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
        ordering = ['-priority', '-is_primary', 'plu_code']
        unique_together = ('product', 'plu_code')
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_primary=True),
                name='unique_primary_plu_per_product'
            )
        ]

    def __str__(self):
        primary_info = " (Primary)" if self.is_primary else ""
        return f"PLU {self.plu_code}{primary_info}"

    def clean(self):
        super().clean()

        if self.plu_code:
            self.plu_code = self.plu_code.strip()

        # PLU кодовете са за везни продукти
        if self.product and self.product.unit_type != Product.WEIGHT:
            raise ValidationError({
                'product': _('PLU codes are only for weight-based products')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)