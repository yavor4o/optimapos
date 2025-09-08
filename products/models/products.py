# products/models/products.py


from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.urls import reverse
from decimal import Decimal
from typing import Tuple, Dict, List


# === CHOICES ===
class ProductLifecycleChoices(models.TextChoices):
    """Product lifecycle stages"""
    NEW = 'NEW', _('New Product')
    ACTIVE = 'ACTIVE', _('Active')
    PHASE_OUT = 'PHASE_OUT', _('Phasing Out')
    DISCONTINUED = 'DISCONTINUED', _('Discontinued')
    ARCHIVED = 'ARCHIVED', _('Archived')


# === MANAGERS ===
class ProductManager(models.Manager):
    """Enhanced Product Manager"""

    def active(self):
        """Get active products only"""
        return self.filter(
            lifecycle_status__in=[
                ProductLifecycleChoices.ACTIVE,
                ProductLifecycleChoices.NEW
            ]
        )

    def sellable(self):
        """Get products that can be sold"""
        return self.filter(
            lifecycle_status__in=[
                ProductLifecycleChoices.ACTIVE,
                ProductLifecycleChoices.PHASE_OUT
            ],
            sales_blocked=False
        )

    def purchasable(self):
        """Get products that can be purchased"""
        return self.filter(
            lifecycle_status__in=[
                ProductLifecycleChoices.ACTIVE,
                ProductLifecycleChoices.NEW
            ],
            purchase_blocked=False
        )

    def with_stock(self):
        """Get products with stock in any location"""
        from inventory.models import InventoryItem
        return self.filter(
            id__in=InventoryItem.objects.filter(
                current_qty__gt=0
            ).values('product_id').distinct()
        )


