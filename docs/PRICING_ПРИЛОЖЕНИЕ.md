# Документация на PRICING приложението

## 🎯 Преглед

**PRICING приложението** предоставя софистицирано управление на ценообразуването за OptimaPOS, поддържайки множество стратегии за ценообразуване, клиентски групи, промоционални цени, отстъпки при количество и packaging-специфично ценообразуване. То се интегрира с inventory за cost-based ценообразуване и поддържа търсене на цени по баркод.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Ценови модели](#ценови-модели)
3. [Pricing Service](#pricing-service)  
4. [Стратегии за ценообразуване](#стратегии-за-ценообразуване)
5. [VATCalculationService интеграция](#vatcalculationservice-интеграция)
6. [Десетична точност](#десетична-точност)
7. [Интеграционни точки](#интеграционни-точки)
8. [Шаблони за използване](#шаблони-за-използване)
9. [API справочник](#api-справочник)

---

## Архитектура

```
PRICING Структура на приложението:
├── models/
│   ├── base_prices.py        # ProductPrice (базови цени)
│   ├── group_prices.py       # ProductPriceByGroup (клиентски групи)
│   ├── step_prices.py        # ProductStepPrice (отстъпки при количество)
│   ├── promotions.py         # PromotionalPrice (time-based оферти)
│   └── packaging_prices.py   # PackagingPrice (алтернативни единици)
├── services/
│   ├── pricing_service.py    # Главна логика за ценообразуване
│   └── promotion_service.py  # Управление на промоционални кампании
├── admin/
│   ├── prices.py            # Администрация на базови цени
│   ├── promotions.py        # Управление на промоции
│   └── packaging.py         # Настройка на packaging цени
└── views.py                 # API endpoints
```

### Философия на дизайна

- **🎯 Гъвкаво ценообразуване** - Множество стратегии за различни сценарии
- **📊 Базирано на приоритети** - Ясна йерархия: Промоции → Групи → Стъпкови → Базови → Fallback
- **💰 Profit-Aware** - Автоматична интеграция на себестойности за калкулации на печалбата
- **⚡ Location-Based** - Различно ценообразуване за локация/склад
- **🔄 В реално време** - Динамично ценообразуване с мигновени калкулации
- **📦 Packaging поддръжка** - Различни цени за различни packaging единици
- **💰 ДДС интеграция** - Интегрирано с VATCalculationService

---

## Ценови модели

### 1. **ProductPrice** (Базово ценообразуване)

**Цел**: Основно ценообразуване за продукти в специфични локации

```python
from core.models.fields import CurrencyField

# Методи за ценообразуване
pricing_method = [
    'FIXED',    # Фиксирана цена (използва base_price)
    'MARKUP',   # Себестойност + markup % (използва markup_percentage)  
    'AUTO'      # Location default markup
]

# Ключови полета
base_price = CurrencyField()         # Фиксирана продажна цена (2dp)
markup_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # Markup над себестойност
effective_price = CurrencyField()    # Калкулирана финална цена (авто-актуализирана)

# Generic Location поддръжка
content_type = models.ForeignKey(ContentType)
object_id = models.PositiveIntegerField()
priceable_location = GenericForeignKey()
```

**Location гъвкавост:**
```python
# Работи с всяка ILocation имплементация
warehouse_price = ProductPrice.objects.create_for_location(
    location=warehouse,           # InventoryLocation
    product=product,
    pricing_method='FIXED',
    base_price=Decimal('15.99')   # Автоматично 2dp точност
)

online_price = ProductPrice.objects.create_for_location(
    location=online_store,        # OnlineStore  
    product=product,
    pricing_method='MARKUP',
    markup_percentage=Decimal('35.00')
)
```

### 2. **ProductPriceByGroup** (Ценообразуване за клиентски групи)

**Цел**: Специални цени за клиентски сегменти

```python
from core.models.fields import CurrencyField

# Ценообразуване за клиентски сегментация
customer_group = models.ForeignKey('partners.CustomerGroup')
price = CurrencyField()              # Group-специфична цена (2dp точност)
min_quantity = QuantityField()       # Опционално минимално количество

# Generic location поддръжка
content_type = models.ForeignKey(ContentType)
object_id = models.PositiveIntegerField()
```

**Примери за използване:**
- Клиенти на едро получават по-ниски цени
- VIP клиенти получават premium отстъпки
- Корпоративни договори с договорени ставки

### 3. **VATCalculationService интеграция**

**Цел**: Използва VATCalculationService за правилни ДДС калкулации

```python
from nomenclatures.services.vat_calculation_service import VATCalculationService

class ProductPrice(models.Model):
    # ... други полета ...
    
    def get_price_with_vat(self, customer=None, location=None):
        """Получава цена с ДДС използвайки VATCalculationService"""
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        
        # Използва VATCalculationService за правилни ДДС калкулации
        result = VATCalculationService.calculate_line_vat(
            line=None,  # Dummy line object ако е нужно
            entered_price=self.effective_price,
            save=False
        )
        
        if result.ok:
            return result.data['unit_price_with_vat']
        
        # Fallback до основната цена
        return self.effective_price
```

---

## Десетична точност

### Интеграция със стандартизираните полета

```python
from core.models.fields import CurrencyField, QuantityField
from core.utils.decimal_utils import round_currency, round_cost_price

class ProductPrice(models.Model):
    # Автоматично 2dp точност за дисплей цени
    base_price = CurrencyField()
    effective_price = CurrencyField()
    
    # Стандартна точност за количества
    min_quantity = QuantityField()  # 3dp точност
    
    def calculate_effective_price(self):
        """Калкулира effective price със правилна точност"""
        if self.pricing_method == 'FIXED':
            # Директно използвай base_price (вече правилно закръглена)
            self.effective_price = self.base_price
            
        elif self.pricing_method == 'MARKUP':
            # Получи себестойност с висока точност
            cost_price = self.get_current_cost_price()  # 4dp от inventory
            
            # Калкулирай с висока точност
            markup_multiplier = 1 + (self.markup_percentage / 100)
            calculated_price = cost_price * markup_multiplier
            
            # Закръгли за дисплей/съхранение
            self.effective_price = round_currency(calculated_price)  # 2dp
```

### Profit калкулации

```python
from core.utils.decimal_utils import round_currency

def calculate_profit_metrics(self, quantity=None):
    """Калкулира печалби с правилна десетична точност"""
    cost_price = self.get_current_cost_price()  # 4dp точност
    selling_price = self.effective_price        # 2dp точност
    
    if not cost_price or cost_price <= 0:
        return {
            'profit_amount': Decimal('0.00'),
            'markup_percentage': Decimal('0.00'),
            'margin_percentage': Decimal('0.00'),
            'cost_valid': False
        }
    
    # Калкулирай печалба за единица
    profit_per_unit = selling_price - cost_price
    profit_per_unit = round_currency(profit_per_unit)  # 2dp за дисплей
    
    # Калкулирай проценти
    markup_pct = (profit_per_unit / cost_price) * 100
    margin_pct = (profit_per_unit / selling_price) * 100
    
    metrics = {
        'profit_amount': profit_per_unit,
        'markup_percentage': round(markup_pct, 2),
        'margin_percentage': round(margin_pct, 2),
        'cost_valid': True
    }
    
    # Ако е предоставено количество, калкулирай общите суми
    if quantity:
        total_profit = profit_per_unit * quantity
        metrics['total_profit'] = round_currency(total_profit)
    
    return metrics
```

---

## Pricing Service

### Primary API (Result Pattern)

```python
from pricing.services import PricingService
from core.utils.decimal_utils import Decimal

# Получава изчерпателно ценообразуване
result = PricingService.get_product_pricing(
    location=warehouse,
    product=product,
    customer=customer,           # За групово ценообразуване
    quantity=Decimal('25.000'),  # За стъпково ценообразуване
    date=datetime.now().date()   # За промоции
)

if result.ok:
    pricing_data = result.data
    final_price = pricing_data['final_price']        # 2dp точност
    pricing_rule = pricing_data['pricing_rule']      # Кое правило се прилага
    profit_metrics = pricing_data['profit_metrics']  # Анализ на печалбата
    vat_data = pricing_data['vat_data']             # ДДС информация
```

### Анализ на ценообразуването

```python
# Подробна разбивка на ценообразуването
analysis_result = PricingService.get_pricing_analysis(
    location=warehouse,
    product=product,
    customer=customer,
    quantity=Decimal('50.000')
)

if analysis_result.ok:
    analysis = analysis_result.data
    
    # Всички ценови компоненти
    pricing_summary = analysis['pricing_summary']
    discount_analysis = analysis['discount_analysis'] 
    price_comparison = analysis['price_comparison']
    recommendations = analysis['recommendations']
    decimal_info = analysis['decimal_precision_info']  # Информация за точност
```

### Barcode ценообразуване

```python
# Ценообразуване по баркод (продукт или packaging)
barcode_result = PricingService.get_barcode_pricing(
    barcode='1234567890123',
    location=warehouse,
    customer=customer
)

if barcode_result.ok:
    barcode_data = barcode_result.data
    price = barcode_data['price']                    # 2dp точност
    pricing_type = barcode_data['pricing_type']      # 'PRODUCT' or 'PACKAGING'
    
    if barcode_data['packaging']:
        unit_price = barcode_data['unit_price']      # 2dp точност
        conversion_factor = barcode_data['packaging']['conversion_factor']  # 3dp точност
```

---

## Стратегии за ценообразуване

### 1. **Ред на приоритети (Автоматична селекция)**

Системата автоматично избира най-добрата приложима цена използвайки този приоритет:

1. **🎯 Промоции** (най-висок приоритет)
2. **👥 Цени за клиентски групи**  
3. **📦 Стъпкови цени** (базирани на количество)
4. **💰 Базова цена**
5. **🔄 Fallback цена** (себестойност + location markup)

```python
def _determine_final_price(base, promo, group, step, fallback):
    """Определя финалната цена със правилна десетична точност"""
    from core.utils.decimal_utils import round_currency
    
    selected_price = None
    rule_type = None
    
    if promo and promo > 0:
        selected_price, rule_type = promo, 'PROMOTION'
    elif group and group > 0:
        selected_price, rule_type = group, 'CUSTOMER_GROUP'
    elif step and step > 0:
        selected_price, rule_type = step, 'STEP_PRICE'
    elif base and base > 0:
        selected_price, rule_type = base, 'BASE_PRICE'
    else:
        selected_price, rule_type = fallback, 'FALLBACK'
    
    # Гарантирай правилна точност
    final_price = round_currency(selected_price)
    
    return final_price, rule_type
```

### 2. **Cost-Based методи за ценообразуване**

```python
from core.utils.decimal_utils import round_currency

# Фиксирана цена
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product,
    pricing_method='FIXED',
    base_price=Decimal('19.99')  # Автоматично правилна точност
)

# Markup-базирано ценообразуване
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product, 
    pricing_method='MARKUP',
    markup_percentage=Decimal('40.00')  # 40% markup над себестойност
)

# Auto (използва location's default markup)
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product,
    pricing_method='AUTO'  # Използва warehouse.default_markup_percentage
)
```

### 3. **Динамично изчисляване на цени**

```python
from core.utils.decimal_utils import round_currency, round_cost_price

def calculate_effective_price(self):
    """Калкулира effective price със стандартизирана точност"""
    if self.pricing_method == 'FIXED':
        self.effective_price = self.base_price  # Вече с правилна точност
        
    elif self.pricing_method == 'MARKUP':
        cost_price = self.get_current_cost_price()  # 4dp от inventory
        if cost_price and cost_price > 0:
            # Изчисли с висока точност
            markup_multiplier = 1 + (self.markup_percentage / 100)
            calculated_price = cost_price * markup_multiplier
            
            # Закръгли за дисплей/съхранение
            self.effective_price = round_currency(calculated_price)
        else:
            self.effective_price = self.base_price or Decimal('0.00')
            
    elif self.pricing_method == 'AUTO':
        cost_price = self.get_current_cost_price()
        location_markup = getattr(self.priceable_location, 'default_markup_percentage', 0)
        
        if cost_price and cost_price > 0 and location_markup > 0:
            markup_multiplier = 1 + (location_markup / 100)
            calculated_price = cost_price * markup_multiplier
            self.effective_price = round_currency(calculated_price)
        else:
            self.effective_price = self.base_price or Decimal('0.00')
```

---

## VATCalculationService интеграция

### Интеграция с ДДС калкулации

```python
class PricingService:
    @staticmethod
    def get_product_pricing_with_vat(location, product, customer=None, quantity=None):
        """Получава ценообразуване включително ДДС данни"""
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        
        # Получи основно ценообразуване
        pricing_result = PricingService.get_product_pricing(
            location=location,
            product=product,
            customer=customer,
            quantity=quantity
        )
        
        if not pricing_result.ok:
            return pricing_result
        
        pricing_data = pricing_data.data
        net_price = pricing_data['final_price']  # 2dp точност
        
        # Получи ДДС ставка
        vat_rate = VATCalculationService.get_vat_rate(product, location)
        
        # Калкулирай ДДС
        from core.utils.decimal_utils import round_vat_amount, round_currency
        vat_amount = round_vat_amount(net_price * vat_rate / 100)
        gross_price = round_currency(net_price + vat_amount)
        
        # Добави ДДС данни към резултата
        pricing_data['vat_data'] = {
            'net_price': net_price,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'gross_price': gross_price
        }
        
        return Result.success(data=pricing_data)
```

---

## Интеграционни точки

### **С INVENTORY App:**

```python
from core.utils.decimal_utils import round_cost_price

def get_current_cost_price(self):
    """Получава себестойност от inventory за markup калкулации"""
    try:
        from inventory.models import InventoryItem
        item = InventoryItem.objects.get(
            location=self.priceable_location,
            product=self.product
        )
        # InventoryItem.avg_cost вече има 4dp точност
        return item.avg_cost
    except InventoryItem.DoesNotExist:
        # Fallback към product weighted average cost
        cost = self.product.weighted_avg_cost or Decimal('0.0000')
        return round_cost_price(cost)  # Гарантирай 4dp точност
```

**Автоматични актуализации на цените:**
- Когато себестойността в inventory се промени значително (>5%), pricing service се уведомява
- Markup-базираните цени се преизчисляват автоматично с правилна точност
- Историята на промените в цените се поддържа

### **С PRODUCTS App:**

```python
from core.utils.decimal_utils import round_currency

def get_packaging_price(product, packaging):
    """Получава цена за специфично packaging с правилна точност"""
    try:
        pkg_price = PackagingPrice.objects.get(
            product=product,
            packaging=packaging,
            is_active=True
        )
        return pkg_price.price  # Вече с 2dp точност
    except PackagingPrice.DoesNotExist:
        # Калкулирай от базовата цена
        base_price_result = PricingService.get_product_pricing(location, product)
        if base_price_result.ok:
            unit_price = base_price_result.data['final_price']  # 2dp точност
            calculated_price = unit_price * packaging.conversion_factor
            return round_currency(calculated_price)  # Правилно закръгляване
        
        return Decimal('0.00')
```

---

## Шаблони за използване

### 1. **Настройка на базово ценообразуване**

```python
from pricing.models import ProductPrice
from core.utils.decimal_utils import Decimal

# Фиксирано ценообразуване за retail локация
ProductPrice.objects.create_for_location(
    location=retail_store,
    product=widget,
    pricing_method='FIXED',
    base_price=Decimal('24.99')  # Автоматично 2dp точност
)

# Markup ценообразуване за wholesale локация  
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=widget,
    pricing_method='MARKUP',
    markup_percentage=Decimal('25.00')  # 25% над себестойност
)
```

### 2. **Работа с десетична точност**

```python
from core.utils.decimal_utils import round_currency, round_cost_price

def setup_dynamic_pricing():
    # Входни данни могат да имат различна точност
    raw_cost = Decimal('15.256789')      # От inventory система
    raw_markup = Decimal('33.333333')   # От калкулации
    
    # Използвай правилното закръгляване
    cost_price = round_cost_price(raw_cost)     # 15.2568 за калкулации
    markup_pct = round(raw_markup, 2)           # 33.33 за markup
    
    # Калкулирай с висока точност
    calculated_price = cost_price * (1 + markup_pct / 100)
    
    # Закръгли за дисплей/съхранение
    final_price = round_currency(calculated_price)  # 20.34 за дисплей
    
    return {
        'cost_price': cost_price,       # 4dp
        'markup_percentage': markup_pct, # 2dp
        'selling_price': final_price    # 2dp
    }
```

---

## API справочник

### PricingService методи

| Метод | Цел | Връща | Ключови параметри |
|-------|-----|-------|------------------|
| `get_product_pricing()` | Пълно изчисляване на ценообразуването | Result | location, product, customer, quantity, date |
| `get_product_pricing_with_vat()` | Ценообразуване включително ДДС | Result | location, product, customer, quantity |
| `get_pricing_analysis()` | Подробна разбивка на ценообразуването | Result | location, product, customer, quantity |
| `get_all_pricing_options()` | Всички налични правила за ценообразуване | Result | location, product, customer |
| `validate_pricing_setup()` | Валидира конфигурацията на цените | Result | location, product |
| `get_barcode_pricing()` | Ценообразуване чрез търсене на баркод | Result | barcode, location, customer |

### Структури от данни в Result

**Пълен резултат от ценообразуването:**
```python
{
    'final_price': Decimal('21.24'),        # 2dp точност
    'pricing_rule': 'CUSTOMER_GROUP',
    'base_price': Decimal('24.99'),         # 2dp точност
    'promotional_price': None,
    'group_price': Decimal('21.24'),        # 2dp точност
    'step_price': None,
    'fallback_price': Decimal('18.75'),     # 2dp точност
    'cost_price': Decimal('15.0000'),       # 4dp точност от inventory
    'quantity': Decimal('10.000'),          # 3dp точност
    'location_code': 'WH01',
    'product_code': 'WIDGET123',
    'customer_info': {
        'customer_id': 42,
        'price_group': 'Wholesale'
    },
    'profit_metrics': {
        'profit_amount': Decimal('6.24'),    # 2dp точност
        'markup_percentage': Decimal('41.60'),
        'margin_percentage': Decimal('29.38'),
        'cost_valid': True
    },
    'vat_data': {
        'net_price': Decimal('21.24'),       # 2dp точност
        'vat_rate': Decimal('20.00'),
        'vat_amount': Decimal('4.25'),       # 2dp точност
        'gross_price': Decimal('25.49')      # 2dp точност
    },
    'decimal_precision_info': {
        'currency_precision': 2,
        'cost_precision': 4,
        'quantity_precision': 3
    }
}
```

---

## Най-добри практики

### 1. **Винаги използвайте Result Pattern**

```python
# ✅ Добро
result = PricingService.get_product_pricing(location, product, customer)
if result.ok:
    price = result.data['final_price']           # 2dp точност
    profit = result.data['profit_metrics']['profit_amount']  # 2dp точност
else:
    handle_pricing_error(result.code, result.msg)

# ❌ Избягвайте директен достъп до модел за сложно ценообразуване
try:
    price = ProductPrice.objects.get(product=product).effective_price
except ProductPrice.DoesNotExist:
    price = Decimal('0.00')  # Липсва групово ценообразуване, стъпково ценообразуване, и т.н.
```

### 2. **Използвайте правилната десетична точност**

```python
# ✅ Добро - използвайте стандартизираните утилити
from core.utils.decimal_utils import round_currency, round_cost_price

# За цени които се показват на клиента
display_price = round_currency(Decimal('24.9876'))    # → 24.99

# За вътрешни калкулации на себестойност
cost = round_cost_price(Decimal('15.256789'))         # → 15.2568

# За ДДС суми
vat = round_vat_amount(Decimal('4.8976'))             # → 4.90

# ❌ Избягвайте - директно използване на round()
price = round(Decimal('24.9876'), 2)  # Не използва правилните правила
```

### 3. **Валидирайте настройките на ценообразуването**

```python
# ✅ Добро - валидирайте преди използване
validation = PricingService.validate_pricing_setup(location, product)
if validation.ok:
    pricing_result = PricingService.get_product_pricing(...)
else:
    # Обработете проблеми с конфигурацията
    setup_base_pricing(location, product)

# ❌ Избягвайте предположения че ценообразуването съществува
pricing_result = PricingService.get_product_pricing(...)  # Може да върне fallback
```

### 4. **Интегрирайте с ДДС калкулациите**

```python
# ✅ Добро - използвайте VATCalculationService за ДДС
result = PricingService.get_product_pricing_with_vat(
    location=location,
    product=product,
    customer=customer
)

if result.ok:
    net_price = result.data['vat_data']['net_price']      # 2dp точност
    vat_amount = result.data['vat_data']['vat_amount']     # 2dp точност
    gross_price = result.data['vat_data']['gross_price']   # 2dp точност

# ❌ Избягвайте ръчни ДДС калкулации
manual_vat = price * 0.20  # Може да има неправилна точност
```

---

## Зависимости

**PRICING app зависи от:**
- Django framework
- CORE app (Result pattern, ILocation интерфейс, десетични утилити)
- PRODUCTS app (Product, ProductPackaging модели)
- INVENTORY app (интеграция на себестойности)
- NOMENCLATURES app (VATCalculationService)

**Други apps зависят от PRICING:**
- SALES (ценообразуване на поръчки)
- POS (ценообразуване по баркод)
- REPORTS (анализ на печалбата)
- NOMENCLATURES (ДДС калкулации)

---

## История на версиите

- **v1.0** - Основно фиксирано ценообразуване
- **v1.1** - Добавено markup-базирано ценообразуване
- **v1.2** - Ценообразуване за клиентски групи
- **v1.3** - Стъпково ценообразуване и промоции
- **v1.4** - Generic location поддръжка
- **v1.5** - Packaging ценообразуване
- **v2.0** - Result pattern рефакториране
- **v2.1** - Подобрени API-та за анализ и валидация
- **v3.0** - Стандартизирана десетична точност, VATCalculationService интеграция

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Актуализирано според актуалния код с десетична точност и ДДС интеграция*