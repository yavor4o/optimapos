# PURCHASES Приложение Документация

## 🎯 Общ преглед

**PURCHASES приложението** имплементира работния поток за снабдяване в OptimaPOS. То предоставя **тънка обвивка** около NOMENCLATURES facade, обработвайки специфичната за покупки бизнес логика, докато делегира всички документни операции към унифицираната система.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Thin Wrapper Pattern](#thin-wrapper-pattern)
3. [Типове документи](#типове-документи)
4. [Работен поток за покупки](#работен-поток-за-покупки)
5. [Модели](#модели)
6. [Услуги](#услуги)
7. [Интеграционни точки](#интеграционни-точки)
8. [Шаблони за използване](#шаблони-за-използване)

---

## Архитектура

```
PURCHASES App Структура:
├── services/                    # Тънки обвиващи услуги
│   └── purchase_service.py     # 🏗️ Главна услуга - делегира към NOMENCLATURES
├── models/                      # Специфични за покупки модели
│   ├── requests.py             # Purchase Request + Lines
│   ├── orders.py               # Purchase Order + Lines
│   └── deliveries.py           # Delivery Receipt + Lines  
├── admin/                       # Admin интерфейс за документи за покупки
└── views.py                     # Базови изгледи (ако има такива)
```

### Ключови дизайн принципи

- **🏗️ Thin Wrapper Pattern** - Минимален код, максимално делегиране
- **🎯 Domain-Специфична логика** - Само конверсии и бизнес правила специфични за покупки
- **🏛️ Facade Делегиране** - ВСИЧКИ операции преминават през NOMENCLATURES DocumentService
- **♻️ Преизползване на код** - 700+ реда намалени до ~150 реда (75% намаление)

---

## Thin Wrapper Pattern

### Основна концепция: 100% Делегиране

```python
class PurchaseDocumentService:
    """
    Тънка обвивка която делегира ВСИЧКО към nomenclatures.DocumentService
    Обработва само специфичната за покупки domain логика
    """
    
    def __init__(self, document=None, user: User = None):
        # ПРИНЦИП: Всичко през facade!
        self.facade = DocumentService(document, user)
        self.document = document
        self.user = user
```

### Какво ПРАВИ това приложение:
- ✅ **Конверсии специфични за покупки** (Request → Order → Delivery)
- ✅ **Domain бизнес правила** (валидация на доставчици, работни потоци за покупки)
- ✅ **Purchase модели** (PurchaseRequest, PurchaseOrder, DeliveryReceipt)
- ✅ **Мапиране на полета** (generic вход → специфични полета)

### Какво НЕ ПРАВИ това приложение:
- ❌ **Валидация на документи** → Делегирано към NOMENCLATURES
- ❌ **Преходи на статуси** → Делегирано към NOMENCLATURES  
- ❌ **Управление на редове** → Делегирано към NOMENCLATURES
- ❌ **Финансови калкулации** → Делегирано към NOMENCLATURES
- ❌ **Складови движения** → Делегирано към NOMENCLATURES → INVENTORY

---

## Типове документи

### 1. **Purchase Request** 📋
**Цел:** Първоначална заявка за продукти от доставчици.

```python
# Модел: PurchaseRequest + PurchaseRequestLine
class PurchaseRequest(BaseDocument, FinancialMixin):
    request_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)
    
class PurchaseRequestLine(BaseDocumentLine, FinancialLineMixin):
    requested_quantity = models.DecimalField(...)  # ← Специфично поле за количество
    estimated_price = models.DecimalField(...)     # Прогнозна единична цена
```

**Използване:**
```python
# Създаване на заявка за покупка
result = service.create_document(
    'request',
    supplier=supplier,
    location=location,
    lines=[
        {
            'product': product,
            'quantity': Decimal('10'),  # → Мапва се към requested_quantity
            'unit_price': Decimal('25') # → Мапва се към estimated_price
        }
    ]
)
```

### 2. **Purchase Order** 📦
**Цел:** Официална поръчка изпратена към доставчици.

```python  
# Модел: PurchaseOrder + PurchaseOrderLine
class PurchaseOrder(BaseDocument, FinancialMixin, PaymentMixin):
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True)
    supplier_order_reference = models.CharField(...)
    
class PurchaseOrderLine(BaseDocumentLine, FinancialLineMixin):
    ordered_quantity = models.DecimalField(...)   # ← Специфично поле за количество  
    confirmed_price = models.DecimalField(...)    # Окончателна договорена цена
    source_request_line = models.ForeignKey(...)  # Връзка обратно към заявката
```

**Използване:**
```python
# Конвертиране на заявка към поръчка
result = service.convert_to_order(
    request_document=purchase_request,
    conversion_data={
        'expected_delivery_date': date(2025, 9, 15),
        'supplier_order_reference': 'SUP-REF-12345'
    }
)
```

### 3. **Delivery Receipt** 🚛
**Цел:** Запис на действително получени стоки.

```python
# Модел: DeliveryReceipt + DeliveryLine  
class DeliveryReceipt(BaseDocument, FinancialMixin, PaymentMixin):
    delivery_date = models.DateField(default=timezone.now)
    received_by = models.ForeignKey(User, ...)
    quality_status = models.CharField(...)         # Контрол на качеството
    
class DeliveryLine(BaseDocumentLine, FinancialLineMixin):
    received_quantity = models.DecimalField(...)   # ← Специфично поле за количество
    quality_approved = models.BooleanField(...)    # Резултат от проверката на качеството
    batch_number = models.CharField(...)           # Проследяване на партиди
    source_order_line = models.ForeignKey(...)     # Връзка обратно към поръчката
```

**Използване:**
```python
# Конвертиране на поръчка към доставка  
result = service.convert_to_delivery(
    order_document=purchase_order,
    delivery_data={
        'delivery_date': date.today(),
        'received_quantities': {1: Decimal('9.5'), 2: Decimal('15')}
    }
)
```

---

## Работен поток за покупки

### Пълен цикъл на снабдяване

```
📋 REQUEST → 📦 ORDER → 🚛 DELIVERY
    ↓           ↓         ↓
  чернова    чернова    чернова → завършен (📦 склад)
    ↓           ↓         ↓                     ↓
  подадена  потвърдена получен            отказан (🗑️ reverse)
    ↓           ↓         ↓                     ↓
 одобрена    изпратена завършен       обратно към завършен (♻️ recreate)
```

### Интеграция на статуси със склада

**Ключова точка:** Всеки тип документ може да има различно поведение в склада:

- **Purchase Request:** Няма въздействие върху склада (само планиране)
- **Purchase Order:** Няма въздействие върху склада (само ангажимент)  
- **Delivery Receipt:** Пълна интеграция със склада
  - `чернова` → Няма движения
  - `завършен` → ✅ Създаване на складови движения  
  - `отказан` → ❌ Изтриване на складови движения

### Логика за конвертиране

**1. Конвертиране Request → Order:**
```python
def convert_to_order(self, request_document, conversion_data):
    # Извличане на редове от заявката
    lines = []
    for req_line in request_document.lines.all():
        lines.append({
            'product': req_line.product,
            'quantity': req_line.requested_quantity,    # Source поле
            'unit_price': conversion_data.get('confirmed_price', req_line.estimated_price),
            'source_request_line_id': req_line.id       # Поддържай връзката
        })
    
    # Създаване на поръчка чрез facade
    return self.facade.create(
        document_type='purchase_order',
        partner=request_document.partner, 
        location=request_document.location,
        lines=lines,
        **conversion_data
    )
```

**2. Конвертиране Order → Delivery:**  
```python
def convert_to_delivery(self, order_document, delivery_data):
    # Извличане на редове от поръчката с действителни получени количества
    lines = []
    received_quantities = delivery_data.get('received_quantities', {})
    
    for order_line in order_document.lines.all():
        received_qty = received_quantities.get(
            str(order_line.line_number), 
            order_line.ordered_quantity  # По подразбиране към поръчано количество
        )
        lines.append({
            'product': order_line.product,
            'quantity': received_qty,                   # Действително получено
            'unit_price': order_line.unit_price,
            'entered_price': order_line.unit_price,     # Активира ДДС калкулации
            'source_order_line_id': order_line.id       # Поддържай връзката
        })
    
    # Създаване на доставка чрез facade
    return self.facade.create(
        document_type='delivery_receipt', 
        partner=order_document.partner,
        location=order_document.location,
        lines=lines,
        **delivery_data
    )
```

---

## Модели

### Йерархия на моделите

**Базови класове:**
- Всички модели за покупки наследяват от `BaseDocument` и `BaseDocumentLine` (от NOMENCLATURES)
- Финансовите модели използват `FinancialMixin` и `FinancialLineMixin` (от NOMENCLATURES)
- Проследяването на плащания използва `PaymentMixin` (от NOMENCLATURES)

### Ключови функционалности на моделите

**1. Generic отношения:**
```python
# Всички документи използват generic отношения за гъвкавост
class PurchaseRequest(BaseDocument):
    # partner_content_type, partner_object_id → GenericForeignKey към доставчици
    # location_content_type, location_object_id → GenericForeignKey към складове
```

**2. Свързване на документи:**
```python
# Поддържай пълна проследимост през работния поток
class PurchaseOrder(BaseDocument):
    source_request = models.ForeignKey('PurchaseRequest', ...)
    
class DeliveryReceipt(BaseDocument):  
    source_order = models.ForeignKey('PurchaseOrder', ...)
    
class DeliveryLine(BaseDocumentLine):
    source_order_line = models.ForeignKey('PurchaseOrderLine', ...)
```

**3. Специализация на полетата за количество:**
```python
# Всеки тип документ има специализирани полета за количество
PurchaseRequestLine.requested_quantity  # Какво искаме
PurchaseOrderLine.ordered_quantity      # Какво поръчахме  
DeliveryLine.received_quantity          # Какво получихме

# Но API е унифицирано:
lines = [{'product': p, 'quantity': 10}]  # Същия входен формат
# → Авто-мапва се към правилното поле от DocumentLineService
```

**4. Разширени мениджъри:**
```python
class DeliveryReceiptManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type', 'location_content_type', 'source_order'
        )
    
    def pending_quality_control(self):
        return self.filter(quality_status='pending')
        
    def ready_for_inventory(self):
        return self.filter(quality_status='approved')
```

---

## Услуги

### PurchaseDocumentService - Главната услуга

**Архитектура: Thin Wrapper + Facade Pattern**

```python
class PurchaseDocumentService:
    def __init__(self, document=None, user: User = None):
        self.facade = DocumentService(document, user)  # 🏛️ Делегирай всичко
        
    def create_document(self, doc_type, partner, location, lines, **kwargs):
        """Създаване на всеки тип документ за покупка"""
        # 1. Валидация специфична за покупки
        validation_result = self._validate_purchase_creation(partner, location, lines)
        if not validation_result.ok:
            return validation_result
            
        # 2. Мапиране на типа документ към модел
        model_map = {
            'request': 'purchases.PurchaseRequest',
            'order': 'purchases.PurchaseOrder', 
            'delivery': 'purchases.DeliveryReceipt'
        }
        
        # 3. Делегиране към facade
        return self.facade.create(
            document_type=model_map[doc_type],
            partner=partner,
            location=location, 
            lines=lines,
            **kwargs
        )
```

### Услуги за конвертиране

**Request → Order:**
```python
def convert_to_order(self, request_document, conversion_data=None):
    """Конвертиране на заявка за покупка към поръчка за покупка"""
    
    # 1. Валидиране че заявката е в правилен статус
    if request_document.status not in ['одобрена', 'потвърдена']:
        return Result.error('INVALID_STATUS', 
            f'Не може да се конвертира заявка в статус {request_document.status}')
    
    # 2. Извличане и трансформиране на редове
    lines = self._extract_request_lines(request_document, conversion_data)
    
    # 3. Създаване на поръчка чрез facade  
    return self.create_document(
        'order',
        partner=request_document.partner,
        location=request_document.location,
        lines=lines,
        source_request=request_document,
        **conversion_data
    )
```

**Order → Delivery:**
```python
def convert_to_delivery(self, order_document, delivery_data=None):
    """Конвертиране на поръчка за покупка към доставна разписка"""
    
    # 1. Валидиране на статуса на поръчката
    if order_document.status not in ['потвърдена', 'изпратена']:
        return Result.error('INVALID_STATUS',
            f'Не може да се конвертира поръчка в статус {order_document.status}')
            
    # 2. Обработка на частични доставки и корекции в количествата
    lines = self._extract_order_lines(order_document, delivery_data)
    
    # 3. Създаване на доставка чрез facade
    return self.create_document(
        'delivery',
        partner=order_document.partner,
        location=order_document.location,
        lines=lines,
        source_order=order_document,
        **delivery_data
    )
```

---

## Интеграционни точки

### С NOMENCLATURES приложението

**100% Facade делегиране:**
```python
# ВСИЧКО преминава през DocumentService facade
class PurchaseDocumentService:
    def create_document(self, ...):
        return self.facade.create(...)           # Създаване на документи
        
    def add_line(self, ...):  
        return self.facade.add_line(...)         # Управление на редове
        
    def transition_status(self, ...):
        return self.facade.transition_to(...)    # Промени на статуси
        
    def calculate_totals(self):
        return self.facade.calculate_totals()    # Финансови калкулации
```

### С INVENTORY приложението  

**Автоматично чрез преходи на статуси:**
```python  
# БЕЗ директна интеграция! Преминава през NOMENCLATURES → INVENTORY

# Когато доставката премине към 'завършен':
# 1. PURCHASES извиква NOMENCLATURES.transition_to('завършен')
# 2. NOMENCLATURES.StatusManager проверява DocumentTypeStatus
# 3. StatusManager извиква INVENTORY.MovementService  
# 4. Складовите движения се създават автоматично

# Резултат: Документите за покупки получават интеграция със склада с НУЛА код
```

### С PARTNERS приложението

**Валидация на доставчици:**
```python
def _validate_purchase_creation(self, partner, location, lines):
    """Валидации специфични за покупки"""
    
    # Валидирай че партньорът е доставчик
    if not hasattr(partner, 'supplier_profile'):
        return Result.error('INVALID_PARTNER', 'Партньорът трябва да бъде доставчик')
        
    # Проверка на статуса на доставчика
    if not partner.is_active:
        return Result.error('INACTIVE_SUPPLIER', 'Доставчикът не е активен')
        
    # Бизнес правила специфични за покупки
    # ... допълнителни валидации
```

---

## Шаблони за използване

### 1. **Основно създаване на документи**

```python
from purchases.services import PurchaseDocumentService

# Инициализиране на услугата
service = PurchaseDocumentService(user=current_user)

# Създаване на заявка за покупка  
result = service.create_document(
    'request',
    partner=supplier,
    location=warehouse,
    lines=[
        {
            'product': Product.objects.get(code='PROD001'),
            'quantity': Decimal('50'),        # → requested_quantity
            'unit_price': Decimal('12.50')    # → estimated_price
        }
    ],
    comments='Месечно попълване на склада',
    priority='висок',
    expected_delivery_date=date(2025, 9, 15)
)

if result.ok:
    request = result.data['document']
    print(f"Заявката е създадена: {request.document_number}")
```

### 2. **Работен поток за конвертиране на документи**

```python
# Пълен работен поток за снабдяване
service = PurchaseDocumentService(user=current_user)

# Стъпка 1: Създаване на заявка
request_result = service.create_document('request', supplier, warehouse, lines)
request = request_result.data['document']

# Стъпка 2: Одобрение на заявката (преход на статус)
approval_result = service.facade.transition_to('одобрена')

# Стъпка 3: Конвертиране към поръчка
order_result = service.convert_to_order(
    request, 
    conversion_data={
        'supplier_order_reference': 'SUP-2025-001',
        'expected_delivery_date': date(2025, 9, 20)
    }
)
order = order_result.data['document']

# Стъпка 4: Потвърждаване на поръчката (преход на статус)
confirm_result = service.facade.transition_to('потвърдена')

# Стъпка 5: Конвертиране към доставка
delivery_result = service.convert_to_delivery(
    order,
    delivery_data={
        'delivery_date': date.today(),
        'received_quantities': {
            1: Decimal('48'),  # Ред 1: получени 48 вместо 50
            2: Decimal('25')   # Ред 2: получени както е поръчано
        }
    }
)
delivery = delivery_result.data['document']

# Стъпка 6: Завършване на доставката (активира складови движения!)
complete_result = service.facade.transition_to('завършен')
# → Автоматично се създават складови движения
```

### 3. **Операции управлявани от статуси**

```python
# Силата на работния поток управляван от статуси
delivery_service = PurchaseDocumentService(document=delivery, user=user)

# Завършване на доставката → Създаване на складови движения
result = delivery_service.facade.transition_to('завършен')
# ✅ Складовите движения се създават автоматично

# Отказ на доставката → Изтриване на складови движения  
result = delivery_service.facade.transition_to('отказан')
# ❌ Складовите движения се изтриват автоматично

# Възстановяване → Пресъздаване на складови движения
result = delivery_service.facade.transition_to('завършен')
# ✅ Складовите движения се пресъздават автоматично
```

### 4. **Работен поток за контрол на качеството**

```python
# Доставка с контрол на качеството
delivery = DeliveryReceipt.objects.get(document_number='DEL-001')

# Проверка на индивидуални редове
for line in delivery.lines.all():
    if line.quality_approved is None:
        # Извършване на проверка на качеството
        line.quality_approved = True  # или False
        line.quality_notes = "Прошла всички проверки"
        line.save()

# Актуализиране на общия статус на качеството на доставката
if delivery.lines.filter(quality_approved=False).exists():
    delivery.quality_status = 'частично'
elif delivery.lines.filter(quality_approved__isnull=True).exists():
    delivery.quality_status = 'в процес'
else:
    delivery.quality_status = 'одобрено'
    
delivery.save()

# Завършване само след одобрение на качеството
if delivery.quality_status == 'одобрено':
    service = PurchaseDocumentService(document=delivery, user=user)
    result = service.facade.transition_to('завършен')
    # → Складови движения за артикули одобрени по качество
```

---

## Конфигурация

### Настройка на типовете документи

**В NOMENCLATURES админ, конфигурирай DocumentTypeStatus за типовете документи за покупки:**

```python
# Статуси на заявка за покупка
request_statuses = [
    {'code': 'чернова', 'is_initial': True, 'allows_editing': True},
    {'code': 'подадена', 'allows_editing': False}, 
    {'code': 'одобрена', 'allows_editing': False},
    {'code': 'отказана', 'is_cancellation': True}
]

# Статуси на поръчка за покупка  
order_statuses = [
    {'code': 'чернова', 'is_initial': True, 'allows_editing': True},
    {'code': 'потвърдена', 'allows_editing': False},
    {'code': 'изпратена', 'allows_editing': False},
    {'code': 'отказана', 'is_cancellation': True}
]

# Статуси на доставна разписка (с интеграция със склада!)
delivery_statuses = [
    {
        'code': 'чернова', 
        'is_initial': True, 
        'allows_editing': True,
        'creates_inventory_movements': False
    },
    {
        'code': 'завършен',
        'creates_inventory_movements': True,    # 🎯 Ключова настройка!
        'allows_editing': False
    },
    {
        'code': 'отказан',
        'is_cancellation': True,
        'reverses_inventory_movements': True,   # 🎯 Ключова настройка!
        'allows_editing': True
    }
]
```

### Админ интерфейс

**Документите за покупки получават пълен админ интерфейс с:**
- Формуляри за създаване/редактиране на документи
- Inline редактиране на редове
- Действия за преходи на статуси  
- Интерфейси за контрол на качеството
- Действия за конвертиране (Request → Order → Delivery)

---

## Съображения за производителност

### Оптимизация на заявките

**Разширени мениджъри:**
```python
# Автоматично select_related в мениджърите намалява DB заявките
class DeliveryReceiptManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type',
            'location_content_type', 
            'source_order',
            'received_by'
        )
```

**Prefetching на редове:**
```python
# Когато работиш с документи, винаги prefetch редовете
deliveries = DeliveryReceipt.objects.prefetch_related(
    'lines__product',
    'lines__source_order_line'
)
```

### Намаляване на кода

**Преди рефакториране:** 700+ реда в услугите за покупки  
**След рефакториране:** ~150 реда (75% намаление)

**Постигнато чрез:**
- ✅ Facade pattern делегиране
- ✅ Елиминиране на дублирана валидационна логика  
- ✅ Споделени услуги за финансови калкулации
- ✅ Унифицирана система за управление на статуси

---

## Най-добри практики

### 1. **Винаги използвай Facade**

```python
# ✅ Добре - Използвай PurchaseDocumentService facade
service = PurchaseDocumentService(user=user)
result = service.create_document('delivery', supplier, location, lines)

# ❌ Избягвай - Директно създаване на модели
delivery = DeliveryReceipt.objects.create(...)  # Прескача валидации, номериране, и т.н.
```

### 2. **Обработвай конверсиите правилно**

```python  
# ✅ Добре - Пълна конверсия с обработка на грешки
conversion_result = service.convert_to_order(request, conversion_data)
if conversion_result.ok:
    order = conversion_result.data['document']
    # Маркирай заявката като конвертирана
    request.status = 'конвертирана'
    request.save()
else:
    logger.error(f"Конверсията не успя: {conversion_result.msg}")

# ❌ Избягвай - Ръчно създаване на документи без подходящо свързване
order = PurchaseOrder.objects.create(...)  # Няма връзка към изходната заявка
```

### 3. **Използвай преходи на статуси**

```python
# ✅ Добре - Използвай facade за промени на статуси  
result = service.facade.transition_to('завършен')
# Обработва валидация, склад, логиране автоматично

# ❌ Избягвай - Директни актуализации на полетата за статус
delivery.status = 'завършен'  # Без валидация, без интеграция със склада
delivery.save()
```

### 4. **Използвай generic входен формат**

```python
# ✅ Добре - Консистентен входен формат за всички типове документи
lines_format = [
    {
        'product': product,
        'quantity': Decimal('10'),     # Винаги използвай 'quantity'
        'unit_price': Decimal('25')    # Винаги използвай 'unit_price'  
    }
]

# Работи за всички типове документи:
service.create_document('request', ...)    # → requested_quantity
service.create_document('order', ...)      # → ordered_quantity
service.create_document('delivery', ...)   # → received_quantity
```

---

## Отстраняване на неизправности

### Чести проблеми

**1. Складовите движения не се създават:**
```python
# Проверка на конфигурацията DocumentTypeStatus
status_config = DocumentTypeStatus.objects.get(
    document_type__name='Доставна разписка',
    status__code='завършен'
)
print(f"Създава движения: {status_config.creates_inventory_movements}")
# Трябва да бъде True за автоматична интеграция със склада
```

**2. Неуспешни конверсии:**
```python
# Проверка на статуса на изходния документ
if request.status not in ['одобрена', 'потвърдена']:
    # Заявката трябва да бъде одобрена преди конвертиране към поръчка
    
if order.status not in ['потвърдена', 'изпратена']:
    # Поръчката трябва да бъде потвърдена преди конвертиране към доставка
```

**3. Проблеми с контрола на качеството:**
```python
# Проверка на статуса на качеството на ниво ред
for line in delivery.lines.all():
    if line.quality_approved is None:
        print(f"Ред {line.line_number} чака проверка на качеството")
```

---

## Зависимости

**PURCHASES зависи от:**
- `core` - Базова инфраструктура, Result pattern
- `nomenclatures` - DocumentService facade (главна зависимост!)
- `products` - Модели на продукти за редове
- `partners` - Модели на доставчици
- `inventory` - Модели на локации

**Никое друго приложение не зависи от PURCHASES:**
- PURCHASES е листово възел в графа на зависимостите
- Цялата интеграция се случва чрез NOMENCLATURES facade

---

## История на версиите

- **v1.0** - Основни модели и услуги за покупки (700+ реда)
- **v1.5** - Интеграция с услугите на nomenclatures  
- **v2.0** - Facade pattern имплементация, thin wrapper рефакториране
- **v2.1** - Работни потоци за конвертиране на документи
- **v2.2** - Функционалности за контрол на качеството
- **v2.3** - Пълна интеграция със склада чрез преходи на статуси (150 реда, 75% намаление)

---

*Последно актуализиране: 2025-08-29*  
*Версия: 2.3*  
*Статус: ✅ Готово за производство - Напълно интегрирано с NOMENCLATURES Facade*