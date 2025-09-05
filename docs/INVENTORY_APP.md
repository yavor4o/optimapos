# INVENTORY App Documentation

## 🎯 Overview

The **INVENTORY app** manages all inventory tracking, stock movements, and warehouse operations in OptimaPOS. It serves as the central system for monitoring product quantities, locations, batch tracking, and automated inventory movements triggered by document status changes.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Core Models](#core-models)  
3. [Services](#services)
4. [Inventory Movement System](#inventory-movement-system)
5. [Batch Tracking](#batch-tracking)
6. [Integration with Document System](#integration-with-document-system)
7. [Usage Patterns](#usage-patterns)
8. [API Reference](#api-reference)

---

## Architecture

```
INVENTORY App Structure:
├── models/
│   ├── locations.py         # InventoryLocation
│   ├── movements.py         # InventoryMovement (source of truth)
│   └── items.py            # InventoryItem, InventoryBatch (cached data)
├── services/
│   ├── movement_service.py  # Movement creation and FIFO logic
│   └── inventory_service.py # Stock validation and reservations
├── admin.py                # Admin interface
└── views.py               # API endpoints
```

### Design Philosophy

- **🎯 Movement-Centric** - All inventory changes tracked as movements
- **📊 Source of Truth** - InventoryMovement is authoritative record
- **⚡ Cached Performance** - InventoryItem/InventoryBatch for fast queries
- **🔄 Event-Driven** - Automatic movements from document status changes
- **🏷️ Batch Tracking** - Full FIFO support with expiry dates
- **🔒 Concurrency Safe** - Atomic operations with proper locking

---

## Core Models

### 1. **InventoryMovement** (Source of Truth)

**Purpose**: Records every inventory transaction with complete audit trail

```python
# Key Fields
movement_type = ['IN', 'OUT', 'TRANSFER', 'ADJUSTMENT', 'PRODUCTION', 'CYCLE_COUNT']
quantity = Decimal()  # Always positive (type determines direction)
cost_price = Decimal()  # Unit cost for this movement
sale_price = Decimal()  # Unit sale price (for profit tracking)
profit_amount = Decimal()  # Calculated: sale_price - cost_price

# Document Integration
source_document_type = CharField()  # e.g., 'DELIVERY', 'SALE'
source_document_number = CharField()
source_document_line_id = PositiveIntegerField()

# Batch/Lot Tracking
batch_number = CharField()
expiry_date = DateField()
serial_number = CharField()

# Transfer-specific
from_location = ForeignKey()
to_location = ForeignKey()
```

**Key Properties:**
- `effective_quantity` - Signed quantity based on movement type
- `total_cost_value` - quantity × cost_price  
- `total_profit` - quantity × profit_amount
- `profit_margin_percentage` - Profit as percentage of sale price

### 2. **InventoryItem** (Performance Cache)

**Purpose**: Fast access to current stock levels per location/product

```python
# Current State
current_qty = Decimal()    # Total quantity on hand
reserved_qty = Decimal()   # Quantity reserved for orders
avg_cost = Decimal()       # Weighted average cost

# Derived Properties
@property
def available_qty(self):
    return self.current_qty - self.reserved_qty

@property 
def stock_value(self):
    return self.current_qty * self.avg_cost
```

**Cache Refresh**: Automatically updated by MovementService operations

### 3. **InventoryBatch** (Batch Tracking)

**Purpose**: Track individual batches for FIFO and expiry management

```python
# Batch Identity
batch_number = CharField()
expiry_date = DateField()

# Quantities
received_qty = Decimal()    # Originally received
remaining_qty = Decimal()   # Still available
cost_price = Decimal()      # Cost for this batch

# Batch Status
is_unknown_batch = Boolean()  # Auto-generated batch
received_date = DateField()
```

### 4. **InventoryLocation**

**Purpose**: Define warehouse locations with specific behaviors

```python
# Location Settings
allow_negative_stock = Boolean()
should_track_batches = Boolean()

# Methods
def should_track_batches(self, product):
    return self.track_batches and product.track_batches
```

---

## Services

### 1. **MovementService** - Core Movement Operations

**Primary API (Result Pattern):**

```python
# Incoming Stock
result = MovementService.create_incoming_stock(
    location=warehouse,
    product=product,
    quantity=Decimal('100'),
    cost_price=Decimal('12.50'),
    source_document_type='DELIVERY',
    source_document_number='DEL-001',
    batch_number='BATCH-2024-001'
)

# Outgoing Stock (FIFO)
result = MovementService.create_outgoing_stock(
    location=warehouse,
    product=product,
    quantity=Decimal('50'),
    source_document_type='SALE',
    sale_price=Decimal('18.00'),  # For profit tracking
    use_fifo=True
)

# Stock Transfer
result = MovementService.create_stock_transfer(
    from_location=warehouse_a,
    to_location=warehouse_b,
    product=product,
    quantity=Decimal('25')
)

# Inventory Adjustment
result = MovementService.create_stock_adjustment(
    location=warehouse,
    product=product,
    adjustment_qty=Decimal('-5'),  # Negative for decrease
    reason='Damaged goods'
)
```

**Document Integration:**
```python
# Process document automatically
result = MovementService.process_document_movements(delivery_document)

# Sync movements with document status
result = MovementService.sync_movements_with_document(purchase_order)
```

### 2. **InventoryService** - Stock Validation & Reservations

```python
# Check Stock Availability
result = InventoryService.validate_availability(location, product, Decimal('75'))
if result.ok:
    available_qty = result.data['available_qty']
    can_fulfill = result.data['can_fulfill']

# Batch Availability (FIFO-aware)
result = InventoryService.validate_batch_availability(location, product, Decimal('75'))
if result.ok:
    batch_details = result.data['batch_details']

# Reserve Stock
result = InventoryService.reserve_stock_qty(location, product, Decimal('25'))

# Stock Summary
result = InventoryService.get_stock_summary(location, product)
stock_data = result.data
```

---

## Inventory Movement System

### Movement Types

| Type | Direction | Purpose | Example |
|------|-----------|---------|---------|
| `IN` | Incoming | Purchases, receipts | Delivery receipt |
| `OUT` | Outgoing | Sales, issues | Sales order fulfillment |
| `TRANSFER` | Both | Between locations | Warehouse transfer |
| `ADJUSTMENT` | Both | Corrections | Cycle count adjustments |
| `PRODUCTION` | Incoming | Manufacturing | Product assembly |
| `CYCLE_COUNT` | Both | Inventory audits | Physical count corrections |

### FIFO Implementation

**Automatic FIFO for Batch-Tracked Products:**

```python
# When creating outgoing movement for batch-tracked product
movements = MovementService._create_fifo_outgoing_movements(
    location, product, quantity=100,
    sale_price=Decimal('15.00')
)

# Results in multiple movements from different batches:
# Movement 1: 60 units from BATCH-A @ cost $10.00
# Movement 2: 40 units from BATCH-B @ cost $12.00
# Total profit calculated per batch
```

### Profit Tracking

**Enhanced Movement Model:**
- `sale_price` - Unit sale price for OUT movements
- `profit_amount` - Calculated profit per unit  
- `total_profit` property - Total profit for movement
- `profit_margin_percentage` - Margin as percentage

**Profit Analysis:**
```python
# Get profit summary for location
summary = InventoryMovement.get_profit_summary(
    location=warehouse,
    date_from=start_date,
    date_to=end_date
)

# Results include:
# - total_revenue, total_cost, total_profit
# - profit_margin_percentage
# - Movement count and quantities
```

---

## Batch Tracking

### Auto-Generated Batches

**For Products Requiring Batch Tracking:**
```python
# When no batch_number provided for incoming movement
auto_batch = f"AUTO_{product.code}_{date}_{location.code}"
# Example: "AUTO_WIDGET123_241201_WH01"
```

### Batch Validation

```python
def clean(self):
    # Auto-generate batch for tracked products
    if (self.product and self.product.track_batches and
            self.movement_type == self.IN and not self.batch_number):
        self.batch_number = self.generate_auto_batch()
```

### FIFO Batch Consumption

**Order**: `created_at` ASC (oldest first)
```python
available_batches = InventoryBatch.objects.filter(
    location=location,
    product=product, 
    remaining_qty__gt=0
).order_by('created_at')

for batch in available_batches:
    qty_from_batch = min(remaining_qty, batch.remaining_qty)
    # Create movement from this batch
    # Update batch.remaining_qty
```

---

## Integration with Document System

### Status-Driven Movement Creation

**Configuration via DocumentTypeStatus:**

```python
# When document status changes
current_config = DocumentTypeStatus.objects.filter(
    document_type=document.document_type,
    status__code=document.status,
    is_active=True
).first()

if current_config.creates_inventory_movements:
    # Create movements automatically
    movements = MovementService.process_document_movements(document)
```

### Document Movement Synchronization

**Smart Sync Logic:**
```python
def sync_movements_with_document(document):
    # 1. Check if correction allowed by status configuration
    if not current_config.allows_movement_correction:
        return error
    
    # 2. Delete existing movements
    original_movements.delete()
    reversal_movements.delete()
    
    # 3. Recreate if status requires movements
    if current_config.creates_inventory_movements:
        new_movements = create_from_document(document)
```

### Supported Document Types

| Document Type | Movement Type | Trigger Status | Notes |
|---------------|---------------|----------------|-------|
| DeliveryReceipt | IN | completed | Creates incoming stock |
| PurchaseOrder | IN | approved (if auto_receive) | Optional auto-receipt |
| SalesOrder | OUT | shipped | Creates outgoing stock |
| StockTransfer | TRANSFER | completed | Between locations |
| StockAdjustment | ADJUSTMENT | approved | Quantity corrections |

---

## Usage Patterns

### 1. **Document Processing Pattern**

```python
# In DocumentService when status changes to 'completed'
from inventory.services import MovementService

def transition_to_completed(self):
    # Other status change logic...
    
    # Check if this status creates movements
    if self.status_config.creates_inventory_movements:
        movement_result = MovementService.process_document_movements(self.document)
        if not movement_result.ok:
            return Result.error('MOVEMENT_FAILED', movement_result.msg)
    
    return Result.success()
```

### 2. **Sales Integration Pattern**

```python
# In sales processing
def fulfill_order_line(order_line):
    # Check availability
    availability = InventoryService.validate_availability(
        location, product, order_line.quantity
    )
    
    if not availability.ok:
        return availability  # Insufficient stock
    
    # Create outgoing movement with profit tracking
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
# Reserve stock for pending orders
def reserve_stock_for_order(order):
    for line in order.lines.all():
        reserve_result = InventoryService.reserve_stock_qty(
            location=order.location,
            product=line.product,
            quantity=line.quantity,
            reason=f"Reserved for order {order.number}"
        )
        
        if not reserve_result.ok:
            # Handle insufficient stock
            return reserve_result
    
    return Result.success()
```

---

## API Reference

### MovementService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `create_incoming_stock()` | Add inventory | Result | location, product, quantity, cost_price |
| `create_outgoing_stock()` | Remove inventory | Result | location, product, quantity, sale_price |
| `create_stock_transfer()` | Transfer between locations | Result | from_location, to_location, product, quantity |
| `create_stock_adjustment()` | Inventory corrections | Result | location, product, adjustment_qty, reason |
| `process_document_movements()` | Auto-create from document | Result | document |
| `sync_movements_with_document()` | Sync with document changes | Result | document |

### InventoryService Methods

| Method | Purpose | Returns | Key Parameters |
|--------|---------|---------|----------------|
| `validate_availability()` | Check stock levels | Result | location, product, required_qty |
| `validate_batch_availability()` | Check batch stock (FIFO) | Result | location, product, required_qty |
| `reserve_stock_qty()` | Reserve inventory | Result | location, product, quantity |
| `release_reservation()` | Release reservation | Result | location, product, quantity |
| `get_stock_summary()` | Complete stock info | Result | location, product |

### Result Data Structures

**Movement Creation Result:**
```python
{
    'movement_id': 12345,
    'quantity': Decimal('100'),
    'cost_price': Decimal('12.50'),
    'location_code': 'WH01',
    'product_code': 'WIDGET123',
    'batch_number': 'BATCH-001',
    'cache_updated': True
}
```

**Availability Check Result:**
```python
{
    'available': True,
    'current_qty': Decimal('500'),
    'available_qty': Decimal('450'),
    'reserved_qty': Decimal('50'),
    'can_fulfill': True,
    'shortage': Decimal('0'),
    'avg_cost': Decimal('10.25'),
    'product_code': 'WIDGET123',
    'location_code': 'WH01'
}
```

**Batch Availability Result:**
```python
{
    'total_available': Decimal('450'),
    'can_fulfill': True,
    'batch_count': 3,
    'batch_details': [
        {
            'batch_number': 'BATCH-A',
            'remaining_qty': Decimal('200'),
            'cost_price': Decimal('10.00'),
            'expiry_date': '2024-12-31',
            'is_expired': False,
            'can_use_qty': Decimal('100')
        }
        # ... more batches
    ]
}
```

---

## Error Handling

### Common Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `INSUFFICIENT_STOCK` | Not enough available stock | Check availability first |
| `INSUFFICIENT_BATCH_STOCK` | Not enough in batches | Check batch availability |
| `INVALID_QUANTITY` | Quantity <= 0 | Validate input |
| `FRACTIONAL_PIECES` | Non-integer for piece products | Round to integer |
| `MOVEMENT_CREATION_ERROR` | System error in movement | Check logs, retry |
| `ITEM_NOT_FOUND` | No inventory record | Initialize stock first |

### Error Response Pattern

```python
if not result.ok:
    error_info = {
        'code': result.code,           # Error code
        'message': result.msg,         # Human-readable message  
        'data': result.data,           # Additional context
        'suggestions': [               # Possible solutions
            'Check stock availability',
            'Verify product exists at location'
        ]
    }
```

---

## Performance Considerations

### 1. **Concurrent Operations**

```python
# All critical operations use select_for_update()
with transaction.atomic():
    item = InventoryItem.objects.select_for_update().get(
        location=location, product=product
    )
    # Atomic quantity updates
    item.current_qty = F('current_qty') - quantity
    item.save()
```

### 2. **Batch Processing**

```python
# Use bulk operations for multiple movements
result = MovementService.bulk_create_movements(movement_data_list)
```

### 3. **Cache Strategy**

- InventoryItem updated incrementally (not full refresh)
- Batch quantities updated atomically with F() expressions
- Movement history paginated for large datasets

---

## Integration Points

### **With NOMENCLATURES App:**
- DocumentService triggers movement creation via status changes
- StatusManager checks movement configuration flags
- Document lines provide movement details (quantity, price, batch)

### **With PRICING App:**
- Auto-detects sale prices for profit calculations
- Triggers pricing updates when costs change significantly
- Provides cost data for markup calculations

### **With PRODUCTS App:**
- Product.track_batches determines batch tracking behavior
- Unit type validation (no fractional pieces)
- Product costs updated from inventory movements

### **With PARTNERS App:**  
- Customer-specific pricing detection for sales movements
- Supplier cost tracking from purchase movements

---

## Best Practices

### 1. **Always Use Result Pattern**
```python
# ✅ Good
result = MovementService.create_incoming_stock(...)
if result.ok:
    movement_data = result.data
else:
    handle_error(result.code, result.msg)

# ❌ Avoid
try:
    movement = create_movement(...)  # Exception-based
except Exception as e:
    # Inconsistent error handling
```

### 2. **Check Availability First**
```python
# ✅ Good  
availability = InventoryService.validate_availability(location, product, qty)
if availability.ok and availability.data['can_fulfill']:
    movement_result = MovementService.create_outgoing_stock(...)

# ❌ Avoid
movement_result = MovementService.create_outgoing_stock(...)  # May fail
```

### 3. **Use Atomic Transactions**
```python
# ✅ Good
with transaction.atomic():
    reserve_result = InventoryService.reserve_stock_qty(...)
    movement_result = MovementService.create_outgoing_stock(...)
    
# ❌ Avoid separate operations without transaction
```

### 4. **Leverage Document Integration**
```python
# ✅ Good - let status configuration drive movements
document.transition_to('completed')  # Automatically creates movements

# ❌ Avoid manual movement creation for documents
MovementService.create_incoming_stock(...)  # Should be automatic
```

---

## Dependencies

**INVENTORY app depends on:**
- Django framework
- CORE app (Result pattern, interfaces)
- PRODUCTS app (Product model)

**Other apps depend on INVENTORY:**
- NOMENCLATURES (document-driven movements)
- PRICING (cost data)
- Sales modules (stock validation)

---

## Version History

- **v1.0** - Basic inventory tracking
- **v1.5** - FIFO batch tracking
- **v2.0** - Result pattern refactoring  
- **v2.1** - Document integration via status configuration
- **v2.2** - Enhanced profit tracking and analysis

---

*Last Updated: 2025-08-29*  
*Version: 2.2*