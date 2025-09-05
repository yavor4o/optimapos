# PARTNERS App Documentation

## 🎯 Overview

The **PARTNERS app** manages business relationships in OptimaPOS, handling both customers and suppliers with their complex business requirements including credit management, pricing groups, delivery schedules, multiple sites, and financial controls.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Core Models](#core-models)
3. [Services](#services)
4. [Business Logic](#business-logic)
5. [Integration Points](#integration-points)
6. [Usage Patterns](#usage-patterns)
7. [API Reference](#api-reference)
8. [Best Practices](#best-practices)

---

## Architecture

```
PARTNERS App Structure:
├── models/
│   ├── base.py           # PartnerBase, PartnerScheduleBase
│   ├── customers.py      # Customer, CustomerSite, CustomerDaySchedule
│   └── suppliers.py      # Supplier, SupplierDivision, SupplierDaySchedule
├── services/
│   ├── customer_service.py  # Customer operations and analytics
│   └── supplier_service.py  # Supplier operations and analytics
├── admin/
│   ├── customers.py      # Customer administration
│   └── suppliers.py      # Supplier administration
└── views.py              # API endpoints
```

### Design Philosophy

- **🏢 Business-Centric** - Models real business relationships and processes
- **💰 Credit Management** - Built-in financial controls and limits
- **📅 Schedule-Aware** - Delivery and ordering schedules per partner
- **🏷️ Category-Based** - Customer groups, VIP status, pricing tiers
- **🏢 Multi-Site Support** - Multiple locations per customer
- **🔄 Integration-Ready** - Seamless integration with sales, pricing, and purchases
- **📊 Analytics-Driven** - Rich reporting and dashboard capabilities

---

## Core Models

### 1. **PartnerBase** (Abstract Base)

**Purpose**: Shared fields and behavior for all business partners

```python
# Core Identity
code = CharField(unique=True)        # Short unique code (ABC, PIXEL)
name = CharField()                   # Full business name

# Tax Information  
vat_number = CharField()             # VAT/BULSTAT number
vat_registered = BooleanField()      # VAT registration status

# Contact Information
contact_person = CharField()
city = CharField()
address = TextField()
phone = CharField()
email = EmailField()

# Status
is_active = BooleanField()
notes = TextField()
```

**Automatic Data Cleaning:**
```python
def clean(self):
    # Automatic formatting
    self.name = self.name.strip()
    self.vat_number = self.vat_number.strip().upper()
    self.email = self.email.strip().lower()
    
    # Validation
    if not self.name.strip():
        raise ValidationError({'name': 'Name cannot be empty'})
```

### 2. **Customer** (Extends PartnerBase)

**Purpose**: Customer management with credit, pricing, and scheduling

```python
# Customer Classification
type = ['COMPANY', 'PERSON']
category = ['REGULAR', 'VIP', 'PROBLEMATIC']

# Credit Management
credit_limit = Decimal()             # Maximum credit allowed
payment_delay_days = Integer()       # Deferred payment days
credit_blocked = BooleanField()      # Block credit sales
sales_blocked = BooleanField()       # Block all sales

# Pricing
price_group = ForeignKey('nomenclatures.PriceGroup')
discount_percent = Decimal()         # Default discount when no group

# Business Logic Methods
def can_buy(self):
    return self.is_active and not self.sales_blocked

def can_buy_on_credit(self):
    return self.can_buy() and not self.credit_blocked and self.credit_limit > 0

def get_effective_discount(self):
    if self.price_group:
        return self.price_group.discount_percentage
    return self.discount_percent or 0
```

### 3. **CustomerSite** (Customer Locations)

**Purpose**: Multiple delivery/billing addresses per customer

```python
# Site Identity
customer = ForeignKey(Customer)
name = CharField()                   # Site name/identifier

# Address Information
city = CharField()
address = TextField()
contact_person = CharField()
phone = CharField()
email = EmailField()

# Site Types
is_delivery_address = BooleanField()
is_billing_address = BooleanField()
is_primary = BooleanField()          # Only one per customer

# Special Conditions
special_discount = Decimal()         # Site-specific discount
```

**Validation Rules:**
```python
def clean(self):
    # Ensure only one primary site per customer
    if self.is_primary:
        existing_primary = CustomerSite.objects.filter(
            customer=self.customer,
            is_primary=True
        ).exclude(pk=self.pk)
        
        if existing_primary.exists():
            raise ValidationError('Customer can have only one primary site')
```

### 4. **Supplier** (Extends PartnerBase)

**Purpose**: Supplier management with divisions and delivery schedules

```python
# Financial Terms
credit_limit = Decimal()             # Credit limit with supplier
payment_days = Integer()             # Payment term days

# Delivery Management  
delivery_blocked = BooleanField()    # Block all deliveries
can_deliver_today = BooleanField()   # Quick delivery flag

# Business Logic
def can_deliver(self):
    return self.is_active and not self.delivery_blocked

def get_effective_payment_days(self):
    # Can be overridden by division
    return self.payment_days
```

### 5. **SupplierDivision** (Supplier Departments)

**Purpose**: Organizational divisions within suppliers

```python
supplier = ForeignKey(Supplier)
name = CharField()                   # Division name
code = CharField()                   # Division code

# Division-specific terms
payment_days = Integer()             # Override supplier payment terms
contact_person = CharField()
phone = CharField()
email = EmailField()

def get_effective_payment_days(self):
    return self.payment_days or self.supplier.payment_days
```

### 6. **Partner Schedules** (Weekly Operations)

**Customer Schedule:**
```python
class CustomerDaySchedule:
    customer = ForeignKey(Customer)
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    
    # Customer Activities
    expects_order = BooleanField()           # Places orders this day
    expects_delivery = BooleanField()        # Expects deliveries this day
    
    # Time Preferences
    preferred_delivery_time_from = TimeField()
    preferred_delivery_time_to = TimeField()
```

**Supplier Schedule:**
```python  
class SupplierDaySchedule:
    supplier = ForeignKey(Supplier)
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    
    # Supplier Activities
    expects_order = BooleanField()           # Accepts orders this day
    makes_delivery = BooleanField()          # Makes deliveries this day
    
    # Order Deadlines
    order_deadline_time = TimeField()       # Order cutoff time
    delivery_time_from = TimeField()
    delivery_time_to = TimeField()
```

---

## Services

### 1. **CustomerService** (Result Pattern)

```python
from partners.services import CustomerService

# Get comprehensive customer dashboard
result = CustomerService.get_dashboard_data(customer_id=42)
if result.ok:
    dashboard = result.data
    basic_info = dashboard['basic_info']
    financial = dashboard['financial']
    sites = dashboard['sites']
    schedule = dashboard['schedule']
    statistics = dashboard['statistics']
```

**Key Methods:**
- `get_dashboard_data(customer_id)` - Complete customer overview
- `get_financial_data(customer)` - Credit usage, payment history
- `get_sites_data(customer)` - All customer locations
- `get_schedule_data(customer)` - Weekly order/delivery schedule
- `get_statistics_data(customer)` - Purchase history analytics
- `validate_customer_operation(customer, amount)` - Credit/sales validation

### 2. **SupplierService** (Result Pattern)

```python
from partners.services import SupplierService

# Get supplier dashboard with all divisions
result = SupplierService.get_dashboard_data(supplier_id=15)
if result.ok:
    dashboard = result.data
    basic_info = dashboard['basic_info']
    divisions = dashboard['divisions']
    financial = dashboard['financial']
    deliveries = dashboard['deliveries']

# Validate purchase operation
validation = SupplierService.validate_supplier_operation(
    supplier=supplier,
    amount=Decimal('5000.00')
)
if not validation.ok:
    handle_supplier_error(validation.code, validation.msg)
```

**Key Methods:**
- `get_dashboard_data(supplier_id)` - Complete supplier overview  
- `get_divisions_data(supplier)` - Active divisions and terms
- `get_financial_data(supplier)` - Credit usage, unpaid orders
- `get_delivery_data(supplier, date_range)` - Delivery history
- `get_statistics_data(supplier)` - Purchase volume analytics
- `validate_supplier_operation(supplier, amount)` - Credit limit validation

---

## Business Logic

### 1. **Customer Credit Management**

```python
class Customer:
    def can_buy(self):
        """Basic purchase validation"""
        return self.is_active and not self.sales_blocked
        
    def can_buy_on_credit(self):
        """Credit purchase validation"""
        return (self.can_buy() and 
                not self.credit_blocked and 
                self.credit_limit > 0)

# Service-level credit validation
def validate_customer_operation(customer, amount):
    if not customer.can_buy():
        return Result.error('CUSTOMER_BLOCKED', 'Customer cannot make purchases')
        
    if amount > customer.credit_limit:
        return Result.error('CREDIT_EXCEEDED', 'Purchase exceeds credit limit')
        
    return Result.success()
```

### 2. **Supplier Delivery Management**

```python
class Supplier:
    def can_deliver(self):
        """Delivery capability check"""
        return self.is_active and not self.delivery_blocked

# Get today's delivery suppliers
def get_today_delivery_suppliers():
    """Returns suppliers that deliver today"""
    today = timezone.now().strftime('%a').lower()[:3]  # 'mon', 'tue', etc.
    
    return Supplier.objects.filter(
        day_schedules__day=today,
        day_schedules__makes_delivery=True,
        is_active=True,
        delivery_blocked=False
    ).distinct()
```

### 3. **Pricing Integration**

```python
class Customer:
    def get_effective_discount(self):
        """Get applicable discount percentage"""
        # Price group takes precedence
        if self.price_group and hasattr(self.price_group, 'discount_percentage'):
            return self.price_group.discount_percentage
        
        # Fallback to direct discount
        return self.discount_percent or 0

# Usage in pricing service
def calculate_customer_price(base_price, customer):
    discount = customer.get_effective_discount()
    return base_price * (1 - discount / 100)
```

### 4. **Schedule Management**

```python
# Customer order/delivery days
class Customer:
    def get_delivery_days(self):
        """Days when customer expects deliveries"""
        return self.day_schedules.filter(expects_delivery=True)
        
    def get_order_days(self):
        """Days when customer places orders"""
        return self.day_schedules.filter(expects_order=True)

# Supplier order/delivery days  
class Supplier:
    def get_order_days(self):
        """Days when supplier accepts orders"""
        return self.day_schedules.filter(expects_order=True)
        
    def get_delivery_days(self):
        """Days when supplier makes deliveries"""
        return self.day_schedules.filter(makes_delivery=True)
```

---

## Integration Points

### **With PRICING App:**

```python
# Customer price group integration
class Customer:
    price_group = ForeignKey('nomenclatures.PriceGroup')
    discount_percent = Decimal()
    
    def get_effective_discount(self):
        if self.price_group:
            return self.price_group.discount_percentage
        return self.discount_percent or 0

# Used in PricingService
def get_customer_pricing(location, product, customer):
    if customer and customer.price_group:
        group_price = ProductPriceByGroup.objects.filter(
            location=location,
            product=product,
            customer_group=customer.price_group
        ).first()
        
        if group_price:
            return group_price.price
```

### **With PURCHASES App:**

```python
# Supplier integration in purchase documents
class PurchaseOrder:
    supplier = ForeignKey('partners.Supplier')
    
    def clean(self):
        # Validate supplier can deliver
        if not self.supplier.can_deliver():
            raise ValidationError('Supplier delivery is blocked')

# Financial integration
def get_supplier_financial_data(supplier):
    # Get unpaid purchase orders
    unpaid_orders = PurchaseOrder.objects.filter(
        supplier=supplier,
        status__in=['pending', 'approved']
    ).aggregate(
        unpaid_amount=Sum('total'),
        unpaid_count=Count('id')
    )
    
    # Check credit availability
    used_credit = unpaid_orders['unpaid_amount'] or Decimal('0')
    available_credit = supplier.credit_limit - used_credit
```

### **With SALES App:**

```python
# Customer integration in sales documents
class SalesOrder:
    customer = ForeignKey('partners.Customer')
    customer_site = ForeignKey('partners.CustomerSite', null=True)
    
    def clean(self):
        # Validate customer can buy
        if not self.customer.can_buy():
            raise ValidationError('Customer sales are blocked')
            
        # Check credit for credit sales
        if self.payment_method == 'CREDIT':
            if not self.customer.can_buy_on_credit():
                raise ValidationError('Customer credit is blocked')

# Customer site for delivery
def get_delivery_address(customer):
    # Use primary site or first delivery address
    primary_site = customer.sites.filter(is_primary=True).first()
    if primary_site:
        return primary_site
        
    return customer.sites.filter(is_delivery_address=True).first()
```

### **With INVENTORY App:**

```python
# Schedule-based inventory planning
def get_expected_deliveries(date):
    """Get expected deliveries for date based on supplier schedules"""
    weekday = date.strftime('%a').lower()[:3]
    
    suppliers = Supplier.objects.filter(
        day_schedules__day=weekday,
        day_schedules__makes_delivery=True,
        is_active=True
    )
    
    return suppliers

def get_order_deadline_suppliers(date):
    """Get suppliers with order deadlines today"""
    weekday = date.strftime('%a').lower()[:3]
    
    return Supplier.objects.filter(
        day_schedules__day=weekday,
        day_schedules__expects_order=True,
        is_active=True
    )
```

---

## Usage Patterns

### 1. **Customer Setup with Sites**

```python
# Create customer
customer = Customer.objects.create(
    code='ACME001',
    name='ACME Corporation',
    type=Customer.COMPANY,
    vat_number='BG123456789',
    credit_limit=Decimal('10000.00'),
    payment_delay_days=30,
    price_group=wholesale_group,
    category=Customer.VIP
)

# Add primary site
primary_site = CustomerSite.objects.create(
    customer=customer,
    name='Headquarters',
    city='Sofia',
    address='Business Park, Building A',
    contact_person='John Smith',
    phone='+359888123456',
    is_primary=True,
    is_delivery_address=True,
    is_billing_address=True
)

# Add delivery schedule
CustomerDaySchedule.objects.create(
    customer=customer,
    day='tue',  # Tuesday
    expects_order=True,
    expects_delivery=False
)

CustomerDaySchedule.objects.create(
    customer=customer,
    day='fri',  # Friday  
    expects_delivery=True,
    preferred_delivery_time_from='09:00',
    preferred_delivery_time_to='17:00'
)
```

### 2. **Supplier Setup with Divisions**

```python
# Create supplier
supplier = Supplier.objects.create(
    code='DIST001',
    name='Premium Distributor Ltd',
    vat_number='BG987654321',
    credit_limit=Decimal('50000.00'),
    payment_days=45,
    is_active=True
)

# Add divisions
foods_division = SupplierDivision.objects.create(
    supplier=supplier,
    name='Foods Division',
    code='FOODS',
    payment_days=30,  # Different terms
    contact_person='Maria Petrova',
    phone='+359888654321'
)

# Add delivery schedule
SupplierDaySchedule.objects.create(
    supplier=supplier,
    day='mon',  # Monday
    expects_order=True,
    order_deadline_time='14:00'
)

SupplierDaySchedule.objects.create(
    supplier=supplier,
    day='wed',  # Wednesday
    makes_delivery=True,
    delivery_time_from='08:00',
    delivery_time_to='16:00'
)
```

### 3. **Customer Validation in Sales**

```python
def process_sales_order(customer, order_data):
    # Validate customer can buy
    if not customer.can_buy():
        return Result.error(
            'CUSTOMER_BLOCKED',
            f'Customer {customer.name} is blocked from purchases'
        )
    
    # Validate credit for credit sales
    if order_data['payment_method'] == 'CREDIT':
        if not customer.can_buy_on_credit():
            return Result.error(
                'CREDIT_BLOCKED', 
                'Customer credit is blocked or limit is zero'
            )
        
        # Check amount against limit
        if order_data['total'] > customer.credit_limit:
            return Result.error(
                'CREDIT_EXCEEDED',
                f'Order total {order_data["total"]} exceeds credit limit {customer.credit_limit}'
            )
    
    # Apply customer discount
    discount = customer.get_effective_discount()
    if discount > 0:
        order_data['discount_percent'] = discount
    
    return Result.success(data=order_data)
```

### 4. **Supplier Validation in Purchases**

```python
def process_purchase_order(supplier, order_data):
    # Validate supplier operation
    validation = SupplierService.validate_supplier_operation(
        supplier=supplier,
        amount=order_data['total']
    )
    
    if not validation.ok:
        return validation
    
    # Check delivery capability
    if not supplier.can_deliver():
        return Result.error(
            'DELIVERY_BLOCKED',
            f'Supplier {supplier.name} delivery is blocked'
        )
    
    # Get effective payment terms
    if 'division_id' in order_data:
        division = supplier.divisions.get(id=order_data['division_id'])
        payment_days = division.get_effective_payment_days()
    else:
        payment_days = supplier.payment_days
    
    order_data['payment_days'] = payment_days
    
    return Result.success(data=order_data)
```

### 5. **Schedule-Based Operations**

```python
def get_daily_operations(target_date):
    """Get planned operations for a specific date"""
    weekday = target_date.strftime('%a').lower()[:3]
    
    operations = {
        'suppliers_expecting_orders': [],
        'suppliers_making_deliveries': [],
        'customers_placing_orders': [],
        'customers_expecting_deliveries': []
    }
    
    # Suppliers
    operations['suppliers_expecting_orders'] = Supplier.objects.filter(
        day_schedules__day=weekday,
        day_schedules__expects_order=True,
        is_active=True
    ).distinct()
    
    operations['suppliers_making_deliveries'] = Supplier.objects.filter(
        day_schedules__day=weekday,
        day_schedules__makes_delivery=True,
        is_active=True,
        delivery_blocked=False
    ).distinct()
    
    # Customers  
    operations['customers_placing_orders'] = Customer.objects.filter(
        day_schedules__day=weekday,
        day_schedules__expects_order=True,
        is_active=True,
        sales_blocked=False
    ).distinct()
    
    operations['customers_expecting_deliveries'] = Customer.objects.filter(
        day_schedules__day=weekday,
        day_schedules__expects_delivery=True,
        is_active=True
    ).distinct()
    
    return operations
```

---

## API Reference

### CustomerService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `get_dashboard_data(customer_id)` | Complete customer overview | Result | customer_id |
| `get_financial_data(customer)` | Credit and payment analysis | Result | customer |
| `get_sites_data(customer)` | All customer locations | Result | customer |
| `get_schedule_data(customer)` | Weekly schedule | Result | customer |
| `get_statistics_data(customer)` | Purchase analytics | Result | customer, period |
| `validate_customer_operation(customer, amount)` | Sales validation | Result | customer, amount |

### SupplierService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `get_dashboard_data(supplier_id)` | Complete supplier overview | Result | supplier_id |
| `get_divisions_data(supplier)` | Active divisions | Result | supplier |
| `get_financial_data(supplier)` | Credit and payment analysis | Result | supplier |
| `get_delivery_data(supplier, ...)` | Delivery history | Result | supplier, date_range, limit |
| `get_statistics_data(supplier)` | Purchase volume analytics | Result | supplier, period |
| `validate_supplier_operation(supplier, amount)` | Purchase validation | Result | supplier, amount |

### Result Data Structures

**Customer Dashboard:**
```python
{
    'basic_info': {
        'id': 42,
        'name': 'ACME Corporation',
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
        'credit_limit': Decimal('10000.00'),
        'used_credit': Decimal('2500.00'),
        'available_credit': Decimal('7500.00'),
        'payment_delay_days': 30,
        'total_orders_amount': Decimal('25000.00'),
        'unpaid_amount': Decimal('2500.00')
    },
    'sites': [
        {
            'id': 1,
            'name': 'Headquarters',
            'city': 'Sofia',
            'address': 'Business Park, Building A',
            'is_primary': True,
            'is_delivery_address': True
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
        'name': 'Premium Distributor Ltd',
        'code': 'DIST001',
        'contact_person': 'Ivan Petrov',
        'is_active': True,
        'delivery_blocked': False,
        'can_deliver': True
    },
    'divisions': [
        {
            'id': 5,
            'name': 'Foods Division',
            'code': 'FOODS',
            'contact_person': 'Maria Petrova',
            'payment_days': 30
        }
    ],
    'financial': {
        'credit_limit': Decimal('50000.00'),
        'used_credit': Decimal('15000.00'),
        'available_credit': Decimal('35000.00'),
        'payment_days': 45,
        'total_orders_amount': Decimal('125000.00'),
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

## Error Handling

### Common Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `CUSTOMER_NOT_FOUND` | Customer ID not found | Verify customer exists |
| `SUPPLIER_NOT_FOUND` | Supplier ID not found | Verify supplier exists |
| `CUSTOMER_BLOCKED` | Customer sales blocked | Check customer status |
| `SUPPLIER_INACTIVE` | Supplier not active | Activate supplier |
| `DELIVERY_BLOCKED` | Supplier delivery blocked | Check delivery settings |
| `CREDIT_LIMIT_EXCEEDED` | Amount exceeds credit | Increase limit or reduce amount |
| `CREDIT_BLOCKED` | Customer credit blocked | Enable credit or use cash |

### Error Response Pattern

```python
if not result.ok:
    error_data = {
        'code': result.code,
        'message': result.msg,
        'details': result.data,
        'timestamp': timezone.now()
    }
    
    if result.code == 'CREDIT_LIMIT_EXCEEDED':
        available = result.data['available_credit']
        requested = result.data['requested_amount']
        suggest_amount = min(available, requested * 0.8)
        
        error_data['suggestions'] = [
            f'Maximum allowed amount: {available}',
            f'Suggested amount: {suggest_amount}'
        ]
```

---

## Performance Considerations

### 1. **Efficient Queries**

```python
# Use manager methods for common queries
customers = Customer.objects.active().companies()
suppliers = Supplier.objects.filter(is_active=True, delivery_blocked=False)

# Prefetch related data
customer = Customer.objects.select_related('price_group').prefetch_related(
    'sites', 'day_schedules'
).get(id=customer_id)

# Optimized schedule queries
today_suppliers = Supplier.objects.filter(
    day_schedules__day='mon',
    day_schedules__makes_delivery=True
).distinct()
```

### 2. **Dashboard Performance**

```python
# Batch service calls for dashboard
def get_dashboard_data(customer_id):
    customer = Customer.objects.select_related('price_group').prefetch_related(
        'sites', 'day_schedules'
    ).get(id=customer_id)
    
    # Run all data gathering in parallel
    basic_info = extract_basic_info(customer)
    financial_data = get_financial_data_optimized(customer)
    sites_data = extract_sites_data(customer)  # Already prefetched
    schedule_data = extract_schedule_data(customer)  # Already prefetched
    
    return combine_dashboard_data(basic_info, financial_data, sites_data, schedule_data)
```

### 3. **Caching Strategy**

```python
from django.core.cache import cache

def get_customer_dashboard_cached(customer_id):
    cache_key = f"customer_dashboard:{customer_id}"
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        result = CustomerService.get_dashboard_data(customer_id)
        if result.ok:
            cache.set(cache_key, result.data, timeout=600)  # 10 minutes
            return result
    
    return Result.success(data=cached_data)

# Invalidate cache on customer changes
def customer_post_save(sender, instance, **kwargs):
    cache_key = f"customer_dashboard:{instance.id}"
    cache.delete(cache_key)
```

---

## Best Practices

### 1. **Always Use Result Pattern**

```python
# ✅ Good
result = CustomerService.get_dashboard_data(customer_id)
if result.ok:
    dashboard = result.data
    financial = dashboard['financial']
else:
    handle_error(result.code, result.msg)

# ❌ Avoid direct model access for complex operations
try:
    customer = Customer.objects.get(id=customer_id)
    # Manual dashboard building - missing error handling, consistency
except Customer.DoesNotExist:
    pass
```

### 2. **Validate Business Operations**

```python
# ✅ Good - validate before processing
validation = CustomerService.validate_customer_operation(customer, amount)
if validation.ok:
    proceed_with_sale(customer, amount)
else:
    return validation

# ❌ Avoid skipping validation
if customer.is_active:  # Incomplete validation
    proceed_with_sale(customer, amount)
```

### 3. **Use Appropriate Manager Methods**

```python
# ✅ Good - use semantic manager methods
active_customers = Customer.objects.active()
vip_customers = Customer.objects.filter(category=Customer.CATEGORY_VIP)
credit_customers = Customer.objects.with_credit()

# ❌ Avoid raw filtering everywhere
customers = Customer.objects.filter(is_active=True, sales_blocked=False)
```

### 4. **Handle Sites Properly**

```python
# ✅ Good - get appropriate site
delivery_site = customer.sites.filter(is_delivery_address=True).first()
if not delivery_site:
    delivery_site = customer.sites.filter(is_primary=True).first()

billing_site = customer.sites.filter(is_billing_address=True).first()
if not billing_site:
    billing_site = customer.sites.filter(is_primary=True).first()

# ❌ Avoid assuming sites exist
delivery_address = customer.sites.first().address  # May fail
```

### 5. **Schedule-Aware Operations**

```python
# ✅ Good - respect partner schedules
def can_place_order_today(supplier):
    today = timezone.now().strftime('%a').lower()[:3]
    schedule = supplier.day_schedules.filter(
        day=today,
        expects_order=True
    ).first()
    
    if not schedule:
        return False
        
    # Check deadline if specified
    if schedule.order_deadline_time:
        current_time = timezone.now().time()
        return current_time <= schedule.order_deadline_time
    
    return True

# ✅ Good - plan deliveries based on schedules
def get_next_delivery_date(supplier):
    today = timezone.now().date()
    for i in range(7):  # Check next 7 days
        check_date = today + timedelta(days=i)
        weekday = check_date.strftime('%a').lower()[:3]
        
        if supplier.day_schedules.filter(
            day=weekday,
            makes_delivery=True
        ).exists():
            return check_date
    
    return None  # No delivery days
```

---

## Dependencies

**PARTNERS app depends on:**
- Django framework
- CORE app (Result pattern)
- NOMENCLATURES app (PriceGroup model)

**Other apps depend on PARTNERS:**
- PURCHASES (Supplier model)
- SALES (Customer model)  
- PRICING (customer group pricing)
- REPORTS (partner analytics)

---

## Version History

- **v1.0** - Basic customer and supplier models
- **v1.1** - Added multi-site support for customers
- **v1.2** - Added supplier divisions  
- **v1.3** - Added weekly schedules
- **v1.4** - Enhanced credit management
- **v1.5** - Added customer categories and VIP status
- **v2.0** - Result pattern service refactoring
- **v2.1** - Enhanced dashboard and analytics

---

*Last Updated: 2025-08-29*  
*Version: 2.1*