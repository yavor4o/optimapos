# CORE App Documentation

## 🎯 Overview

The **CORE app** provides the foundational infrastructure for OptimaPOS - base models, utilities, interfaces, and shared components that all other apps depend on.

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Core Components](#core-components)
3. [Interfaces](#interfaces)
4. [Utils](#utils)
5. [Models](#models)
6. [Usage Patterns](#usage-patterns)
7. [Integration Points](#integration-points)

---

## Architecture

```
CORE App Structure:
├── interfaces/          # Abstract interfaces for all services
├── utils/              # Shared utilities (Result pattern, etc.)
├── models/             # Base models and mixins  
├── views.py            # Basic views
└── __init__.py
```

### Core Design Principles

- **🏗️ Foundation First** - Provides base infrastructure
- **🔌 Interface-Driven** - Defines contracts for all services
- **⚡ Result Pattern** - Standardized error handling
- **♻️ Reusability** - Shared components across apps

---

## Core Components

### 1. **Result Pattern** (`core/utils/result.py`)

Standardized return type for all service operations:

```python
from core.utils.result import Result

# Success case
return Result.success(
    data={'document': delivery}, 
    msg='Document created successfully'
)

# Error case  
return Result.error(
    code='VALIDATION_FAILED',
    msg='Required fields missing'
)

# Usage
result = service.create_document(...)
if result.ok:
    document = result.data['document']
else:
    print(f"Error: {result.msg}")
```

**Benefits:**
- ✅ Consistent error handling across all apps
- ✅ No exceptions for business logic failures
- ✅ Rich error information with codes
- ✅ Chainable operations

### 2. **Base Models** (`core/models/`)

Provides abstract base models that other apps inherit:

```python
# Example usage in other apps
from core.models import TimeStampedModel

class Product(TimeStampedModel):
    # Automatically gets created_at, updated_at fields
    name = models.CharField(max_length=200)
```

**Available Base Models:**
- `TimeStampedModel` - Adds created_at, updated_at
- `UserTrackingModel` - Adds created_by, updated_by  
- `ActiveModel` - Adds is_active field with manager

---

## Interfaces

The **interfaces/** directory defines contracts for all major services:

### Available Interfaces

| Interface | Purpose | Used By |
|-----------|---------|---------|
| `IDocumentService` | Document operations | nomenclatures, purchases |
| `IInventoryService` | Inventory management | inventory app |
| `IMovementService` | Inventory movements | inventory app |
| `IPricingService` | Price calculations | pricing app |
| `IVATCalculationService` | VAT computations | nomenclatures |
| `ISupplierService` | Supplier operations | partners app |
| `ILocation` | Location interface | inventory, pricing |

### Example Interface Usage

```python
from core.interfaces import IDocumentService

class MyDocumentService(IDocumentService):
    def create_document(self, model_class, data, user, location) -> Result:
        # Implementation here
        pass
        
    def transition_document(self, document, to_status, user, comments) -> Result:
        # Implementation here  
        pass
```

**Benefits:**
- ✅ Enforces consistent API across implementations
- ✅ Makes testing easier with mocks
- ✅ Clear contracts between apps
- ✅ IDE support with type hints

---

## Utils

### 1. **Result Pattern** (`utils/result.py`)

See detailed description above in Core Components.

### 2. **Common Utilities**

```python
# Example additional utils that might be here
from core.utils.validators import validate_decimal
from core.utils.formatters import format_currency
from core.utils.dates import normalize_date
```

---

## Models

### Base Model Examples

```python
# core/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class TimeStampedModel(models.Model):
    """Base model with timestamp tracking"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class UserTrackingModel(TimeStampedModel):
    """Base model with user tracking"""
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+', null=True)
    
    class Meta:
        abstract = True

class ActiveModel(models.Model):
    """Base model with active/inactive functionality"""
    is_active = models.BooleanField(default=True)
    
    objects = models.Manager()  # Default manager
    active_objects = ActiveManager()  # Only active records
    
    class Meta:
        abstract = True
```

---

## Usage Patterns

### 1. **Service Implementation Pattern**

```python
from core.interfaces import IDocumentService
from core.utils.result import Result

class MyService(IDocumentService):
    def create_document(self, model_class, data, user, location) -> Result:
        try:
            # Business logic here
            document = model_class.objects.create(**data)
            return Result.success(data={'document': document})
        except Exception as e:
            return Result.error('CREATION_FAILED', str(e))
```

### 2. **Result Handling Pattern**

```python
# In views or other services
def my_view(request):
    service = MyService()
    result = service.create_document(...)
    
    if result.ok:
        # Success path
        return JsonResponse({
            'success': True,
            'data': result.data
        })
    else:
        # Error path
        return JsonResponse({
            'success': False,
            'error': result.msg,
            'code': result.code
        }, status=400)
```

### 3. **Base Model Inheritance**

```python
# In any app
from core.models import TimeStampedModel, UserTrackingModel

class MyModel(TimeStampedModel, UserTrackingModel):
    """Gets timestamp and user tracking automatically"""
    name = models.CharField(max_length=100)
    
    def save(self, *args, **kwargs):
        # Custom save logic
        super().save(*args, **kwargs)
```

---

## Integration Points

### How Other Apps Use CORE

**NOMENCLATURES App:**
- Inherits from `IDocumentService` 
- Uses `Result` pattern for all operations
- Extends base models for documents

**PURCHASES App:**  
- Uses CORE interfaces to define service contracts
- Leverages `Result` pattern for error handling
- Inherits base models for purchase documents

**INVENTORY App:**
- Implements `IInventoryService` and `IMovementService`
- Uses `Result` pattern for movement operations
- Base models for inventory tracking

**PRICING App:**
- Implements `IPricingService`
- Uses `Result` for price calculations
- Base models for pricing rules

**PARTNERS App:**
- Implements partner-related interfaces
- Uses base models for suppliers/customers
- `Result` pattern for partner operations

---

## Best Practices

### 1. **Always Use Result Pattern**
```python
# ✅ Good
def create_something() -> Result:
    if validation_fails:
        return Result.error('VALIDATION_FAILED', 'Details here')
    return Result.success(data={'item': item})

# ❌ Avoid
def create_something():
    if validation_fails:
        raise ValidationError('Details here')  # Don't use exceptions for business logic
```

### 2. **Implement Interfaces**
```python
# ✅ Good - implements interface
class DocumentService(IDocumentService):
    def create_document(self, ...):  # Must implement all interface methods
        pass

# ❌ Avoid - no interface contract
class DocumentService:  # Hard to test, no contract
    def create_doc(self, ...):  # Different method names across services
        pass
```

### 3. **Use Base Models**
```python
# ✅ Good
class Product(TimeStampedModel, UserTrackingModel):
    name = models.CharField(max_length=200)
    # Gets created_at, updated_at, created_by, updated_by automatically

# ❌ Avoid
class Product(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)  # Duplicated logic
    updated_at = models.DateTimeField(auto_now=True)
```

---

## Dependencies

**CORE app depends on:**
- Django framework only
- No other OptimaPOS apps

**Other apps depend on CORE:**
- ALL other OptimaPOS apps import from CORE
- CORE must be in INSTALLED_APPS before other custom apps

---

## Testing

```python
# Example test using CORE components
from core.utils.result import Result
from core.interfaces import IDocumentService

class TestDocumentService(IDocumentService):
    """Mock implementation for testing"""
    def create_document(self, *args, **kwargs):
        return Result.success(data={'document': 'mock_doc'})

def test_service():
    service = TestDocumentService()
    result = service.create_document()
    assert result.ok
    assert result.data['document'] == 'mock_doc'
```

---

## Version History

- **v1.0** - Initial CORE app with basic utilities
- **v1.5** - Added interface system
- **v2.0** - Result pattern implementation
- **v2.1** - Enhanced base models

---

*Last Updated: 2025-08-29*  
*Version: 2.1*