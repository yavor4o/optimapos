# Документация на INVENTORY приложението

## 🎯 Преглед

**INVENTORY приложението** управлява цялото следене на склада, складови движения и операции във складовете в OptimaPOS. То служи като централна система за мониторинг на продуктови количества, локации, batch следене и автоматизирани складови движения задействани от промени в статуса на документите.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Основни модели](#основни-модели)  
3. [Услуги](#услуги)
4. [Система за складови движения](#система-за-складови-движения)
5. [Batch следене](#batch-следене)
6. [Интеграция с документната система](#интеграция-с-документната-система)
7. [Десетична точност](#десетична-точност)
8. [Шаблони за използване](#шаблони-за-използване)
9. [API справочник](#api-справочник)

---

## Архитектура

```
INVENTORY Структура на приложението:
├── models/
│   ├── locations.py         # InventoryLocation
│   ├── movements.py         # InventoryMovement (източник на истината)
│   └── items.py            # InventoryItem, InventoryBatch (кеширани данни)
├── services/
│   ├── movement_service.py  # Създаване на движения и FIFO логика
│   └── inventory_service.py # Валидация на склада и резервации
├── admin.py                # Admin интерфейс
└── views.py               # API endpoints
```

### Философия на дизайна

- **🎯 Movement-Centric** - Всички складови промени се следят като движения
- **📊 Източник на истината** - InventoryMovement е авторитативният запис
- **⚡ Кеширана производителност** - InventoryItem/InventoryBatch за бързи заявки
- **🔄 Event-Driven** - Автоматични движения от промени в статуса на документите
- **🏷️ Batch следене** - Пълна FIFO поддръжка с дати на изтичане
- **🔒 Concurrency безопасност** - Атомни операции с правилно заключване
- **💰 Десетична точност** - 4dp за себестойности, 2dp за дисплей цени

---

## Основни модели

### 1. **InventoryMovement** (Източник на истината)

**Цел**: Записва всяка складова транзакция с пълен audit trail

```python
from core.models.fields import CostPriceField, CurrencyField, QuantityField

class InventoryMovement(models.Model):
    # Ключови полета
    movement_type = models.CharField(
        choices=['IN', 'OUT', 'TRANSFER', 'ADJUSTMENT', 'PRODUCTION', 'CYCLE_COUNT']
    )
    quantity = QuantityField()  # Винаги положителна (типът определя посоката)
    cost_price = CostPriceField()  # Единична себестойност за това движение (4dp)
    sale_price = CurrencyField()  # Единична продажна цена за проследяване на печалбата (2dp)
    profit_amount = CurrencyField()  # Калкулирана: sale_price - cost_price

    # Интеграция с документи
    source_document_type = models.CharField(max_length=50)  # e.g., 'DELIVERY', 'SALE'
    source_document_number = models.CharField(max_length=100)
    source_document_line_id = models.PositiveIntegerField()

    # Batch/Lot следене
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True)
    serial_number = models.CharField(max_length=100, blank=True)

    # Transfer-специфични
    from_location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT)
    to_location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, null=True)
```

**Ключови свойства:**
- `effective_quantity` - Знаково количество базирано на типа движение
- `total_cost_value` - quantity × cost_price  
- `total_profit` - quantity × profit_amount
- `profit_margin_percentage` - Печалба като процент от продажната цена

**Десетична точност интеграция:**
```python
from core.utils.decimal_utils import round_cost_price, round_currency

def save(self, *args, **kwargs):
    # Автоматично правилно закръгляване
    if self.cost_price:
        self.cost_price = round_cost_price(self.cost_price)  # 4dp
    if self.sale_price:
        self.sale_price = round_currency(self.sale_price)    # 2dp
    super().save(*args, **kwargs)
```

### 2. **InventoryItem** (Кеш за производителност)

**Цел**: Бърз достъп до текущи нива на склада за локация/продукт

```python
class InventoryItem(models.Model):
    # Текущо състояние
    current_qty = QuantityField()      # Общо количество на разположение
    reserved_qty = QuantityField()     # Количество резервирано за поръчки
    avg_cost = CostPriceField()        # Претеглена средна себестойност (4dp)

    # Изведени свойства
    @property
    def available_qty(self):
        return self.current_qty - self.reserved_qty

    @property 
    def stock_value(self):
        from core.utils.decimal_utils import round_currency
        return round_currency(self.current_qty * self.avg_cost)
```

**Освежаване на кеша**: Автоматично актуализиран от MovementService операции

### 3. **InventoryBatch** (Batch следене)

**Цел**: Проследява индивидуални партиди за FIFO и управление на дати на изтичане

```python
class InventoryBatch(models.Model):
    # Batch идентичност
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True)

    # Количества
    received_qty = QuantityField()      # Първоначално получено
    remaining_qty = QuantityField()     # Все още налично
    cost_price = CostPriceField()       # Себестойност за тази партида (4dp)

    # Batch статус
    is_unknown_batch = models.BooleanField(default=False)  # Авто-генерирана партида
    received_date = models.DateField()
```

### 4. **InventoryLocation**

**Цел**: Дефинира складови локации със специфични поведения

```python
class InventoryLocation(models.Model):
    # Настройки на локацията
    allow_negative_stock = models.BooleanField(default=False)
    should_track_batches = models.BooleanField(default=True)

    # Методи
    def should_track_batches(self, product):
        return self.track_batches and product.track_batches
```

---

## Услуги

### 1. **MovementService** - Основни операции с движения

**Първичен API (Result Pattern):**

```python
from inventory.services.movement_service import MovementService
from core.utils.decimal_utils import Decimal

# Входящ склад
result = MovementService.create_incoming_stock(
    location=warehouse,
    product=product,
    quantity=Decimal('100.000'),
    cost_price=Decimal('12.5000'),  # 4dp точност за себестойности
    source_document_type='DELIVERY',
    source_document_number='DEL-001',
    batch_number='BATCH-2024-001'
)

# Изходящ склад (FIFO)
result = MovementService.create_outgoing_stock(
    location=warehouse,
    product=product,
    quantity=Decimal('50.000'),
    source_document_type='SALE',
    sale_price=Decimal('18.00'),  # 2dp за дисплей цени
    use_fifo=True
)

# Складов трансфер
result = MovementService.create_stock_transfer(
    from_location=warehouse_a,
    to_location=warehouse_b,
    product=product,
    quantity=Decimal('25.000')
)

# Корекция на склада
result = MovementService.create_stock_adjustment(
    location=warehouse,
    product=product,
    adjustment_qty=Decimal('-5.000'),  # Отрицателно за намаляване
    reason='Повредени стоки'
)
```

**Интеграция с документи:**
```python
# Обработва документ автоматично
result = MovementService.process_document_movements(delivery_document)

# Синхронизира движения със статуса на документа
result = MovementService.sync_movements_with_document(purchase_order)
```

### 2. **InventoryService** - Валидация на склада и резервации

```python
from inventory.services.inventory_service import InventoryService

# Проверява наличност на склада
result = InventoryService.validate_availability(
    location, product, Decimal('75.000')
)
if result.ok:
    available_qty = result.data['available_qty']
    can_fulfill = result.data['can_fulfill']

# Наличност на партиди (FIFO-aware)
result = InventoryService.validate_batch_availability(
    location, product, Decimal('75.000')
)
if result.ok:
    batch_details = result.data['batch_details']

# Резервира склад
result = InventoryService.reserve_stock_qty(
    location, product, Decimal('25.000')
)

# Резюме на склада
result = InventoryService.get_stock_summary(location, product)
stock_data = result.data
```

---

## Система за складови движения

### Типове движения

| Тип | Посока | Цел | Пример |
|-----|--------|-----|--------|
| `IN` | Входящо | Покупки, получавания | Получаване на доставка |
| `OUT` | Изходящо | Продажби, издавания | Изпълнение на продажба |
| `TRANSFER` | И двете | Между локации | Складов трансфер |
| `ADJUSTMENT` | И двете | Корекции | Корекции от инвентаризация |
| `PRODUCTION` | Входящо | Производство | Сглобяване на продукт |
| `CYCLE_COUNT` | И двете | Складови одити | Корекции от физическо броене |

### FIFO имплементация

**Автоматичен FIFO за batch-tracked продукти:**

```python
# При създаване на изходящо движение за batch-tracked продукт
movements = MovementService._create_fifo_outgoing_movements(
    location, product, quantity=Decimal('100.000'),
    sale_price=Decimal('15.00')
)

# Резултира в множество движения от различни партиди:
# Movement 1: 60 единици от BATCH-A @ себестойност $10.00
# Movement 2: 40 единици от BATCH-B @ себестойност $12.00
# Общата печалба се калкулира за всяка партида
```

### Проследяване на печалбата

**Подобрен Movement модел:**
- `sale_price` - Единична продажна цена за OUT движения (2dp точност)
- `profit_amount` - Калкулирана печалба за единица (2dp точност)
- `total_profit` свойство - Обща печалба за движението
- `profit_margin_percentage` - Марж като процент

**Анализ на печалбата:**
```python
# Получава резюме на печалбата за локация
summary = InventoryMovement.get_profit_summary(
    location=warehouse,
    date_from=start_date,
    date_to=end_date
)

# Резултатите включват:
# - total_revenue, total_cost, total_profit
# - profit_margin_percentage
# - Брой движения и количества
```

---

## Batch следене

### Автоматично генерирани партиди

**За продукти изискващи batch следене:**
```python
# Когато не е предоставен batch_number за входящо движение
auto_batch = f"AUTO_{product.code}_{date}_{location.code}"
# Пример: "AUTO_WIDGET123_241201_WH01"
```

### Batch валидация

```python
def clean(self):
    # Авто-генерира партида за tracked продукти
    if (self.product and self.product.track_batches and
            self.movement_type == self.IN and not self.batch_number):
        self.batch_number = self.generate_auto_batch()
```

### FIFO Batch консумация

**Ред**: `created_at` ASC (най-старите първо)
```python
available_batches = InventoryBatch.objects.filter(
    location=location,
    product=product, 
    remaining_qty__gt=0
).order_by('created_at')

for batch in available_batches:
    qty_from_batch = min(remaining_qty, batch.remaining_qty)
    # Създава движение от тази партида
    # Актуализира batch.remaining_qty
```

---

## Интеграция с документната система

### Status-Driven създаване на движения

**Конфигурация чрез DocumentTypeStatus:**

```python
# Когато се променя статуса на документа
current_config = DocumentTypeStatus.objects.filter(
    document_type=document.document_type,
    status__code=document.status,
    is_active=True
).first()

if current_config.creates_inventory_movements:
    # Създава движения автоматично
    movements = MovementService.process_document_movements(document)
```

### Синхронизация на документни движения

**Умна Sync логика:**
```python
def sync_movements_with_document(document):
    # 1. Проверява дали корекцията е позволена от status конфигурацията
    if not current_config.allows_movement_correction:
        return error
    
    # 2. Изтрива съществуващи движения
    original_movements.delete()
    reversal_movements.delete()
    
    # 3. Пресъздава ако статусът изисква движения
    if current_config.creates_inventory_movements:
        new_movements = create_from_document(document)
```

### Поддържани типове документи

| Тип документ | Тип движение | Trigger статус | Бележки |
|--------------|-------------|---------------|---------|
| DeliveryReceipt | IN | completed | Създава входящ склад |
| PurchaseOrder | IN | approved (ако auto_receive) | Опционално авто-получаване |
| SalesOrder | OUT | shipped | Създава изходящ склад |
| StockTransfer | TRANSFER | completed | Между локации |
| StockAdjustment | ADJUSTMENT | approved | Корекции на количества |

---

## Десетична точност

### Интеграция със стандартизираните полета

```python
from core.models.fields import CostPriceField, CurrencyField, QuantityField
from core.utils.decimal_utils import round_cost_price, round_currency

class InventoryMovement(models.Model):
    # Автоматично 3dp точност за количества
    quantity = QuantityField()
    
    # Автоматично 4dp точност за калкулационни цени
    cost_price = CostPriceField()
    
    # Автоматично 2dp точност за дисплей цени
    sale_price = CurrencyField()
    profit_amount = CurrencyField()
```

### Калкулационна логика

```python
def calculate_profit_amount(self):
    """Калкулира печалба използвайки правилната десетична точност"""
    if self.sale_price and self.cost_price:
        # Междинни калкулации с по-висока точност
        profit_per_unit = self.sale_price - self.cost_price
        # Финално закръгляване за дисплей
        self.profit_amount = round_currency(profit_per_unit)
    return self.profit_amount

@property
def total_profit(self):
    """Обща печалба за движението"""
    if self.profit_amount:
        total = self.quantity * self.profit_amount
        return round_currency(total)
    return Decimal('0.00')
```

### Weighted Average Cost калкулация

```python
def update_average_cost(self, new_quantity, new_cost):
    """Актуализира претеглената средна себестойност с правилна точност"""
    from core.utils.decimal_utils import round_cost_price
    
    current_value = self.current_qty * self.avg_cost
    new_value = new_quantity * new_cost
    total_qty = self.current_qty + new_quantity
    
    if total_qty > 0:
        # Калкулира с висока точност, после закръгля за съхранение
        new_avg = (current_value + new_value) / total_qty
        self.avg_cost = round_cost_price(new_avg)  # 4dp за калкулации
```

---

## Шаблони за използване

### 1. **Document Processing Pattern**

```python
# В DocumentService когато статуса се променя към 'completed'
from inventory.services.movement_service import MovementService

def transition_to_completed(self):
    # Друга логика за промяна на статус...
    
    # Проверява дали този статус създава движения
    if self.status_config.creates_inventory_movements:
        movement_result = MovementService.process_document_movements(self.document)
        if not movement_result.ok:
            return Result.error('MOVEMENT_FAILED', movement_result.msg)
    
    return Result.success()
```

### 2. **Sales Integration Pattern**

```python
# В sales обработка
def fulfill_order_line(order_line):
    # Проверява наличност
    availability = InventoryService.validate_availability(
        location, product, order_line.quantity
    )
    
    if not availability.ok:
        return availability  # Недостатъчен склад
    
    # Създава изходящо движение с проследяване на печалбата
    movement_result = MovementService.create_outgoing_stock(
        location=warehouse,
        product=order_line.product,
        quantity=order_line.quantity,
        source_document_type='SALE',
        source_document_number=order.number,
        sale_price=order_line.unit_price,
        use_fifo=True
    )
    
    return movement_result
```

### 3. **Reservation Pattern**

```python
# Резервира склад за чакащи поръчки
def reserve_stock_for_order(order):
    for line in order.lines.all():
        reserve_result = InventoryService.reserve_stock_qty(
            location=order.location,
            product=line.product,
            quantity=line.quantity,
            reason=f"Резервирано за поръчка {order.number}"
        )
        
        if not reserve_result.ok:
            # Обработва недостатъчен склад
            return reserve_result
    
    return Result.success()
```

### 4. **Десетична точност Pattern**

```python
# Правилна работа с цени и калкулации
from core.utils.decimal_utils import round_cost_price, round_currency

def process_inventory_transaction():
    # Входни данни могат да имат различна точност
    raw_cost = Decimal('15.256789')
    raw_price = Decimal('24.9876')
    
    # Използвай правилното закръгляване за различни цели
    storage_cost = round_cost_price(raw_cost)    # 15.2568 за калкулации
    display_price = round_currency(raw_price)    # 24.99 за дисплей
    
    # Създай движение с правилна точност
    result = MovementService.create_incoming_stock(
        cost_price=storage_cost,    # 4dp за точни калкулации
        sale_price=display_price,   # 2dp за дисплей
        ...
    )
```

---

## API справочник

### MovementService методи

| Метод | Цел | Връща | Ключови параметри |
|-------|-----|-------|------------------|
| `create_incoming_stock()` | Добавя inventory | Result | location, product, quantity, cost_price |
| `create_outgoing_stock()` | Премахва inventory | Result | location, product, quantity, sale_price |
| `create_stock_transfer()` | Трансфер между локации | Result | from_location, to_location, product, quantity |
| `create_stock_adjustment()` | Корекции на inventory | Result | location, product, adjustment_qty, reason |
| `process_document_movements()` | Авто-създава от документ | Result | document |
| `sync_movements_with_document()` | Синхронизира с промени в документа | Result | document |

### InventoryService методи

| Метод | Цел | Връща | Ключови параметри |
|-------|-----|-------|------------------|
| `validate_availability()` | Проверява нива на склада | Result | location, product, required_qty |
| `validate_batch_availability()` | Проверява batch склад (FIFO) | Result | location, product, required_qty |
| `reserve_stock_qty()` | Резервира inventory | Result | location, product, quantity |
| `release_reservation()` | Освобождава резервация | Result | location, product, quantity |
| `get_stock_summary()` | Пълна информация за склада | Result | location, product |

### Result структури от данни

**Резултат от създаване на движение:**
```python
{
    'movement_id': 12345,
    'quantity': Decimal('100.000'),
    'cost_price': Decimal('12.5000'),  # 4dp точност
    'sale_price': Decimal('18.00'),    # 2dp точност
    'location_code': 'WH01',
    'product_code': 'WIDGET123',
    'batch_number': 'BATCH-001',
    'cache_updated': True,
    'profit_amount': Decimal('5.50'),   # 2dp точност
    'total_profit': Decimal('550.00')   # 2dp точност
}
```

**Резултат от проверка на наличност:**
```python
{
    'available': True,
    'current_qty': Decimal('500.000'),     # 3dp точност
    'available_qty': Decimal('450.000'),   # 3dp точност
    'reserved_qty': Decimal('50.000'),     # 3dp точност
    'can_fulfill': True,
    'shortage': Decimal('0.000'),
    'avg_cost': Decimal('10.2500'),        # 4dp точност
    'stock_value': Decimal('5125.00'),     # 2dp за дисплей
    'product_code': 'WIDGET123',
    'location_code': 'WH01'
}
```

**Резултат от batch наличност:**
```python
{
    'total_available': Decimal('450.000'),
    'can_fulfill': True,
    'batch_count': 3,
    'batch_details': [
        {
            'batch_number': 'BATCH-A',
            'remaining_qty': Decimal('200.000'),      # 3dp точност
            'cost_price': Decimal('10.0000'),         # 4dp точност
            'expiry_date': '2024-12-31',
            'is_expired': False,
            'can_use_qty': Decimal('100.000')
        }
        # ... повече партиди
    ]
}
```

---

## Обработка на грешки

### Общи кодове за грешки

| Код | Значение | Решение |
|-----|----------|---------|
| `INSUFFICIENT_STOCK` | Недостатъчен наличен склад | Проверете наличността първо |
| `INSUFFICIENT_BATCH_STOCK` | Недостатъчно в партидите | Проверете batch наличност |
| `INVALID_QUANTITY` | Количество <= 0 | Валидирайте входа |
| `FRACTIONAL_PIECES` | Не-цяло число за продукти в бройки | Закръгляване до цяло число |
| `MOVEMENT_CREATION_ERROR` | Системна грешка в движението | Проверете логовете, опитайте отново |
| `ITEM_NOT_FOUND` | Няма inventory запис | Инициализирайте склада първо |
| `DECIMAL_PRECISION_ERROR` | Грешна десетична точност | Използвайте правилните decimal utilities |

### Pattern за отговор при грешка

```python
if not result.ok:
    error_info = {
        'code': result.code,           # Код за грешка
        'message': result.msg,         # Човешки четливо съобщение
        'data': result.data,           # Допълнителен контекст
        'suggestions': [               # Възможни решения
            'Проверете наличността на склада',
            'Проверете дали продуктът съществува в локацията',
            'Проверете десетичната точност на входните данни'
        ]
    }
```

---

## Съображения за производителност

### 1. **Едновременни операции**

```python
# Всички критични операции използват select_for_update()
with transaction.atomic():
    item = InventoryItem.objects.select_for_update().get(
        location=location, product=product
    )
    # Атомни актуализации на количества
    item.current_qty = F('current_qty') - quantity
    item.save()
```

### 2. **Batch обработка**

```python
# Използвайте bulk операции за множество движения
result = MovementService.bulk_create_movements(movement_data_list)
```

### 3. **Стратегия за кеширане**

- InventoryItem актуализиран инкрементално (не пълно освежаване)
- Batch количества актуализирани атомично с F() expressions
- Историята на движенията пагинирана за големи набори данни
- Decimal калкулации кеширани където е подходящо

---

## Интеграционни точки

### **С NOMENCLATURES App:**
- DocumentService задейства създаване на движения чрез промени в статуса
- StatusManager проверява movement конфигурационни флагове
- Document lines предоставят детайли за движенията (количество, цена, batch)

### **С PRICING App:**
- Автоматично открива продажни цени за калкулации на печалбата
- Задейства актуализации на ценообразуването когато себестойностите се променят значително
- Предоставя данни за себестойности за markup калкулации

### **С PRODUCTS App:**
- Product.track_batches определя поведението на batch следенето
- Валидация на типа единица (без дробни бройки)
- Себестойностите на продуктите се актуализират от складови движения

### **С CORE App:**
- Използва стандартизирани decimal полета за консистентна точност
- Интегрира се с Service Registry за resolve-ване на услуги
- Използва десетични утилити за правилно закръгляване

---

## Най-добри практики

### 1. **Винаги използвайте Result Pattern**
```python
# ✅ Добро
result = MovementService.create_incoming_stock(...)
if result.ok:
    movement_data = result.data
else:
    handle_error(result.code, result.msg)

# ❌ Избягвайте
try:
    movement = create_movement(...)  # Базиран на exceptions
except Exception as e:
    # Несъвместимо обработване на грешки
```

### 2. **Проверявайте наличността първо**
```python
# ✅ Добро  
availability = InventoryService.validate_availability(location, product, qty)
if availability.ok and availability.data['can_fulfill']:
    movement_result = MovementService.create_outgoing_stock(...)

# ❌ Избягвайте
movement_result = MovementService.create_outgoing_stock(...)  # Може да се провали
```

### 3. **Използвайте правилната десетична точност**
```python
# ✅ Добро - използвайте стандартизираните утилити
from core.utils.decimal_utils import round_cost_price, round_currency

cost = round_cost_price(Decimal('15.256789'))    # 15.2568 за калкулации
price = round_currency(Decimal('24.9876'))       # 24.99 за дисплей

# ❌ Избягвайте - ръчно закръгляване
cost = round(Decimal('15.256789'), 4)  # Не следва правилата на системата
```

### 4. **Използвайте атомни транзакции**
```python
# ✅ Добро
with transaction.atomic():
    reserve_result = InventoryService.reserve_stock_qty(...)
    movement_result = MovementService.create_outgoing_stock(...)
    
# ❌ Избягвайте отделни операции без транзакция
```

### 5. **Използвайте Document интеграцията**
```python
# ✅ Добро - позволете на status конфигурацията да управлява движенията
document.transition_to('completed')  # Автоматично създава движения

# ❌ Избягвайте ръчно създаване на движения за документи
MovementService.create_incoming_stock(...)  # Трябва да е автоматично
```

---

## Зависимости

**INVENTORY app зависи от:**
- Django framework
- CORE app (Result pattern, интерфейси, десетична точност)
- PRODUCTS app (Product модел)
- NOMENCLATURES app (DocumentTypeStatus конфигурация)

**Други apps зависят от INVENTORY:**
- NOMENCLATURES (document-driven движения)
- PRICING (данни за себестойности)
- Sales модули (валидация на склада)

---

## История на версиите

- **v1.0** - Основно складово следене
- **v1.5** - FIFO batch следене
- **v2.0** - Result pattern рефакториране  
- **v2.1** - Интеграция с документи чрез status конфигурация
- **v2.2** - Подобрено проследяване на печалбата и анализ
- **v3.0** - Стандартизирани decimal полета, Service Registry интеграция

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Актуализирано според актуалния код с десетична точност*