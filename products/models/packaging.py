# products/models/packaging.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class ProductPackaging(models.Model):
    """
    Опаковки на продукти

    Концепция:
    - Всеки продукт има base_unit (например "кг")
    - Може да има опаковки: кашон 12кг, палет 500кг и т.н.
    - conversion_factor показва колко base_unit има в опаковката

    Примери:
    - Продукт: Кока-Кола (base_unit: бутилка)
    - Опаковки: кашон=24 бутилки, палет=1200 бутилки
    """

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='packagings',
        verbose_name=_('Product')
    )
    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit'),
        help_text=_('Мерна единица за тази опаковка')
    )
    conversion_factor = models.DecimalField(
        _('Conversion Factor'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Колко base_unit има в тази опаковка')
    )

    # Настройки за употреба
    is_default_sale_unit = models.BooleanField(
        _('Default Sale Unit'),
        default=False,
        help_text=_('Основна единица за продажба')
    )
    is_default_purchase_unit = models.BooleanField(
        _('Default Purchase Unit'),
        default=False,
        help_text=_('Основна единица за покупка')
    )

    # Физически характеристики (опционално)
    weight_kg = models.DecimalField(
        _('Weight (kg)'),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Тегло на празната опаковка')
    )

    # Статус
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

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

    # === СВОЙСТВА ===

    @property
    def unit_price_from_base(self):
        """Ако има базова цена, пресмята цената за опаковката"""
        # Ще се използва от pricing модула
        pass

    # === МЕТОДИ ===

    def convert_to_base_units(self, packaging_qty):
        """Конвертира количество опаковки към базови единици"""
        return packaging_qty * self.conversion_factor

    def convert_from_base_units(self, base_qty):
        """Конвертира от базови единици към опаковки"""
        return base_qty / self.conversion_factor


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
        'Product',
        on_delete=models.CASCADE,
        related_name='barcodes',
        verbose_name=_('Product')
    )
    barcode = models.CharField(
        _('Barcode'),
        max_length=50,
        unique=True,
        help_text=_('EAN13, UPC или вътрешен баркод')
    )
    packaging = models.ForeignKey(
        ProductPackaging,
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

        # Опаковката трябва да принадлежи на същия продукт
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

    # === СВОЙСТВА ===

    @property
    def quantity_in_base_units(self):
        """Количество в базови единици, което представлява този баркод"""
        if self.packaging:
            return self.packaging.conversion_factor
        return Decimal('1.000')

    @property
    def display_unit(self):
        """Мерната единица за показване"""
        if self.packaging:
            return self.packaging.unit
        return self.product.base_unit

    # === МЕТОДИ ===

    def decode_weight_barcode(self):
        """
        Декодира везни баркод (28xxxxx)

        Формат: 28PPPPPWWWWC
        - 28: префикс
        - PPPPP: код на продукта  
        - WWWW: тегло в грамове
        - C: контролно число

        Returns: (product_code, weight_grams) или None
        """
        if self.barcode_type != self.WEIGHT or len(self.barcode) != 13:
            return None

        try:
            product_code = self.barcode[2:7]
            weight_str = self.barcode[7:11]
            weight_grams = int(weight_str)
            weight_kg = weight_grams / 1000.0

            return {
                'product_code': product_code,
                'weight_grams': weight_grams,
                'weight_kg': weight_kg
            }
        except (ValueError, IndexError):
            return None

    def is_weight_barcode(self):
        """Проверява дали е везни баркод"""
        return self.barcode_type == self.WEIGHT