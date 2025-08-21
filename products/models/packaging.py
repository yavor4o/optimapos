# products/models/packaging.py
from typing import Optional, Any, Dict

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal




class ProductPackaging(models.Model):
    """
    Опаковки на продукти (кашон, палет, и др.)

    Концепция:
    - Дефинира алтернативни единици за продукта
    - Всяка опаковка има коефициент на преобразуване към базова единица
    - Използва се за покупки и продажби в различни единици
    """

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='packagings',
        verbose_name=_('Product')
    )

    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Packaging Unit'),
        help_text=_('Unit for this packaging (e.g., Box, Pallet)')
    )

    conversion_factor = models.DecimalField(
        _('Conversion Factor'),
        max_digits=10,
        decimal_places=3,
        help_text=_('How many base units in one packaging unit')
    )

    # Purchase/Sale flags
    allow_purchase = models.BooleanField(
        _('Allow Purchase'),
        default=True,
        help_text=_('Can be used for purchasing')
    )

    allow_sale = models.BooleanField(
        _('Allow Sale'),
        default=True,
        help_text=_('Can be used for selling')
    )

    is_default_sale_unit = models.BooleanField(
        _('Default Sale Unit'),
        default=False,
        help_text=_('Default unit for sales')
    )

    is_default_purchase_unit = models.BooleanField(
        _('Default Purchase Unit'),
        default=False,
        help_text=_('Default unit for purchases')
    )

    # Physical properties
    weight_kg = models.DecimalField(
        _('Weight (kg)'),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Weight of packaging in kilograms')
    )

    volume_m3 = models.DecimalField(
        _('Volume (m³)'),
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Volume of packaging in cubic meters')
    )

    # Dimensions
    length_cm = models.DecimalField(
        _('Length (cm)'),
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True
    )

    width_cm = models.DecimalField(
        _('Width (cm)'),
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True
    )

    height_cm = models.DecimalField(
        _('Height (cm)'),
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True
    )

    # Status
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    # Audit
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Product Packaging')
        verbose_name_plural = _('Product Packagings')
        ordering = ['product', 'conversion_factor']
        unique_together = ('product', 'unit')
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

        # Не може опаковката да е същата като базовата единица
        if self.unit == self.product.base_unit:
            raise ValidationError({
                'unit': _('Packaging unit cannot be the same as base unit')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # === HELPER METHODS ===

    def convert_to_base_units(self, packaging_qty: Decimal) -> Decimal:
        """
        Конвертира количество опаковки към базови единици
        Например: 5 кашона * 12 = 60 бройки
        """
        return packaging_qty * self.conversion_factor

    def convert_from_base_units(self, base_qty: Decimal) -> Decimal:
        """
        Конвертира от базови единици към опаковки
        Например: 60 бройки / 12 = 5 кашона
        """
        if self.conversion_factor > 0:
            return base_qty / self.conversion_factor
        return Decimal('0')

    @property
    def calculated_volume(self) -> Decimal:
        """Calculate volume from dimensions if not set"""
        if self.volume_m3:
            return self.volume_m3

        if self.length_cm and self.width_cm and self.height_cm:
            # Convert cm³ to m³
            volume_cm3 = self.length_cm * self.width_cm * self.height_cm
            return volume_cm3 / Decimal('1000000')

        return Decimal('0')


class ProductBarcode(models.Model):
    """
    Баркодове на продукти

    Концепция:
    - Всеки продукт може да има множество баркодове
    - Баркодовете могат да са за различни опаковки
    - Автоматично разпознаване на тип баркод
    """

    # Типове баркодове
    STANDARD = 'STANDARD'
    WEIGHT = 'WEIGHT'  # 28xxxxx за везни
    INTERNAL = 'INTERNAL'  # Вътрешни кодове

    BARCODE_TYPE_CHOICES = [
        (STANDARD, _('Standard EAN/UPC')),
        (WEIGHT, _('Weight-based (28xxx)')),
        (INTERNAL, _('Internal Code')),
    ]

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='barcodes',
        verbose_name=_('Product')
    )

    barcode = models.CharField(
        _('Barcode'),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_('Barcode value (EAN-13, EAN-8, etc.)')
    )

    packaging = models.ForeignKey(
        'products.ProductPackaging',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Packaging'),
        help_text=_('За коя опаковка е този баркод')
    )

    is_primary = models.BooleanField(
        _('Is Primary'),
        default=False,
        help_text=_('Основен баркод за този продукт')
    )

    barcode_type = models.CharField(
        _('Barcode Type'),
        max_length=10,
        choices=BARCODE_TYPE_CHOICES,
        default=STANDARD
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
        primary = " (Primary)" if self.is_primary else ""
        pkg = f" [{self.packaging.unit.code}]" if self.packaging else ""
        return f"{self.barcode}{pkg}{primary}"

    def clean(self):
        super().clean()

        if self.barcode:
            self.barcode = self.barcode.strip()

        # Проверка дали packaging е от същия продукт
        if self.packaging and self.packaging.product != self.product:
            raise ValidationError({
                'packaging': _('Packaging must belong to the same product')
            })

        # Автоматично разпознаване на тип баркод
        if self.barcode.startswith('28') and len(self.barcode) == 13:
            self.barcode_type = self.WEIGHT
        elif len(self.barcode) in [8, 12, 13, 14]:
            self.barcode_type = self.STANDARD
        else:
            self.barcode_type = self.INTERNAL

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # === HELPER METHODS ===

    @property
    def quantity_in_base_units(self) -> Decimal:
        """
        Количество в базови единици, което представлява този баркод
        """
        if self.packaging:
            return self.packaging.conversion_factor
        return Decimal('1.000')

    @property
    def display_unit(self):
        """Мерната единица за показване"""
        if self.packaging:
            return self.packaging.unit
        return self.product.base_unit

    def decode_weight_barcode(self) -> Optional[Dict[str, Any]]:
        """
        Декодира везни баркод (28xxxxx)

        Формат: 28PPPPPWWWWWC
        - 28: префикс
        - PPPPP: код на продукта
        - WWWWW: тегло (в грамове или стотинки)
        - C: контролно число

        Returns: dict с декодирани данни или None
        """
        if self.barcode_type != self.WEIGHT or len(self.barcode) != 13:
            return None

        try:
            product_code = self.barcode[2:7]
            weight_str = self.barcode[7:12]
            weight_value = int(weight_str)

            # Обикновено е в грамове, но може да е и в стотинки (за цена)
            weight_kg = weight_value / 1000.0

            return {
                'product_code': product_code,
                'weight_value': weight_value,
                'weight_kg': weight_kg,
                'check_digit': self.barcode[12]
            }
        except (ValueError, IndexError):
            return None

    def is_weight_barcode(self) -> bool:
        """Проверява дали е везни баркод"""
        return self.barcode_type == self.WEIGHT

    def get_product_from_weight_barcode(self):
        """
        Намира продукта от везни баркод
        Returns: Product или None
        """
        if not self.is_weight_barcode():
            return None

        decoded = self.decode_weight_barcode()
        if decoded:
            # Търси продукт по PLU код
            from .products import Product
            try:
                return Product.objects.get(
                    plu_codes__plu_code=decoded['product_code'],
                    plu_codes__is_active=True
                )
            except Product.DoesNotExist:
                return None
        return None