# PRICING App Documentation

## 🎯 Overview

The **PRICING app** provides sophisticated pricing management for OptimaPOS, supporting multiple pricing strategies, customer groups, promotional pricing, bulk discounts, and packaging-specific pricing. It integrates with inventory for cost-based pricing and supports barcode-based pricing lookups.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Pricing Models](#pricing-models)
3. [Pricing Service](#pricing-service)  
4. [Pricing Strategies](#pricing-strategies)
5. [Integration Points](#integration-points)
6. [Usage Patterns](#usage-patterns)
7. [API Reference](#api-reference)
8. [Best Practices](#best-practices)

---

## Architecture

```
PRICING App Structure:
├── models/
│   ├── base_prices.py        # ProductPrice (base prices)
│   ├── group_prices.py       # ProductPriceByGroup (customer groups)
│   ├── step_prices.py        # ProductStepPrice (bulk discounts)
│   ├── promotions.py         # PromotionalPrice (time-based offers)
│   └── packaging_prices.py   # PackagingPrice (alternate units)
├── services/
│   ├── pricing_service.py    # Main pricing logic  
│   └── promotion_service.py  # Promotional campaign management
├── admin/
│   ├── prices.py            # Base price administration
│   ├── promotions.py        # Promotion management
│   └── packaging.py         # Packaging price setup
└── views.py                 # API endpoints
```

### Design Philosophy

- **🎯 Flexible Pricing** - Multiple pricing strategies for different scenarios
- **📊 Priority-Based** - Clear hierarchy: Promotions → Groups → Step → Base → Fallback
- **💰 Profit-Aware** - Automatic cost integration for profit calculations
- **⚡ Location-Based** - Different pricing per location/warehouse
- **🔄 Real-Time** - Dynamic pricing with instant calculations
- **📦 Packaging Support** - Different prices for different packaging units

---

## Pricing Models

### 1. **ProductPrice** (Base Pricing)

**Purpose**: Foundation pricing for products at specific locations

```python
# Pricing Methods
pricing_method = [
    'FIXED',    # Fixed price (uses base_price)
    'MARKUP',   # Cost + markup % (uses markup_percentage)  
    'AUTO'      # Location default markup
]

# Key Fields
base_price = Decimal()           # Fixed selling price
markup_percentage = Decimal()    # Markup over cost
effective_price = Decimal()      # Calculated final price (auto-updated)

# Generic Location Support
content_type = ForeignKey(ContentType)  # Supports any ILocation
object_id = PositiveIntegerField()
priceable_location = GenericForeignKey()
```

**Location Flexibility:**
```python
# Works with any ILocation implementation
warehouse_price = ProductPrice.objects.create_for_location(
    location=warehouse,           # InventoryLocation
    product=product,
    pricing_method='FIXED',
    base_price=Decimal('15.99')
)

online_price = ProductPrice.objects.create_for_location(
    location=online_store,        # OnlineStore  
    product=product,
    pricing_method='MARKUP',
    markup_percentage=Decimal('35.00')
)
```

### 2. **ProductPriceByGroup** (Customer Group Pricing)

**Purpose**: Special pricing for customer segments

```python
# Customer segmentation pricing
customer_group = ForeignKey('partners.CustomerGroup')
price = Decimal()               # Group-specific price
min_quantity = Decimal()        # Optional minimum quantity

# Generic location support
content_type = ForeignKey(ContentType)
object_id = PositiveIntegerField()
```

**Example Use Cases:**
- Wholesale customers get lower prices
- VIP customers get premium discounts
- Corporate contracts with negotiated rates

### 3. **ProductStepPrice** (Bulk Discounts)

**Purpose**: Quantity-based pricing tiers

```python
# Bulk pricing tiers
min_quantity = Decimal()        # Minimum quantity for this price
price = Decimal()               # Price for this quantity tier

# Example: 
# 1-10 units:  $15.99 each
# 11-50 units: $14.50 each  
# 51+ units:   $13.25 each
```

### 4. **PromotionalPrice** (Time-Based Offers)

**Purpose**: Temporary promotional pricing

```python
# Promotion details
name = CharField()              # "Black Friday Sale"
promotional_price = Decimal()   # Special offer price
start_date = DateField()
end_date = DateField()

# Optional constraints
min_quantity = Decimal()        # Minimum purchase quantity
customer_groups = ManyToMany()  # Limit to specific groups
max_uses_per_customer = Integer() # Usage limits
```

### 5. **PackagingPrice** (Alternative Units)

**Purpose**: Pricing for different packaging/unit combinations

```python
# Packaging-specific pricing
packaging = ForeignKey('products.ProductPackaging')
price = Decimal()               # Price for this packaging
unit_price = Decimal()          # Calculated per base unit

# Example:
# Product: Widget (base unit: piece)
# - Single piece:  $2.50
# - Box of 12:     $28.00 ($2.33 per piece) 
# - Case of 144:   $320.00 ($2.22 per piece)
```

---

## Pricing Service

### Primary API (Result Pattern)

```python
from pricing.services import PricingService

# Get comprehensive pricing
result = PricingService.get_product_pricing(
    location=warehouse,
    product=product,
    customer=customer,           # For group pricing
    quantity=Decimal('25'),      # For step pricing
    date=datetime.now().date()   # For promotions
)

if result.ok:
    pricing_data = result.data
    final_price = pricing_data['final_price']
    pricing_rule = pricing_data['pricing_rule']  # Which rule applied
    profit_metrics = pricing_data['profit_metrics']
```

### Pricing Analysis

```python
# Detailed pricing breakdown
analysis_result = PricingService.get_pricing_analysis(
    location=warehouse,
    product=product,
    customer=customer,
    quantity=Decimal('50')
)

if analysis_result.ok:
    analysis = analysis_result.data
    
    # All pricing components
    pricing_summary = analysis['pricing_summary']
    discount_analysis = analysis['discount_analysis'] 
    price_comparison = analysis['price_comparison']
    recommendations = analysis['recommendations']
```

### Barcode Pricing

```python
# Pricing by barcode (product or packaging)
barcode_result = PricingService.get_barcode_pricing(
    barcode='1234567890123',
    location=warehouse,
    customer=customer
)

if barcode_result.ok:
    barcode_data = barcode_result.data
    price = barcode_data['price']
    pricing_type = barcode_data['pricing_type']  # 'PRODUCT' or 'PACKAGING'
    
    if barcode_data['packaging']:
        unit_price = barcode_data['unit_price']
        conversion_factor = barcode_data['packaging']['conversion_factor']
```

---

## Pricing Strategies

### 1. **Priority Order (Automatic Selection)**

The system automatically selects the best applicable price using this priority:

1. **🎯 Promotions** (highest priority)
2. **👥 Customer Group Prices**  
3. **📦 Step Prices** (quantity-based)
4. **💰 Base Price**
5. **🔄 Fallback Price** (cost + location markup)

```python
# Pricing decision flow
def _determine_final_price(base, promo, group, step, fallback):
    if promo and promo > 0:
        return promo, 'PROMOTION'
    elif group and group > 0:
        return group, 'CUSTOMER_GROUP'  
    elif step and step > 0:
        return step, 'STEP_PRICE'
    elif base and base > 0:
        return base, 'BASE_PRICE'
    else:
        return fallback, 'FALLBACK'
```

### 2. **Cost-Based Pricing Methods**

```python
# Fixed Price
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product,
    pricing_method='FIXED',
    base_price=Decimal('19.99')
)

# Markup-Based  
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product, 
    pricing_method='MARKUP',
    markup_percentage=Decimal('40.00')  # 40% markup over cost
)

# Auto (uses location's default markup)
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=product,
    pricing_method='AUTO'  # Uses warehouse.default_markup_percentage
)
```

### 3. **Dynamic Price Calculation**

```python
def calculate_effective_price(self):
    if self.pricing_method == 'FIXED':
        self.effective_price = self.base_price
        
    elif self.pricing_method == 'MARKUP':
        cost_price = self.get_current_cost_price()  # From inventory
        self.effective_price = cost_price * (1 + self.markup_percentage / 100)
        
    elif self.pricing_method == 'AUTO':
        cost_price = self.get_current_cost_price()
        location_markup = self.priceable_location.default_markup_percentage
        self.effective_price = cost_price * (1 + location_markup / 100)
```

---

## Integration Points

### **With INVENTORY App:**

```python
# Cost price integration
def get_current_cost_price(self):
    """Get cost from inventory for markup calculations"""
    try:
        from inventory.models import InventoryItem
        item = InventoryItem.objects.get(
            location=self.priceable_location,
            product=self.product
        )
        return item.avg_cost
    except InventoryItem.DoesNotExist:
        return self.product.weighted_avg_cost or Decimal('0')
```

**Automatic Price Updates:**
- When inventory cost changes significantly (>5%), pricing service is notified
- Markup-based prices are automatically recalculated
- Price change history is maintained

### **With PRODUCTS App:**

```python
# Product packaging integration
def get_packaging_price(product, packaging):
    """Get price for specific packaging"""
    try:
        pkg_price = PackagingPrice.objects.get(
            product=product,
            packaging=packaging,
            is_active=True
        )
        return pkg_price.price
    except PackagingPrice.DoesNotExist:
        # Calculate from base price
        base_price_result = PricingService.get_product_pricing(location, product)
        unit_price = base_price_result.data['final_price']
        return unit_price * packaging.conversion_factor
```

### **With PARTNERS App:**

```python
# Customer group pricing
def get_customer_pricing(customer):
    """Get customer-specific pricing"""
    if customer and hasattr(customer, 'price_group'):
        group_price = ProductPriceByGroup.objects.for_location(location).filter(
            product=product,
            customer_group=customer.price_group,
            is_active=True
        ).first()
        
        if group_price:
            return group_price.price
    
    return None  # Fall back to other pricing rules
```

### **With SALES App:**

```python
# Point of sale integration
def calculate_order_line_pricing(order_line):
    """Calculate pricing for sales order line"""
    pricing_result = PricingService.get_product_pricing(
        location=order_line.order.location,
        product=order_line.product,
        customer=order_line.order.customer,
        quantity=order_line.quantity
    )
    
    if pricing_result.ok:
        order_line.unit_price = pricing_result.data['final_price']
        order_line.cost_price = pricing_result.data['cost_price'] 
        order_line.profit_amount = pricing_result.data['profit_metrics']['profit_amount']
```

---

## Usage Patterns

### 1. **Setup Base Pricing**

```python
# Set up basic product pricing
from pricing.models import ProductPrice

# Fixed pricing for retail location
ProductPrice.objects.create_for_location(
    location=retail_store,
    product=widget,
    pricing_method='FIXED',
    base_price=Decimal('24.99')
)

# Markup pricing for wholesale location  
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=widget,
    pricing_method='MARKUP',
    markup_percentage=Decimal('25.00')  # 25% over cost
)
```

### 2. **Customer Group Discounts**

```python
# Set up customer group pricing
from pricing.models import ProductPriceByGroup

# Wholesale customers get 15% discount
wholesale_group = CustomerGroup.objects.get(name='Wholesale')
ProductPriceByGroup.objects.create_for_location(
    location=warehouse,
    product=widget,
    customer_group=wholesale_group,
    price=Decimal('21.24'),  # 15% off base price
    min_quantity=Decimal('10')
)
```

### 3. **Bulk Pricing Tiers**

```python
# Set up quantity-based discounts
from pricing.models import ProductStepPrice

# Bulk discount tiers
ProductStepPrice.objects.create_for_location(
    location=warehouse,
    product=widget,
    min_quantity=Decimal('1'),
    price=Decimal('24.99')     # 1-9 units
)

ProductStepPrice.objects.create_for_location(
    location=warehouse,
    product=widget, 
    min_quantity=Decimal('10'),
    price=Decimal('22.49')     # 10-49 units
)

ProductStepPrice.objects.create_for_location(
    location=warehouse,
    product=widget,
    min_quantity=Decimal('50'),
    price=Decimal('19.99')     # 50+ units
)
```

### 4. **Promotional Campaigns**

```python
# Set up time-limited promotion
from pricing.models import PromotionalPrice

# Black Friday sale
PromotionalPrice.objects.create_for_location(
    location=retail_store,
    product=widget,
    name='Black Friday Special',
    promotional_price=Decimal('19.99'),
    start_date=datetime.date(2024, 11, 29),
    end_date=datetime.date(2024, 12, 2),
    min_quantity=Decimal('2'),  # Buy 2 or more
    max_uses_per_customer=5
)
```

### 5. **Packaging Pricing**

```python
# Set up packaging-specific pricing
from pricing.models import PackagingPrice

# Individual unit pricing
base_packaging = ProductPackaging.objects.get(
    product=widget,
    unit__code='EA'  # Each
)

# Box pricing (12 units per box)
box_packaging = ProductPackaging.objects.get(
    product=widget,
    unit__code='BOX'
)

PackagingPrice.objects.create_for_location(
    location=warehouse,
    product=widget,
    packaging=box_packaging,
    price=Decimal('275.00')  # $22.92 per unit vs $24.99 individual
)
```

---

## API Reference

### PricingService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `get_product_pricing()` | Complete pricing calculation | Result | location, product, customer, quantity, date |
| `get_pricing_analysis()` | Detailed pricing breakdown | Result | location, product, customer, quantity |
| `get_all_pricing_options()` | All available pricing rules | Result | location, product, customer |
| `validate_pricing_setup()` | Validate price configuration | Result | location, product |
| `get_barcode_pricing()` | Pricing by barcode lookup | Result | barcode, location, customer |

### Result Data Structures

**Complete Pricing Result:**
```python
{
    'final_price': Decimal('21.24'),
    'pricing_rule': 'CUSTOMER_GROUP',
    'base_price': Decimal('24.99'),
    'promotional_price': None,
    'group_price': Decimal('21.24'),
    'step_price': None,
    'fallback_price': Decimal('18.75'),
    'cost_price': Decimal('15.00'),
    'quantity': Decimal('10'),
    'location_code': 'WH01',
    'product_code': 'WIDGET123',
    'customer_info': {
        'customer_id': 42,
        'price_group': 'Wholesale'
    },
    'profit_metrics': {
        'profit_amount': Decimal('6.24'),
        'markup_percentage': Decimal('41.60'),
        'margin_percentage': Decimal('29.38'),
        'cost_valid': True
    }
}
```

**Pricing Analysis Result:**
```python
{
    'pricing_summary': { /* Complete pricing data above */ },
    'all_pricing_options': {
        'base_price': Decimal('24.99'),
        'step_prices': [
            {'min_quantity': 10, 'price': Decimal('22.49'), 'savings_vs_base': Decimal('2.50')},
            {'min_quantity': 50, 'price': Decimal('19.99'), 'savings_vs_base': Decimal('5.00')}
        ],
        'group_prices': [
            {'group_name': 'Wholesale', 'price': Decimal('21.24'), 'savings_vs_base': Decimal('3.75')}
        ],
        'promotions': [
            {'name': 'Flash Sale', 'price': Decimal('18.99'), 'end_date': '2024-12-31'}
        ]
    },
    'discount_analysis': {
        'customer_discount': Decimal('3.75'),
        'discount_percentage': Decimal('15.00'),
        'savings_amount': Decimal('37.50')  # For quantity 10
    },
    'price_comparison': {
        'cheapest_available': Decimal('18.99'),
        'most_expensive': Decimal('24.99')
    },
    'recommendations': [
        'Consider setting up promotional pricing for special offers'
    ]
}
```

**Barcode Pricing Result:**
```python
# Product barcode
{
    'barcode': '1234567890123',
    'product': {'code': 'WIDGET123', 'name': 'Premium Widget'},
    'packaging': None,
    'price': Decimal('24.99'),
    'unit_price': Decimal('24.99'),
    'quantity_represented': Decimal('1'),
    'pricing_type': 'PRODUCT'
}

# Packaging barcode  
{
    'barcode': '9876543210987',
    'product': {'code': 'WIDGET123', 'name': 'Premium Widget'},
    'packaging': {
        'display_name': 'Box (x12)',
        'unit_code': 'BOX',
        'conversion_factor': Decimal('12')
    },
    'price': Decimal('275.00'),
    'unit_price': Decimal('22.92'),  # Per individual unit
    'quantity_represented': Decimal('12'),
    'pricing_type': 'PACKAGING'
}
```

---

## Error Handling

### Common Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `PRICING_SETUP_INVALID` | No valid pricing configuration | Set up base price |
| `BARCODE_NOT_FOUND` | Barcode not in system | Verify barcode or create product |
| `INVALID_QUANTITY` | Quantity <= 0 | Use positive quantity |
| `LOCATION_NOT_SUPPORTED` | Location doesn't implement ILocation | Check location interface |
| `COST_UNAVAILABLE` | No cost data for markup pricing | Initialize inventory |

### Validation API

```python
# Validate pricing setup before using
validation_result = PricingService.validate_pricing_setup(
    location=warehouse,
    product=product
)

if not validation_result.ok:
    issues = validation_result.data['pricing_issues']
    recommendations = validation_result.data['recommendations']
    
    # Handle setup problems
    for issue in issues:
        logger.warning(f"Pricing issue: {issue}")
    
    for rec in recommendations:
        logger.info(f"Recommendation: {rec}")
```

---

## Performance Considerations

### 1. **Efficient Queries**

```python
# Use manager methods for optimized queries
ProductPrice.objects.for_location(warehouse).for_product(product)

# Prefetch related data
prices = ProductPrice.objects.for_location(warehouse).select_related(
    'product', 'content_type'
).prefetch_related('product__packaging_set')
```

### 2. **Caching Strategy**

```python
# Cache frequently accessed pricing data
from django.core.cache import cache

def get_cached_pricing(location_id, product_id, customer_id=None):
    cache_key = f"pricing:{location_id}:{product_id}:{customer_id}"
    cached_result = cache.get(cache_key)
    
    if cached_result is None:
        result = PricingService.get_product_pricing(...)
        if result.ok:
            cache.set(cache_key, result.data, timeout=300)  # 5 minutes
            return result
    
    return Result.success(data=cached_result)
```

### 3. **Bulk Operations**

```python
# Bulk pricing setup
bulk_prices = []
for product in products:
    bulk_prices.append(ProductPrice(
        content_type=location_content_type,
        object_id=location.id,
        product=product,
        pricing_method='MARKUP',
        markup_percentage=Decimal('30.00')
    ))

ProductPrice.objects.bulk_create(bulk_prices, batch_size=100)
```

---

## Best Practices

### 1. **Always Use Result Pattern**

```python
# ✅ Good
result = PricingService.get_product_pricing(location, product, customer)
if result.ok:
    price = result.data['final_price']
    profit = result.data['profit_metrics']['profit_amount']
else:
    handle_pricing_error(result.code, result.msg)

# ❌ Avoid direct model access for complex pricing
try:
    price = ProductPrice.objects.get(product=product).effective_price
except ProductPrice.DoesNotExist:
    price = Decimal('0')  # Missing group pricing, step pricing, etc.
```

### 2. **Validate Pricing Setup**

```python
# ✅ Good - validate before using
validation = PricingService.validate_pricing_setup(location, product)
if validation.ok:
    pricing_result = PricingService.get_product_pricing(...)
else:
    # Handle configuration issues
    setup_base_pricing(location, product)

# ❌ Avoid assuming pricing exists
pricing_result = PricingService.get_product_pricing(...)  # May return fallback
```

### 3. **Use Appropriate Pricing Method**

```python
# ✅ Good - choose method based on business needs
# High-margin products: Fixed pricing
ProductPrice.objects.create_for_location(
    location=retail_store,
    product=luxury_item,
    pricing_method='FIXED',
    base_price=Decimal('299.99')
)

# Cost-varying products: Markup pricing  
ProductPrice.objects.create_for_location(
    location=warehouse,
    product=commodity_item,
    pricing_method='MARKUP',
    markup_percentage=Decimal('25.00')
)

# ❌ Avoid fixed prices for cost-volatile products
```

### 4. **Consider Customer Experience**

```python
# ✅ Good - provide pricing transparency
analysis_result = PricingService.get_pricing_analysis(location, product, customer)
if analysis_result.ok:
    analysis = analysis_result.data
    customer_discount = analysis['discount_analysis']['customer_discount']
    
    if customer_discount > 0:
        show_savings_message(f"You saved ${customer_discount}!")

# ✅ Good - handle promotions gracefully
pricing_result = PricingService.get_product_pricing(location, product, quantity=qty)
if pricing_result.data['pricing_rule'] == 'PROMOTION':
    promo_name = get_active_promotion_name(product)
    show_promo_message(f"Special offer: {promo_name}")
```

### 5. **Monitor Pricing Health**

```python
# Regular pricing validation
def validate_pricing_health():
    """Validate pricing setup across all products/locations"""
    issues_found = []
    
    for location in InventoryLocation.objects.active():
        for product in Product.objects.active():
            validation = PricingService.validate_pricing_setup(location, product)
            if not validation.ok:
                issues_found.append({
                    'location': location.code,
                    'product': product.code,
                    'issues': validation.data['pricing_issues']
                })
    
    return issues_found
```

---

## Dependencies

**PRICING app depends on:**
- Django framework
- CORE app (Result pattern, ILocation interface)
- PRODUCTS app (Product, ProductPackaging models)
- INVENTORY app (cost price integration)

**Other apps depend on PRICING:**
- SALES (order pricing)
- POS (barcode pricing)
- REPORTS (profit analysis)

---

## Version History

- **v1.0** - Basic fixed pricing
- **v1.1** - Added markup-based pricing  
- **v1.2** - Customer group pricing
- **v1.3** - Step pricing and promotions
- **v1.4** - Generic location support
- **v1.5** - Packaging pricing
- **v2.0** - Result pattern refactoring
- **v2.1** - Enhanced analysis and validation APIs

---

*Last Updated: 2025-08-29*  
*Version: 2.1*