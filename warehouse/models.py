from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal


# === CUSTOM MANAGERS ===

class WarehouseManager(models.Manager):
    def active(self):
        return self.filter(is_active=True)

    def shops(self):
        return self.filter(warehouse_type='shop', is_active=True)

    def main_warehouses(self):
        return self.filter(warehouse_type='main', is_active=True)


class StockLevelManager(models.Manager):
    def with_stock(self):
        return self.filter(quantity__gt=0)

    def for_warehouse(self, warehouse):
        return self.filter(warehouse=warehouse)

    def for_product(self, product):
        return self.filter(product=product)

    def by_batch(self):
        return self.filter(batch_number__isnull=False)

    def without_batch(self):
        return self.filter(batch_number__isnull=True)




# === ОСНОВНИ СКЛАДОВИ МОДЕЛИ ===

class Warehouse(models.Model):
    """
    Склад/Магазин - основната складова единица
    """

    # Типове складове
    SHOP = 'shop'
    MAIN = 'main'
    RESERVE = 'reserve'

    WAREHOUSE_TYPES = [
        (SHOP, _('Shop/Store')),
        (MAIN, _('Main Warehouse')),
        (RESERVE, _('Reserve Warehouse')),
    ]

    # Основни данни
    code = models.CharField(_('Warehouse Code'), max_length=10, unique=True)
    name = models.CharField(_('Warehouse Name'), max_length=100)
    warehouse_type = models.CharField(
        _('Warehouse Type'),
        max_length=10,
        choices=WAREHOUSE_TYPES,
        default=SHOP
    )

    # Адрес и контакти
    address = models.TextField(_('Address'), blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)

    # Отговорник
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Manager')
    )

    # Ценова политика (fallback за продукти без зададени цени)
    default_markup_percentage = models.DecimalField(
        _('Default Markup %'),
        max_digits=5,
        decimal_places=2,
        default=30.00,
        help_text=_('Used when no specific price is set for a product')
    )

    # Статус
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Мета данни
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = WarehouseManager()

    class Meta:
        verbose_name = _('Warehouse')
        verbose_name_plural = _('Warehouses')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_pos_locations(self):
        """Връща POS местата за този склад"""
        from nomenclatures.models import POSLocation
        return POSLocation.objects.filter(warehouse=self, is_active=True)

    def get_total_stock_value(self):
        """Обща стойност на склада"""
        total = self.stock_levels.aggregate(
            total_value=models.Sum(
                models.F('quantity') * models.F('avg_purchase_price')
            )
        )['total_value']
        return total or Decimal('0.00')


class StockMovement(models.Model):
    """
    Движения на стоката - пълна история на всички операции
    """

    # Типове движения
    IN = 'in'  # Постъпване
    OUT = 'out'  # Излизане

    MOVEMENT_TYPES = [
        (IN, _('Incoming')),
        (OUT, _('Outgoing')),
    ]

    # Основни данни
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='movements',
        verbose_name=_('Warehouse')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name=_('Product')
    )

    # Партида (опционално)
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        null=True,
        blank=True
    )

    # Количество и тип
    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Always positive - type determines direction')
    )
    movement_type = models.CharField(
        _('Movement Type'),
        max_length=10,
        choices=MOVEMENT_TYPES
    )

    # Цена
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Cost price for incoming, sale price for outgoing')
    )

    # Документ
    document = models.CharField(_('Document'), max_length=50)
    document_date = models.DateField(_('Document Date'))
    # purchase_document = models.ForeignKey(
    #     'purchases.PurchaseDocument',
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     verbose_name=_('Purchase Document'),
    #     help_text=_('Reference to source purchase document if applicable')
    # )

    # Допълнителна информация
    reason = models.CharField(_('Reason'), max_length=100, blank=True)
    notes = models.TextField(_('Notes'), blank=True)

    # За партиди - срок на годност
    expiry_date = models.DateField(_('Expiry Date'), null=True, blank=True)

    # Одит информация
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Created By')
    )

    class Meta:
        verbose_name = _('Stock Movement')
        verbose_name_plural = _('Stock Movements')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['warehouse', 'product', '-created_at']),
            models.Index(fields=['document', '-created_at']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['movement_type', '-created_at']),
        ]

    def __str__(self):
        direction = "+" if self.movement_type == self.IN else "-"
        batch_info = f" ({self.batch_number})" if self.batch_number else ""
        return f"{direction}{self.quantity} {self.product.code}{batch_info} @ {self.warehouse.code}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Автоматично обновяване на StockLevel
        StockLevel.refresh_for_combination(
            warehouse=self.warehouse,
            product=self.product,
            batch_number=self.batch_number,
            expiry_date=self.expiry_date,
        )


