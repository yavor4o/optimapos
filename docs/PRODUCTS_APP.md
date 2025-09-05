# PRODUCTS App Documentation

## 🎯 Overview

The **PRODUCTS app** manages the product catalog in OptimaPOS, providing comprehensive product lifecycle management, packaging configurations, barcode/PLU support, and seamless integration with inventory, pricing, and sales systems. It focuses on static product definitions while delegating dynamic data to specialized apps.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Core Models](#core-models)
3. [Product Lifecycle Management](#product-lifecycle-management)
4. [Packaging System](#packaging-system)
5. [Services](#services)
6. [Integration Points](#integration-points)
7. [Usage Patterns](#usage-patterns)
8. [API Reference](#api-reference)
9. [Best Practices](#best-practices)

---

## Architecture

```
PRODUCTS App Structure:
├── models/
│   ├── products.py         # Product, ProductPLU, ProductLifecycleChoices  
│   └── packaging.py        # ProductPackaging, ProductBarcode
├── services/
│   ├── product_service.py  # Search, lookup, statistics
│   ├── lifecycle_service.py # Lifecycle management
│   └── validation_service.py # Product validation
├── admin.py                # Product administration
└── views.py                # API endpoints
```

### Design Philosophy

- **📊 Static Definition Focus** - Products store static data, dynamic data in other apps
- **🔄 Lifecycle-Driven** - Full product lifecycle from NEW to ARCHIVED  
- **📦 Flexible Packaging** - Multiple units and packaging configurations
- **🏷️ Multi-Identification** - Codes, barcodes, PLU codes for different use cases
- **🔍 Search-Optimized** - Fast product lookup by any identifier
- **⚙️ Integration-Ready** - Clean separation with inventory, pricing, sales
- **✅ Validation-Heavy** - Comprehensive business rule validation

---

## Core Models

### 1. **Product** (Main Product Definition)

**Purpose**: Core product catalog with static definitions and lifecycle management

```python
# Core Identity
code = CharField(unique=True, max_length=50)     # Internal product code
name = CharField(max_length=255)                 # Product name  
description = TextField()                        # Detailed description

# Classification (via NOMENCLATURES)
brand = ForeignKey('nomenclatures.Brand')
product_group = ForeignKey('nomenclatures.ProductGroup')  
product_type = ForeignKey('nomenclatures.ProductType')

# Units & Measurement
base_unit = ForeignKey('nomenclatures.UnitOfMeasure')
unit_type = ['PIECE', 'WEIGHT', 'VOLUME', 'LENGTH']

# Tax Configuration
tax_group = ForeignKey('nomenclatures.TaxGroup')

# Tracking Settings
track_batches = BooleanField()
track_serial_numbers = BooleanField()
requires_expiry_date = BooleanField()

# Lifecycle Management
lifecycle_status = ProductLifecycleChoices
sales_blocked = BooleanField()
purchase_blocked = BooleanField()
allow_negative_sales = BooleanField()
```

**Lifecycle States:**
```python
class ProductLifecycleChoices:
    NEW = 'NEW'                    # New product, not yet active
    ACTIVE = 'ACTIVE'              # Active product, can buy/sell
    PHASE_OUT = 'PHASE_OUT'        # Phasing out, sell only (no purchase)
    DISCONTINUED = 'DISCONTINUED'  # Discontinued, no sales/purchases
    ARCHIVED = 'ARCHIVED'          # Archived, historical only
```

**Dynamic Properties (Integration with INVENTORY):**
```python
@property
def total_stock(self) -> Decimal:
    """Total stock across all locations"""
    return InventoryItem.objects.filter(product=self).aggregate(
        total=Sum('current_qty')
    )['total'] or Decimal('0')

@property
def weighted_avg_cost(self) -> Decimal:
    """Weighted average cost across all locations"""
    # Complex calculation using InventoryItem data

@property
def stock_value(self) -> Decimal:
    """Total stock value across all locations"""
    # current_qty × avg_cost per location
```

### 2. **ProductPackaging** (Alternative Units)

**Purpose**: Define alternative packaging/units for products

```python
# Package Definition
product = ForeignKey(Product)
unit = ForeignKey('nomenclatures.UnitOfMeasure')
conversion_factor = Decimal()                    # How many base units

# Usage Settings
allow_sale = BooleanField()                      # Can sell in this unit
allow_purchase = BooleanField()                  # Can purchase in this unit
is_default_sale_unit = BooleanField()
is_default_purchase_unit = BooleanField()

# Constraints
is_active = BooleanField()

# Example: Widget (base: pieces)
# - Single piece:  conversion_factor = 1
# - Box of 12:     conversion_factor = 12  
# - Case of 144:   conversion_factor = 144
```

**Business Rules:**
```python
def clean(self):
    # PIECE products must have whole number conversions
    if self.product.unit_type == 'PIECE':
        if self.conversion_factor != int(self.conversion_factor):
            raise ValidationError('PIECE products cannot have fractional packaging')
    
    # Only one default per type
    if self.is_default_sale_unit:
        existing = ProductPackaging.objects.filter(
            product=self.product,
            is_default_sale_unit=True
        ).exclude(pk=self.pk)
        if existing.exists():
            raise ValidationError('Only one default sale unit allowed')
```

### 3. **ProductBarcode** (Barcode Management)

**Purpose**: Multiple barcodes per product/packaging combination

```python
# Barcode Definition
barcode = CharField(unique=True)                 # The actual barcode
product = ForeignKey(Product)                    # Related product
packaging = ForeignKey(ProductPackaging, null=True) # Optional packaging

# Priority & Status
is_primary = BooleanField()                      # Main barcode for product
is_active = BooleanField()
priority = IntegerField()                        # Higher = preferred
```

**Barcode Types:**
- **Product Barcodes**: Scan → get product (quantity = 1 base unit)
- **Packaging Barcodes**: Scan → get product + packaging info (quantity = conversion_factor)

### 4. **ProductPLU** (Weight-Based Products)

**Purpose**: PLU codes for scale/weight-based products

```python
# PLU Definition
product = ForeignKey(Product)
plu_code = CharField(max_length=10)              # PLU code (digits)
is_primary = BooleanField()
priority = IntegerField()

# Validation
def clean(self):
    # Only for weight-based products
    if self.product.unit_type != Product.WEIGHT:
        raise ValidationError('PLU codes only for weight-based products')
```

---

## Product Lifecycle Management

### Lifecycle States & Transitions

```python
# State Definitions
ProductLifecycleChoices = [
    ('NEW', 'New Product'),           # → ACTIVE
    ('ACTIVE', 'Active'),             # → PHASE_OUT, DISCONTINUED  
    ('PHASE_OUT', 'Phasing Out'),     # → DISCONTINUED, ACTIVE
    ('DISCONTINUED', 'Discontinued'), # → ARCHIVED
    ('ARCHIVED', 'Archived')          # Final state
]

# Business Rules by State
def is_sellable(self) -> bool:
    return (self.lifecycle_status in ['ACTIVE', 'PHASE_OUT'] and 
            not self.sales_blocked)

def is_purchasable(self) -> bool:
    return (self.lifecycle_status in ['NEW', 'ACTIVE'] and 
            not self.purchase_blocked)
```

### Manager Methods (Lifecycle-Aware)

```python
class ProductManager:
    def active(self):
        """Products in active use"""
        return self.filter(lifecycle_status__in=['NEW', 'ACTIVE'])
    
    def sellable(self):
        """Products that can be sold"""
        return self.filter(
            lifecycle_status__in=['ACTIVE', 'PHASE_OUT'],
            sales_blocked=False
        )
    
    def purchasable(self):
        """Products that can be purchased"""
        return self.filter(
            lifecycle_status__in=['NEW', 'ACTIVE'],
            purchase_blocked=False
        )
```

### Lifecycle Automation

```python
# Get products needing attention
def get_products_needing_attention():
    attention_needed = {
        'phase_out_with_stock': [],      # Should sell out inventory
        'discontinued_with_stock': [],   # Should clear remaining stock
        'blocked_sales': [],             # Check why blocked
        'blocked_purchases': []          # Check why blocked
    }
    
    # Find phase-out products with inventory
    for product in Product.objects.filter(lifecycle_status='PHASE_OUT'):
        if product.total_stock > 0:
            attention_needed['phase_out_with_stock'].append({
                'product': product,
                'stock': product.total_stock,
                'value': product.stock_value
            })
```

---

## Packaging System

### Unit Conversion Engine

```python
def get_conversion_factor(product, from_unit, to_unit):
    """Get conversion factor between any two units"""
    
    # Same unit
    if from_unit == to_unit:
        return Decimal('1.0')
    
    # Base unit conversions
    if from_unit == product.base_unit:
        packaging = ProductPackaging.objects.get(
            product=product, unit=to_unit
        )
        return Decimal('1.0') / packaging.conversion_factor
    
    if to_unit == product.base_unit:
        packaging = ProductPackaging.objects.get(
            product=product, unit=from_unit
        )
        return packaging.conversion_factor
    
    # Package-to-package conversion
    from_pkg = ProductPackaging.objects.get(product=product, unit=from_unit)
    to_pkg = ProductPackaging.objects.get(product=product, unit=to_unit)
    
    return from_pkg.conversion_factor / to_pkg.conversion_factor

# Usage
conversion = get_conversion_factor(widget, box_unit, piece_unit)
pieces = box_quantity * conversion  # Convert boxes to pieces
```

### Packaging Validation

```python
def validate_packaging_configuration(self):
    """Comprehensive packaging validation"""
    issues = []
    
    # PIECE product validation
    if self.unit_type == 'PIECE':
        for packaging in self.packagings.filter(is_active=True):
            if packaging.conversion_factor != int(packaging.conversion_factor):
                issues.append(
                    f"PIECE product has fractional packaging: "
                    f"{packaging.conversion_factor} {packaging.unit.name}"
                )
    
    # Default unit validation
    sale_defaults = self.packagings.filter(is_default_sale_unit=True).count()
    if sale_defaults > 1:
        issues.append("Multiple default sale units defined")
    
    return len(issues) == 0, issues
```

### Packaging Consistency Analysis

```python
def get_packaging_consistency_report(self):
    """Detailed packaging analysis"""
    packagings = self.packagings.filter(is_active=True)
    
    report = {
        'is_consistent': True,
        'conversion_matrix': {},
        'issues': [],
        'recommendations': []
    }
    
    # Build conversion matrix
    for pkg1 in packagings:
        report['conversion_matrix'][pkg1.unit.name] = {}
        for pkg2 in packagings:
            if pkg1 != pkg2:
                ratio = pkg1.conversion_factor / pkg2.conversion_factor
                report['conversion_matrix'][pkg1.unit.name][pkg2.unit.name] = {
                    'ratio': ratio,
                    'is_whole': ratio == int(ratio),
                    'problematic': (self.unit_type == 'PIECE' and 
                                   ratio != int(ratio))
                }
    
    # Generate recommendations based on issues found
    if not report['is_consistent']:
        report['recommendations'].append(
            'Use whole number conversion factors for PIECE products'
        )
```

---

## Services

### 1. **ProductService** - Core Product Operations

```python
from products.services import ProductService

# Product Search & Lookup
product = ProductService.get_product('WIDGET001')           # By code
product = ProductService.find_by_barcode('1234567890123')  # By barcode  
products = ProductService.find_by_plu('4011')             # By PLU
results = ProductService.search_products('widget', limit=20)

# Lifecycle-Aware Queries
sellable = ProductService.get_sellable_products(location=warehouse)
purchasable = ProductService.get_purchasable_products(supplier=supplier)
phase_out = ProductService.get_products_by_lifecycle('PHASE_OUT')

# Unit Conversions
factor = ProductService.get_conversion_factor(product, box_unit, piece_unit)
pieces = ProductService.convert_quantity(product, 5, box_unit, piece_unit)
units = ProductService.get_available_units(product)

# Product Creation (Enterprise Pattern)
result = ProductService.create_product_with_inventory({
    'code': 'WIDGET001',
    'name': 'Premium Widget',
    'base_unit': piece_unit,
    'tax_group': standard_tax,
    'unit_type': 'PIECE'
})

if result.ok:
    product_data = result.data
    product_id = product_data['product']['id']
    inventory_items = product_data['inventory_items_created']
```

### 2. **LifecycleService** - Product Lifecycle Management

```python
from products.services import LifecycleService

# Lifecycle Transitions
result = LifecycleService.transition_to_phase_out(product, reason="Low demand")
result = LifecycleService.transition_to_discontinued(product, reason="EOL")
result = LifecycleService.archive_product(product)

# Bulk Operations
result = LifecycleService.bulk_update_lifecycle(
    product_ids=[1, 2, 3],
    new_status='PHASE_OUT'
)

# Analysis
attention = LifecycleService.get_products_needing_attention()
phase_out_with_stock = attention['phase_out_with_stock']
```

### 3. **ValidationService** - Product Validation

```python
from products.services import ValidationService

# Product Data Validation
result = ValidationService.validate_product_data({
    'code': 'WIDGET001',
    'name': 'Premium Widget',
    'unit_type': 'PIECE'
})

# Packaging Validation
valid, issues = ValidationService.validate_packaging_configuration(product)
consistency = ValidationService.get_packaging_consistency_report(product)

# Sale Quantity Validation
valid, message = ValidationService.validate_sale_quantity(
    product=product,
    quantity=Decimal('2.5'),
    location=warehouse
)
```

---

## Integration Points

### **With NOMENCLATURES App:**

```python
# Product classification via nomenclatures
class Product:
    brand = ForeignKey('nomenclatures.Brand')
    product_group = ForeignKey('nomenclatures.ProductGroup')
    product_type = ForeignKey('nomenclatures.ProductType')
    base_unit = ForeignKey('nomenclatures.UnitOfMeasure')
    tax_group = ForeignKey('nomenclatures.TaxGroup')

# Usage in product creation
product = Product.objects.create(
    code='WIDGET001',
    name='Premium Widget',
    brand=Brand.objects.get(name='ACME'),
    product_group=ProductGroup.objects.get(name='Widgets'),
    base_unit=UnitOfMeasure.objects.get(code='PC'),
    tax_group=TaxGroup.objects.get(code='STANDARD')
)
```

### **With INVENTORY App:**

```python
# Dynamic stock data from inventory
@property
def total_stock(self):
    """Total stock across all locations"""
    from inventory.models import InventoryItem
    return InventoryItem.objects.filter(product=self).aggregate(
        total=Sum('current_qty')
    )['total'] or Decimal('0')

# Product creation automatically creates inventory items
def create_product_with_inventory(product_data):
    # 1. Create product
    product = Product.objects.create(**product_data)
    
    # 2. Create InventoryItem for each active location
    for location in InventoryLocation.objects.filter(is_active=True):
        InventoryItem.objects.create(
            product=product,
            location=location,
            current_qty=Decimal('0'),
            avg_cost=Decimal('0')
        )
```

### **With PRICING App:**

```python
# Pricing integration via generic location support
def get_product_pricing(location, product):
    """Pricing automatically works with product data"""
    
    # Check if product is sellable
    if not product.is_sellable:
        return Result.error('PRODUCT_NOT_SELLABLE', 'Product cannot be sold')
    
    # Get pricing (pricing app handles the rest)
    return PricingService.get_product_pricing(location, product)

# Unit validation for pricing
def validate_pricing_unit(product, unit):
    """Ensure unit is valid for this product"""
    return product.is_unit_compatible(unit)
```

### **With SALES App:**

```python
# Sales integration with lifecycle validation
def validate_sale_line(order_line):
    """Validate product can be sold"""
    product = order_line.product
    
    # Lifecycle check
    if not product.is_sellable:
        return Result.error(
            'PRODUCT_NOT_SELLABLE',
            f'Product {product.code} is {product.get_lifecycle_status_display()}'
        )
    
    # Quantity validation
    valid, message = product.validate_sale_quantity(
        quantity=order_line.quantity,
        location=order_line.location
    )
    
    if not valid:
        return Result.error('INVALID_QUANTITY', message)
    
    return Result.success()
```

### **With PURCHASES App:**

```python
# Purchase validation with lifecycle
def validate_purchase_line(order_line):
    """Validate product can be purchased"""
    product = order_line.product
    
    if not product.is_purchasable:
        return Result.error(
            'PRODUCT_NOT_PURCHASABLE',
            f'Product {product.code} purchase is blocked'
        )
    
    # Unit compatibility check
    if not product.is_unit_compatible(order_line.unit):
        return Result.error(
            'INVALID_UNIT',
            f'Unit {order_line.unit} not valid for {product.code}'
        )
    
    return Result.success()
```

---

## Usage Patterns

### 1. **Product Creation with Full Setup**

```python
def create_complete_product():
    """Enterprise-grade product creation"""
    
    # Step 1: Prepare product data
    product_data = {
        'code': 'WIDGET001',
        'name': 'Premium Widget',
        'description': 'High-quality widget for professional use',
        'brand': Brand.objects.get(name='ACME'),
        'product_group': ProductGroup.objects.get(name='Widgets'),
        'base_unit': UnitOfMeasure.objects.get(code='PC'),
        'tax_group': TaxGroup.objects.get(code='STANDARD'),
        'unit_type': 'PIECE',
        'lifecycle_status': 'ACTIVE',
        'track_batches': False
    }
    
    # Step 2: Create product with inventory
    result = ProductService.create_product_with_inventory(product_data)
    
    if not result.ok:
        return result
    
    product_id = result.data['product']['id']
    product = Product.objects.get(id=product_id)
    
    # Step 3: Add packaging configurations
    ProductPackaging.objects.create(
        product=product,
        unit=UnitOfMeasure.objects.get(code='BOX'),
        conversion_factor=Decimal('12'),
        allow_sale=True,
        allow_purchase=True,
        is_default_purchase_unit=True
    )
    
    # Step 4: Add barcodes
    ProductBarcode.objects.create(
        product=product,
        barcode='1234567890123',
        is_primary=True
    )
    
    # Step 5: Setup pricing (via pricing app)
    PricingService.setup_base_pricing(product, warehouse, price=Decimal('25.99'))
    
    return Result.success({'product': product}, 'Product created successfully')
```

### 2. **Product Search & Selection**

```python
def product_lookup_workflow(identifier):
    """Multi-method product lookup"""
    
    # Try exact product code first
    product = ProductService.get_product(identifier, only_sellable=True)
    if product:
        return [product]
    
    # Try barcode lookup
    product = ProductService.find_by_barcode(identifier, only_sellable=True) 
    if product:
        return [product]
    
    # Try PLU lookup (for scales)
    products = ProductService.find_by_plu(identifier, only_sellable=True)
    if products:
        return products
    
    # Fallback to text search
    products = ProductService.search_products(identifier, limit=10, only_sellable=True)
    return products

# Usage in POS system
def handle_product_scan(scanned_code):
    """Handle barcode/code scan in POS"""
    products = product_lookup_workflow(scanned_code)
    
    if not products:
        return {'error': 'Product not found'}
    
    if len(products) == 1:
        product = products[0]
        return {
            'product': product,
            'code': product.code,
            'name': product.name,
            'is_sellable': product.is_sellable,
            'unit': product.base_unit.name
        }
    else:
        return {
            'multiple_matches': True,
            'products': [{'id': p.id, 'code': p.code, 'name': p.name} for p in products]
        }
```

### 3. **Lifecycle Management Workflow**

```python
def phase_out_product_workflow(product, reason="Low demand"):
    """Complete phase-out workflow"""
    
    # Step 1: Transition to phase-out
    result = LifecycleService.transition_to_phase_out(product, reason)
    if not result.ok:
        return result
    
    # Step 2: Block new purchases  
    product.purchase_blocked = True
    product.save()
    
    # Step 3: Update pricing for clearance
    current_pricing = PricingService.get_product_pricing(warehouse, product)
    if current_pricing.ok:
        clearance_price = current_pricing.data['final_price'] * Decimal('0.8')
        PricingService.update_base_price(product, warehouse, clearance_price)
    
    # Step 4: Create promotional pricing
    PromotionalPrice.objects.create(
        product=product,
        name=f'{product.name} - Clearance',
        promotional_price=clearance_price,
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timedelta(days=90)
    )
    
    # Step 5: Notify stakeholders
    notify_phase_out(product, reason)
    
    return Result.success({'product': product}, 'Product phased out successfully')

def monitor_lifecycle_transitions():
    """Daily monitoring task"""
    
    # Find products that need attention
    attention = ProductService.get_products_needing_attention()
    
    # Phase-out products with high stock
    for item in attention['phase_out_with_stock']:
        if item['stock_value'] > Decimal('1000'):
            # Create aggressive promotion
            create_clearance_promotion(item['product'])
    
    # Discontinued products with remaining stock
    for item in attention['discontinued_with_stock']:
        # Consider donation or write-off
        evaluate_stock_disposal(item['product'])
```

### 4. **Unit Conversion in Operations**

```python
def handle_multi_unit_sale(product_code, quantity, unit_code):
    """Handle sale in any valid unit"""
    
    # Get product and validate
    product = ProductService.get_product(product_code, only_sellable=True)
    if not product:
        return Result.error('PRODUCT_NOT_FOUND', f'Product {product_code} not found')
    
    # Get unit
    unit = UnitOfMeasure.objects.get(code=unit_code)
    
    # Validate unit compatibility
    if not product.is_unit_compatible(unit):
        return Result.error('INVALID_UNIT', f'Unit {unit_code} not valid for {product_code}')
    
    # Convert to base units for inventory
    base_quantity = ProductService.convert_quantity(
        product=product,
        quantity=quantity,
        from_unit=unit,
        to_unit=product.base_unit
    )
    
    if base_quantity is None:
        return Result.error('CONVERSION_FAILED', 'Cannot convert units')
    
    # Validate sale quantity (in base units)
    valid, message = product.validate_sale_quantity(base_quantity, location=warehouse)
    if not valid:
        return Result.error('INVALID_QUANTITY', message)
    
    # Process sale
    return {
        'product': product,
        'sale_quantity': quantity,
        'sale_unit': unit,
        'base_quantity': base_quantity,
        'base_unit': product.base_unit
    }
```

### 5. **Barcode Management**

```python
def setup_product_barcodes(product, barcode_data):
    """Setup multiple barcodes for product"""
    
    # Primary product barcode
    ProductBarcode.objects.create(
        product=product,
        barcode=barcode_data['primary_barcode'],
        is_primary=True,
        priority=100
    )
    
    # Packaging barcodes
    for packaging_barcode in barcode_data.get('packaging_barcodes', []):
        packaging = ProductPackaging.objects.get(
            product=product,
            unit__code=packaging_barcode['unit_code']
        )
        
        ProductBarcode.objects.create(
            product=product,
            packaging=packaging,
            barcode=packaging_barcode['barcode'],
            priority=50
        )
    
    # Alternative barcodes
    for alt_barcode in barcode_data.get('alternative_barcodes', []):
        ProductBarcode.objects.create(
            product=product,
            barcode=alt_barcode,
            priority=10
        )

def barcode_lookup_with_packaging(barcode):
    """Lookup with packaging awareness"""
    try:
        barcode_obj = ProductBarcode.objects.select_related(
            'product', 'packaging', 'packaging__unit'
        ).get(barcode=barcode, is_active=True)
        
        result = {
            'product': barcode_obj.product,
            'barcode': barcode,
            'is_packaging': bool(barcode_obj.packaging)
        }
        
        if barcode_obj.packaging:
            # This is a packaging barcode
            result.update({
                'packaging': barcode_obj.packaging,
                'unit': barcode_obj.packaging.unit,
                'quantity_per_scan': barcode_obj.packaging.conversion_factor,
                'scan_type': 'PACKAGING'
            })
        else:
            # This is a product barcode
            result.update({
                'unit': barcode_obj.product.base_unit,
                'quantity_per_scan': Decimal('1'),
                'scan_type': 'PRODUCT'
            })
        
        return result
        
    except ProductBarcode.DoesNotExist:
        return None
```

---

## API Reference

### ProductService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `get_product(identifier)` | Get product by code/barcode | Product | identifier, only_sellable |
| `find_by_barcode(barcode)` | Find by barcode | Product | barcode, only_sellable |
| `find_by_plu(plu_code)` | Find by PLU code | List[Product] | plu_code, only_sellable |
| `search_products(query)` | Text search products | List[Product] | query, limit, only_sellable |
| `get_sellable_products()` | Get sellable products | List[Product] | location, category, limit |
| `get_conversion_factor(product, from_unit, to_unit)` | Unit conversion | Decimal | product, from_unit, to_unit |
| `convert_quantity(product, qty, from_unit, to_unit)` | Convert quantities | Decimal | product, quantity, units |
| `create_product_with_inventory(data)` | Create product + inventory | Result | product_data |
| `validate_product_data(data)` | Validate product data | Result | product_data |

### Result Data Structures

**Product Search Result:**
```python
[
    {
        'product': <Product>,
        'code': 'WIDGET001',
        'name': 'Premium Widget',
        'is_sellable': True,
        'lifecycle_status': 'ACTIVE',
        'brand': 'ACME',
        'base_unit': 'PC'
    }
]
```

**Unit Conversion Info:**
```python
{
    'available_units': [
        {
            'unit': <UnitOfMeasure: PC>,
            'conversion_factor': Decimal('1.0'),
            'is_base': True,
            'can_sell': True,
            'can_purchase': True
        },
        {
            'unit': <UnitOfMeasure: BOX>,
            'conversion_factor': Decimal('12.0'),
            'is_base': False,
            'is_default_sale': False,
            'is_default_purchase': True,
            'can_sell': True,
            'can_purchase': True
        }
    ]
}
```

**Product Creation Result:**
```python
{
    'product': {
        'id': 42,
        'code': 'WIDGET001',
        'name': 'Premium Widget',
        'lifecycle_status': 'ACTIVE'
    },
    'inventory_items_created': 5,
    'active_locations': 5,
    'warnings': []
}
```

**Packaging Consistency Report:**
```python
{
    'is_consistent': True,
    'total_packagings': 3,
    'unit_type': 'PIECE',
    'issues': [],
    'warnings': [],
    'conversion_matrix': {
        'PC': {
            'BOX': {'ratio': 0.083, 'is_whole': False, 'problematic': False},
            'CASE': {'ratio': 0.007, 'is_whole': False, 'problematic': False}
        },
        'BOX': {
            'PC': {'ratio': 12.0, 'is_whole': True, 'problematic': False},
            'CASE': {'ratio': 0.083, 'is_whole': False, 'problematic': False}
        }
    },
    'recommendations': []
}
```

---

## Error Handling

### Common Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `PRODUCT_NOT_FOUND` | Product doesn't exist | Verify product code/barcode |
| `PRODUCT_NOT_SELLABLE` | Product cannot be sold | Check lifecycle status |
| `PRODUCT_NOT_PURCHASABLE` | Product cannot be purchased | Check lifecycle/blocked status |
| `INVALID_UNIT` | Unit not compatible | Use valid packaging unit |
| `INVALID_QUANTITY` | Quantity validation failed | Check PIECE product rules |
| `FRACTIONAL_PIECES` | Non-integer for PIECE | Use whole numbers only |
| `CONVERSION_FAILED` | Unit conversion failed | Verify packaging setup |
| `VALIDATION_FAILED` | Product data invalid | Fix validation errors |

### Validation Patterns

```python
# Product operation validation
def validate_product_operation(product, operation):
    """Validate product can perform operation"""
    
    validations = {
        'SELL': product.is_sellable,
        'PURCHASE': product.is_purchasable,
        'MODIFY': product.lifecycle_status != 'ARCHIVED'
    }
    
    if not validations.get(operation, False):
        return Result.error(
            f'{operation}_NOT_ALLOWED',
            f'Product {product.code} cannot {operation.lower()}: {product.lifecycle_status}'
        )
    
    return Result.success()

# Error handling in services
def service_operation(product_id):
    try:
        product = Product.objects.get(id=product_id)
        
        # Validate operation
        validation = validate_product_operation(product, 'SELL')
        if not validation.ok:
            return validation
            
        # Continue with operation...
        
    except Product.DoesNotExist:
        return Result.error('PRODUCT_NOT_FOUND', f'Product {product_id} not found')
    except Exception as e:
        logger.error(f'Service error: {e}')
        return Result.error('SERVICE_ERROR', 'Operation failed')
```

---

## Performance Considerations

### 1. **Optimized Queries**

```python
# Use manager methods with prefetching
sellable_products = Product.objects.sellable().select_related(
    'brand', 'product_group', 'base_unit', 'tax_group'
).prefetch_related(
    'packagings__unit', 'barcodes'
)

# Efficient search with proper indexing
def search_with_indexes(query):
    return Product.objects.filter(
        Q(code__icontains=query) |           # Indexed
        Q(name__icontains=query) |           # Indexed  
        Q(barcodes__barcode=query)           # Indexed via barcodes table
    ).distinct().select_related('brand')[:20]
```

### 2. **Caching Strategy**

```python
from django.core.cache import cache

def get_product_cached(code):
    """Cache product lookups"""
    cache_key = f"product:{code}"
    product = cache.get(cache_key)
    
    if product is None:
        try:
            product = Product.objects.select_related(
                'brand', 'product_group', 'base_unit'
            ).get(code=code)
            cache.set(cache_key, product, timeout=1800)  # 30 minutes
        except Product.DoesNotExist:
            cache.set(cache_key, 'NOT_FOUND', timeout=300)  # 5 minutes
            return None
    
    return product if product != 'NOT_FOUND' else None

# Cache invalidation on product changes
def invalidate_product_cache(product_code):
    cache_keys = [
        f"product:{product_code}",
        f"product_sellable:{product_code}",
        f"product_units:{product_code}"
    ]
    cache.delete_many(cache_keys)
```

### 3. **Bulk Operations**

```python
# Efficient bulk lifecycle updates
def bulk_lifecycle_update(product_codes, new_status):
    """Update multiple products efficiently"""
    
    updated_count = Product.objects.filter(
        code__in=product_codes
    ).update(
        lifecycle_status=new_status,
        updated_at=timezone.now()
    )
    
    # Bulk cache invalidation
    cache_keys = [f"product:{code}" for code in product_codes]
    cache.delete_many(cache_keys)
    
    return updated_count

# Batch inventory creation
def create_inventory_for_products(product_ids, location):
    """Create inventory items in batch"""
    
    inventory_items = []
    for product_id in product_ids:
        inventory_items.append(InventoryItem(
            product_id=product_id,
            location=location,
            current_qty=Decimal('0'),
            avg_cost=Decimal('0')
        ))
    
    InventoryItem.objects.bulk_create(
        inventory_items, 
        batch_size=100,
        ignore_conflicts=True
    )
```

---

## Best Practices

### 1. **Always Use Lifecycle-Aware Queries**

```python
# ✅ Good - respects product lifecycle
sellable_products = Product.objects.sellable()
purchasable_products = Product.objects.purchasable()

# ❌ Avoid - ignores lifecycle
all_products = Product.objects.filter(name__contains='widget')  # May include discontinued
```

### 2. **Validate Before Operations**

```python
# ✅ Good - validate before sale
def process_sale(product_code, quantity):
    product = ProductService.get_product(product_code, only_sellable=True)
    if not product:
        return Result.error('PRODUCT_NOT_SELLABLE')
    
    valid, message = product.validate_sale_quantity(quantity, location)
    if not valid:
        return Result.error('INVALID_QUANTITY', message)
    
    # Proceed with sale...

# ❌ Avoid - assuming product is valid
def process_sale_bad(product_code, quantity):
    product = Product.objects.get(code=product_code)  # May fail
    # Process sale without validation...
```

### 3. **Use Proper Unit Conversions**

```python
# ✅ Good - use service methods
base_quantity = ProductService.convert_quantity(
    product=product,
    quantity=order_quantity,
    from_unit=order_unit,
    to_unit=product.base_unit
)

if base_quantity is None:
    return Result.error('CONVERSION_FAILED')

# ❌ Avoid - manual conversion calculations
# base_quantity = order_quantity * packaging.conversion_factor  # Error-prone
```

### 4. **Handle PIECE Products Correctly**

```python
# ✅ Good - validate PIECE quantities
def validate_piece_quantity(product, quantity):
    if product.unit_type == 'PIECE':
        if quantity != int(quantity):
            return Result.error('FRACTIONAL_PIECES', 'Piece products must be whole numbers')
    return Result.success()

# ✅ Good - PIECE packaging setup
ProductPackaging.objects.create(
    product=piece_product,
    unit=box_unit,
    conversion_factor=Decimal('12'),  # Whole number for PIECE
    allow_sale=True
)

# ❌ Avoid - fractional PIECE packaging  
ProductPackaging.objects.create(
    product=piece_product,
    conversion_factor=Decimal('12.5')  # Invalid for PIECE
)
```

### 5. **Implement Proper Product Creation**

```python
# ✅ Good - enterprise pattern with full setup
result = ProductService.create_product_with_inventory({
    'code': 'WIDGET001',
    'name': 'Premium Widget',
    'base_unit': base_unit,
    'tax_group': tax_group,
    'unit_type': 'PIECE',
    'lifecycle_status': 'ACTIVE'
})

if result.ok:
    product_id = result.data['product']['id']
    # Continue with packaging, barcodes, pricing setup...

# ❌ Avoid - direct model creation without setup
product = Product.objects.create(code='WIDGET001', name='Widget')
# Missing inventory items, validation, etc.
```

---

## Dependencies

**PRODUCTS app depends on:**
- Django framework
- CORE app (Result pattern)
- NOMENCLATURES app (Brand, ProductGroup, UnitOfMeasure, TaxGroup)
- INVENTORY app (InventoryItem for stock data)

**Other apps depend on PRODUCTS:**
- INVENTORY (product definitions)
- PRICING (product-based pricing)
- SALES (product selection)
- PURCHASES (product procurement)
- REPORTS (product analytics)

---

## Version History

- **v1.0** - Basic product model with categories
- **v2.0** - Added packaging system and barcodes
- **v2.1** - Added PLU support for weight products  
- **v3.0** - Lifecycle management and nomenclatures integration
- **v3.1** - Service layer with Result pattern
- **v3.2** - Enhanced packaging validation and consistency checks

---

*Last Updated: 2025-08-29*  
*Version: 3.2*