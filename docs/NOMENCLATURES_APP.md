# NOMENCLATURES App Documentation

## 🎯 Overview

The **NOMENCLATURES app** is the **heart of OptimaPOS** - it provides the unified document management system, status workflow engine, and serves as the **facade** for all document operations across the system.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Core Services](#core-services)
3. [Models](#models)
4. [Status-Driven Workflow](#status-driven-workflow)
5. [Document Lifecycle](#document-lifecycle)
6. [Service Integration](#service-integration)
7. [Usage Patterns](#usage-patterns)
8. [Configuration](#configuration)

---

## Architecture

```
NOMENCLATURES App Structure:
├── services/                    # The service layer - MAIN LOGIC
│   ├── document_service.py     # 🏛️ FACADE - Main entry point
│   ├── status_manager.py       # 🔄 Status transitions + inventory integration  
│   ├── document_line_service.py # 📋 Line operations
│   ├── vat_calculation_service.py # 💰 VAT and financial calculations
│   ├── validator.py            # ✅ Business validations
│   ├── creator.py              # 🆕 Document creation logic
│   ├── query.py                # 🔍 Query operations  
│   └── numbering_service.py    # 📄 Document numbering
├── models/                      # Configuration models
│   ├── documents.py            # Base document models
│   ├── statuses.py             # Status configuration system
│   └── types.py                # Document types
├── mixins/                      # Reusable model mixins
│   └── financial.py            # Financial calculation mixins
└── admin/                       # Admin interface
```

### Key Design Principles

- **🏛️ Facade Pattern** - DocumentService as single entry point
- **⚙️ Configuration-Driven** - Everything controlled by DocumentTypeStatus  
- **🔄 Status-Driven Inventory** - "Статусите дирижират движенията"
- **🎯 Separation of Concerns** - Each service has single responsibility
- **🔌 Service Integration** - Clean interfaces to other apps

---

## Core Services

### 1. **DocumentService** - The Main Facade 🏛️

**Purpose:** Single entry point for ALL document operations across the system.

```python
from nomenclatures.services import DocumentService

# Initialize  
service = DocumentService(document=delivery, user=user)

# Main operations
result = service.create(**kwargs)                    # Create documents
result = service.transition_to('completed')         # Change status  
result = service.add_line(product, quantity=10)     # Add line
result = service.calculate_totals()                 # Recalculate
permissions = service.get_permissions()            # Check what user can do
```

**Internal Collaborators:**
```python
class DocumentService:
    def __init__(self):
        self._creator = DocumentCreator()           # Document creation
        self._validator = DocumentValidator()       # Business validations  
        self._status_manager = StatusManager()      # Status transitions
        self._line_service = DocumentLineService()  # Line operations
        self._vat_service = VATCalculationService() # Financial calculations
```

**Public API:**
- `create()` - Create new document with validation
- `transition_to(status)` - Change document status  
- `add_line(product, quantity)` - Add document line
- `remove_line(line_number)` - Remove document line
- `calculate_totals()` - Recalculate financial totals
- `get_permissions()` - Check user permissions
- `get_available_actions()` - Get possible status transitions

### 2. **StatusManager** - Status Transitions + Inventory 🔄

**Purpose:** Handles ALL status transitions and automatically manages inventory movements.

```python
from nomenclatures.services import StatusManager

# Main operation - handles everything automatically
result = StatusManager.transition_document(
    document=delivery,
    to_status='completed',
    user=user,
    comments='Ready for inventory'
)
```

**Core Logic - Configuration-Driven:**
```python
# StatusManager reads DocumentTypeStatus configuration:
if new_status_config.creates_inventory_movements:
    # Automatically create.html inventory movements
    MovementService.process_document_movements(document)
    
if new_status_config.reverses_inventory_movements:  
    # Automatically delete inventory movements
    InventoryMovement.objects.filter(source_document_number=document.document_number).delete()
```

**Workflow Examples:**
```python
# Normal workflow
StatusManager.transition_document(delivery, 'draft')      # No movements
StatusManager.transition_document(delivery, 'completed')  # ✅ Creates movements
StatusManager.transition_document(delivery, 'cancelled')  # ❌ Deletes movements

# Revival workflow  
StatusManager.transition_document(delivery, 'completed')  # ✅ Recreates movements
```

### 3. **DocumentLineService** - Line Operations 📋

**Purpose:** Handles all document line operations with automatic field mapping.

```python
from nomenclatures.services.document_line_service import DocumentLineService

line_service = DocumentLineService()

# Add line - automatically maps 'quantity' to correct field
result = line_service.add_line(
    document=delivery,
    product=product, 
    quantity=Decimal('10.5'),  # Maps to 'received_quantity' for DeliveryLine
    unit_price=Decimal('25.0')
)
```

**Field Mapping Logic:**
```python
def _get_quantity_field(line_class):
    """Automatic mapping based on line type"""
    field_names = [field.name for field in line_class._meta.fields]
    
    if 'requested_quantity' in field_names:
        return 'requested_quantity'      # PurchaseRequestLine
    elif 'ordered_quantity' in field_names:
        return 'ordered_quantity'        # PurchaseOrderLine  
    elif 'received_quantity' in field_names:
        return 'received_quantity'       # DeliveryLine
    else:
        return 'quantity'                # Generic fallback
```

### 4. **VATCalculationService** - Financial Engine 💰

**Purpose:** Handles ALL VAT and financial calculations across the system.

```python
from nomenclatures.services.vat_calculation_service import VATCalculationService

# Document-level calculations
result = VATCalculationService.calculate_document_vat(document)

# Line-level calculations  
result = VATCalculationService.calculate_line_vat(
    line=delivery_line,
    entered_price=Decimal('30.00'),
    save=True
)
```

**Calculation Flow:**
1. **Price Entry Mode Detection** - With or without VAT
2. **Unit Price Calculation** - Convert entered price to stored price
3. **VAT Calculation** - Apply correct VAT rate
4. **Line Totals** - Calculate line amounts  
5. **Document Totals** - Sum all lines + apply document-level discounts

**Field Mapping for Different Models:**
```python
# Automatically maps calculation results to correct fields
field_mapping = {
    'unit_price': 'unit_price_with_vat',     # For FinancialLineMixin
    'vat_amount_per_unit': 'vat_amount',     # VAT per unit
    'line_total_without_vat': 'net_amount',  # Line subtotal
    'line_total_with_vat': 'gross_amount',   # Line total with VAT
}
```

### 5. **DocumentValidator** - Business Rules ✅

**Purpose:** Centralized business validation for all document operations.

```python
from nomenclatures.services.validator import DocumentValidator

# Validate document creation
result = DocumentValidator.validate_document_creation(
    document_type='delivery_receipt',
    partner=supplier,
    location=warehouse,
    lines_data=lines
)

# Validate status transition
result = DocumentValidator.validate_status_transition(
    document=delivery,
    from_status='draft',
    to_status='completed',
    user=user
)
```

**Validation Categories:**
- **Document-level:** Partner compatibility, location permissions, amounts
- **Line-level:** Product availability, quantities, pricing  
- **Status-level:** Transition permissions, business rules
- **User-level:** Access permissions, approval requirements

---

## Models

### 1. **Base Document Models** (`models/documents.py`)

```python
class BaseDocument(TimeStampedModel, UserTrackingModel):
    """Base class for all documents"""
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
    """Base class for all document lines"""
    line_number = models.PositiveIntegerField()
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    unit = models.ForeignKey('products.Unit', on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
```

### 2. **Status Configuration System** (`models/statuses.py`)

The **heart of the configuration-driven system:**

```python
class DocumentStatus(models.Model):
    """Global status definitions"""
    code = models.CharField(max_length=50, unique=True)  # 'draft', 'completed'
    name = models.CharField(max_length=100)              # 'Draft', 'Completed'
    is_active = models.BooleanField(default=True)

class DocumentTypeStatus(models.Model):
    """Configuration that controls EVERYTHING"""
    document_type = models.ForeignKey('DocumentType', on_delete=models.CASCADE)
    status = models.ForeignKey('DocumentStatus', on_delete=models.CASCADE)
    
    # Workflow configuration
    is_initial = models.BooleanField(default=False)      # Starting status
    is_final = models.BooleanField(default=False)        # Ending status
    is_cancellation = models.BooleanField(default=False) # Cancellation status
    
    # 🎯 INVENTORY INTEGRATION - The magic happens here!
    creates_inventory_movements = models.BooleanField(default=False)     # Create movements on entry
    reverses_inventory_movements = models.BooleanField(default=False)    # Delete movements on entry
    allows_movement_correction = models.BooleanField(default=False)      # Allow sync operations
    auto_correct_movements_on_edit = models.BooleanField(default=False)  # Auto-sync on document edit
    
    # Document permissions  
    allows_editing = models.BooleanField(default=True)   # Can edit document  
    allows_deletion = models.BooleanField(default=False) # Can delete document
    
    sort_order = models.PositiveIntegerField(default=0)  # Workflow order
```

**Example Configuration:**
```python
# Delivery Receipt workflow
draft_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type,
    status=draft_status,
    is_initial=True,                        # Starting point
    allows_editing=True,                    # Can modify
    creates_inventory_movements=False       # No inventory yet
)

completed_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type,
    status=completed_status,
    creates_inventory_movements=True,       # ✅ Create inventory on completion
    allows_editing=False                    # Read-only after completion
)

cancelled_status = DocumentTypeStatus.objects.create(
    document_type=delivery_receipt_type, 
    status=cancelled_status,
    is_cancellation=True,                   # Special cancellation status
    reverses_inventory_movements=True,      # ❌ Delete inventory on cancellation
    allows_editing=True                     # Can edit cancelled docs
)
```

---

## Status-Driven Workflow

### Core Principle: "Статусите дирижират движенията"

**Configuration Controls Everything:**

```python
# When document transitions to new status:
if new_status_config.creates_inventory_movements:
    # ✅ Automatically create.html inventory movements
    from inventory.services import MovementService
    result = MovementService.process_document_movements(document)
    
if new_status_config.reverses_inventory_movements:
    # ❌ Automatically delete inventory movements  
    InventoryMovement.objects.filter(
        source_document_number=document.document_number
    ).delete()
```

### Workflow Examples

**1. Normal Delivery Workflow:**
```
📦 DELIVERY LIFECYCLE:
draft → completed → [business complete]
  ↓        ↓
 🚫      ✅ create movements
edit    read-only
```

**2. Cancellation Workflow:**  
```
📦 CANCELLATION:
completed → cancelled
    ↓          ↓  
✅ has       ❌ delete  
movements   movements
```

**3. Revival Workflow:**
```
📦 REVIVAL:  
cancelled → completed
    ↓          ↓
❌ no      ✅ recreate
movements  movements  
```

### Configuration-Driven Benefits

- ✅ **No hardcoded logic** - Everything driven by configuration
- ✅ **Easy customization** - Change behavior via admin interface
- ✅ **Consistent behavior** - Same rules across all document types
- ✅ **Audit trail** - All changes tracked through status transitions
- ✅ **Reversible operations** - Can undo any operation by status change

---

## Document Lifecycle

### Phase 1: Creation
```python
# DocumentCreator handles initial setup
result = DocumentService.create(
    document_type='delivery_receipt',
    partner=supplier,
    location=warehouse,
    lines=[...],
    **kwargs
)
# → Document created in 'draft' status (is_initial=True)
```

### Phase 2: Line Management
```python
# DocumentLineService handles line operations
service.add_line(product, quantity=10, unit_price=25)
service.remove_line(line_number=2) 
service.calculate_totals()  # VATCalculationService recalculates
```

### Phase 3: Status Transitions
```python
# StatusManager handles workflow + inventory integration
result = service.transition_to('completed')
# → Automatic inventory movement creation
# → Document becomes read-only (allows_editing=False)

result = service.transition_to('cancelled')  
# → Automatic inventory movement deletion
# → Document becomes editable again (allows_editing=True)
```

### Phase 4: Revival (Optional)
```python  
# Revival workflow - back to active status
result = service.transition_to('completed')
# → Inventory movements recreated
# → Full document restoration
```

---

## Service Integration

### How NOMENCLATURES Integrates with Other Apps

**PURCHASES App Integration:**
```python
# PURCHASES uses NOMENCLATURES as facade
from nomenclatures.services import DocumentService

class PurchaseDocumentService:
    def __init__(self, user):
        self.facade = DocumentService(user=user)  # Delegate everything!
        
    def create_document(self, doc_type, partner, location, lines):
        return self.facade.create(...)  # Use nomenclatures facade
```

**INVENTORY App Integration:**
```python
# NOMENCLATURES calls INVENTORY for movements
from inventory.services import MovementService

# In StatusManager:
if new_status_config.creates_inventory_movements:
    result = MovementService.process_document_movements(document)
```

**PRICING App Integration:**
```python  
# VATCalculationService uses pricing for rates
from pricing.services import PricingService

vat_rate = PricingService.get_vat_rate(product, location)
```

---

## Usage Patterns

### 1. **Facade Pattern Usage**

```python
# ✅ Always use DocumentService as entry point
from nomenclatures.services import DocumentService

def create_purchase_order(partner, location, lines, user):
    service = DocumentService(user=user)
    return service.create(
        document_type='purchase_order',
        partner=partner,
        location=location, 
        lines=lines
    )

# ❌ Don't access internal services directly
from nomenclatures.services.creator import DocumentCreator  # Avoid this
```

### 2. **Status Transition Pattern**

```python
# ✅ Use transition_document for status changes
from nomenclatures.services import StatusManager

result = StatusManager.transition_document(
    document=delivery,
    to_status='completed', 
    user=user,
    comments='Quality check passed'
)

# This automatically:
# - Validates transition is allowed
# - Updates document status
# - Creates inventory movements (if configured)
# - Logs the transition
# - Updates permissions
```

### 3. **Configuration-First Approach**

```python
# ✅ Configure behavior via DocumentTypeStatus 
# Don't hardcode business logic in code

# Configure in admin or via code:
DocumentTypeStatus.objects.filter(
    document_type__code='delivery_receipt',
    status__code='received'
).update(creates_inventory_movements=True)

# The system automatically follows the configuration
```

### 4. **Result Pattern Usage**

```python
# ✅ Always handle Results properly
result = service.create_document(...)

if result.ok:
    document = result.data['document'] 
    print(f"Created: {document.document_number}")
else:
    logger.error(f"Failed: {result.msg}")
    return HttpResponse(result.msg, status=400)
```

---

## Configuration

### Admin Interface Configuration

**DocumentTypeStatus Configuration:**

1. **Workflow Setup:**
   - `is_initial` - Mark starting status
   - `is_final` - Mark ending status  
   - `is_cancellation` - Mark cancellation status
   - `sort_order` - Define workflow sequence

2. **Inventory Integration:**
   - `creates_inventory_movements` - Auto-create on status entry
   - `reverses_inventory_movements` - Auto-delete on status entry
   - `allows_movement_correction` - Permit sync operations
   - `auto_correct_movements_on_edit` - Auto-sync on document changes

3. **Permissions:**
   - `allows_editing` - Control document editability
   - `allows_deletion` - Control document deletion

### Example Configurations

**Delivery Receipt Workflow:**
```python
statuses = [
    {
        'status': 'draft',
        'is_initial': True,
        'allows_editing': True,
        'creates_inventory_movements': False
    },
    {
        'status': 'completed', 
        'creates_inventory_movements': True,  # ✅ Key configuration!
        'allows_editing': False
    },
    {
        'status': 'cancelled',
        'is_cancellation': True,
        'reverses_inventory_movements': True,  # ❌ Key configuration!
        'allows_editing': True
    }
]
```

---

## Best Practices

### 1. **Always Use the Facade**
```python
# ✅ Good
from nomenclatures.services import DocumentService
service = DocumentService(document, user)
result = service.transition_to('completed')

# ❌ Avoid  
from nomenclatures.services.status_manager import StatusManager
StatusManager.transition_document(...)  # Skip facade
```

### 2. **Configure, Don't Code**
```python
# ✅ Good - Configure in DocumentTypeStatus
creates_inventory_movements = True  # In admin interface

# ❌ Avoid - Hardcode in business logic
if document.status == 'completed':  # Hardcoded logic
    create_inventory_movements()
```

### 3. **Use Result Pattern**  
```python
# ✅ Good
result = service.create_document(...)
if result.ok:
    return result.data
else:
    handle_error(result.msg)

# ❌ Avoid
try:
    document = service.create_document(...)  # Can raise exceptions
except Exception as e:
    handle_error(str(e))
```

### 4. **Leverage Status-Driven Workflow**
```python  
# ✅ Good - Let status drive behavior
transition_result = service.transition_to('completed')
# Inventory movements created automatically based on configuration

# ❌ Avoid - Manual inventory management
service.transition_to('completed') 
create_inventory_movements(document)  # Manual, error-prone
```

---

## Dependencies

**NOMENCLATURES depends on:**
- `core` - Base infrastructure, Result pattern, interfaces
- `products` - Product models for document lines
- `inventory` - MovementService for inventory integration  
- `pricing` - PricingService for VAT calculations

**Apps that depend on NOMENCLATURES:**
- `purchases` - Uses DocumentService facade
- `sales` - Uses DocumentService facade (if implemented)
- `inventory` - Receives calls from StatusManager

---

## Version History

- **v1.0** - Basic document models
- **v1.5** - Service layer introduction
- **v2.0** - Facade pattern implementation
- **v2.1** - Status-driven workflow system  
- **v2.2** - Inventory integration
- **v2.3** - Configuration-driven architecture

---

*Last Updated: 2025-08-29*  
*Version: 2.3*  
*Status: ✅ Production Ready*