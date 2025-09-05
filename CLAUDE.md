# CLAUDE.md

Този файл предоставя насоки на Claude Code (claude.ai/code) при работа с кода в тази библиотека.

## Команди за разработка

### Frontend разработка
```bash
# Компилиране на CSS и JavaScript
npm run build

# Наблюдение на CSS промени по време на разработка
npm run build:css:watch

# Production build (минифициран)
npm run build:prod

# Lint JavaScript/TypeScript
npm run lint

# ВАЖНО: ВИНАГИ rebuild CSS след промени в templates!
npm run build:css
```

### Django разработка
```bash
# Стартиране на development сървър
python manage.py runserver

# Стартиране на база данни миграции
python manage.py migrate

# Създаване на нова миграция
python manage.py makemigrations

# Django shell
python manage.py shell

# Стартиране на тестове (когато е налично)
python manage.py test
```

## Архитектурен преглед

### Основна философия
OptimaPOS е построен на **унифицирана service facade архитектура** със строго разделение на задълженията:

- **Nomenclatures модул**: Централен хъб съдържащ всички споделени услуги, утилити и конфигурация
- **App модули** (purchases, inventory, и др.): Тънки обвивки които делегират към nomenclatures услуги
- **Без дублиране**: Цялата бизнес логика, валидация и управление на статуси е централизирана
- **Service Registry Pattern**: Централизирано управление на service dependencies чрез интерфейси
- **Result Pattern**: Всички service методи връщат Result обекти вместо да хвърлят изключения

### Ключови архитектурни модели

#### 1. Service Facade Pattern
Всички операции преминават през централизирани услуги в `nomenclatures/services/`:
- `DocumentService`: Унифициран facade за всички документни операции
- `VATCalculationService`: Централизирани ДДС/данъчни изчисления
- `StatusResolver`: Динамично резолване на статуси (без hardcoded статуси)
- `ApprovalService`: Система за одобрения с Result pattern
- `MovementService`: Складови движения с прецизни калкулации

#### 2. Result Pattern
Всички service методи връщат `Result` обекти вместо да хвърлят изключения:
```python
from core.utils.result import Result

result = DocumentService.create_document(data)
if result.ok:
    document = result.data
else:
    error_message = result.msg
```

#### 3. Service Registry Pattern
Централизирано управление на service dependencies чрез интерфейси:
```python
from core.interfaces.service_registry import ServiceRegistry

# Resolve services по интерфейс име
pricing_service = ServiceRegistry.resolve('IPricingService')
product_service = ServiceRegistry.resolve('IProductService')
```

#### 4. Dynamic Configuration System
Системата избягва hardcoded стойности чрез configuration-driven подход:
- **Документни статуси**: Конфигурирани по тип документ, поддържа всички езици
- **ДДС ставки**: Конфигурируеми по местоположение и продукт
- **Десетична точност**: Конфигурируема по контекст (валута vs себестойност vs количество)

### Критични услуги

#### DocumentService (`nomenclatures/services/document_service.py`)
Централен facade за всички документни операции:
```python
from nomenclatures.services import DocumentService

service = DocumentService(document=doc, user=user)
result = service.create()  # Авто-номериране, валидация, статус setup
result = service.add_line(product, quantity, price)  # Управление на редове
result = service.transition_to('одобрена')  # Преходи на статуси
```

#### StatusResolver (`nomenclatures/services/_status_resolver.py`)
**Никога не използвай hardcoded имена на статуси**. Винаги използвай StatusResolver:
```python
from nomenclatures.services._status_resolver import StatusResolver

# Вземи статуси динамично
editable_statuses = StatusResolver.get_editable_statuses(document_type)
can_edit = document.status in editable_statuses

# Semantic status resolution (работи на всички езици)
approval_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'approval')
```

#### ApprovalService (`nomenclatures/services/approval_service.py`)
Система за одобрения с Result pattern:
```python
from nomenclatures.services.approval_service import ApprovalService

# Авторизирай преход на документ
result = ApprovalService.authorize_document_transition(
    document, 'одобрена', user, comments='Одобрено след проверка'
)

if result.ok:
    decision = result.data  # ApprovalDecision object
    print(f"Авторизиран: {decision.authorized}")
```

#### MovementService (`inventory/services/movement_service.py`)
Складови движения с прецизни калкулации:
```python
from inventory.services.movement_service import MovementService

# Създай входящ склад
result = MovementService.create_incoming_stock(
    location=warehouse,
    product=product,
    quantity=Decimal('100.000'),
    cost_price=Decimal('15.5000')
)
```

#### VATCalculationService (`nomenclatures/services/vat_calculation_service.py`)
ДДС изчисления съобразени с българското данъчно законодателство:
```python
from nomenclatures.services.vat_calculation_service import VATCalculationService

# Изчисли ДДС на ред
result = VATCalculationService.calculate_line_vat(line, entered_price, save=True)

# Изчисли общо за документа
result = VATCalculationService.calculate_document_vat(document, save=True)
```