class StockLevel(models.Model):
    """
    Текущи наличности - агрегирани данни от StockMovement
    """

    # Уникална комбинация
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stock_levels',
        verbose_name=_('Warehouse')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='stock_levels',
        verbose_name=_('Product')
    )
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        null=True,
        blank=True
    )

    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True
    )

    # Изчислени стойности
    quantity = models.DecimalField(
        _('Current Quantity'),
        max_digits=12,
        decimal_places=3,
        default=0
    )

    avg_purchase_price = models.DecimalField(
        _('Average Purchase Price'),
        max_digits=10,
        decimal_places=4,
        default=0
    )

    # Резервирано количество
    quantity_reserved = models.DecimalField(
        _('Quantity Reserved'),
        max_digits=12,
        decimal_places=3,
        default=0
    )

    # Нива за поръчване
    min_stock_level = models.DecimalField(
        _('Minimum Stock Level'),
        max_digits=12,
        decimal_places=3,
        default=0
    )

    # Мета данни
    last_movement_date = models.DateTimeField(_('Last Movement'), null=True, blank=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = StockLevelManager()

    class Meta:
        unique_together = ('warehouse', 'product', 'batch_number', 'expiry_date')
        verbose_name = _('Stock Level')
        verbose_name_plural = _('Stock Levels')
        indexes = [
            models.Index(fields=['warehouse', 'quantity']),
            models.Index(fields=['product', 'quantity']),
        ]

    def __str__(self):
        batch_info = f" ({self.batch_number})" if self.batch_number else ""
        return f"{self.product.code}{batch_info} @ {self.warehouse.code}: {self.quantity_available}"

    @property
    def quantity_available(self):
        return self.quantity - self.quantity_reserved

    @property
    def needs_reorder(self):
        return self.quantity_available <= self.min_stock_level

    @classmethod
    def refresh_for_combination(cls, warehouse, product, batch_number=None, expiry_date=None):
        """Преизчислява наличността от движенията"""
        movements = StockMovement.objects.filter(
            warehouse=warehouse,
            product=product,
            batch_number=batch_number,
            expiry_date = expiry_date
        )

        if not movements.exists():
            cls.objects.filter(
                warehouse=warehouse,
                product=product,
                batch_number=batch_number,
                expiry_date = expiry_date
            ).delete()
            return None

        # Изчислява количество
        total_in = movements.filter(movement_type=StockMovement.IN).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        total_out = movements.filter(movement_type=StockMovement.OUT).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        current_quantity = total_in - total_out

        if current_quantity <= 0:
            cls.objects.filter(
                warehouse=warehouse,
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date
            ).delete()
            return None

        # Изчислява средна покупна цена
        in_movements = movements.filter(movement_type=StockMovement.IN)
        total_cost = sum(Decimal(str(m.quantity)) * m.unit_price for m in in_movements)
        total_in_qty = sum(Decimal(str(m.quantity)) for m in in_movements)
        avg_price = total_cost / total_in_qty if total_in_qty > 0 else Decimal('0')

        # Последно движение
        last_movement = movements.order_by('-created_at').first()

        # Обновява записа
        stock_level, created = cls.objects.update_or_create(
            warehouse=warehouse,
            product=product,
            batch_number=batch_number,
            expiry_date=expiry_date,
            defaults={
                'quantity': current_quantity,
                'avg_purchase_price': avg_price,
                'last_movement_date': last_movement.created_at if last_movement else None,
            }
        )

        return stock_level


    def get_markup_percentage(self):
        """Надценка % за този продукт в този склад"""
        sale_price = PricingService.get_sale_price(self.warehouse, self.product)
        return PricingService.calculate_markup_percentage(self.avg_purchase_price, sale_price)

    def get_margin_percentage(self):
        """Маржа % за този продукт в този склад"""
        sale_price = PricingService.get_sale_price(self.warehouse, self.product)
        return PricingService.calculate_margin_percentage(self.avg_purchase_price, sale_price)

    def get_profit_per_unit(self):
        """Печалба на единица"""
        sale_price = PricingService.get_sale_price(self.warehouse, self.product)
        return sale_price - self.avg_purchase_price


# === ЦЕНОВИ МОДЕЛИ (warehouse-specific) ===

class WarehouseProductPrice(models.Model):
    """
    Базови цени за продукти по склад
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='product_prices'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='warehouse_prices'
    )

    # Основна цена
    base_price = models.DecimalField(
        _('Base Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Base selling price for this product in this warehouse')
    )



    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        unique_together = ('warehouse', 'product')
        verbose_name = _('Warehouse Product Price')
        verbose_name_plural = _('Warehouse Product Prices')

    def __str__(self):
        return f"{self.product.code} @ {self.warehouse.code}: {self.base_price:.2f}"




class WarehouseProductPriceByGroup(models.Model):
    """
    Цени по ценова група за конкретен склад
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='group_prices'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='warehouse_group_prices'
    )
    price_group = models.ForeignKey(
        'PriceGroup',
        on_delete=models.CASCADE
    )
    price = models.DecimalField(_('Price'), max_digits=10, decimal_places=2)

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        unique_together = ('warehouse', 'product', 'price_group')
        verbose_name = _('Warehouse Product Price by Group')
        verbose_name_plural = _('Warehouse Product Prices by Group')

    def __str__(self):
        return f"{self.product.code} @ {self.warehouse.code} / {self.price_group.name} = {self.price}"


