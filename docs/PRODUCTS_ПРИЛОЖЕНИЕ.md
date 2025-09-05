# Документация на PRODUCTS приложението

## 🎯 Преглед

**PRODUCTS приложението** управлява продуктовия каталог в OptimaPOS, предоставяйки изчерпателно управление на жизнения цикъл на продуктите, packaging конфигурации, баркод/PLU поддръжка и безпроблемна интеграция със склад, ценообразуване и системи за продажби. То се фокусира на статични продуктови дефиниции докато делегира динамични данни към специализирани приложения.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Основни модели](#основни-модели)
3. [Управление на жизнения цикъл на продуктите](#управление-на-жизнения-цикъл-на-продуктите)
4. [Packaging система](#packaging-система)
5. [Услуги](#услуги)
6. [Интеграционни точки](#интеграционни-точки)
7. [Шаблони за използване](#шаблони-за-използване)
8. [API справочник](#api-справочник)
9. [Най-добри практики](#най-добри-практики)

---

## Архитектура

```
PRODUCTS Структура на приложението:
├── models/
│   ├── products.py         # Product, ProductPLU, ProductLifecycleChoices
│   └── packaging.py        # ProductPackaging, ProductBarcode
├── services/
│   ├── product_service.py  # Търсене, lookup, статистики
│   ├── lifecycle_service.py # Управление на жизнения цикъл
│   └── validation_service.py # Валидация на продукти
├── admin.py                # Администрация на продукти
└── views.py                # API endpoints
```

### Философия на дизайна

- **📊 Фокус на статичната дефиниция** - Продуктите съхраняват статични данни, динамични данни в други apps
- **🔄 Lifecycle-Driven** - Пълен жизнен цикъл на продукта от NEW до ARCHIVED
- **📦 Гъвкаво packaging** - Множество единици и packaging конфигурации
- **🏷️ Multi-Identification** - Кодове, баркодове, PLU кодове за различни случаи
- **🔍 Оптимизирано за търсене** - Бързо търсене на продукти по всякакъв идентификатор
- **⚙️ Integration-Ready** - Чисто разделение със склад, ценообразуване, продажби
- **✅ Heavy валидация** - Изчерпателна валидация на бизнес правила

---

## Основни модели

### 1. **Product** (Главна дефиниция на продукт)

**Цел**: Основен продуктов каталог със статични дефиниции и управление на жизнения цикъл

```python
from core.models.fields import QuantityField

# Основна идентичност
code = models.CharField(unique=True, max_length=50)     # Вътрешен код на продукт
name = models.CharField(max_length=255)                 # Име на продукта
description = models.TextField()                        # Подробно описание

# Класификация (чрез NOMENCLATURES)
brand = models.ForeignKey('nomenclatures.Brand')
product_group = models.ForeignKey('nomenclatures.ProductGroup')
product_type = models.ForeignKey('nomenclatures.ProductType')

# Единици и измервания
base_unit = models.ForeignKey('nomenclatures.UnitOfMeasure')
unit_type = models.CharField(
    choices=[('PIECE', 'Бройки'), ('WEIGHT', 'Тегло'), ('VOLUME', 'Обем'), ('LENGTH', 'Дължина')]
)

# Данъчна конфигурация
tax_group = models.ForeignKey('nomenclatures.TaxGroup')

# Настройки за проследяване
track_batches = models.BooleanField(default=False)
track_serial_numbers = models.BooleanField(default=False)
requires_expiry_date = models.BooleanField(default=False)

# Управление на жизнения цикъл
lifecycle_status = models.CharField(
    max_length=20,
    choices=ProductLifecycleChoices.choices,
    default=ProductLifecycleChoices.NEW
)
sales_blocked = models.BooleanField(default=False)
purchase_blocked = models.BooleanField(default=False)
allow_negative_sales = models.BooleanField(default=False)
```

**Състояния на жизнения цикъл:**
```python
class ProductLifecycleChoices:
    NEW = 'NEW'                    # Нов продукт, все още не е активен
    ACTIVE = 'ACTIVE'              # Активен продукт, може да се купува/продава
    PHASE_OUT = 'PHASE_OUT'        # Извеждане от употреба, само продажба (без покупка)
    DISCONTINUED = 'DISCONTINUED'  # Прекратен, без продажби/покупки
    ARCHIVED = 'ARCHIVED'          # Архивиран, само исторически
```

**Динамични свойства (Интеграция с INVENTORY):**
```python
from core.utils.decimal_utils import round_quantity, round_cost_price, round_currency

@property
def total_stock(self) -> Decimal:
    """Общ склад в всички локации"""
    from inventory.models import InventoryItem
    total = InventoryItem.objects.filter(product=self).aggregate(
        total=Sum('current_qty')
    )['total'] or Decimal('0.000')
    
    return round_quantity(total)  # 3dp точност за количества

@property  
def weighted_avg_cost(self) -> Decimal:
    """Претеглена средна себестойност в всички локации"""
    from inventory.models import InventoryItem
    from core.utils.decimal_utils import round_cost_price
    
    items = InventoryItem.objects.filter(
        product=self, 
        current_qty__gt=0
    )
    
    total_value = Decimal('0.0000')
    total_qty = Decimal('0.000')
    
    for item in items:
        if item.current_qty > 0 and item.avg_cost > 0:
            value = item.current_qty * item.avg_cost
            total_value += value
            total_qty += item.current_qty
    
    if total_qty > 0:
        avg_cost = total_value / total_qty
        return round_cost_price(avg_cost)  # 4dp за калкулационна точност
    
    return Decimal('0.0000')

@property
def stock_value(self) -> Decimal:
    """Обща стойност на склада в всички локации"""
    from inventory.models import InventoryItem
    
    total_value = Decimal('0.0000')
    items = InventoryItem.objects.filter(product=self, current_qty__gt=0)
    
    for item in items:
        if item.avg_cost > 0:
            value = item.current_qty * item.avg_cost
            total_value += value
    
    return round_currency(total_value)  # 2dp за дисплей
```

### 2. **ProductPackaging** (Алтернативни единици)

**Цел**: Дефинира алтернативно packaging/единици за продукти

```python
from core.models.fields import QuantityField

# Дефиниция на опаковка
product = models.ForeignKey(Product, on_delete=models.CASCADE)
unit = models.ForeignKey('nomenclatures.UnitOfMeasure', on_delete=models.PROTECT)
conversion_factor = QuantityField()  # Колко базови единици (3dp точност)

# Настройки за използване
allow_sale = models.BooleanField(default=True)           # Може да се продава в тази единица
allow_purchase = models.BooleanField(default=True)       # Може да се купува в тази единица
is_default_sale_unit = models.BooleanField(default=False)
is_default_purchase_unit = models.BooleanField(default=False)

# Ограничения
is_active = models.BooleanField(default=True)

# Пример: Widget (база: бройки)
# - Единична бройка:  conversion_factor = 1.000
# - Кутия с 12:       conversion_factor = 12.000
# - Каса с 144:       conversion_factor = 144.000
```

**Бизнес правила:**
```python
from core.utils.decimal_utils import round_quantity

def clean(self):
    # PIECE продукти трябва да имат цели числа за конверсии
    if self.product.unit_type == 'PIECE':
        # Закръгли до правилната точност за проверка
        rounded_factor = round_quantity(self.conversion_factor)
        if rounded_factor != int(rounded_factor):
            raise ValidationError('PIECE продукти не могат да имат дробни packaging')
    
    # Само един default на тип
    if self.is_default_sale_unit:
        existing = ProductPackaging.objects.filter(
            product=self.product,
            is_default_sale_unit=True
        ).exclude(pk=self.pk)
        if existing.exists():
            raise ValidationError('Разрешена е само една default единица за продажба')
```

### 3. **ProductBarcode** (Управление на баркодове)

**Цел**: Множество баркодове за продукт/packaging комбинация

```python
# Дефиниция на баркод
barcode = models.CharField(unique=True, max_length=50)   # Действителният баркод
product = models.ForeignKey(Product, on_delete=models.CASCADE)
packaging = models.ForeignKey(ProductPackaging, null=True, blank=True)

# Приоритет и статус
is_primary = models.BooleanField(default=False)          # Главен баркод за продукта
is_active = models.BooleanField(default=True)
priority = models.IntegerField(default=0)                # По-високо = предпочитано
```

**Типове баркодове:**
- **Продуктови баркодове**: Scan → получи продукт (количество = 1 базова единица)
- **Packaging баркодове**: Scan → получи продукт + packaging info (количество = conversion_factor)

### 4. **ProductPLU** (Weight-Based продукти)

**Цел**: PLU кодове за scale/weight-based продукти

```python
# PLU дефиниция
product = models.ForeignKey(Product, on_delete=models.CASCADE)
plu_code = models.CharField(max_length=10)               # PLU код (цифри)
is_primary = models.BooleanField(default=False)
priority = models.IntegerField(default=0)

# Валидация
def clean(self):
    # Само за weight-based продукти
    if self.product.unit_type != 'WEIGHT':
        raise ValidationError('PLU кодове само за weight-based продукти')
```

---

## Управление на жизнения цикъл на продуктите

### Състояния и преходи на жизнения цикъл

```python
class ProductLifecycleService:
    
    @staticmethod
    def transition_to_active(product):
        """Премина продукт към ACTIVE статус"""
        from core.utils.result import Result
        
        if product.lifecycle_status == ProductLifecycleChoices.NEW:
            product.lifecycle_status = ProductLifecycleChoices.ACTIVE
            product.sales_blocked = False
            product.purchase_blocked = False
            product.save()
            
            return Result.success(
                data={'product': product, 'new_status': 'ACTIVE'},
                msg=f'Продукт {product.code} е активиран'
            )
        
        return Result.error(
            'INVALID_TRANSITION',
            f'Не може да се активира продукт от статус {product.lifecycle_status}'
        )
    
    @staticmethod
    def phase_out_product(product):
        """Започни извеждане на продукт от употреба"""
        product.lifecycle_status = ProductLifecycleChoices.PHASE_OUT
        product.purchase_blocked = True  # Не може да се купува
        product.sales_blocked = False    # Все още може да се продава
        product.save()
        
        return Result.success(
            data={'product': product},
            msg=f'Продукт {product.code} е в процес на извеждане'
        )
```

### Бизнес правила за жизнения цикъл

```python
def can_purchase(self):
    """Може ли продуктът да се купува"""
    return (
        self.lifecycle_status in [ProductLifecycleChoices.NEW, ProductLifecycleChoices.ACTIVE] and
        not self.purchase_blocked
    )

def can_sell(self):
    """Може ли продуктът да се продава"""
    return (
        self.lifecycle_status in [ProductLifecycleChoices.ACTIVE, ProductLifecycleChoices.PHASE_OUT] and
        not self.sales_blocked
    )

def requires_batch_tracking(self):
    """Изисква ли продуктът batch следене"""
    return self.track_batches or self.requires_expiry_date
```

---

## Packaging система

### Packaging hierarchy

```python
class ProductPackaging:
    
    def get_base_quantity(self, packaging_quantity):
        """Преобразува packaging количество в базови единици"""
        from core.utils.decimal_utils import round_quantity
        
        base_qty = packaging_quantity * self.conversion_factor
        return round_quantity(base_qty)  # 3dp точност
    
    def get_packaging_quantity(self, base_quantity):
        """Преобразува базово количество в packaging количество"""
        from core.utils.decimal_utils import round_quantity
        
        if self.conversion_factor > 0:
            pkg_qty = base_quantity / self.conversion_factor
            return round_quantity(pkg_qty)
        
        return Decimal('0.000')
    
    @property
    def display_name(self):
        """Дисплей име за packaging"""
        if self.conversion_factor == 1:
            return self.unit.name
        else:
            return f"{self.unit.name} (x{int(self.conversion_factor)})"
```

### Packaging валидация

```python
def validate_packaging_consistency():
    """Валидира консистентността на packaging системата"""
    from core.utils.result import Result
    
    errors = []
    
    # Провери че има поне един активен packaging на продукт
    products_without_packaging = Product.objects.filter(
        packaging_set__isnull=True,
        lifecycle_status__in=['ACTIVE', 'NEW']
    )
    
    for product in products_without_packaging:
        errors.append(f'Продукт {product.code} няма packaging конфигурация')
    
    # Провери за дублирани default packaging
    duplicate_defaults = ProductPackaging.objects.values('product').annotate(
        default_sale_count=Count('id', filter=Q(is_default_sale_unit=True)),
        default_purchase_count=Count('id', filter=Q(is_default_purchase_unit=True))
    ).filter(
        Q(default_sale_count__gt=1) | Q(default_purchase_count__gt=1)
    )
    
    for item in duplicate_defaults:
        product = Product.objects.get(id=item['product'])
        errors.append(f'Продукт {product.code} има множество default packaging')
    
    if errors:
        return Result.error('PACKAGING_VALIDATION_FAILED', '; '.join(errors))
    
    return Result.success(msg='Packaging валидацията премина успешно')
```

---

## Услуги

### 1. **ProductService** - Основни операции с продукти

```python
from products.services import ProductService

# Търсене на продукти по различни критерии
result = ProductService.search_products(
    search_term='widget',
    category='electronics',
    lifecycle_status='ACTIVE',
    has_stock=True
)

# Lookup по баркод/PLU/код
result = ProductService.lookup_by_identifier(
    identifier='1234567890123',  # Може да е баркод, PLU или код
    identifier_type='auto'       # Автоматично откриване
)

# Получаване на пълна информация за продукт
result = ProductService.get_product_details(
    product_id=42,
    include_stock=True,
    include_pricing=True,
    location=warehouse
)
```

### 2. **LifecycleService** - Управление на жизнения цикъл

```python
from products.services import LifecycleService

# Активиране на нов продукт
result = LifecycleService.activate_product(product)

# Започни извеждане от употреба
result = LifecycleService.phase_out_product(
    product=product,
    reason='Заменен с нов модел'
)

# Прекрати продукт
result = LifecycleService.discontinue_product(
    product=product,
    archive_date=date.today() + timedelta(days=90)
)
```

---

## Интеграционни точки

### **С INVENTORY App:**

```python
# Интеграция на stock информация
class Product:
    @property
    def current_stock_by_location(self):
        """Текущ склад по локации с правилна точност"""
        from inventory.models import InventoryItem
        from core.utils.decimal_utils import round_quantity
        
        stock_data = {}
        items = InventoryItem.objects.filter(product=self, current_qty__gt=0)
        
        for item in items:
            stock_data[item.location.code] = {
                'current_qty': round_quantity(item.current_qty),      # 3dp точност
                'available_qty': round_quantity(item.available_qty),  # 3dp точност
                'avg_cost': item.avg_cost,                            # 4dp точност
                'stock_value': round_currency(item.stock_value)       # 2dp точност
            }
        
        return stock_data
```

### **С PRICING App:**

```python
# Интеграция за цени
def get_product_with_pricing(product_id, location, customer=None):
    """Получава продукт с ценова информация"""
    from pricing.services import PricingService
    
    product = Product.objects.get(id=product_id)
    
    # Получи ценообразуване
    pricing_result = PricingService.get_product_pricing(
        location=location,
        product=product,
        customer=customer
    )
    
    product_data = {
        'product': product,
        'pricing': pricing_result.data if pricing_result.ok else None,
        'stock_info': product.current_stock_by_location.get(location.code, {}),
        'packaging_options': list(product.packaging_set.filter(
            is_active=True,
            allow_sale=True
        ))
    }
    
    return product_data
```

### **С NOMENCLATURES App:**

```python
# Интеграция за ДДС калкулации
def get_product_vat_info(product, location=None):
    """Получава ДДС информация за продукт"""
    from nomenclatures.services.vat_calculation_service import VATCalculationService
    
    # Получи ДДС ставка за продукта
    vat_rate = VATCalculationService.get_vat_rate(product, location)
    
    return {
        'tax_group': product.tax_group.name if product.tax_group else 'Стандартна',
        'vat_rate': vat_rate,
        'vat_exempt': vat_rate == 0
    }
```

---

## Шаблони за използване

### 1. **Създаване на продукт с packaging**

```python
from core.utils.decimal_utils import Decimal

# Създай основен продукт
product = Product.objects.create(
    code='WIDGET001',
    name='Premium Widget',
    description='Висококачествен widget за професионална употреба',
    brand=electronics_brand,
    product_group=widgets_group,
    base_unit=piece_unit,
    unit_type='PIECE',
    track_batches=True,
    lifecycle_status=ProductLifecycleChoices.NEW
)

# Добави packaging опции
# Единична бройка
single_packaging = ProductPackaging.objects.create(
    product=product,
    unit=piece_unit,
    conversion_factor=Decimal('1.000'),  # 3dp точност
    is_default_sale_unit=True,
    is_default_purchase_unit=False
)

# Кутия с 12 бройки
box_packaging = ProductPackaging.objects.create(
    product=product,
    unit=box_unit,
    conversion_factor=Decimal('12.000'),  # 3dp точност
    is_default_purchase_unit=True
)

# Каса с 144 бройки
case_packaging = ProductPackaging.objects.create(
    product=product,
    unit=case_unit,
    conversion_factor=Decimal('144.000')  # 3dp точност
)
```

### 2. **Работа с баркодове**

```python
# Добави баркодове за различни packaging нива
ProductBarcode.objects.create(
    barcode='1234567890123',  # Единичен продукт
    product=product,
    packaging=single_packaging,
    is_primary=True,
    priority=100
)

ProductBarcode.objects.create(
    barcode='9876543210987',  # Кутия
    product=product,
    packaging=box_packaging,
    priority=90
)

ProductBarcode.objects.create(
    barcode='5555666677778',  # Каса
    product=product,
    packaging=case_packaging,
    priority=80
)
```

### 3. **Търсене и lookup операции**

```python
# Търсене по множество критерии
def search_products_with_precision():
    result = ProductService.search_products(
        search_term='widget',
        lifecycle_status=['ACTIVE', 'PHASE_OUT'],
        has_stock=True,
        location=warehouse
    )
    
    if result.ok:
        for product_data in result.data['products']:
            product = product_data['product']
            stock_info = product_data['stock_info']
            
            print(f"Продукт: {product.name}")
            print(f"Склад: {stock_info['current_qty']} {product.base_unit.symbol}")
            print(f"Стойност: {stock_info['stock_value']} лв.")

# Lookup по баркод с автоматично откриване на packaging
def barcode_lookup_with_packaging(barcode_value):
    result = ProductService.lookup_by_identifier(barcode_value)
    
    if result.ok:
        lookup_data = result.data
        product = lookup_data['product']
        packaging = lookup_data['packaging']
        
        if packaging:
            quantity_per_scan = packaging.conversion_factor
            print(f"Баркод представлява {quantity_per_scan} {product.base_unit.symbol}")
        else:
            print(f"Баркод за единичен {product.name}")
```

---

## API справочник

### ProductService методи

| Метод | Цел | Връща | Ключови параметри |
|-------|-----|-------|------------------|
| `search_products()` | Търсене на продукти | Result | search_term, filters, pagination |
| `lookup_by_identifier()` | Търсене по баркод/PLU/код | Result | identifier, identifier_type |
| `get_product_details()` | Подробна информация | Result | product_id, include_options |
| `validate_product_data()` | Валидация преди запазване | Result | product_data |

### Result структури от данни

**Детайли за продукт:**
```python
{
    'product': {
        'id': 42,
        'code': 'WIDGET001',
        'name': 'Premium Widget',
        'lifecycle_status': 'ACTIVE',
        'unit_type': 'PIECE',
        'can_purchase': True,
        'can_sell': True,
        'track_batches': True
    },
    'stock_info': {
        'total_stock': Decimal('150.000'),          # 3dp точност
        'weighted_avg_cost': Decimal('15.2500'),    # 4dp точност
        'stock_value': Decimal('3787.50'),          # 2dp точност
        'locations': {
            'WH01': {
                'current_qty': Decimal('100.000'),   # 3dp точност
                'available_qty': Decimal('85.000'),  # 3dp точност
                'avg_cost': Decimal('15.0000'),      # 4dp точност
                'stock_value': Decimal('1500.00')    # 2dp точност
            }
        }
    },
    'packaging_options': [
        {
            'id': 1,
            'unit_name': 'бр.',
            'conversion_factor': Decimal('1.000'),    # 3dp точност
            'display_name': 'бр.',
            'is_default_sale': True
        },
        {
            'id': 2,
            'unit_name': 'кутия',
            'conversion_factor': Decimal('12.000'),   # 3dp точност
            'display_name': 'кутия (x12)',
            'is_default_purchase': True
        }
    ],
    'barcodes': [
        {
            'barcode': '1234567890123',
            'packaging_id': 1,
            'is_primary': True
        }
    ]
}
```

---

## Най-добри практики

### 1. **Винаги използвайте правилната десетична точност**

```python
# ✅ Добро - използвайте стандартизираните утилити
from core.utils.decimal_utils import round_quantity, round_cost_price

def create_packaging_with_precision():
    packaging = ProductPackaging.objects.create(
        product=product,
        unit=box_unit,
        conversion_factor=round_quantity(Decimal('12.000'))  # 3dp точност
    )
    
    # Калкулации с правилна точност
    base_qty = round_quantity(packaging.conversion_factor * Decimal('5.000'))
    
    return packaging

# ❌ Избягвайте - директно използване на Decimal без правилна точност
conversion = Decimal('12')  # Може да има неправилна точност
```

### 2. **Използвайте lifecycle управление**

```python
# ✅ Добро - проверявайте lifecycle статус
def can_process_product_operation(product, operation_type):
    if operation_type == 'purchase':
        if not product.can_purchase():
            return Result.error(
                'PRODUCT_CANNOT_PURCHASE',
                f'Продукт {product.code} не може да се купува в статус {product.lifecycle_status}'
            )
    
    elif operation_type == 'sale':
        if not product.can_sell():
            return Result.error(
                'PRODUCT_CANNOT_SELL', 
                f'Продукт {product.code} не може да се продава в статус {product.lifecycle_status}'
            )
    
    return Result.success()

# ❌ Избягвайте - игнориране на lifecycle статус
def process_without_lifecycle_check():
    # Директни операции без проверки - може да доведе до грешки
    pass
```

### 3. **Валидирайте packaging конфигурацията**

```python
# ✅ Добро - валидирайте packaging преди използване
def setup_product_packaging(product, packaging_configs):
    validation_result = ProductService.validate_packaging_configs(
        product, packaging_configs
    )
    
    if not validation_result.ok:
        return validation_result
    
    # Продължи с настройка
    for config in packaging_configs:
        ProductPackaging.objects.create(
            product=product,
            unit=config['unit'],
            conversion_factor=round_quantity(config['conversion_factor']),
            **config.get('options', {})
        )

# ❌ Избягвайте - създаване без валидация
ProductPackaging.objects.create(...)  # Може да наруши consistency
```

### 4. **Използвайте интегрираните свойства правилно**

```python
# ✅ Добро - използвайте кеширани properties за производителност
def get_product_summary_efficient(product):
    # Използвай properties които са оптимизирани
    stock_data = {
        'total_stock': product.total_stock,          # Кеширана заявка
        'avg_cost': product.weighted_avg_cost,       # Калкулирана с правилна точност
        'stock_value': product.stock_value           # 2dp точност за дисплей
    }
    
    return stock_data

# ❌ Избягвайте - ръчни заявки за данни които са достъпни като properties
def get_product_summary_inefficient(product):
    # Ръчни заявки - бавно и може да има грешки в точността
    items = InventoryItem.objects.filter(product=product)
    total = sum(item.current_qty for item in items)  # Неправилна точност
```

---

## Зависимости

**PRODUCTS app зависи от:**
- Django framework
- CORE app (Result pattern, десетични утилити)
- NOMENCLATURES app (Brand, ProductGroup, UnitOfMeasure, TaxGroup модели)

**Други apps зависят от PRODUCTS:**
- INVENTORY (Product модел за stock tracking)
- PRICING (Product модел за ценообразуване)
- PURCHASES (Product модел за покупки)
- SALES (Product модел за продажби)

---

## История на версиите

- **v1.0** - Основни продуктови модели
- **v1.1** - Добавено packaging система
- **v1.2** - Lifecycle управление
- **v1.3** - Баркод и PLU поддръжка
- **v1.4** - Подобрена валидация
- **v2.0** - Result pattern services
- **v2.1** - Интеграция със склад и ценообразуване
- **v3.0** - Стандартизирана десетична точност, оптимизирани properties

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Актуализирано според актуалния код с десетична точност*