### Система за десетична точност

#### Основни утилити (`core/utils/decimal_utils.py`)
Системата има софистицирана система за десетична точност съобразена с българското данъчно законодателство:

- **Валутни суми**: 2 десетични места (`round_currency()`)
- **Себестойности**: 4 десетични места (`round_cost_price()`) за точни калкулации
- **ДДС суми**: 2 десетични места (`round_vat_amount()`)
- **Данъчна основа**: 2 десетични места (`round_tax_base()`)

**Винаги използвай подходящата функция за закръгляване:**
```python
from core.utils.decimal_utils import round_currency, round_cost_price, round_vat_amount

# За дисплей/съхранение цени
display_price = round_currency(calculation_result)

# За вътрешни себестойностни калкулации
batch_cost = round_cost_price(batch.cost_price)

# За ДДС суми
vat_amount = round_vat_amount(net_amount * vat_rate)
```

#### Стандартизирани полета (`core/models/fields.py`)
Използвай стандартизирани decimal полета които прилагат консистентна точност:
```python
from core.models.fields import CurrencyField, CostPriceField, QuantityField

class MyModel(models.Model):
    price = CurrencyField()  # 2dp, правилно закръгляване
    cost = CostPriceField()  # 4dp, калкулационна точност
    quantity = QuantityField()  # 3dp, поддържа грамове/ml
```

### Модулна структура

#### Nomenclatures (`nomenclatures/`)
**Централен хъб** - съдържа цялата споделена логика:
- `services/`: Всички бизнес логика услуги
- `models/`: Споделени модели (DocumentType, DocumentStatus, Currency, и др.)
- `admin/`: Динамичен admin с workflow конфигурация
- Без app-специфична бизнес логика

#### App модули (`purchases/`, `inventory/`, и др.)
**Само тънки обвивки**:
- `models/`: Domain-специфични модели наследяващи от nomenclatures base класове
- `services/`: Минимални обвивки които делегират към nomenclatures услуги
- `views/`: UI контролери (делегират към услуги)
- **Без дублиране на бизнес логика**

### Шаблони за базата данни

#### Наследяване на модели
Използвай abstract base класове от nomenclatures:
```python
from nomenclatures.models import BaseDocument, BaseDocumentLine

class PurchaseRequest(BaseDocument):
    # Само purchase-специфични полета
    supplier = models.ForeignKey(Partner)

class PurchaseRequestLine(BaseDocumentLine):  
    # Само purchase-специфични полета на ред
    delivery_date = models.DateField()
```

#### Service Registry интеграция
Използвай ServiceResolverMixin за лесен достъп до услуги:
```python
from core.interfaces import ServiceResolverMixin

class DeliveryReceipt(ServiceResolverMixin, BaseDocument):
    def calculate_totals(self):
        pricing_service = self.get_pricing_service()
        return pricing_service.calculate_document_total(self)
```

#### Custom User модел
Системата използва `accounts.User`, не Django's default:
```python
from accounts.models import User  # Не django.contrib.auth.models.User
```

### Подход към тестване

#### Test файлове в Root
Development/integration тестове са в root директорията:
- `test_*.py` файлове съдържат integration тестове
- Фокус върху service-level тестване, не unit тестове
- Тестване на реални сценарии с актуални database операции

#### Тестване на български статуси
Системата е направена за българския пазар:
```python
# Пример за български status workflow
bulgarian_statuses = ['чернова', 'подадена', 'одобрена', 'завършена']
```

### Важни конвенции

#### Никога не използвай hardcoded статуси
```python
# ❌ НЕПРАВИЛНО
if document.status == 'approved':
    pass
    
# ✅ ПРАВИЛНО  
approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'processing')
if document.status in approval_statuses:
    pass
```

#### Винаги използвай Services
```python
# ❌ НЕПРАВИЛНО - Директна манипулация на модел
 line = PurchaseRequestLine.objects.create(...)

# ✅ ПРАВИЛНО - Използвай service facade
service = DocumentService(document, user)
result = service.add_line(product, quantity, price)
```

#### Обработвай Result обекти
```python
# Винаги проверявай result.ok преди да продължиш
result = service.some_operation()
if result.ok:
    # Success path
    data = result.data
else:
    # Error handling
    logger.error(result.msg)
```

#### Service Registry интеграция
```python
# ✅ НОВ ПОДХОД - Използвай Service Registry
from core.interfaces.service_registry import ServiceRegistry

pricing_service = ServiceRegistry.resolve('IPricingService')
result = pricing_service.calculate_line_price(product, quantity)

# Или с ServiceResolverMixin
class MyView(ServiceResolverMixin, View):
    def get(self, request):
        product_service = self.get_product_service()
        return JsonResponse(product_service.get_product_data())
```

### Frontend интеграция

#### Metronic тема
Използва Metronic 9 с Tailwind CSS 4:
- Компилирани файлове отиват в `dist/assets/`
- Source файлове в `src/`
- Поддържани са TypeScript и съвременни JavaScript функционалности

