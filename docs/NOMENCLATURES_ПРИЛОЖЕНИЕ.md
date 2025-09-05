# Документация на NOMENCLATURES приложението

## 🎯 Преглед

**NOMENCLATURES приложението** е **сърцето на OptimaPOS** - то предоставя унифицираната система за управление на документи, engine за status workflow и служи като **централен хъб** за всички услуги и документни операции в системата.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Основни услуги](#основни-услуги)
3. [Модели](#модели)
4. [Status-Driven Workflow](#status-driven-workflow)
5. [StatusResolver](#statusresolver)
6. [ApprovalService](#approvalservice)
7. [Жизнен цикъл на документа](#жизнен-цикъл-на-документа)
8. [Service интеграция](#service-интеграция)
9. [Шаблони за използване](#шаблони-за-използване)
10. [Конфигурация](#конфигурация)

---

## Архитектура

```
NOMENCLATURES Структура на приложението:
├── services/                        # Service слой - ГЛАВНА ЛОГИКА
│   ├── document_service.py         # 🏛️ FACADE - Главна входна точка
│   ├── _status_resolver.py         # 🎯 Динамично резолване на статуси
│   ├── approval_service.py         # ✅ Система за одобрения с Result pattern
│   ├── status_manager.py           # 🔄 Status преходи + inventory интеграция
│   ├── document_service.py         # 📋 Операции с редове
│   ├── vat_calculation_service.py  # 💰 ДДС и финансови калкулации
│   ├── validator.py                # ✅ Бизнес валидации
│   ├── creator.py                  # 🆕 Логика за създаване на документи
│   ├── query.py                    # 🔍 Query операции
│   └── numbering_service.py        # 📄 Номериране на документи
├── models/                          # Конфигурационни модели
│   ├── documents.py                # Базови document модели
│   ├── approvals.py                # Approval system модели
│   ├── statuses.py                 # Status конфигурационна система
│   └── types.py                    # Типове документи
├── mixins/                          # Преизползваеми model mixins
│   └── financial.py                # Financial calculation mixins
├── admin/                           # Admin интерфейс
│   └── workflow.py                 # Workflow конфигурация
└── forms/                           # Django forms
```

### Ключови принципи на дизайна

- **🏛️ Service Facade Pattern** - Централизирани услуги, тънки app обвивки
- **🎯 StatusResolver** - Никога не използвай hardcoded статуси
- **✅ ApprovalService** - Система за одобрения с Result pattern
- **🔄 Status-Driven Inventory** - "Статусите дирижират движенията"
- **🎯 Separation of Concerns** - Всяка услуга има единична отговорност
- **🔌 Service Registry Integration** - Интеграция чрез Service Registry

---

## Основни услуги

### 1. **DocumentService** - Главният Facade 🏛️

**Цел:** Единична входна точка за ВСИЧКИ документни операции в системата.

```python
from nomenclatures.services import DocumentService

# Инициализация
service = DocumentService(document=doc, user=user)

# Главни операции
result = service.create(**kwargs)                    # Създаване на документи
result = service.transition_to('completed')         # Промяна на статус
result = service.add_line(product, quantity=10)     # Добавяне на ред
result = service.calculate_totals()                 # Преизчисляване
permissions = service.get_permissions()            # Проверка какво може да прави потребителя
```

**Вътрешни колаборатори:**
```python
class DocumentService:
    def __init__(self):
        self._creator = DocumentCreator()           # Създаване на документи
        self._validator = DocumentValidator()       # Бизнес валидации
        self._status_manager = StatusManager()      # Status преходи
        self._line_service = DocumentLineService()  # Операции с редове
        self._vat_service = VATCalculationService() # Финансови калкулации
```

**Публичен API:**
- `create()` - Създаване на нов документ с валидация
- `transition_to(status)` - Промяна на статус на документ
- `add_line(product, quantity)` - Добавяне на ред към документ
- `remove_line(line_number)` - Премахване на ред от документ
- `calculate_totals()` - Преизчисляване на финансови общи суми
- `get_permissions()` - Проверка на потребителски разрешения
- `get_available_actions()` - Получаване на възможни status преходи

### 2. **StatusResolver** - Динамично резолване на статуси 🎯

**Цел:** **НИКОГА не използвай hardcoded имена на статуси**. Динамично резолване на статуси работещо на всички езици.

```python
from nomenclatures.services._status_resolver import StatusResolver

# Semantic status resolution (работи на всички езици)
approval_statuses = StatusResolver.get_statuses_by_semantic_type(
    document_type, 'approval'
)

# Получи editiable статуси
editable_statuses = StatusResolver.get_editable_statuses(document_type)
can_edit = document.status in editable_statuses

# Получи финални статуси  
final_statuses = StatusResolver.get_final_statuses(document_type)
is_final = document.status in final_statuses

# Получи отказни статуси
cancellation_statuses = StatusResolver.get_cancellation_statuses(document_type)
```

**Semantic типове статуси:**
- `'draft'` - Чернови статуси
- `'processing'` - Статуси в обработка
- `'approval'` - Статуси за одобрение
- `'completion'` - Статуси за завършване
- `'cancellation'` - Статуси за отказ

**Кеширане и производителност:**
- Кеширане на status lookups (1 час TTL)
- Резултатите са кеширани по тип документ
- Кешът се инвалидира автоматично при конфигурационни промени

### 3. **ApprovalService** - Система за одобрения ✅

**Цел:** Система за одобрения с Result pattern и detailed ApprovalDecision обекти.

```python
from nomenclatures.services.approval_service import ApprovalService

# Авторизирай преход на документ
result = ApprovalService.authorize_document_transition(
    document=delivery, 
    target_status='одобрена',
    user=user,
    comments='Одобрено след проверка на качеството'
)

if result.ok:
    decision = result.data  # ApprovalDecision object
    print(f"Авторизиран: {decision.authorized}")
    print(f"Статус: {decision.status}")
    print(f"Коментари: {decision.comments}")
else:
    print(f"Отказано: {result.msg}")
```

**ApprovalDecision обект:**
```python
class ApprovalDecision:
    authorized: bool          # Дали е авторизиран преходът
    status: str              # Текущ статус на документа
    comments: str            # Коментари от одобрителя
    approval_level: int      # Ниво на одобрение
    workflow_data: dict      # Данни от workflow-а
    rejection_reason: str    # Причина за отказ (ако има)
```

**Функции на ApprovalService:**
- `authorize_document_transition()` - Авторизира document преходи
- `get_approval_requirements()` - Получава изисквания за одобрение
- `check_approval_permissions()` - Проверява разрешения за одобрение
- `log_approval_action()` - Логира approval действия

### 4. **StatusManager** - Status преходи + Inventory 🔄

**Цел:** Обработва ВСИЧКИ status преходи и автоматично управлява складови движения.

```python
from nomenclatures.services import StatusManager

# Главна операция - обработва всичко автоматично
result = StatusManager.transition_document(
    document=delivery,
    to_status='completed',
    user=user,
    comments='Ready for inventory'
)
```

**Основна логика - конфигурационно-базирана:**
```python
# StatusManager чете DocumentTypeStatus конфигурация:
if new_status_config.creates_inventory_movements:
    # Автоматично създава складови движения
    from inventory.services.movement_service import MovementService
    MovementService.create_incoming_stock(...)
    
if new_status_config.reverses_inventory_movements:
    # Автоматично изтрива складови движения
    InventoryMovement.objects.filter(
        source_document_number=document.document_number
    ).delete()
```

**Workflow примери:**
```python
# Нормален workflow
StatusManager.transition_document(delivery, 'draft')      # Без движения
StatusManager.transition_document(delivery, 'completed')  # ✅ Създава движения
StatusManager.transition_document(delivery, 'cancelled')  # ❌ Изтрива движения

# Revival workflow
StatusManager.transition_document(delivery, 'completed')  # ✅ Пресъздава движения
```

### 5. **VATCalculationService** - Финансов Engine 💰

**Цел:** Обработва ВСИЧКИ ДДС и финансови калкулации в системата съобразени с българското данъчно законодателство.

```python
from nomenclatures.services.vat_calculation_service import VATCalculationService

# Document-ниво калкулации
result = VATCalculationService.calculate_document_vat(document, save=True)

# Line-ниво калкулации
result = VATCalculationService.calculate_line_vat(
    line=delivery_line,
    entered_price=Decimal('30.00'),
    save=True
)
```

**Поток за калкулация:**
1. **Price Entry Mode Detection** - С или без ДДС
2. **Unit Price Calculation** - Конвертира въведена цена в съхранена цена
3. **VAT Calculation** - Прилага правилна ДДС ставка
4. **Line Totals** - Калкулира суми за редове
5. **Document Totals** - Сумира всички редове + прилага document-ниво отстъпки

**Интеграция с десетична точност:**
```python
from core.utils.decimal_utils import round_currency, round_vat_amount

# Използва правилните decimal utilities
vat_amount = round_vat_amount(net_amount * vat_rate)
total_with_vat = round_currency(net_amount + vat_amount)
```

---

## Модели

### 1. **Approval System Models** (`models/approvals.py`)

```python
class ApprovalRule(models.Model):
    """Правила за одобрение по тип документ"""
    document_type = models.ForeignKey('DocumentType', on_delete=models.CASCADE)
    semantic_type = models.CharField(max_length=50)  # 'approval', 'processing', etc.
    min_approval_level = models.IntegerField(default=1)
    requires_comments = models.BooleanField(default=True)
    
class ApprovalDecision(models.Model):  
    """Решения за одобрение"""
    document = models.ForeignKey(BaseDocument, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.CharField(max_length=50)
    authorized = models.BooleanField()
    comments = models.TextField()
    approval_level = models.IntegerField()
    workflow_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 2. **Base Document Models** (`models/documents.py`)

```python
class BaseDocument(TimeStampedModel, UserTrackingModel):
    """Базов клас за всички документи"""
    document_type = models.ForeignKey('DocumentType', on_delete=models.PROTECT)
    document_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=50, default='draft')
    
    # Generic partner (supplier, customer, etc.)
    partner_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    partner_object_id = models.PositiveIntegerField()
    partner = GenericForeignKey('partner_content_type', 'partner_object_id')
    
    # Generic location (warehouse, store, etc.)
    location_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT) 
    location_object_id = models.PositiveIntegerField()
    location = GenericForeignKey('location_content_type', 'location_object_id')

class BaseDocumentLine(TimeStampedModel):
    """Базов клас за всички редове от документи"""
    line_number = models.PositiveIntegerField()
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    unit = models.ForeignKey('products.Unit', on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    
    # Използва стандартизирани полета от core
    from core.models.fields import QuantityField, CurrencyField
    quantity = QuantityField()  # 3dp за поддръжка на грамове
    unit_price = CurrencyField()  # 2dp за дисплей цени
```

### 3. **Status Configuration System** (`models/statuses.py`)

**Сърцето на конфигурационно-базираната система:**

```python
class DocumentStatus(models.Model):
    """Глобални дефиниции на статуси"""
    code = models.CharField(max_length=50, unique=True)  # 'draft', 'completed'
    name = models.CharField(max_length=100)              # 'Чернова', 'Завършен'
    name_en = models.CharField(max_length=100)           # 'Draft', 'Completed'
    is_active = models.BooleanField(default=True)

class DocumentTypeStatus(models.Model):
    """Конфигурация която контролира ВСИЧКО"""
    document_type = models.ForeignKey('DocumentType', on_delete=models.CASCADE)
    status = models.ForeignKey('DocumentStatus', on_delete=models.CASCADE)
    
    # Workflow конфигурация
    is_initial = models.BooleanField(default=False)      # Начален статус
    is_final = models.BooleanField(default=False)        # Финален статус
    is_cancellation = models.BooleanField(default=False) # Отказен статус
    
    # 🎯 INVENTORY ИНТЕГРАЦИЯ - Магията се случва тук!
    creates_inventory_movements = models.BooleanField(default=False)     # Създава движения при влизане
    reverses_inventory_movements = models.BooleanField(default=False)    # Изтрива движения при влизане
    allows_movement_correction = models.BooleanField(default=False)      # Позволява sync операции
    auto_correct_movements_on_edit = models.BooleanField(default=False)  # Авто-sync при редактиране
    
    # Document разрешения
    allows_editing = models.BooleanField(default=True)   # Може да се редактира документ
    allows_deletion = models.BooleanField(default=False) # Може да се изтрие документ
    
    # Semantic grouping за StatusResolver
    semantic_type = models.CharField(max_length=50, blank=True)  # 'draft', 'approval', etc.
    
    sort_order = models.PositiveIntegerField(default=0)  # Workflow ред
```

**Пример за конфигурация:**
```python
# Delivery Receipt workflow
draft_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type,
    status=draft_status,
    is_initial=True,                        # Начална точка
    semantic_type='draft',                  # За StatusResolver
    allows_editing=True,                    # Може да се модифицира
    creates_inventory_movements=False       # Все още няма inventory
)

completed_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type,
    status=completed_status,
    semantic_type='completion',             # За StatusResolver
    creates_inventory_movements=True,       # ✅ Създава inventory при завършване
    allows_editing=False                    # Read-only след завършване
)

cancelled_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type, 
    status=cancelled_status,
    is_cancellation=True,                   # Специален отказен статус
    semantic_type='cancellation',           # За StatusResolver
    reverses_inventory_movements=True,      # ❌ Изтрива inventory при отказ
    allows_editing=True                     # Може да се редактират отказани docs
)
```

---

## Status-Driven Workflow

### Основен принцип: "Статусите дирижират движенията"

**Конфигурацията контролира всичко:**

```python
# Когато документът преминава към нов статус:
if new_status_config.creates_inventory_movements:
    # ✅ Автоматично създава складови движения
    from inventory.services.movement_service import MovementService
    result = MovementService.create_incoming_stock(
        location=document.location,
        product=line.product,
        quantity=line.received_quantity,
        cost_price=line.unit_price
    )
    
if new_status_config.reverses_inventory_movements:
    # ❌ Автоматично изтрива складови движения
    InventoryMovement.objects.filter(
        source_document_number=document.document_number
    ).delete()
```

### Workflow примери

**1. Нормален Delivery Workflow:**
```
📦 DELIVERY ЖИЗНЕН ЦИКЪЛ:
чернова → завършена → [бизнес завършен]
  ↓          ↓
 🚫        ✅ създава движения
редактиране read-only
```

**2. Отказ Workflow:**
```
📦 ОТКАЗ:
завършена → отказана
    ↓          ↓  
✅ има       ❌ изтрива  
движения    движения
```

**3. Възстановяване Workflow:**
```
📦 ВЪЗСТАНОВЯВАНЕ:
отказана → завършена
    ↓          ↓
❌ няма    ✅ пресъздава
движения   движения
```

### Предимства на конфигурационно-базираната система

- ✅ **Няма hardcoded логика** - Всичко се управлява чрез конфигурация
- ✅ **Лесно персонализиране** - Променяне на поведението чрез admin интерфейса
- ✅ **Консистентно поведение** - Еднакви правила в всички типове документи
- ✅ **Audit trail** - Всички промени се проследяват чрез status преходи
- ✅ **Обратими операции** - Всяка операция може да се отмени чрез промяна на статуса

---

## StatusResolver

### Никога не използвай hardcoded статуси

StatusResolver предоставя динамично резолване на статуси работещо на всички езици:

```python
from nomenclatures.services._status_resolver import StatusResolver

# ✅ ПРАВИЛНО - Semantic status resolution
approval_statuses = StatusResolver.get_statuses_by_semantic_type(
    document_type, 'approval'
)
if document.status in approval_statuses:
    # Логика за одобрение

# ✅ ПРАВИЛНО - Editable статуси
editable_statuses = StatusResolver.get_editable_statuses(document_type)
can_edit = document.status in editable_statuses

# ❌ НЕПРАВИЛНО - Hardcoded статуси
if document.status == 'approved':  # Никога не прави това!
    pass
```

### Налични методи

```python
# Semantic grouping
StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
StatusResolver.get_statuses_by_semantic_type(doc_type, 'processing')
StatusResolver.get_statuses_by_semantic_type(doc_type, 'completion')
StatusResolver.get_statuses_by_semantic_type(doc_type, 'cancellation')

# Functional grouping  
StatusResolver.get_editable_statuses(doc_type)
StatusResolver.get_final_statuses(doc_type)
StatusResolver.get_cancellation_statuses(doc_type)
StatusResolver.get_initial_status(doc_type)

# Movement-related
StatusResolver.get_movement_creating_statuses(doc_type)
StatusResolver.get_movement_reversing_statuses(doc_type)
```

### Кеширане за производителност

StatusResolver имплементира интелигентно кеширане:

```python
# Кешира резултатите за 1 час
@cache_result(timeout=3600)
def get_statuses_by_semantic_type(document_type, semantic_type):
    # Expensive database query here
    pass

# В loops използвай кеширани резултати
approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
for document in documents:
    if document.status in approval_statuses:  # Използва кеширан резултат
        process_approval(document)
```

---

## ApprovalService

### Система за одобрения с Result Pattern

ApprovalService предоставя изчерпателна система за одобрения:

```python
from nomenclatures.services.approval_service import ApprovalService

# Авторизирай document transition
result = ApprovalService.authorize_document_transition(
    document=request,
    target_status='одобрена',
    user=manager,
    comments='Бюджетът е одобрен'
)

if result.ok:
    decision = result.data
    if decision.authorized:
        print(f"Одобрено на ниво {decision.approval_level}")
        # Продължи с transition
        StatusManager.transition_document(document, target_status, user)
    else:
        print(f"Отказано: {decision.rejection_reason}")
else:
    print(f"Грешка в approval процеса: {result.msg}")
```

### ApprovalDecision детайли

```python
class ApprovalDecision:
    """Detailed approval decision object"""
    authorized: bool = False
    status: str = ""
    comments: str = ""  
    approval_level: int = 0
    workflow_data: dict = field(default_factory=dict)
    rejection_reason: str = ""
    
    def to_dict(self):
        """Конвертира в dict за JSON serialization"""
        return {
            'authorized': self.authorized,
            'status': self.status,
            'comments': self.comments,
            'approval_level': self.approval_level,
            'workflow_data': self.workflow_data,
            'rejection_reason': self.rejection_reason
        }
```

### Approval Rules конфигурация

```python
# Конфигурирай approval rules в admin
ApprovalRule.objects.create(
    document_type=purchase_request_type,
    semantic_type='approval',          # Свързва със StatusResolver
    min_approval_level=2,              # Минимално ниво 2
    requires_comments=True,            # Задължителни коментари
    max_amount=Decimal('10000.00')     # Ограничение по сума
)
```

---

## Жизнен цикъл на документа

### Фаза 1: Създаване
```python
# DocumentService обработва първоначалната настройка
result = DocumentService.create(
    document_type='delivery_receipt',
    partner=supplier,
    location=warehouse,
    lines=[...],
    **kwargs
)
# → Документ създаден в 'чернова' статус (is_initial=True)
```

### Фаза 2: Управление на редове
```python
# DocumentService обработва line операции
service.add_line(product, quantity=10, unit_price=25)
service.remove_line(line_number=2) 
service.calculate_totals()  # VATCalculationService преизчислява
```

### Фаза 3: Status преходи
```python
# StatusManager обработва workflow + inventory интеграция
result = service.transition_to('завършена')
# → Автоматично създаване на складови движения
# → Документът става read-only (allows_editing=False)

result = service.transition_to('отказана')  
# → Автоматично изтриване на складови движения
# → Документът отново става редактируем (allows_editing=True)
```

### Фаза 4: Възстановяване (по избор)
```python  
# Възстановяване workflow - обратно към активен статус
result = service.transition_to('завършена')
# → Складовите движения са пресъздадени
# → Пълно възстановяване на документа
```

---

## Service интеграция

### Как NOMENCLATURES се интегрира с другите Apps

**PURCHASES App интеграция:**
```python
# PURCHASES използва NOMENCLATURES като facade
from nomenclatures.services import DocumentService

class PurchaseDocumentService:
    def __init__(self, user):
        self.facade = DocumentService(user=user)  # Делегира всичко!
        
    def create_document(self, doc_type, partner, location, lines):
        return self.facade.create(...)  # Използва nomenclatures facade
```

**INVENTORY App интеграция:**
```python
# NOMENCLATURES извиква INVENTORY за движения
from inventory.services.movement_service import MovementService

# В StatusManager:
if new_status_config.creates_inventory_movements:
    result = MovementService.create_incoming_stock(
        location=document.location,
        product=line.product,
        quantity=line.received_quantity,
        cost_price=line.unit_price
    )
```

**Service Registry интеграция:**
```python
# Използва Service Registry за resolve-ване на услуги
from core.interfaces.service_registry import ServiceRegistry

pricing_service = ServiceRegistry.resolve('IPricingService')
vat_rate = pricing_service.get_vat_rate(product, location)
```

---

## Шаблони за използване

### 1. **Facade Pattern използване**

```python
# ✅ Винаги използвай DocumentService като входна точка
from nomenclatures.services import DocumentService

def create_purchase_order(partner, location, lines, user):
    service = DocumentService(user=user)
    return service.create(
        document_type='purchase_order',
        partner=partner,
        location=location, 
        lines=lines
    )

# ❌ Не достъпвай вътрешните услуги директно
from nomenclatures.services.creator import DocumentCreator  # Избягвай това
```

### 2. **StatusResolver Pattern**

```python
# ✅ Използвай StatusResolver за status проверки
from nomenclatures.services._status_resolver import StatusResolver

# Проверка за редактируеми статуси
editable_statuses = StatusResolver.get_editable_statuses(document_type)
if document.status in editable_statuses:
    allow_editing = True

# Semantic status grouping
approval_statuses = StatusResolver.get_statuses_by_semantic_type(
    document_type, 'approval'
)
if document.status in approval_statuses:
    show_approval_buttons = True

# ❌ НЕПРАВИЛНО - Hardcoded статуси
if document.status == 'approved':  # Никога не прави това
    pass
```

### 3. **ApprovalService Pattern**

```python
# ✅ Използвай ApprovalService за одобрения
result = ApprovalService.authorize_document_transition(
    document=request,
    target_status='одобрена',
    user=user,
    comments='Одобрено след проверка'
)

if result.ok and result.data.authorized:
    # Продължи с transition
    transition_result = StatusManager.transition_document(...)
else:
    # Обработи отказ
    print(f"Отказано: {result.data.rejection_reason}")
```

### 4. **Result Pattern използване**

```python
# ✅ Винаги обработвай Results правилно
result = service.create_document(...)

if result.ok:
    document = result.data['document'] 
    print(f"Създаден: {document.document_number}")
else:
    logger.error(f"Неуспешно: {result.msg}")
    return HttpResponse(result.msg, status=400)
```

---

## Конфигурация

### Admin Interface конфигурация

**DocumentTypeStatus конфигурация:**

1. **Workflow Setup:**
   - `is_initial` - Маркирай начален статус
   - `is_final` - Маркирай финален статус  
   - `is_cancellation` - Маркирай отказен статус
   - `semantic_type` - За StatusResolver (draft, approval, completion, cancellation)
   - `sort_order` - Дефинирай workflow последователност

2. **Inventory интеграция:**
   - `creates_inventory_movements` - Авто-създаване при влизане в статус
   - `reverses_inventory_movements` - Авто-изтриване при влизане в статус
   - `allows_movement_correction` - Позволи sync операции
   - `auto_correct_movements_on_edit` - Авто-sync при промени в документа

3. **Разрешения:**
   - `allows_editing` - Контролирай редактирането на документ
   - `allows_deletion` - Контролирай изтриването на документ

### Примери за конфигурации

**Delivery Receipt Workflow:**
```python
statuses = [
    {
        'status': 'чернова',
        'is_initial': True,
        'semantic_type': 'draft',
        'allows_editing': True,
        'creates_inventory_movements': False
    },
    {
        'status': 'завършена', 
        'semantic_type': 'completion',
        'creates_inventory_movements': True,  # ✅ Ключова конфигурация!
        'allows_editing': False
    },
    {
        'status': 'отказана',
        'is_cancellation': True,
        'semantic_type': 'cancellation',
        'reverses_inventory_movements': True,  # ❌ Ключова конфигурация!
        'allows_editing': True
    }
]
```

**ApprovalRule конфигурация:**
```python
rules = [
    {
        'document_type': 'purchase_request',
        'semantic_type': 'approval',
        'min_approval_level': 1,
        'requires_comments': True,
        'max_amount': Decimal('5000.00')
    },
    {
        'document_type': 'purchase_request', 
        'semantic_type': 'approval',
        'min_approval_level': 2,
        'requires_comments': True,
        'max_amount': Decimal('50000.00')
    }
]
```

---

## Най-добри практики

### 1. **Винаги използвай Facade**
```python
# ✅ Добро
from nomenclatures.services import DocumentService
service = DocumentService(document, user)
result = service.transition_to('завършена')

# ❌ Избягвай  
from nomenclatures.services.status_manager import StatusManager
StatusManager.transition_document(...)  # Прескачай facade
```

### 2. **Никога не използвай hardcoded статуси**
```python
# ✅ Добро - Използвай StatusResolver
from nomenclatures.services._status_resolver import StatusResolver

editable_statuses = StatusResolver.get_editable_statuses(document_type)
if document.status in editable_statuses:
    allow_editing = True

# ❌ Избягвай - Hardcoded логика
if document.status == 'завършена':  # Hardcoded логика
    create_inventory_movements()
```

### 3. **Използвай ApprovalService**
```python
# ✅ Добро - Система за одобрения
result = ApprovalService.authorize_document_transition(...)
if result.ok and result.data.authorized:
    proceed_with_transition()

# ❌ Избягвай - Ръчни approval проверки
if user.has_permission('approve_documents'):  # Ръчна логика
    approve_document()
```

### 4. **Използвай Result Pattern**  
```python
# ✅ Добро
result = service.create_document(...)
if result.ok:
    return result.data
else:
    handle_error(result.msg)

# ❌ Избягвай
try:
    document = service.create_document(...)  # Може да хвърли exceptions
except Exception as e:
    handle_error(str(e))
```

### 5. **Конфигурация вместо код**
```python
# ✅ Добро - Конфигурирай в DocumentTypeStatus
creates_inventory_movements = True  # В admin интерфейса

# ❌ Избягвай - Hardcode в бизнес логиката
if document.document_type.code == 'delivery_receipt':  # Hardcoded логика
    if document.status == 'completed':
        create_inventory_movements(document)
```

---

## Зависимости

**NOMENCLATURES зависи от:**
- `core` - Базова инфраструктура, Result pattern, Service Registry
- `products` - Product модели за document lines
- `inventory` - MovementService за inventory интеграция  
- `pricing` - PricingService за ДДС калкулации
- `accounts` - User модел за tracking

**Apps които зависят от NOMENCLATURES:**
- `purchases` - Използва DocumentService facade
- `sales` - Използва DocumentService facade (ако е имплементиран)
- `inventory` - Получава повиквания от StatusManager

---

## История на версиите

- **v1.0** - Базови document модели
- **v1.5** - Service layer въведение
- **v2.0** - Facade pattern имплементация
- **v2.1** - Status-driven workflow система  
- **v2.2** - Inventory интеграция
- **v2.3** - Конфигурационно-базирана архитектура
- **v3.0** - StatusResolver, ApprovalService, Service Registry интеграция

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Статус: ✅ Production Ready - Актуализирано според актуалния код*