class Product(models.Model):
    """
    Core Product model - REFACTORED
    Stores only static product definitions
    Dynamic data (stock, costs) moved to InventoryItem
    """

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

    # === LIFECYCLE MANAGEMENT ===
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

    # === COMPUTED PROPERTIES FOR COMPATIBILITY ===

    @property
    def total_stock(self) -> Decimal:
        """
        Get total stock across all locations
        Replaces old current_stock_qty field
        """
        from inventory.models import InventoryItem
        total = InventoryItem.objects.filter(
            product=self
        ).aggregate(
            total=Sum('current_qty')
        )['total']
        return total or Decimal('0')

    @property
    def stock_by_location(self) -> Dict[str, Decimal]:
        """
        Get stock quantities by location
        Returns: {location_code: quantity}
        """
        from inventory.models import InventoryItem
        items = InventoryItem.objects.filter(
            product=self
        ).select_related('location')

        return {
            item.location.code: item.current_qty
            for item in items
        }

    @property
    def avg_cost_by_location(self) -> Dict[str, Decimal]:
        """
        Get average costs by location
        Returns: {location_code: avg_cost}
        """
        from inventory.models import InventoryItem
        items = InventoryItem.objects.filter(
            product=self
        ).select_related('location')

        return {
            item.location.code: item.avg_cost
            for item in items if item.avg_cost > 0
        }

    @property
    def weighted_avg_cost(self) -> Decimal:
        """
        Calculate weighted average cost across all locations
        Replaces old current_avg_cost field
        """
        from inventory.models import InventoryItem
        items = InventoryItem.objects.filter(
            product=self,
            current_qty__gt=0
        )

        total_value = Decimal('0')
        total_qty = Decimal('0')

        for item in items:
            total_value += item.current_qty * item.avg_cost
            total_qty += item.current_qty

        if total_qty > 0:
            return (total_value / total_qty).quantize(Decimal('0.0001'))
        return Decimal('0')

    @property
    def has_stock(self) -> bool:
        """Check if product has any stock"""
        return self.total_stock > 0

    @property
    def stock_value(self) -> Decimal:
        """Calculate total stock value across all locations"""
        from inventory.models import InventoryItem
        items = InventoryItem.objects.filter(
            product=self,
            current_qty__gt=0
        )

        total_value = Decimal('0')
        for item in items:
            total_value += item.current_qty * item.avg_cost

        return total_value.quantize(Decimal('0.01'))

    # === HELPER METHODS ===

    def get_stock_info(self, location=None) -> Dict:
        """
        Get comprehensive stock information
        Args:
            location: Optional specific location
        Returns:
            Dict with stock details
        """
        from inventory.models import InventoryItem

        if location:
            try:
                item = InventoryItem.objects.get(
                    product=self,
                    location=location
                )
                return {
                    'location': location.code,
                    'current_qty': item.current_qty,
                    'available_qty': item.available_qty,
                    'reserved_qty': item.reserved_qty,
                    'avg_cost': item.avg_cost,
                    'last_movement': item.last_movement_date,
                    'last_purchase_cost': item.last_purchase_cost,
                    'last_sale_price': item.last_sale_price,
                }
            except InventoryItem.DoesNotExist:
                return {
                    'location': location.code,
                    'current_qty': Decimal('0'),
                    'available_qty': Decimal('0'),
                    'reserved_qty': Decimal('0'),
                    'avg_cost': Decimal('0'),
                    'last_movement': None,
                    'last_purchase_cost': None,
                    'last_sale_price': None,
                }
        else:
            # Aggregate across all locations
            items = InventoryItem.objects.filter(product=self)
            return {
                'total_qty': sum(i.current_qty for i in items),
                'total_available': sum(i.available_qty for i in items),
                'total_reserved': sum(i.reserved_qty for i in items),
                'locations': [
                    {
                        'code': i.location.code,
                        'qty': i.current_qty,
                        'cost': i.avg_cost
                    }
                    for i in items if i.current_qty > 0
                ]
            }

    # === STATUS PROPERTIES ===

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
            ProductLifecycleChoices.ACTIVE,
            ProductLifecycleChoices.NEW
        ] and
                not self.purchase_blocked
        )

    @property
    def has_restrictions(self) -> bool:
        """Does this product have any restrictions?"""
        return (
                self.sales_blocked or
                self.purchase_blocked or
                self.lifecycle_status != ProductLifecycleChoices.ACTIVE
        )

    @property
    def lifecycle_badge_class(self) -> str:
        """CSS class for lifecycle status badge"""
        classes = {
            'new': 'badge-info',
            'active': 'badge-success',
            'phase_out': 'badge-warning',
            'discontinued': 'badge-danger',
            'archived': 'badge-secondary',
        }
        return classes.get(self.lifecycle_status, 'badge-secondary')

    # === EXISTING PROPERTIES (keeping for compatibility) ===

    @property
    def full_name(self) -> str:
        """Full name with brand"""
        if self.brand:
            return f"{self.brand.name} {self.name}"
        return self.name

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

    def validate_packaging_configuration(self) -> Tuple[bool, List[str]]:
        '''Validate all packaging configurations for this product'''
        issues = []

        try:
            # Check each active packaging
            for packaging in self.packagings.filter(is_active=True):
                try:
                    packaging.full_clean()
                except ValidationError as e:
                    if hasattr(e, 'message_dict'):
                        for field, errors in e.message_dict.items():
                            for error in errors:
                                issues.append(f"Packaging {packaging.unit.name}: {error}")
                    else:
                        issues.append(f"Packaging {packaging.unit.name}: {str(e)}")

            # Additional business rule checks for PIECE products
            if self.unit_type == 'PIECE':
                for packaging in self.packagings.filter(is_active=True):
                    if packaging.conversion_factor != int(packaging.conversion_factor):
                        issues.append(
                            f"PIECE product has fractional packaging: "
                            f"{packaging.conversion_factor} {packaging.unit.name}"
                        )

            return len(issues) == 0, issues

        except Exception as e:
            return False, [f"Validation error: {str(e)}"]

    def get_problematic_packagings(self) -> List[Dict]:
        '''Get list of packaging configurations that violate business rules'''
        problems = []

        if self.unit_type == 'PIECE':
            for packaging in self.packagings.filter(is_active=True):
                if packaging.conversion_factor != int(packaging.conversion_factor):
                    problems.append({
                        'packaging': packaging,
                        'issue': 'fractional_conversion',
                        'current_factor': packaging.conversion_factor,
                        'suggested_factor': round(packaging.conversion_factor),
                        'severity': 'error'
                    })

        return problems

    def get_packaging_consistency_report(self) -> Dict:
        '''Get detailed packaging consistency analysis'''
        packagings = list(self.packagings.filter(is_active=True))
        report = {
            'is_consistent': True,
            'total_packagings': len(packagings),
            'unit_type': self.unit_type,
            'issues': [],
            'warnings': [],
            'conversion_matrix': {},
            'recommendations': []
        }

        if len(packagings) == 0:
            report['warnings'].append('No packaging configurations defined')
            return report

        # Build conversion matrix
        for pkg1 in packagings:
            report['conversion_matrix'][pkg1.unit.name] = {}

            for pkg2 in packagings:
                if pkg1 != pkg2:
                    ratio = pkg1.conversion_factor / pkg2.conversion_factor if pkg2.conversion_factor != 0 else 0

                    conversion_info = {
                        'ratio': float(ratio),
                        'is_whole': ratio == int(ratio) if ratio > 0 else False,
                        'problematic': False
                    }

                    # Check for PIECE product issues
                    if self.unit_type == 'PIECE' and ratio > 0:
                        if ratio != int(ratio):
                            conversion_info['problematic'] = True
                            report['issues'].append(
                                f"{pkg1.unit.name} to {pkg2.unit.name} creates fractional units ({ratio:.3f})"
                            )
                            report['is_consistent'] = False

                    report['conversion_matrix'][pkg1.unit.name][pkg2.unit.name] = conversion_info

        # Generate recommendations
        if not report['is_consistent'] and self.unit_type == 'PIECE':
            report['recommendations'].extend([
                'Use whole number conversion factors only for PIECE products',
                'Consider adjusting packaging sizes to create.html clean conversions',
                'Example: Instead of 12.5 pieces/box, use 12 or 13 pieces/box'
            ])

        return report

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

        # Stock check if location provided
        if location and not self.allow_negative_sales:
            from inventory.models import InventoryItem
            try:
                item = InventoryItem.objects.get(
                    product=self,
                    location=location
                )
                if item.available_qty < quantity:
                    return False, f"Insufficient stock. Available: {item.available_qty}"
            except InventoryItem.DoesNotExist:
                if not location.allow_negative_stock:
                    return False, "No stock available"

        return True, "OK"

    def get_valid_purchase_units(self) -> List:
        """Get valid units for purchasing"""
        units = [self.base_unit]

        # Add packaging units
        for pkg in self.packagings.filter(is_active=True, allow_purchase=True):
            if pkg.unit not in units:
                units.append(pkg.unit)

        return units

    def is_unit_compatible(self, unit):
        """
        Check if unit is compatible with this product
        Uses existing packaging system for validation
        """
        if not unit:
            return False

        # Base unit is always compatible
        if self.base_unit == unit:
            return True

        # Check if unit exists in product's packaging configurations
        # Използва съществуващия packagings related manager
        return self.packagings.filter(
            unit=unit,
            is_active=True
        ).exists()

    def get_valid_sale_units(self) -> List:
        """Get valid units for selling"""
        units = [self.base_unit]

        # Add packaging units
        for pkg in self.packagings.filter(is_active=True, allow_sale=True):
            if pkg.unit not in units:
                units.append(pkg.unit)

        return units

    def get_active_barcodes(self) -> models.QuerySet:
        """Get all active barcodes"""
        return self.barcodes.filter(is_active=True)

    def get_active_packagings(self) -> models.QuerySet:
        """Get all active packagings"""
        return self.packagings.filter(is_active=True)

    def can_be_sold_by_weight(self) -> bool:
        """Can be sold by weight"""
        return self.unit_type == self.WEIGHT and self.has_plu_codes()

    def has_plu_codes(self) -> bool:
        """Has any PLU codes"""
        return self.plu_codes.filter(is_active=True).exists()

    def get_absolute_url(self):
        """Get URL for product detail view"""
        return reverse('products:product_detail', kwargs={'pk': self.pk})


class ProductPLU(models.Model):
    """
    PLU кодове за продукти (главно за везни)
    PLU = Price Look-Up codes за продукти продавани на тегло
    """

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

    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

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