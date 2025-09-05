# Документация на CORE приложението

## 🎯 Преглед

**CORE приложението** предоставя основната инфраструктура за OptimaPOS - базови модели, утилити, интерфейси и споделени компоненти, от които всички други приложения зависят.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Основни компоненти](#основни-компоненти)
3. [Интерфейси](#интерфейси)
4. [Service Registry](#service-registry)
5. [Утилити](#утилити)
6. [Модели](#модели)
7. [Модели за полета](#модели-за-полета)
8. [Десетична точност](#десетична-точност)
9. [Шаблони за използване](#шаблони-за-използване)
10. [Интеграционни точки](#интеграционни-точки)

---

## Архитектура

```
CORE Структура на приложението:
├── interfaces/              # Service Registry и абстрактни интерфейси
│   ├── service_registry.py # Централизирано управление на services
│   └── __init__.py         # Интерфейс дефиниции
├── utils/                  # Споделени утилити  
│   ├── result.py          # Result pattern implementation
│   └── decimal_utils.py   # Десетични калкулации
├── models/                 # Базови модели и mixins
│   ├── __init__.py        # Базови модели
│   └── fields.py          # Стандартизирани decimal полета
├── views.py               # Базови views
└── __init__.py
```

### Принципи на основния дизайн

- **🏗️ Основа първо** - Предоставя базова инфраструктура
- **🔌 Интерфейс-базиран** - Дефинира договори за всички services
- **⚡ Result Pattern** - Стандартизирано обработване на грешки
- **🏭 Service Registry** - Централизирано управление на dependencies
- **♻️ Преизползваемост** - Споделени компоненти в приложенията

---

## Основни компоненти

### 1. **Result Pattern** (`core/utils/result.py`)

Стандартизиран тип за връщане за всички service операции:

```python
from core.utils.result import Result

# Случай на успех
return Result.success(
    data={'document': delivery}, 
    msg='Документът е създаден успешно'
)

# Случай на грешка
return Result.error(
    code='VALIDATION_FAILED',
    msg='Липсват задължителни полета'
)

# Използване
result = service.create_document(...)
if result.ok:
    document = result.data['document']
else:
    print(f"Грешка: {result.msg}")
```

**Предимства:**
- ✅ Консистентно обработване на грешки във всички apps
- ✅ Без изключения за неуспехи в бизнес логиката
- ✅ Богата информация за грешки с кодове
- ✅ Операции които могат да се свързват в верига

### 2. **Service Registry** (`core/interfaces/service_registry.py`)

Централизирано управление на service dependencies чрез интерфейси:

```python
from core.interfaces.service_registry import ServiceRegistry

# Resolve services по интерфейс име
pricing_service = ServiceRegistry.resolve('IPricingService')
product_service = ServiceRegistry.resolve('IProductService')
inventory_service = ServiceRegistry.resolve('IInventoryService')

# Използване с fallback към директни импорти
try:
    pricing_service = ServiceRegistry.resolve('IPricingService')
    result = pricing_service.calculate_line_price(product, quantity)
except ImportError:
    # Fallback към директен импорт за backward compatibility
    from pricing.services import PricingService
    result = PricingService.calculate_line_price(product, quantity)
```

**ServiceResolverMixin за лесна интеграция:**

```python
from core.interfaces import ServiceResolverMixin

class MyView(ServiceResolverMixin, View):
    def get(self, request):
        # Лесен достъп до услуги
        product_service = self.get_product_service()
        pricing_service = self.get_pricing_service()
        inventory_service = self.get_inventory_service()
        
        return JsonResponse(product_service.get_product_data())
```

**Предимства:**
- ✅ Централизирано управление на service dependencies
- ✅ Кеширане на service instances за производителност
- ✅ Fallback към директни импорти за backward compatibility
- ✅ Лесна интеграция чрез ServiceResolverMixin

### 3. **Базови модели** (`core/models/`)

Предоставя абстрактни базови модели които други apps наследяват:

```python
# Пример за използване в други apps
from core.models import TimeStampedModel, UserTrackingModel

class Product(TimeStampedModel, UserTrackingModel):
    # Автоматично получава created_at, updated_at, created_by, updated_by полета
    name = models.CharField(max_length=200)
```

**Налични базови модели:**
- `TimeStampedModel` - Добавя created_at, updated_at
- `UserTrackingModel` - Добавя created_by, updated_by  
- `ActiveModel` - Добавя is_active поле с manager

---

## Интерфейси

Директорията **interfaces/** дефинира договори за всички основни services:

### Налични интерфейси

| Интерфейс | Цел | Използван от |
|-----------|-----|-------------|
| `IDocumentService` | Документни операции | nomenclatures, purchases |
| `IInventoryService` | Управление на склада | inventory app |
| `IMovementService` | Складови движения | inventory app |
| `IPricingService` | Ценови калкулации | pricing app |
| `IVATCalculationService` | ДДС изчисления | nomenclatures |
| `ISupplierService` | Операции с доставчици | partners app |
| `IProductService` | Продуктови операции | products app |
| `ILocation` | Интерфейс за локации | inventory, pricing |

### Пример за използване на интерфейс

```python
from core.interfaces import IDocumentService

class MyDocumentService(IDocumentService):
    def create_document(self, model_class, data, user, location) -> Result:
        # Имплементация тук
        pass
        
    def transition_document(self, document, to_status, user, comments) -> Result:
        # Имплементация тук
        pass
```

**Предимства:**
- ✅ Прилага консистентен API в имплементациите
- ✅ Прави тестването по-лесно с mock-ове
- ✅ Ясни договори между apps
- ✅ IDE поддръжка с type hints

---

## Service Registry

### Централизирано управление на services

Service Registry предоставя централизирано resolve-ване на services чрез интерфейс имена:

```python
from core.interfaces.service_registry import ServiceRegistry

# Resolve по интерфейс име
pricing_service = ServiceRegistry.resolve('IPricingService')
result = pricing_service.calculate_line_price(product, quantity)

# Resolve с fallback
inventory_service = ServiceRegistry.resolve('IInventoryService')
if inventory_service:
    result = inventory_service.get_stock_level(product, location)
```

### ServiceResolverMixin

Mixin който предоставя лесен достъп до services:

```python
from core.interfaces import ServiceResolverMixin

class DeliveryReceiptView(ServiceResolverMixin, View):
    def get_queryset(self):
        # Лесен достъп до services
        inventory_service = self.get_inventory_service()
        return inventory_service.filter_delivery_receipts(...)
    
    def post(self, request):
        product_service = self.get_product_service()
        product = product_service.get_by_id(request.data['product_id'])
        
        pricing_service = self.get_pricing_service() 
        price = pricing_service.calculate_price(product, quantity)
```

**Налични методи в ServiceResolverMixin:**
- `get_product_service()` - IProductService
- `get_pricing_service()` - IPricingService
- `get_inventory_service()` - IInventoryService
- `get_document_service()` - IDocumentService

---

## Утилити

### 1. **Result Pattern** (`utils/result.py`)

Вижте подробното описание по-горе в основните компоненти.

### 2. **Десетични утилити** (`utils/decimal_utils.py`)

Софистицирана система за десетична точност съобразена с българското данъчно законодателство:

```python
from core.utils.decimal_utils import (
    round_currency,      # 2 десетични места за дисплей
    round_cost_price,    # 4 десетични места за калкулации
    round_vat_amount,    # 2 десетични места за ДДС
    round_tax_base,      # 2 десетични места за данъчна основа
    round_quantity       # 3 десетични места за количества
)

# За дисплей/съхранение цени
display_price = round_currency(calculation_result)

# За вътрешни себестойностни калкулации
batch_cost = round_cost_price(batch.cost_price)

# За ДДС суми
vat_amount = round_vat_amount(net_amount * vat_rate)

# За данъчна основа
tax_base = round_tax_base(net_amount)

# За количества (поддържа грамове/ml)
quantity = round_quantity(Decimal('10.567'))  # → 10.567
```

**Ключови принципи:**
- **Валутни суми**: 2dp за дисплей и съхранение
- **Себестойности**: 4dp за точни калкулации
- **ДДС суми**: 2dp съгласно данъчното законодателство
- **Данъчна основа**: 2dp съгласно данъчното законодателство
- **Количества**: 3dp за поддръжка на грамове/ml

---

## Модели

### Примери за базови модели

```python
# core/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class TimeStampedModel(models.Model):
    """Базов модел със следене на timestamps"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class UserTrackingModel(TimeStampedModel):
    """Базов модел със следене на потребители"""
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, 
        related_name='+', verbose_name='Създаден от'
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, 
        related_name='+', null=True, verbose_name='Актуализиран от'
    )
    
    class Meta:
        abstract = True

class ActiveModel(models.Model):
    """Базов модел с активна/неактивна функционалност"""
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    
    objects = models.Manager()  # По подразбиране manager
    active_objects = ActiveManager()  # Само активни записи
    
    class Meta:
        abstract = True
```

---

## Модели за полета

### Стандартизирани decimal полета (`core/models/fields.py`)

Системата предоставя стандартизирани decimal полета които прилагат консистентна точност:

```python
from core.models.fields import CurrencyField, CostPriceField, QuantityField

class MyModel(models.Model):
    # Валутни полета (2dp, правилно закръгляване)
    price = CurrencyField(verbose_name='Цена')
    total = CurrencyField(verbose_name='Общо')
    
    # Себестойностни полета (4dp, калкулационна точност)
    cost = CostPriceField(verbose_name='Себестойност')
    avg_cost = CostPriceField(verbose_name='Средна себестойност')
    
    # Количествени полета (3dp, поддържа грамове/ml)
    quantity = QuantityField(verbose_name='Количество')
    received_qty = QuantityField(verbose_name='Получено количество')
```

**Field типове:**

| Field тип | Decimal Places | Използване |
|-----------|---------------|------------|
| `CurrencyField` | 2 | Цени за дисплей, фактуриране |
| `CostPriceField` | 4 | Себестойности, калкулации |
| `VATAmountField` | 2 | ДДС суми |
| `TaxBaseField` | 2 | Данъчна основа |
| `QuantityField` | 3 | Количества (поддържа грамове) |

**Предимства:**
- ✅ Консистентна точност в цялата система
- ✅ Автоматично правилно закръгляване
- ✅ Съответствие с българското данъчно законодателство
- ✅ Подходящи за financial калкулации

---

## Десетична точност

### Систем за точност

OptimaPOS има софистицирана система за десетична точност:

```python
from core.utils.decimal_utils import *

# Стандартни точности:
# - Валути: 2dp (24.99)
# - Себестойности: 4dp (15.2567) - за точни калкулации
# - Количества: 3dp (10.567) - поддържа грамове/ml
# - ДДС: 2dp (4.80) - данъчно законодателство
```

### Правила за използване

```python
# ✅ ПРАВИЛНО - Използвай подходящата функция
from core.utils.decimal_utils import round_currency, round_cost_price

# За цени които се показват на потребителя
display_price = round_currency(Decimal('24.9876'))  # → 24.99

# За вътрешни калкулации
internal_cost = round_cost_price(Decimal('15.256789'))  # → 15.2568

# ❌ НЕПРАВИЛНО - Директно използване на round()
price = round(Decimal('24.9876'), 2)  # Не използва правилните rules
```

### Интеграция с полета

```python
# Полетата автоматично прилагат правилната точност
class ProductPrice(models.Model):
    # Автоматично 2dp с правилно закръгляване
    selling_price = CurrencyField()
    
    # Автоматично 4dp за калкулационна точност  
    cost_price = CostPriceField()
    
    def save(self, *args, **kwargs):
        # Полетата автоматично закръгляват стойностите
        super().save(*args, **kwargs)
```

---

## Шаблони за използване

### 1. **Service Implementation Pattern**

```python
from core.interfaces import IDocumentService
from core.utils.result import Result
from core.interfaces.service_registry import ServiceRegistry

class MyService(IDocumentService):
    def create_document(self, model_class, data, user, location) -> Result:
        try:
            # Използвай други services чрез Service Registry
            pricing_service = ServiceRegistry.resolve('IPricingService')
            
            # Бизнес логика тук
            document = model_class.objects.create(**data)
            return Result.success(data={'document': document})
        except Exception as e:
            return Result.error('CREATION_FAILED', str(e))
```

### 2. **Result Handling Pattern**

```python
# В views или други services
def my_view(request):
    service = MyService()
    result = service.create_document(...)
    
    if result.ok:
        # Път на успех
        return JsonResponse({
            'success': True,
            'data': result.data
        })
    else:
        # Път на грешка
        return JsonResponse({
            'success': False,
            'error': result.msg,
            'code': result.code
        }, status=400)
```

### 3. **Base Model Inheritance**

```python
# В всяко приложение
from core.models import TimeStampedModel, UserTrackingModel
from core.models.fields import CurrencyField, QuantityField

class MyModel(TimeStampedModel, UserTrackingModel):
    """Получава timestamp и user tracking автоматично"""
    name = models.CharField(max_length=100)
    price = CurrencyField()  # Автоматично 2dp точност
    quantity = QuantityField()  # Автоматично 3dp точност
    
    def save(self, *args, **kwargs):
        # Custom save логика
        super().save(*args, **kwargs)
```

### 4. **ServiceResolverMixin Pattern**

```python
from core.interfaces import ServiceResolverMixin

class MyView(ServiceResolverMixin, View):
    def get(self, request):
        # Лесен достъп до services
        product_service = self.get_product_service()
        pricing_service = self.get_pricing_service()
        
        # Използвай services
        product = product_service.get_by_id(product_id)
        price = pricing_service.calculate_price(product, quantity)
        
        return JsonResponse({
            'product': product.name,
            'price': str(price)
        })
```

---

## Интеграционни точки

### Как другите Apps използват CORE

**NOMENCLATURES App:**
- Наследява от базови модели за документи
- Използва `Result` pattern за всички операции
- Интегрира се чрез Service Registry
- Използва стандартизирани decimal полета

**PURCHASES App:**  
- Използва ServiceResolverMixin за достъп до услуги
- Наследява базови модели за purchase документи
- Делегира към nomenclatures services чрез Service Registry

**INVENTORY App:**
- Имплементира `IInventoryService` и `IMovementService`
- Използва `Result` pattern за movement операции
- Използва CostPriceField за точни калкулации
- Интегрира се чрез Service Registry

**PRICING App:**
- Имплементира `IPricingService`
- Използва `Result` за price калкулации
- Използва десетични утилити за правилно закръгляване
- Регистрира се в Service Registry

**PARTNERS App:**
- Използва базови модели за suppliers/customers
- `Result` pattern за partner операции
- ServiceResolverMixin в views

---

## Най-добри практики

### 1. **Винаги използвай Result Pattern**
```python
# ✅ Добро
def create_something() -> Result:
    if validation_fails:
        return Result.error('VALIDATION_FAILED', 'Детайли тук')
    return Result.success(data={'item': item})

# ❌ Избягвай
def create_something():
    if validation_fails:
        raise ValidationError('Детайли тук')  # Не използвай exceptions за бизнес логика
```

### 2. **Използвай Service Registry**
```python
# ✅ Добро - използвай Service Registry  
from core.interfaces.service_registry import ServiceRegistry

pricing_service = ServiceRegistry.resolve('IPricingService')
result = pricing_service.calculate_price(product, quantity)

# ❌ Избягвай - директни импорти където е възможно
from pricing.services import PricingService  # Използвай само за fallback
```

### 3. **Използвай стандартизирани полета**
```python
# ✅ Добро
from core.models.fields import CurrencyField, QuantityField

class Product(models.Model):
    price = CurrencyField()  # Автоматично правилна точност
    quantity = QuantityField()  # Поддържа грамове/ml

# ❌ Избягвай
class Product(models.Model):
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Ръчна конфигурация
```

### 4. **Използвай десетични утилити**
```python
# ✅ Добро
from core.utils.decimal_utils import round_currency, round_cost_price

display_price = round_currency(calculation_result)
internal_cost = round_cost_price(batch_cost)

# ❌ Избягвай
display_price = round(calculation_result, 2)  # Не следва правилата
```

### 5. **ServiceResolverMixin в Views**
```python
# ✅ Добро
from core.interfaces import ServiceResolverMixin

class MyView(ServiceResolverMixin, View):
    def get(self, request):
        service = self.get_pricing_service()  # Лесен достъп
        return JsonResponse(service.get_data())

# ❌ Избягвай - ръчно resolve-ване в всеки view
class MyView(View):
    def get(self, request):
        service = ServiceRegistry.resolve('IPricingService')  # Повторение
```

---

## Зависимости

**CORE app зависи от:**
- Django framework само
- Няма други OptimaPOS apps

**Други apps зависят от CORE:**
- ВСИЧКИ други OptimaPOS apps импортират от CORE
- CORE трябва да е в INSTALLED_APPS преди другите custom apps

---

## Тестване

```python
# Пример за тест използвайки CORE компоненти
from core.utils.result import Result
from core.interfaces import IDocumentService
from core.interfaces.service_registry import ServiceRegistry

class TestDocumentService(IDocumentService):
    """Mock implementation за тестване"""
    def create_document(self, *args, **kwargs):
        return Result.success(data={'document': 'mock_doc'})

def test_service_registry():
    # Test Service Registry resolve
    service = ServiceRegistry.resolve('IDocumentService')
    result = service.create_document()
    assert result.ok
    assert result.data['document'] == 'mock_doc'

def test_decimal_utils():
    from core.utils.decimal_utils import round_currency
    result = round_currency(Decimal('24.9876'))
    assert result == Decimal('24.99')
```

---

## История на версиите

- **v1.0** - Първоначален CORE app с основни утилити
- **v1.5** - Добавена система от интерфейси  
- **v2.0** - Result pattern имплементация
- **v2.1** - Подобрени базови модели
- **v3.0** - Service Registry Pattern, стандартизирани полета, десетична точност

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Актуализирано според актуалния код*