class WarehouseProductStepPrice(models.Model):
    """
    Стъпкови цени по количество за конкретен склад
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='step_prices'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='warehouse_step_prices'
    )
    min_quantity = models.DecimalField(_('Min Quantity'), max_digits=10, decimal_places=3)
    price = models.DecimalField(_('Step Price'), max_digits=10, decimal_places=2)

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        unique_together = ('warehouse', 'product', 'min_quantity')
        verbose_name = _('Warehouse Step Price')
        verbose_name_plural = _('Warehouse Step Prices')

    def __str__(self):
        return f"{self.product.code} @ {self.warehouse.code} ≥ {self.min_quantity} = {self.price}"


class WarehousePromotionalPrice(models.Model):
    """
    Промоционални цени за конкретен склад
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='promotional_prices'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='warehouse_promotions'
    )

    name = models.CharField(_('Promotion Name'), max_length=100, blank=True)
    price = models.DecimalField(_('Promotional Price'), max_digits=10, decimal_places=2)
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'))

    min_quantity = models.DecimalField(
        _('Min Quantity'),
        max_digits=10,
        decimal_places=3,
        default=1
    )

    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        unique_together = ('warehouse', 'product', 'start_date')
        verbose_name = _('Warehouse Promotional Price')
        verbose_name_plural = _('Warehouse Promotional Prices')

    def __str__(self):
        return f"{self.product.code} @ {self.warehouse.code} → {self.price} ({self.start_date} – {self.end_date})"

    def is_valid_now(self):
        today = timezone.now().date()
        return (
                self.is_active and
                self.start_date <= today <= self.end_date
        )


# === ЦЕНОВА СЛУЖБА ===

