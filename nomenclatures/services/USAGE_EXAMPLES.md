# DocumentService Usage Examples

## 🎯 Overview

`DocumentService` е унифициран facade за всички document операции в OptimaPOS системата. Централизира достъпа до всички services и скрива сложността на конфигурационната система.

## 📚 Basic Usage

### 1. Creating Documents

```python
from nomenclatures.services import DocumentService
from purchases.models import PurchaseRequest

# Create new purchase request
request = PurchaseRequest()
request.supplier = supplier
request.location = warehouse

# Use DocumentService to create.html with auto-numbering
service = DocumentService(request, user)
result = service.create()

if result.ok:
    print(f"✅ Created: {request.document_number}")
else:
    print(f"❌ Error: {result.msg}")
```

### 2. Adding Lines to Documents

```python
from decimal import Decimal

# Add product lines
service = DocumentService(request, user)

# Add first product
result = service.add_line(
    product=product1,
    quantity=Decimal('10'),
    unit_price=Decimal('25.50'),
    notes="Urgent delivery needed"
)

# Add second product  
result = service.add_line(
    product=product2,
    quantity=Decimal('5'),
    unit_price=Decimal('15.00')
)
```

### 3. Status Transitions

```python
# Submit for approval
service = DocumentService(request, user)
result = service.transition_to('submitted', 'Ready for manager review')

if result.ok:
    print(f"Status changed to: {result.data['new_status']}")

# Approve document
manager_service = DocumentService(request, manager_user)  
result = manager_service.transition_to('approved', 'Budget approved')
```

### 4. Calculating Totals

```python
# Calculate VAT and totals
service = DocumentService(request, user)
result = service.calculate_totals()

if result.ok:
    totals = result.data
    print(f"Subtotal: {totals['net_total']} BGN")
    print(f"VAT: {totals['vat_total']} BGN") 
    print(f"Total: {totals['gross_total']} BGN")
```

## 🔐 Permissions and Actions

### 1. Check Permissions

```python
service = DocumentService(request, user)

# Basic permission checks
can_edit = service.can_edit()
can_delete = service.can_delete()

# Get detailed permissions
permissions = service.get_permissions()
print(f"Can edit: {permissions.get('can_edit')}")
print(f"Reason: {permissions.get('edit_reason')}")
```

### 2. Get Available Actions

```python
# Get context-aware actions for UI
service = DocumentService(request, user)
actions = service.get_available_actions()

for action in actions:
    print(f"Action: {action['action']}")
    print(f"Label: {action['label']}")
    print(f"Style: {action['button_style']}")
    print(f"Icon: {action['icon']}")
```

## 📊 Bulk Operations

### 1. Bulk Status Transitions

```python
# Approve multiple purchase requests
requests = PurchaseRequest.objects.filter(status='submitted')

result = DocumentService.bulk_status_transition(
    documents=requests,
    target_status='approved',
    user=manager,
    comments='Batch approval - budget Q1'
)

print(f"✅ Approved: {len(result.data['successful'])}")
print(f"❌ Failed: {len(result.data['failed'])}")
```

### 2. Query Operations

```python
# Get active documents across all types
active_docs = DocumentService.get_active_documents()

# Get documents pending approval
pending = DocumentService.get_pending_approval_documents()

# Get documents ready for processing
ready = DocumentService.get_ready_for_processing_documents()
```

## 🏪 POS-Specific Examples

### 1. Quick Sale (commented in code - uncomment when sales app is ready)

```python
# Quick POS sale transaction  
# items = [
#     {'product': coke, 'quantity': 2, 'price': Decimal('2.50')},
#     {'product': bread, 'quantity': 1, 'price': Decimal('1.20')}
# ]
# 
# result = DocumentService.quick_sale(
#     items=items,
#     location=shop_location, 
#     user=cashier,
#     customer=customer
# )
# 
# if result.ok:
#     invoice = result.data['invoice']
#     print(f"Sale completed: {invoice.document_number}")
#     print(f"Total: {result.data['total_amount']} BGN")
```

