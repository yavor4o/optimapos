# Документация на PARTNERS приложението

## 🎯 Преглед

**PARTNERS приложението** управлява бизнес отношенията в OptimaPOS, обработвайки както клиенти, така и доставчици с техните сложни бизнес изисквания включително управление на кредити, ценови групи, графици за доставка, множество сайтове и финансови контроли.

## 📋 Съдържание

1. [Архитектура](#архитектура)
2. [Основни модели](#основни-модели)
3. [Услуги](#услуги)
4. [Бизнес логика](#бизнес-логика)
5. [Интеграционни точки](#интеграционни-точки)
6. [Шаблони за използване](#шаблони-за-използване)
7. [API справочник](#api-справочник)
8. [Най-добри практики](#най-добри-практики)

---

## Архитектура

```
PARTNERS Структура на приложението:
├── models/
│   ├── base.py           # PartnerBase, PartnerScheduleBase
│   ├── customers.py      # Customer, CustomerSite, CustomerDaySchedule
│   └── suppliers.py      # Supplier, SupplierDivision, SupplierDaySchedule
├── services/
│   ├── customer_service.py  # Операции с клиенти и анализи
│   └── supplier_service.py  # Операции с доставчици и анализи
├── admin/
│   ├── customers.py      # Администрация на клиенти
│   └── suppliers.py      # Администрация на доставчици
└── views.py              # API endpoints
```

### Философия на дизайна

- **🏢 Бизнес-центричен** - Моделира реални бизнес отношения и процеси
- **💰 Управление на кредити** - Вградени финансови контроли и лимити
- **📅 Schedule-Aware** - Графици за доставка и поръчки за партньор
- **🏷️ Базиран на категории** - Клиентски групи, VIP статус, ценови нива
- **🏢 Multi-Site поддръжка** - Множество локации на клиент
- **🔄 Integration-Ready** - Безпроблемна интеграция с продажби, ценообразуване и покупки
- **📊 Analytics-Driven** - Богати възможности за отчети и dashboard

---

## Основни модели

### 1. **PartnerBase** (Абстрактна база)

**Цел**: Споделени полета и поведение за всички бизнес партньори

```python
# Основна идентичност
code = models.CharField(unique=True, max_length=20)  # Кратък уникален код (ABC, PIXEL)
name = models.CharField(max_length=200)              # Пълно бизнес име

# Данъчна информация
vat_number = models.CharField(max_length=20)         # ДДС/БУЛСТАТ номер
vat_registered = models.BooleanField(default=True)   # ДДС регистрационен статус

# Контактна информация
contact_person = models.CharField(max_length=100)
city = models.CharField(max_length=50)
address = models.TextField()
phone = models.CharField(max_length=20)
email = models.EmailField()

# Статус
is_active = models.BooleanField(default=True)
notes = models.TextField(blank=True)
```

**Автоматично почистване на данни:**
```python
def clean(self):
    # Автоматично форматиране
    self.name = self.name.strip()
    self.vat_number = self.vat_number.strip().upper()
    self.email = self.email.strip().lower()
    
    # Валидация
    if not self.name.strip():
        raise ValidationError({'name': 'Името не може да бъде празно'})
```

### 2. **Customer** (Разширява PartnerBase)

**Цел**: Управление на клиенти с кредит, ценообразуване и планиране

```python
from core.models.fields import CurrencyField

# Класификация на клиенти
type = models.CharField(
    choices=[('COMPANY', 'Фирма'), ('PERSON', 'Физическо лице')]
)
category = models.CharField(
    choices=[('REGULAR', 'Редовен'), ('VIP', 'VIP'), ('PROBLEMATIC', 'Проблемен')]
)

# Управление на кредити
credit_limit = CurrencyField()              # Максимален разрешен кредит (2dp точност)
payment_delay_days = models.IntegerField()  # Дни за отложено плащане
credit_blocked = models.BooleanField(default=False)  # Блокиране на кредитни продажби
sales_blocked = models.BooleanField(default=False)   # Блокиране на всички продажби

# Ценообразуване
price_group = models.ForeignKey('nomenclatures.PriceGroup', null=True, blank=True)
discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

# Бизнес логика методи
def can_buy(self):
    return self.is_active and not self.sales_blocked

def can_buy_on_credit(self):
    return self.can_buy() and not self.credit_blocked and self.credit_limit > 0

def get_effective_discount(self):
    if self.price_group:
        return self.price_group.discount_percentage
    return self.discount_percent or 0
```

### 3. **CustomerSite** (Локации на клиенти)

**Цел**: Множество адреси за доставка/фактуриране на клиент

```python
# Идентичност на сайта
customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
name = models.CharField(max_length=100)  # Име/идентификатор на сайта

# Адресна информация
city = models.CharField(max_length=50)
address = models.TextField()
contact_person = models.CharField(max_length=100)
phone = models.CharField(max_length=20)
email = models.EmailField(blank=True)

# Типове сайтове
is_delivery_address = models.BooleanField(default=True)
is_billing_address = models.BooleanField(default=False)
is_primary = models.BooleanField(default=False)  # Само един на клиент

# Специални условия
special_discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
```

**Правила за валидация:**
```python
def clean(self):
    # Гарантирай само един primary сайт на клиент
    if self.is_primary:
        existing_primary = CustomerSite.objects.filter(
            customer=self.customer,
            is_primary=True
        ).exclude(pk=self.pk)
        
        if existing_primary.exists():
            raise ValidationError('Клиентът може да има само един основен сайт')
```

### 4. **Supplier** (Разширява PartnerBase)

**Цел**: Управление на доставчици с отделения и графици за доставка

```python
from core.models.fields import CurrencyField

# Финансови условия
credit_limit = CurrencyField()               # Кредитен лимит с доставчика (2dp точност)
payment_days = models.IntegerField()         # Дни за плащане

# Управление на доставки
delivery_blocked = models.BooleanField(default=False)  # Блокиране на всички доставки
can_deliver_today = models.BooleanField(default=False)  # Флаг за бърза доставка

# Бизнес логика
def can_deliver(self):
    return self.is_active and not self.delivery_blocked

def get_effective_payment_days(self):
    # Може да се пренаписва от отделение
    return self.payment_days
```

### 5. **SupplierDivision** (Отделения на доставчици)

**Цел**: Организационни отделения в рамките на доставчици

```python
supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
name = models.CharField(max_length=100)      # Име на отделението
code = models.CharField(max_length=20)       # Код на отделението

# Division-специфични условия
payment_days = models.IntegerField(null=True, blank=True)  # Пренаписва условията за плащане на доставчика
contact_person = models.CharField(max_length=100)
phone = models.CharField(max_length=20)
email = models.EmailField(blank=True)

def get_effective_payment_days(self):
    return self.payment_days or self.supplier.payment_days
```

### 6. **Графици на партньори** (Седмични операции)

**График на клиенти:**
```python
class CustomerDaySchedule(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    day = models.CharField(
        max_length=3,
        choices=[('mon', 'Понеделник'), ('tue', 'Вторник'), ('wed', 'Сряда'), 
                ('thu', 'Четвъртък'), ('fri', 'Петък'), ('sat', 'Събота'), ('sun', 'Неделя')]
    )
    
    # Дейности на клиента
    expects_order = models.BooleanField(default=False)     # Прави поръчки този ден
    expects_delivery = models.BooleanField(default=False)  # Очаква доставки този ден
    
    # Предпочитания за време
    preferred_delivery_time_from = models.TimeField(null=True, blank=True)
    preferred_delivery_time_to = models.TimeField(null=True, blank=True)
```

**График на доставчици:**
```python  
class SupplierDaySchedule(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    day = models.CharField(
        max_length=3,
        choices=[('mon', 'Понеделник'), ('tue', 'Вторник'), ('wed', 'Сряда'),
                ('thu', 'Четвъртък'), ('fri', 'Петък'), ('sat', 'Събота'), ('sun', 'Неделя')]
    )
    
    # Дейности на доставчика
    expects_order = models.BooleanField(default=False)     # Приема поръчки този ден
    makes_delivery = models.BooleanField(default=False)    # Прави доставки този ден
    
    # Крайни срокове за поръчки
    order_deadline_time = models.TimeField(null=True, blank=True)  # Краен срок за поръчки
    delivery_time_from = models.TimeField(null=True, blank=True)
    delivery_time_to = models.TimeField(null=True, blank=True)
```

---

## Услуги

### 1. **CustomerService** (Result Pattern)

```python
from partners.services import CustomerService

# Получава изчерпателни данни за dashboard на клиента
result = CustomerService.get_dashboard_data(customer_id=42)
if result.ok:
    dashboard = result.data
    basic_info = dashboard['basic_info']
    financial = dashboard['financial']
    sites = dashboard['sites']
    schedule = dashboard['schedule']
    statistics = dashboard['statistics']
```

**Ключови методи:**
- `get_dashboard_data(customer_id)` - Пълен преглед на клиента
- `get_financial_data(customer)` - Използване на кредит, история на плащания
- `get_sites_data(customer)` - Всички локации на клиента
- `get_schedule_data(customer)` - Седмичен график за поръчки/доставки
- `get_statistics_data(customer)` - Анализи на историята на покупки
- `validate_customer_operation(customer, amount)` - Валидация на кредит/продажби

### 2. **SupplierService** (Result Pattern)

```python
from partners.services import SupplierService

# Получава dashboard на доставчика с всички отделения
result = SupplierService.get_dashboard_data(supplier_id=15)
if result.ok:
    dashboard = result.data
    basic_info = dashboard['basic_info']
    divisions = dashboard['divisions']
    financial = dashboard['financial']
    deliveries = dashboard['deliveries']

# Валидира операция за покупка
validation = SupplierService.validate_supplier_operation(
    supplier=supplier,
    amount=Decimal('5000.00')
)
if not validation.ok:
    handle_supplier_error(validation.code, validation.msg)
```

**Ключови методи:**
- `get_dashboard_data(supplier_id)` - Пълен преглед на доставчика
- `get_divisions_data(supplier)` - Активни отделения и условия
- `get_financial_data(supplier)` - Използване на кредит, неплатени поръчки
- `get_delivery_data(supplier, date_range)` - История на доставки
- `get_statistics_data(supplier)` - Анализи на обема на покупки
- `validate_supplier_operation(supplier, amount)` - Валидация на кредитен лимит

---

## Бизнес логика

### 1. **Управление на кредити на клиенти**

```python
from core.models.fields import CurrencyField
from core.utils.decimal_utils import round_currency

class Customer:
    def can_buy(self):
        """Основна валидация за покупка"""
        return self.is_active and not self.sales_blocked
        
    def can_buy_on_credit(self):
        """Валидация за кредитна покупка"""
        return (self.can_buy() and 
                not self.credit_blocked and 
                self.credit_limit > 0)

    def get_available_credit(self):
        """Получава наличен кредит с правилна десетична точност"""
        used_credit = self.get_used_credit()  # 2dp точност
        available = self.credit_limit - used_credit
        return round_currency(max(available, Decimal('0.00')))

# Service-ниво валидация на кредит
def validate_customer_operation(customer, amount):
    """Валидира клиентска операция с правилна десетична точност"""
    if not customer.can_buy():
        return Result.error('CUSTOMER_BLOCKED', 'Клиентът не може да прави покупки')
    
    # Гарантирай правилна десетична точност за сравнението
    amount = round_currency(amount)
    available_credit = customer.get_available_credit()
        
    if amount > available_credit:
        return Result.error(
            'CREDIT_EXCEEDED', 
            f'Покупката {amount} надвишава наличния кредит {available_credit}'
        )
        
    return Result.success()
```

### 2. **Управление на доставки на доставчици**

```python
class Supplier:
    def can_deliver(self):
        """Проверка за възможност за доставка"""
        return self.is_active and not self.delivery_blocked

# Получава днешните доставчици за доставка
def get_today_delivery_suppliers():
    """Връща доставчици които доставят днес"""
    today = timezone.now().strftime('%a').lower()[:3]  # 'mon', 'tue', и т.н.
    
    return Supplier.objects.filter(
        day_schedules__day=today,
        day_schedules__makes_delivery=True,
        is_active=True,
        delivery_blocked=False
    ).distinct()
```

### 3. **Интеграция на ценообразуването**

```python
class Customer:
    def get_effective_discount(self):
        """Получава приложим процент отстъпка"""
        # Ценовата група има предимство
        if self.price_group and hasattr(self.price_group, 'discount_percentage'):
            return self.price_group.discount_percentage
        
        # Fallback към директна отстъпка
        return self.discount_percent or 0

# Използване в pricing service
def calculate_customer_price(base_price, customer):
    """Калкулира клиентска цена с правилна десетична точност"""
    from core.utils.decimal_utils import round_currency
    
    discount = customer.get_effective_discount()
    discounted_price = base_price * (1 - discount / 100)
    return round_currency(discounted_price)
```

---

## Интеграционни точки

### **С PRICING App:**

```python
# Интеграция на клиентска ценова група
class Customer:
    price_group = models.ForeignKey('nomenclatures.PriceGroup', null=True, blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    def get_effective_discount(self):
        if self.price_group:
            return self.price_group.discount_percentage
        return self.discount_percent or 0

# Използвано в PricingService
def get_customer_pricing(location, product, customer):
    if customer and customer.price_group:
        group_price = ProductPriceByGroup.objects.filter(
            location=location,
            product=product,
            customer_group=customer.price_group
        ).first()
        
        if group_price:
            return group_price.price  # Вече с 2dp точност
    return None
```

### **С PURCHASES App:**

```python
# Интеграция на доставчици в документи за покупка
class PurchaseOrder:
    supplier = models.ForeignKey('partners.Supplier')
    
    def clean(self):
        # Валидира че доставчикът може да доставя
        if not self.supplier.can_deliver():
            raise ValidationError('Доставката на доставчика е блокирана')

# Финансова интеграция
def get_supplier_financial_data(supplier):
    """Получава финансови данни за доставчик с правилна точност"""
    from core.utils.decimal_utils import round_currency
    
    # Получи неплатени поръчки за покупка
    unpaid_orders = PurchaseOrder.objects.filter(
        supplier=supplier,
        status__in=['pending', 'approved']
    ).aggregate(
        unpaid_amount=Sum('total'),
        unpaid_count=Count('id')
    )
    
    # Провери наличност на кредит
    used_credit = unpaid_orders['unpaid_amount'] or Decimal('0.00')
    used_credit = round_currency(used_credit)  # Гарантирай 2dp точност
    
    available_credit = round_currency(supplier.credit_limit - used_credit)
    
    return {
        'used_credit': used_credit,
        'available_credit': available_credit,
        'unpaid_count': unpaid_orders['unpaid_count']
    }
```

---

## Шаблони за използване

### 1. **Настройка на клиент със сайтове**

```python
from core.utils.decimal_utils import Decimal

# Създай клиент
customer = Customer.objects.create(
    code='ACME001',
    name='АКМЕ Корпорейшън',
    type=Customer.COMPANY,
    vat_number='BG123456789',
    credit_limit=Decimal('10000.00'),  # Автоматично 2dp точност
    payment_delay_days=30,
    price_group=wholesale_group,
    category=Customer.VIP
)

# Добави основен сайт
primary_site = CustomerSite.objects.create(
    customer=customer,
    name='Централа',
    city='София',
    address='Бизнес парк, Сграда А',
    contact_person='Иван Петров',
    phone='+359888123456',
    is_primary=True,
    is_delivery_address=True,
    is_billing_address=True
)

# Добави график за доставки
CustomerDaySchedule.objects.create(
    customer=customer,
    day='tue',  # Вторник
    expects_order=True,
    expects_delivery=False
)

CustomerDaySchedule.objects.create(
    customer=customer,
    day='fri',  # Петък
    expects_delivery=True,
    preferred_delivery_time_from='09:00',
    preferred_delivery_time_to='17:00'
)
```

### 2. **Валидация на клиент в продажби**

```python
from core.utils.decimal_utils import round_currency

def process_sales_order(customer, order_data):
    """Обработва поръчка за продажба с валидация на клиента"""
    # Валидира че клиентът може да купува
    if not customer.can_buy():
        return Result.error(
            'CUSTOMER_BLOCKED',
            f'Клиент {customer.name} е блокиран от покупки'
        )
    
    # Валидира кредит за кредитни продажби
    if order_data['payment_method'] == 'CREDIT':
        if not customer.can_buy_on_credit():
            return Result.error(
                'CREDIT_BLOCKED', 
                'Кредитът на клиента е блокиран или лимитът е нула'
            )
        
        # Провери сума спрямо лимит с правилна точност
        order_total = round_currency(order_data['total'])
        available_credit = customer.get_available_credit()
        
        if order_total > available_credit:
            return Result.error(
                'CREDIT_EXCEEDED',
                f'Общо поръчка {order_total} надвишава кредитен лимит {available_credit}'
            )
    
    # Прилагай клиентска отстъпка
    discount = customer.get_effective_discount()
    if discount > 0:
        order_data['discount_percent'] = discount
    
    return Result.success(data=order_data)
```

### 3. **Работа с десетична точност в финансовите операции**

```python
from core.utils.decimal_utils import round_currency

class CustomerService:
    @staticmethod
    def calculate_customer_financial_summary(customer):
        """Калкулира финансово резюме с правилна десетична точност"""
        from django.db.models import Sum
        
        # Получи сумите с database aggregation
        financial_data = SalesOrder.objects.filter(
            customer=customer
        ).aggregate(
            total_orders=Sum('total_amount'),
            unpaid_amount=Sum('unpaid_amount')
        )
        
        # Гарантирай правилна десетична точност
        total_orders = financial_data['total_orders'] or Decimal('0.00')
        unpaid_amount = financial_data['unpaid_amount'] or Decimal('0.00')
        
        total_orders = round_currency(total_orders)      # 2dp точност
        unpaid_amount = round_currency(unpaid_amount)    # 2dp точност
        
        # Калкулирай наличен кредит
        used_credit = unpaid_amount
        available_credit = round_currency(customer.credit_limit - used_credit)
        
        return {
            'credit_limit': customer.credit_limit,       # Вече с 2dp точност
            'used_credit': used_credit,                  # 2dp точност
            'available_credit': available_credit,        # 2dp точност
            'total_orders_amount': total_orders,         # 2dp точност
            'unpaid_amount': unpaid_amount              # 2dp точност
        }
```

---

## API справочник

### Result структури от данни

**Customer Dashboard:**
```python
{
    'basic_info': {
        'id': 42,
        'name': 'АКМЕ Корпорейшън',
        'code': 'ACME001',
        'type': 'COMPANY',
        'category': 'VIP',
        'is_active': True,
        'sales_blocked': False,
        'credit_blocked': False,
        'can_buy': True,
        'can_buy_on_credit': True
    },
    'financial': {
        'credit_limit': Decimal('10000.00'),        # 2dp точност
        'used_credit': Decimal('2500.00'),          # 2dp точност
        'available_credit': Decimal('7500.00'),     # 2dp точност
        'payment_delay_days': 30,
        'total_orders_amount': Decimal('25000.00'), # 2dp точност
        'unpaid_amount': Decimal('2500.00')         # 2dp точност
    },
    'sites': [
        {
            'id': 1,
            'name': 'Централа',
            'city': 'София',
            'address': 'Бизнес парк, Сграда А',
            'is_primary': True,
            'is_delivery_address': True,
            'special_discount': Decimal('0.00')      # 2dp точност
        }
    ],
    'schedule': {
        'order_days': ['tue'],
        'delivery_days': ['fri'],
        'delivery_preferences': [
            {
                'day': 'fri',
                'time_from': '09:00',
                'time_to': '17:00'
            }
        ]
    }
}
```

**Supplier Dashboard:**
```python
{
    'basic_info': {
        'id': 15,
        'name': 'Премиум Дистрибутор ООД',
        'code': 'DIST001',
        'contact_person': 'Иван Петров',
        'is_active': True,
        'delivery_blocked': False,
        'can_deliver': True
    },
    'divisions': [
        {
            'id': 5,
            'name': 'Отделение храни',
            'code': 'FOODS',
            'contact_person': 'Мария Петрова',
            'payment_days': 30
        }
    ],
    'financial': {
        'credit_limit': Decimal('50000.00'),        # 2dp точност
        'used_credit': Decimal('15000.00'),         # 2dp точност
        'available_credit': Decimal('35000.00'),    # 2dp точност
        'payment_days': 45,
        'total_orders_amount': Decimal('125000.00'), # 2dp точност
        'unpaid_count': 5
    },
    'schedule': {
        'order_days': [
            {
                'day': 'mon',
                'deadline': '14:00'
            }
        ],
        'delivery_days': [
            {
                'day': 'wed',
                'time_from': '08:00',
                'time_to': '16:00'
            }
        ]
    }
}
```

---

## Най-добри практики

### 1. **Винаги използвайте Result Pattern**

```python
# ✅ Добро
result = CustomerService.get_dashboard_data(customer_id)
if result.ok:
    dashboard = result.data
    financial = dashboard['financial']
else:
    handle_error(result.code, result.msg)

# ❌ Избягвайте директен достъп до модел за сложни операции
try:
    customer = Customer.objects.get(id=customer_id)
    # Ръчно изграждане на dashboard - липсва error handling, консистентност
except Customer.DoesNotExist:
    pass
```

### 2. **Използвайте правилната десетична точност**

```python
# ✅ Добро - използвайте стандартизираните утилити
from core.utils.decimal_utils import round_currency

def calculate_customer_discount(base_price, discount_percent):
    # Калкулирай с висока точност
    discount_amount = base_price * (discount_percent / 100)
    
    # Закръгли за дисплей/съхранение
    final_discount = round_currency(discount_amount)  # 2dp точност
    final_price = round_currency(base_price - final_discount)
    
    return final_price, final_discount

# ❌ Избягвайте - ръчно закръгляване
discount = round(base_price * 0.15, 2)  # Може да има неточности
```

### 3. **Валидирайте бизнес операции**

```python
# ✅ Добро - валидирайте преди обработка
validation = CustomerService.validate_customer_operation(customer, amount)
if validation.ok:
    proceed_with_sale(customer, amount)
else:
    return validation

# ❌ Избягвайте прескачане на валидация
if customer.is_active:  # Непълна валидация
    proceed_with_sale(customer, amount)
```

### 4. **Обработвайте сайтовете правилно**

```python
# ✅ Добро - получи подходящ сайт
delivery_site = customer.sites.filter(is_delivery_address=True).first()
if not delivery_site:
    delivery_site = customer.sites.filter(is_primary=True).first()

billing_site = customer.sites.filter(is_billing_address=True).first()
if not billing_site:
    billing_site = customer.sites.filter(is_primary=True).first()

# ❌ Избягвайте предположения че сайтовете съществуват
delivery_address = customer.sites.first().address  # Може да се провали
```

---

## Зависимости

**PARTNERS app зависи от:**
- Django framework
- CORE app (Result pattern, десетични утилити)
- NOMENCLATURES app (PriceGroup модел)

**Други apps зависят от PARTNERS:**
- PURCHASES (Supplier модел)
- SALES (Customer модел)  
- PRICING (клиентско групово ценообразуване)
- REPORTS (анализи на партньори)

---

## История на версиите

- **v1.0** - Основни клиентски и доставчически модели
- **v1.1** - Добавена multi-site поддръжка за клиенти
- **v1.2** - Добавени отделения на доставчици
- **v1.3** - Добавени седмични графици
- **v1.4** - Подобрено управление на кредити
- **v1.5** - Добавени клиентски категории и VIP статус
- **v2.0** - Result pattern service рефакториране
- **v2.1** - Подобрени dashboard и анализи
- **v3.0** - Стандартизирана десетична точност, подобрена финансова точност

---

*Последна актуализация: 2025-09-05*  
*Версия: 3.0*  
*Актуализирано според актуалния код с десетична точност*