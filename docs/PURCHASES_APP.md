# PURCHASES App Documentation

## 🎯 Overview

The **PURCHASES app** implements the procurement workflow for OptimaPOS. It provides a **thin wrapper** around the NOMENCLATURES facade, handling purchase-specific business logic while delegating all document operations to the unified system.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Thin Wrapper Pattern](#thin-wrapper-pattern)
3. [Document Types](#document-types)
4. [Purchase Workflow](#purchase-workflow)
5. [Models](#models)
6. [Services](#services)
7. [Integration Points](#integration-points)
8. [Usage Patterns](#usage-patterns)

---

## Architecture

```
PURCHASES App Structure:
├── services/                    # Thin wrapper services
│   └── purchase_service.py     # 🏗️ Main service - delegates to NOMENCLATURES
├── models/                      # Purchase-specific models
│   ├── requests.py             # Purchase Request + Lines
│   ├── orders.py               # Purchase Order + Lines
│   └── deliveries.py           # Delivery Receipt + Lines  
├── admin/                       # Admin interface for purchase documents
└── views.py                     # Basic views (if any)
```

### Key Design Principles

- **🏗️ Thin Wrapper Pattern** - Minimal code, maximum delegation
- **🎯 Domain-Specific Logic** - Only purchase-specific conversions and business rules
- **🏛️ Facade Delegation** - ALL operations go through NOMENCLATURES DocumentService
- **♻️ Code Reuse** - 700+ lines reduced to ~150 lines (75% reduction)

---

## Thin Wrapper Pattern

### Core Concept: 100% Delegation

```python
class PurchaseDocumentService:
    """
    Thin wrapper that delegates EVERYTHING to nomenclatures.DocumentService
    Only handles purchase-specific domain logic
    """
    
    def __init__(self, document=None, user: User = None):
        # PRINCIPLE: Everything through the facade!
        self.facade = DocumentService(document, user)
        self.document = document
        self.user = user
```

### What This App DOES Handle:
- ✅ **Purchase-specific conversions** (Request → Order → Delivery)
- ✅ **Domain business rules** (supplier validation, purchase workflows)
- ✅ **Purchase models** (PurchaseRequest, PurchaseOrder, DeliveryReceipt)
- ✅ **Field mapping** (generic input → specific fields)

### What This App DOES NOT Handle:
- ❌ **Document validation** → Delegated to NOMENCLATURES
- ❌ **Status transitions** → Delegated to NOMENCLATURES  
- ❌ **Line management** → Delegated to NOMENCLATURES
- ❌ **Financial calculations** → Delegated to NOMENCLATURES
- ❌ **Inventory movements** → Delegated to NOMENCLATURES → INVENTORY

---

## Document Types

### 1. **Purchase Request** 📋
**Purpose:** Initial request for products from suppliers.

```python
# Model: PurchaseRequest + PurchaseRequestLine
class PurchaseRequest(BaseDocument, FinancialMixin):
    request_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)
    
class PurchaseRequestLine(BaseDocumentLine, FinancialLineMixin):
    requested_quantity = models.DecimalField(...)  # ← Specific quantity field
    estimated_price = models.DecimalField(...)     # Estimated unit price
```

**Usage:**
```python
# Create purchase request
result = service.create_document(
    'request',
    supplier=supplier,
    location=location,
    lines=[
        {
            'product': product,
            'quantity': Decimal('10'),  # → Maps to requested_quantity
            'unit_price': Decimal('25') # → Maps to estimated_price
        }
    ]
)
```

### 2. **Purchase Order** 📦
**Purpose:** Formal order sent to suppliers.

```python  
# Model: PurchaseOrder + PurchaseOrderLine
class PurchaseOrder(BaseDocument, FinancialMixin, PaymentMixin):
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True)
    supplier_order_reference = models.CharField(...)
    
class PurchaseOrderLine(BaseDocumentLine, FinancialLineMixin):
    ordered_quantity = models.DecimalField(...)   # ← Specific quantity field  
    confirmed_price = models.DecimalField(...)    # Final agreed price
    source_request_line = models.ForeignKey(...)  # Link back to request
```

**Usage:**
```python
# Convert request to order
result = service.convert_to_order(
    request_document=purchase_request,
    conversion_data={
        'expected_delivery_date': date(2025, 9, 15),
        'supplier_order_reference': 'SUP-REF-12345'
    }
)
```

### 3. **Delivery Receipt** 🚛
**Purpose:** Record of actual goods received.

```python
# Model: DeliveryReceipt + DeliveryLine  
class DeliveryReceipt(BaseDocument, FinancialMixin, PaymentMixin):
    delivery_date = models.DateField(default=timezone.now)
    received_by = models.ForeignKey(User, ...)
    quality_status = models.CharField(...)         # Quality control
    
class DeliveryLine(BaseDocumentLine, FinancialLineMixin):
    received_quantity = models.DecimalField(...)   # ← Specific quantity field
    quality_approved = models.BooleanField(...)    # Quality check result
    batch_number = models.CharField(...)           # Batch tracking
    source_order_line = models.ForeignKey(...)     # Link back to order
```

**Usage:**
```python
# Convert order to delivery  
result = service.convert_to_delivery(
    order_document=purchase_order,
    delivery_data={
        'delivery_date': date.today(),
        'received_quantities': {1: Decimal('9.5'), 2: Decimal('15')}
    }
)
```

---

## Purchase Workflow

### Complete Procurement Cycle

```
📋 REQUEST → 📦 ORDER → 🚛 DELIVERY
    ↓           ↓         ↓
  draft      draft     draft → completed (📦 inventory)
    ↓           ↓         ↓                     ↓
submitted  confirmed  received               cancelled (🗑️ reverse)
    ↓           ↓         ↓                     ↓
 approved    sent     completed            back to completed (♻️ recreate)
```

### Status Integration with Inventory

**Key Point:** Each document type can have different inventory behavior:

- **Purchase Request:** No inventory impact (planning only)
- **Purchase Order:** No inventory impact (commitment only)  
- **Delivery Receipt:** Full inventory integration
  - `draft` → No movements
  - `completed` → ✅ Create inventory movements  
  - `cancelled` → ❌ Delete inventory movements

### Conversion Logic

**1. Request → Order Conversion:**
```python
def convert_to_order(self, request_document, conversion_data):
    # Extract lines from request
    lines = []
    for req_line in request_document.lines.all():
        lines.append({
            'product': req_line.product,
            'quantity': req_line.requested_quantity,    # Source field
            'unit_price': conversion_data.get('confirmed_price', req_line.estimated_price),
            'source_request_line_id': req_line.id       # Maintain link
        })
    
    # Create order via facade
    return self.facade.create(
        document_type='purchase_order',
        partner=request_document.partner, 
        location=request_document.location,
        lines=lines,
        **conversion_data
    )
```

**2. Order → Delivery Conversion:**  
```python
def convert_to_delivery(self, order_document, delivery_data):
    # Extract lines from order with actual received quantities
    lines = []
    received_quantities = delivery_data.get('received_quantities', {})
    
    for order_line in order_document.lines.all():
        received_qty = received_quantities.get(
            str(order_line.line_number), 
            order_line.ordered_quantity  # Default to ordered quantity
        )
        lines.append({
            'product': order_line.product,
            'quantity': received_qty,                   # Actual received
            'unit_price': order_line.unit_price,
            'entered_price': order_line.unit_price,     # Trigger VAT calculations
            'source_order_line_id': order_line.id       # Maintain link
        })
    
    # Create delivery via facade
    return self.facade.create(
        document_type='delivery_receipt', 
        partner=order_document.partner,
        location=order_document.location,
        lines=lines,
        **delivery_data
    )
```

---

## Models

### Model Hierarchy

**Base Classes:**
- All purchase models inherit from `BaseDocument` and `BaseDocumentLine` (from NOMENCLATURES)
- Financial models use `FinancialMixin` and `FinancialLineMixin` (from NOMENCLATURES)
- Payment tracking uses `PaymentMixin` (from NOMENCLATURES)

### Key Model Features

**1. Generic Relationships:**
```python
# All documents use generic relationships for flexibility
class PurchaseRequest(BaseDocument):
    # partner_content_type, partner_object_id → GenericForeignKey to suppliers
    # location_content_type, location_object_id → GenericForeignKey to warehouses
```

**2. Document Linking:**
```python
# Maintain full traceability through the workflow
class PurchaseOrder(BaseDocument):
    source_request = models.ForeignKey('PurchaseRequest', ...)
    
class DeliveryReceipt(BaseDocument):  
    source_order = models.ForeignKey('PurchaseOrder', ...)
    
class DeliveryLine(BaseDocumentLine):
    source_order_line = models.ForeignKey('PurchaseOrderLine', ...)
```

**3. Quantity Field Specialization:**
```python
# Each document type has specialized quantity fields
PurchaseRequestLine.requested_quantity  # What we want
PurchaseOrderLine.ordered_quantity      # What we ordered  
DeliveryLine.received_quantity          # What we got

# But API is unified:
lines = [{'product': p, 'quantity': 10}]  # Same input format
# → Auto-mapped to correct field by DocumentLineService
```

**4. Enhanced Managers:**
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

## Services

### PurchaseDocumentService - The Main Service

**Architecture: Thin Wrapper + Facade Pattern**

```python
class PurchaseDocumentService:
    def __init__(self, document=None, user: User = None):
        self.facade = DocumentService(document, user)  # 🏛️ Delegate everything
        
    def create_document(self, doc_type, partner, location, lines, **kwargs):
        """Create any purchase document type"""
        # 1. Purchase-specific validation
        validation_result = self._validate_purchase_creation(partner, location, lines)
        if not validation_result.ok:
            return validation_result
            
        # 2. Map document type to model
        model_map = {
            'request': 'purchases.PurchaseRequest',
            'order': 'purchases.PurchaseOrder', 
            'delivery': 'purchases.DeliveryReceipt'
        }
        
        # 3. Delegate to facade
        return self.facade.create(
            document_type=model_map[doc_type],
            partner=partner,
            location=location, 
            lines=lines,
            **kwargs
        )
```

### Conversion Services

**Request → Order:**
```python
def convert_to_order(self, request_document, conversion_data=None):
    """Convert purchase request to purchase order"""
    
    # 1. Validate request is in correct status
    if request_document.status not in ['approved', 'confirmed']:
        return Result.error('INVALID_STATUS', 
            f'Cannot convert request in status {request_document.status}')
    
    # 2. Extract and transform lines
    lines = self._extract_request_lines(request_document, conversion_data)
    
    # 3. Create order via facade  
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
    """Convert purchase order to delivery receipt"""
    
    # 1. Validate order status
    if order_document.status not in ['confirmed', 'sent']:
        return Result.error('INVALID_STATUS',
            f'Cannot convert order in status {order_document.status}')
            
    # 2. Handle partial deliveries and quantity adjustments
    lines = self._extract_order_lines(order_document, delivery_data)
    
    # 3. Create delivery via facade
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

## Integration Points

### With NOMENCLATURES App

**100% Facade Delegation:**
```python
# EVERYTHING goes through DocumentService facade
class PurchaseDocumentService:
    def create_document(self, ...):
        return self.facade.create(...)           # Document creation
        
    def add_line(self, ...):  
        return self.facade.add_line(...)         # Line management
        
    def transition_status(self, ...):
        return self.facade.transition_to(...)    # Status changes
        
    def calculate_totals(self):
        return self.facade.calculate_totals()    # Financial calculations
```

### With INVENTORY App  

**Automatic via Status Transitions:**
```python  
# NO direct integration! Goes through NOMENCLATURES → INVENTORY

# When delivery transitions to 'completed':
# 1. PURCHASES calls NOMENCLATURES.transition_to('completed')
# 2. NOMENCLATURES.StatusManager checks DocumentTypeStatus
# 3. StatusManager calls INVENTORY.MovementService  
# 4. Inventory movements created automatically

# Result: Purchase documents get inventory integration with ZERO code
```

### With PARTNERS App

**Supplier Validation:**
```python
def _validate_purchase_creation(self, partner, location, lines):
    """Purchase-specific validations"""
    
    # Validate partner is a supplier
    if not hasattr(partner, 'supplier_profile'):
        return Result.error('INVALID_PARTNER', 'Partner must be a supplier')
        
    # Check supplier status
    if not partner.is_active:
        return Result.error('INACTIVE_SUPPLIER', 'Supplier is not active')
        
    # Purchase-specific business rules
    # ... additional validations
```

---

## Usage Patterns

### 1. **Basic Document Creation**

```python
from purchases.services import PurchaseDocumentService

# Initialize service
service = PurchaseDocumentService(user=current_user)

# Create purchase request  
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
    comments='Monthly stock replenishment',
    priority='high',
    expected_delivery_date=date(2025, 9, 15)
)

if result.ok:
    request = result.data['document']
    print(f"Request created: {request.document_number}")
```

### 2. **Document Conversion Workflow**

```python
# Complete procurement workflow
service = PurchaseDocumentService(user=current_user)

# Step 1: Create request
request_result = service.create_document('request', supplier, warehouse, lines)
request = request_result.data['document']

# Step 2: Approve request (status transition)
approval_result = service.facade.transition_to('approved')

# Step 3: Convert to order
order_result = service.convert_to_order(
    request, 
    conversion_data={
        'supplier_order_reference': 'SUP-2025-001',
        'expected_delivery_date': date(2025, 9, 20)
    }
)
order = order_result.data['document']

# Step 4: Confirm order (status transition)
confirm_result = service.facade.transition_to('confirmed')

# Step 5: Convert to delivery
delivery_result = service.convert_to_delivery(
    order,
    delivery_data={
        'delivery_date': date.today(),
        'received_quantities': {
            1: Decimal('48'),  # Line 1: received 48 instead of 50
            2: Decimal('25')   # Line 2: received as ordered
        }
    }
)
delivery = delivery_result.data['document']

# Step 6: Complete delivery (triggers inventory movements!)
complete_result = service.facade.transition_to('completed')
# → Automatic inventory movements created
```

### 3. **Status-Driven Operations**

```python
# The power of status-driven workflow
delivery_service = PurchaseDocumentService(document=delivery, user=user)

# Complete delivery → Create inventory movements
result = delivery_service.facade.transition_to('completed')
# ✅ Inventory movements created automatically

# Cancel delivery → Delete inventory movements  
result = delivery_service.facade.transition_to('cancelled')
# ❌ Inventory movements deleted automatically

# Revival → Recreate inventory movements
result = delivery_service.facade.transition_to('completed')
# ✅ Inventory movements recreated automatically
```

### 4. **Quality Control Workflow**

```python
# Delivery with quality control
delivery = DeliveryReceipt.objects.get(document_number='DEL-001')

# Check individual lines
for line in delivery.lines.all():
    if line.quality_approved is None:
        # Perform quality check
        line.quality_approved = True  # or False
        line.quality_notes = "Passed all checks"
        line.save()

# Update overall delivery quality status
if delivery.lines.filter(quality_approved=False).exists():
    delivery.quality_status = 'partial'
elif delivery.lines.filter(quality_approved__isnull=True).exists():
    delivery.quality_status = 'pending'
else:
    delivery.quality_status = 'approved'
    
delivery.save()

# Complete only after quality approval
if delivery.quality_status == 'approved':
    service = PurchaseDocumentService(document=delivery, user=user)
    result = service.facade.transition_to('completed')
    # → Inventory movements for quality-approved items
```

---

## Configuration

### Document Type Setup

**In NOMENCLATURES admin, configure DocumentTypeStatus for purchase document types:**

```python
# Purchase Request statuses
request_statuses = [
    {'code': 'draft', 'is_initial': True, 'allows_editing': True},
    {'code': 'submitted', 'allows_editing': False}, 
    {'code': 'approved', 'allows_editing': False},
    {'code': 'cancelled', 'is_cancellation': True}
]

# Purchase Order statuses  
order_statuses = [
    {'code': 'draft', 'is_initial': True, 'allows_editing': True},
    {'code': 'confirmed', 'allows_editing': False},
    {'code': 'sent', 'allows_editing': False},
    {'code': 'cancelled', 'is_cancellation': True}
]

# Delivery Receipt statuses (with inventory integration!)
delivery_statuses = [
    {
        'code': 'draft', 
        'is_initial': True, 
        'allows_editing': True,
        'creates_inventory_movements': False
    },
    {
        'code': 'completed',
        'creates_inventory_movements': True,    # 🎯 Key setting!
        'allows_editing': False
    },
    {
        'code': 'cancelled',
        'is_cancellation': True,
        'reverses_inventory_movements': True,   # 🎯 Key setting!
        'allows_editing': True
    }
]
```

### Admin Interface

**Purchase documents get full admin interface with:**
- Document creation/editing forms
- Line inline editing
- Status transition actions  
- Quality control interfaces
- Conversion actions (Request → Order → Delivery)

---

## Performance Considerations

### Query Optimization

**Enhanced Managers:**
```python
# Automatic select_related in managers reduces DB queries
class DeliveryReceiptManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type',
            'location_content_type', 
            'source_order',
            'received_by'
        )
```

**Line Prefetching:**
```python
# When working with documents, always prefetch lines
deliveries = DeliveryReceipt.objects.prefetch_related(
    'lines__product',
    'lines__source_order_line'
)
```

### Code Reduction

**Before Refactoring:** 700+ lines in purchase services  
**After Refactoring:** ~150 lines (75% reduction)

**Achieved through:**
- ✅ Facade pattern delegation
- ✅ Elimination of duplicate validation logic  
- ✅ Shared financial calculation services
- ✅ Unified status management system

---

## Best Practices

### 1. **Always Use the Facade**

```python
# ✅ Good - Use PurchaseDocumentService facade
service = PurchaseDocumentService(user=user)
result = service.create_document('delivery', supplier, location, lines)

# ❌ Avoid - Direct model creation
delivery = DeliveryReceipt.objects.create(...)  # Skips validations, numbering, etc.
```

### 2. **Handle Conversions Properly**

```python  
# ✅ Good - Full conversion with error handling
conversion_result = service.convert_to_order(request, conversion_data)
if conversion_result.ok:
    order = conversion_result.data['document']
    # Mark request as converted
    request.status = 'converted'
    request.save()
else:
    logger.error(f"Conversion failed: {conversion_result.msg}")

# ❌ Avoid - Manual document creation without proper linking
order = PurchaseOrder.objects.create(...)  # No link to source request
```

### 3. **Use Status Transitions**

```python
# ✅ Good - Use facade for status changes  
result = service.facade.transition_to('completed')
# Handles validation, inventory, logging automatically

# ❌ Avoid - Direct status field updates
delivery.status = 'completed'  # No validation, no inventory integration
delivery.save()
```

### 4. **Leverage Generic Input Format**

```python
# ✅ Good - Consistent input format for all document types
lines_format = [
    {
        'product': product,
        'quantity': Decimal('10'),     # Always use 'quantity'
        'unit_price': Decimal('25')    # Always use 'unit_price'  
    }
]

# Works for all document types:
service.create_document('request', ...)    # → requested_quantity
service.create_document('order', ...)      # → ordered_quantity
service.create_document('delivery', ...)   # → received_quantity
```

---

## Troubleshooting

### Common Issues

**1. Inventory Movements Not Created:**
```python
# Check DocumentTypeStatus configuration
status_config = DocumentTypeStatus.objects.get(
    document_type__name='Delivery Receipt',
    status__code='completed'
)
print(f"Creates movements: {status_config.creates_inventory_movements}")
# Should be True for automatic inventory integration
```

**2. Conversion Failures:**
```python
# Check source document status
if request.status not in ['approved', 'confirmed']:
    # Request must be approved before conversion to order
    
if order.status not in ['confirmed', 'sent']:
    # Order must be confirmed before conversion to delivery
```

**3. Quality Control Issues:**
```python
# Check line-level quality status
for line in delivery.lines.all():
    if line.quality_approved is None:
        print(f"Line {line.line_number} pending quality check")
```

---

## Dependencies

**PURCHASES depends on:**
- `core` - Base infrastructure, Result pattern
- `nomenclatures` - DocumentService facade (main dependency!)
- `products` - Product models for lines
- `partners` - Supplier models
- `inventory` - Location models

**No other apps depend on PURCHASES:**
- PURCHASES is a leaf node in the dependency graph
- All integration happens through NOMENCLATURES facade

---

## Version History

- **v1.0** - Basic purchase models and services (700+ lines)
- **v1.5** - Integration with nomenclatures services  
- **v2.0** - Facade pattern implementation, thin wrapper refactoring
- **v2.1** - Document conversion workflows
- **v2.2** - Quality control features
- **v2.3** - Complete inventory integration via status transitions (150 lines, 75% reduction)

---

*Last Updated: 2025-08-29*  
*Version: 2.3*  
*Status: ✅ Production Ready - Fully Integrated with NOMENCLATURES Facade*