### Производителност съображения

#### StatusResolver кеширане
StatusResolver имплементира интелигентно кеширане (1 час TTL):
- Кеширане на status lookups в loops
- Резултатите са кеширани по тип документ
- Кешът се инвалидира автоматично при промени в конфигурацията

#### Service Registry производителност
ServiceRegistry имплементира кеширане на instances:
- Кеширани service instances за по-бързо resolve-ване
- Fallback към директни импорти за backward compatibility

#### Десетични калкулации
- Всички парични калкулации използват `Decimal` (никога `float`)
- Междинни калкулации с по-висока точност (4dp)
- Крайни display стойности закръглени с подходяща точност (2dp)

### Философия от обработка на грешки

#### Graceful Degradation
Услугите предоставят смислени fallback-ове:
- Ако конфигурацията липсва, премини на разумни defaults
- Ако StatusResolver не работи, използвай основни hardcoded fallbacks
- Винаги логирай грешки, но продължи операцията когато е възможно

#### Result Pattern предимства
- Няма изключения за бизнес логика грешки
- Консистентна обработка на грешки в всички операции
- Лесно chain-ване на операции и униформна обработка на грешки

## Ключови файлове за разбиране

- `nomenclatures/services/document_service.py` - Централни документни операции
- `nomenclatures/services/_status_resolver.py` - Динамично резолване на статуси
- `nomenclatures/services/approval_service.py` - Система за одобрения с Result pattern
- `inventory/services/movement_service.py` - Складови движения с прецизни калкулации
- `core/interfaces/service_registry.py` - Централизирано управление на service dependencies
- `core/utils/decimal_utils.py` - Калкулации съобразени с българското данъчно законодателство
- `core/models/fields.py` - Стандартизирани decimal field типове
- `nomenclatures/services/STATUS_RESOLVER_GUIDE.md` - Обширно ръководство за използване на status
- `nomenclatures/services/USAGE_EXAMPLES.md` - Примери за използване на DocumentService

## Философия на разработка

OptimaPOS приоритизира:
1. **Конфигурация над конвенция**: Всичко конфигурируемо, минимално hardcoding
2. **Централизирани услуги**: Цялата логика в споделени услуги, тънки app обвивки
3. **Българско съответствие**: Данъчни калкулации следват българските счетоводни стандарти
4. **Graceful Degradation**: Системата продължава да работи дори при проблеми с конфигурацията
5. **Result Pattern**: Предсказуема обработка на грешки без изключения
6. **Service Registry Pattern**: Централизирано управление на dependencies чрез интерфейси

## MCP Tools Available

### Context7
- **Цел**: Получаване на актуална документация за библиотеки и frameworks
- **Използвай когато**: Работиш с външни библиотеки (Django, Tailwind CSS, Metronic, React, и др.)
- **Предимства**: Актуални API референции, код примери, и документация вместо остарели знания

```python
# Пример: Вместо да предполагам как работи Django 5.0
# Използвай Context7 за най-новата документация
```

## Скорошни обновления и промени

### Нови тестове в root директорията
- `test_bulgarian_statuses.py` - Тестване на български статуси в реални сценарии
- `test_cancel_different_statuses.py` - Тестване на отказ в различни статуси
- `test_cancel_logic.py` - Цялостна логика за отказ на документи
- `test_delivery_buttons.py` - UI логика за бутони при доставки
- `test_final_statuses.py` - Тестване на финални статуси
- `test_interface_integration.py` - Интеграционни тестове за Service Registry
- `test_semantic_actions.py` - Тестване на semantic actions в StatusResolver

### Views с ServiceResolverMixin
Purchases views сега използват ServiceResolverMixin за интеграция с Service Registry:
```python
class DeliveryReceiptListView(LoginRequiredMixin, PermissionRequiredMixin, ListView, ServiceResolverMixin):
    def get_queryset(self):
        # Използва service registry за достъп до услуги
        inventory_service = self.get_inventory_service()
        return inventory_service.filter_delivery_receipts(...)
```

### Разширен ApprovalService
ApprovalService сега подкрепя Result pattern и предоставя детайлни ApprovalDecision обекти с:
- Авторизация информация
- Работен поток данни 
- Причини за отказ
- Одобрения статуси

### MovementService подобрения
MovementService сега включва:
- Стандартизирани decimal утилити за точни калкулации
- Batch tracking с expiry dates
- Подкрепа за различни типове движения (RECEIPT, ADJUSTMENT, TRANSFER)
- Result pattern за всички операции

# important-instruction-reminders
Прави това, което е поискано; нищо повече, нищо по-малко.
НИКОГА не създавай файлове освен ако не са абсолютно необходими за постигане на целта.
ВИНАГИ предпочитай редактиране на съществуващ файл пред създаване на нов.
НИКОГА не създавай проактивно документация (*.md) или README файлове. Създавай документация файлове само ако потребителят изрично го поиска.