### 2. Process Return (commented in code)

```python
# Process product return
# return_items = [
#     {'product': coke, 'quantity': 1}  # Return 1 coke
# ]
# 
# result = DocumentService.process_return(
#     original_invoice=invoice,
#     return_items=return_items,
#     user=cashier,
#     reason='Product defect'
# )
```

### 3. Daily Closing (commented in code)

```python
# End-of-day closing
# result = DocumentService.daily_closing(
#     location=shop_location,
#     user=manager
# )
# 
# if result.ok:
#     summary = result.data
#     print(f"Sales: {summary['sales']['count']} transactions")
#     print(f"Net sales: {summary['net_sales']} BGN")
```

## ⚙️ Configuration Utilities

### 1. Document Configuration

```python
service = DocumentService(request, user)
config = service.get_document_config()

# Document type info
doc_type = config['document_type']
print(f"Type: {doc_type['name']}")
print(f"Affects inventory: {doc_type['affects_inventory']}")
print(f"Is fiscal: {doc_type['is_fiscal']}")

# Current status info  
status = config['current_status']
print(f"Status: {status['name']}")
print(f"Allows editing: {status['allows_editing']}")
print(f"Creates movements: {status['creates_inventory_movements']}")
```

### 2. Preview Next Number

```python
service = DocumentService(request, user)
next_number = service.preview_next_number()
print(f"Next document number will be: {next_number}")
```

## 🔄 Backward Compatibility

```python
# Old style - still works
from nomenclatures.services import (
    create_document,
    transition_document,
    can_edit_document
)

# Old function calls
success = create_document(request, user)
result = transition_document(request, 'submitted', user, 'Comments')
can_edit, reason = can_edit_document(request, user)
```

## 🧪 Error Handling

```python
service = DocumentService(request, user)

# All methods return Result objects
result = service.create()

if result.ok:
    # Success
    data = result.data
    message = result.msg
    print(f"✅ {message}")
else:
    # Error
    error_code = result.code
    error_message = result.msg
    print(f"❌ {error_code}: {error_message}")
```

## 🎛️ Advanced Usage

### 1. Custom Configuration Caching

```python
# Configuration is automatically cached per document type + status
service = DocumentService(request, user)

# First call - queries database
config1 = service.get_document_config()

# Second call - uses cache
config2 = service.get_document_config()  # Faster!
```

### 2. Integration with Views

```python
# Django view example
from django.http import JsonResponse
from nomenclatures.services import DocumentService

def approve_document(request, document_id):
    document = get_object_or_404(PurchaseRequest, id=document_id)
    
    service = DocumentService(document, request.user)
    
    # Check permissions first
    if not service.can_edit():
        return JsonResponse({
            'success': False,
            'error': 'Permission denied'
        })
    
    # Perform transition
    result = service.transition_to('approved', 'Web approval')
    
    return JsonResponse({
        'success': result.ok,
        'message': result.msg,
        'new_status': result.data.get('new_status') if result.ok else None
    })
```

### 3. Custom Line Operations

```python
service = DocumentService(request, user)

# Add line with custom attributes
result = service.add_line(
    product=product,
    quantity=Decimal('10'),
    unit_price=Decimal('25.00'),
    discount_percent=Decimal('5.0'),
    notes="Promotional price",
    delivery_date='2024-03-15'
)

# Remove specific line
result = service.remove_line(line_number=2)
```

## 🚨 Important Notes

1. **Always check Result.ok** before using result data
2. **Use decimal.Decimal** for all monetary amounts
3. **Pass user parameter** for audit trail and permissions
4. **Cache DocumentService instances** for multiple operations on same document
5. **Use bulk operations** for processing multiple documents

## 🔧 Troubleshooting

### Common Issues

1. **"Document instance required"** - Pass document to constructor
2. **"User required for status transitions"** - Pass user to constructor  
3. **Permission denied** - Check user permissions and document status
4. **Configuration errors** - Ensure DocumentType and DocumentTypeStatus are configured
5. **Numbering failures** - Check NumberingConfiguration for document type