# products/models/products.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone


class ProductManager(models.Manager):
    """Мениджър за продукти с полезни методи"""

    def active(self):
        return self.filter(is_active=True)

    def by_group(self, group):
        return self.filter(product_group=group, is_active=True)

    def by_brand(self, brand):
        return self.filter(brand=brand, is_active=True)

    def with_stock(self):
        return self.filter(current_stock_qty__gt=0, is_active=True)

    def search(self, query):
        """Търсене по код, име или баркод"""
        if not query:
            return self.none()

        return self.filter(
            models.Q(code__icontains=query) |
            models.Q(name__icontains=query) |
            models.Q(barcodes__barcode=query)
        ).distinct()


class Product(models.Model):
    """
    Основен продуктов модел - сърцето на системата

    Концепция:
    - Всеки продукт има базова мерна единица (base_unit)
    - Може да има множество опаковки (ProductPackaging)
    - Може да има множество баркодове (ProductBarcode)
    - За везни продукти може да има PLU кодове (ProductPLU)
    """

    # Типове продукти по начин на продажба
    PIECE = 'PIECE'  # Брой/парче (хляб, кутии)
    WEIGHT = 'WEIGHT'  # Тегло (месо, плодове)
    VOLUME = 'VOLUME'  # Обем (течности)
    LENGTH = 'LENGTH'  # Дължина (кабели, тръби)

    UNIT_TYPE_CHOICES = [
        (PIECE, _('Piece/Count')),
        (WEIGHT, _('Weight (kg, g)')),
        (VOLUME, _('Volume (l, ml)')),
        (LENGTH, _('Length (m, cm)')),
    ]

    # === ОСНОВНА ИДЕНТИФИКАЦИЯ ===
    code = models.CharField(
        _('Product Code'),
        max_length=50,
        unique=True,
        help_text=_('Уникален вътрешен код')
    )
    name = models.CharField(
        _('Product Name'),
        max_length=255,
        db_index=True
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Подробно описание на продукта')
    )

    # === КЛАСИФИКАЦИЯ (връзки към nomenclatures) ===
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

    # === МЕРНИ ЕДИНИЦИ ===
    base_unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Base Unit'),
        help_text=_('Основна мерна единица за съхранение')
    )
    unit_type = models.CharField(
        _('Unit Type'),
        max_length=10,
        choices=UNIT_TYPE_CHOICES,
        default=PIECE,
        help_text=_('Как се мери/продава този продукт')
    )

    # === ДАНЪЧНА ГРУПА ===
    tax_group = models.ForeignKey(
        'nomenclatures.TaxGroup',
        on_delete=models.PROTECT,
        verbose_name=_('Tax Group')
    )

    # === НАСТРОЙКИ ЗА ПРОСЛЕДЯВАНЕ ===
    track_batches = models.BooleanField(
        _('Track Batches'),
        default=False,
        help_text=_('Проследяване на партиди/лотове')
    )
    track_serial_numbers = models.BooleanField(
        _('Track Serial Numbers'),
        default=False,
        help_text=_('Проследяване на серийни номера (за скъпи стоки)')
    )
    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Изисква срок на годност')
    )

    # === MOVING AVERAGE COST (MAC) ===
    current_avg_cost = models.DecimalField(
        _('Current Average Cost'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Среднопретегелна себестойност')
    )
    current_stock_qty = models.DecimalField(
        _('Current Stock Quantity'),
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Общо количество във всички складове')
    )

    # === ПОСЛЕДНА ПОКУПКА ===
    last_purchase_cost = models.DecimalField(
        _('Last Purchase Cost'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Цена от последната покупка')
    )
    last_purchase_date = models.DateTimeField(
        _('Last Purchase Date'),
        null=True,
        blank=True
    )

    # === ПОСЛЕДНА ПРОДАЖБА ===
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

    # === МЕТА ИНФОРМАЦИЯ ===
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        db_index=True
    )
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
            models.Index(fields=['is_active', 'product_group']),
            models.Index(fields=['unit_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """Валидация на продукта"""
        super().clean()

        # Почистване на полета
        if self.code:
            self.code = self.code.upper().strip()
        if self.name:
            self.name = self.name.strip()

        # Проверки за серийни номера
        if self.track_serial_numbers and self.unit_type != self.PIECE:
            raise ValidationError({
                'track_serial_numbers': _('Serial numbers can only be tracked for PIECE unit types')
            })

        # Проверки за последователност на датите
        if (self.last_purchase_date and self.last_sale_date and
                self.last_purchase_date > timezone.now()):
            raise ValidationError({
                'last_purchase_date': _('Last purchase date cannot be in the future')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # === СВОЙСТВА ===

    @property
    def full_name(self):
        """Пълно име с бранд"""
        if self.brand:
            return f"{self.brand.name} {self.name}"
        return self.name

    @property
    def has_stock(self):
        """Има ли наличност"""
        return self.current_stock_qty > 0

    @property
    def stock_value(self):
        """Стойност на наличността"""
        return self.current_stock_qty * self.current_avg_cost

    @property
    def primary_barcode(self):
        """Основен баркод"""
        return self.barcodes.filter(is_primary=True).first()

    @property
    def primary_plu(self):
        """Основен PLU код"""
        return self.plu_codes.filter(is_primary=True).first()

    @property
    def default_sale_packaging(self):
        """Основна опаковка за продажба"""
        return self.packagings.filter(is_default_sale_unit=True).first()

    @property
    def default_purchase_packaging(self):
        """Основна опаковка за покупка"""
        return self.packagings.filter(is_default_purchase_unit=True).first()

    # === БИЗНЕС МЕТОДИ ===

    def update_average_cost(self, new_qty, new_cost):
        """
        Обновява среднопретеглената цена

        Formula: MAC = (existing_qty * existing_cost + new_qty * new_cost) / total_qty
        """
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
        """Добавя складова наличност"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if cost_per_unit:
            self.update_average_cost(quantity, cost_per_unit)
        else:
            self.current_stock_qty += quantity
            self.save(update_fields=['current_stock_qty'])

    def remove_stock(self, quantity):
        """Премахва складова наличност"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if quantity > self.current_stock_qty:
            raise ValueError("Insufficient stock")

        self.current_stock_qty -= quantity
        self.last_sale_date = timezone.now()
        self.save(update_fields=['current_stock_qty', 'last_sale_date'])

    def get_active_barcodes(self):
        """Всички активни баркодове"""
        return self.barcodes.filter(is_active=True)

    def get_active_packagings(self):
        """Всички активни опаковки"""
        return self.packagings.filter(is_active=True)

    def can_be_sold_by_weight(self):
        """Може ли да се продава на тегло"""
        return self.unit_type == self.WEIGHT and self.plu_codes.filter(is_active=True).exists()


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