class PricingService:
    """
    Централизирана логика за ценообразуване по склад
    """

    @staticmethod
    def get_sale_price(warehouse, product, customer=None, quantity=1):
        """
        Връща продажната цена за продукт в конкретен склад
        """
        today = timezone.now().date()

        # 1. Промоционална цена за склада
        promo = WarehousePromotionalPrice.objects.filter(
            warehouse=warehouse,
            product=product,
            start_date__lte=today,
            end_date__gte=today,
            min_quantity__lte=quantity,
            is_active=True
        ).order_by('-min_quantity').first()

        if promo:
            return promo.price

        # 2. Ценова група на клиента за склада
        if customer and hasattr(customer, 'price_group') and customer.price_group:
            group_price = WarehouseProductPriceByGroup.objects.filter(
                warehouse=warehouse,
                product=product,
                price_group=customer.price_group,
                is_active=True
            ).first()
            if group_price:
                return group_price.price

        # 3. Стъпкова цена за склада
        step_price = WarehouseProductStepPrice.objects.filter(
            warehouse=warehouse,
            product=product,
            min_quantity__lte=quantity,
            is_active=True
        ).order_by('-min_quantity').first()

        if step_price:
            return step_price.price

        # 4. Базова цена за склада
        try:
            base_price = WarehouseProductPrice.objects.get(
                warehouse=warehouse,
                product=product,
                is_active=True
            )
            return base_price.base_price
        except WarehouseProductPrice.DoesNotExist:
            pass

        # 5. Fallback - default markup на склада
        try:
            stock_level = StockLevel.objects.get(warehouse=warehouse, product=product)
            if stock_level.avg_purchase_price > 0:
                return stock_level.avg_purchase_price * (1 + warehouse.default_markup_percentage / 100)
        except StockLevel.DoesNotExist:
            pass

        return Decimal('0.00')

    @staticmethod
    def calculate_markup_percentage(cost_price, sale_price):
        """
        Изчислява надценка % върху себестойността
        Markup = (Sale Price - Cost Price) / Cost Price × 100
        """
        if cost_price <= 0:
            return Decimal('0.00')

        markup = ((sale_price - cost_price) / cost_price) * 100
        return round(markup, 2)

    @staticmethod
    def calculate_margin_percentage(cost_price, sale_price):
        """
        Изчислява маржа % от продажната цена
        Margin = (Sale Price - Cost Price) / Sale Price × 100
        """
        if sale_price <= 0:
            return Decimal('0.00')

        margin = ((sale_price - cost_price) / sale_price) * 100
        return round(margin, 2)

    @staticmethod
    def get_pricing_analysis(warehouse, product, quantity=1, customer=None):
        """
        Пълен анализ на ценообразуването за продукт
        """
        try:
            # Вземи cost цената
            stock_level = StockLevel.objects.get(warehouse=warehouse, product=product)
            cost_price = stock_level.avg_purchase_price

            # Вземи продажната цена
            sale_price = PricingService.get_sale_price(
                warehouse=warehouse,
                product=product,
                customer=customer,
                quantity=quantity
            )

            if cost_price > 0 and sale_price > 0:
                return {
                    'cost_price': cost_price,
                    'sale_price': sale_price,
                    'markup_percentage': PricingService.calculate_markup_percentage(cost_price, sale_price),
                    'margin_percentage': PricingService.calculate_margin_percentage(cost_price, sale_price),
                    'profit_per_unit': sale_price - cost_price,
                    'quantity': quantity
                }
        except StockLevel.DoesNotExist:
            pass

        return None


# === ПОМОЩНИ ФУНКЦИИ ===

def process_incoming_movement(warehouse, product, quantity, unit_price, document,
                              document_date, batch_number=None, expiry_date=None,
                              reason="", created_by=None):
    """Записва постъпващо движение"""
    movement = StockMovement.objects.create(
        warehouse=warehouse,
        product=product,
        batch_number=batch_number,
        quantity=quantity,
        movement_type=StockMovement.IN,
        unit_price=unit_price,
        document=document,
        document_date=document_date,
        reason=reason,
        expiry_date=expiry_date,
        created_by=created_by
    )
    return movement


def process_outgoing_movement(warehouse, product, quantity, unit_price, document,
                              document_date, batch_number=None, reason="", created_by=None):
    """Записва излизащо движение"""
    movement = StockMovement.objects.create(
        warehouse=warehouse,
        product=product,
        batch_number=batch_number,
        quantity=quantity,
        movement_type=StockMovement.OUT,
        unit_price=unit_price,
        document=document,
        document_date=document_date,
        reason=reason,
        created_by=created_by
    )
    return movement


# === ЦЕНОВА ГРУПА ===
class PriceGroup(models.Model):
    name = models.CharField(_('Price Group Name'), max_length=100, unique=True)
    description = models.TextField(_('Description'), blank=True)
    discount_percentage = models.DecimalField(
        _('Default Discount %'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Default discount for this group')
    )
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Price Group')
        verbose_name_plural = _('Price Groups')
        ordering = ['name']

    def __str__(self):
        return self.name