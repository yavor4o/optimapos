# StatusResolver Usage Guide

## 🎯 Dynamic Status Resolution System

The `StatusResolver` is the core component that enables configuration-driven status management in OptimaPOS. This guide provides comprehensive usage patterns and best practices.

---

## 📋 Quick Reference

### Core Methods

```python
from nomenclatures.services._status_resolver import StatusResolver

# Basic status resolution
initial = StatusResolver.get_initial_status(document_type)
final_statuses = StatusResolver.get_final_statuses(document_type)
cancellation = StatusResolver.get_cancellation_status(document_type)

# Permission-based resolution
editable = StatusResolver.get_editable_statuses(document_type)
deletable = StatusResolver.get_deletable_statuses(document_type)

# Semantic type resolution
approval_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'approval')
processing_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'processing')
```

### Convenience Functions

```python
from nomenclatures.services._status_resolver import (
    is_initial_status, is_final_status, is_cancellation_status,
    can_edit_in_status, can_delete_in_status
)

# Quick status checks
if is_initial_status(document):
    print("Document is in initial status")

if can_edit_in_status(document):
    print("Document can be edited")
```

---

## 🔧 Detailed Usage Patterns

### 1. Replacing Hardcoded Status Checks

#### ❌ BEFORE (Hardcoded)
```python
# Bad: Hardcoded status names
if document.status == 'draft':
    allow_editing = True

if document.status in ['approved', 'confirmed']:
    ready_for_processing = True
    
if document.status == 'cancelled':
    is_cancelled = True
```

#### ✅ AFTER (Dynamic)
```python
# Good: Configuration-driven  
from nomenclatures.services._status_resolver import StatusResolver

# Check if document can be edited
editable_statuses = StatusResolver.get_editable_statuses(document.document_type)
allow_editing = document.status in editable_statuses

# Check if ready for processing
processing_statuses = StatusResolver.get_statuses_by_semantic_type(
    document.document_type, 'processing'
)
ready_for_processing = document.status in processing_statuses

# Check if cancelled
cancellation_status = StatusResolver.get_cancellation_status(document.document_type)
is_cancelled = document.status == cancellation_status
```

### 2. Model Manager Methods

#### ❌ BEFORE (Hardcoded)
```python
class PurchaseRequestManager(models.Manager):
    def pending_approval(self):
        return self.filter(status='submitted')
    
    def approved(self):
        return self.filter(status='approved')
        
    def active(self):
        return self.exclude(status__in=['cancelled', 'completed'])
```

#### ✅ AFTER (Dynamic)
```python
class PurchaseRequestManager(models.Manager):
    def pending_approval(self):
        """Documents pending approval - works with any status names"""
        from nomenclatures.services.query import DocumentQuery
        return DocumentQuery.get_pending_approval_documents(queryset=self.get_queryset())
    
    def ready_for_processing(self):
        """Documents ready for processing - works with any status names"""
        from nomenclatures.services.query import DocumentQuery  
        return DocumentQuery.get_ready_for_processing_documents(queryset=self.get_queryset())
        
    def active(self):
        """Active documents - works with any status names"""
        from nomenclatures.services.query import DocumentQuery
        return DocumentQuery.get_active_documents(queryset=self.get_queryset())
```

### 3. View Logic

#### ❌ BEFORE (Hardcoded)
```python
def purchase_request_detail(request, pk):
    purchase_request = get_object_or_404(PurchaseRequest, pk=pk)
    
    # Hardcoded status checks
    can_edit = purchase_request.status in ['draft', 'pending']
    can_approve = purchase_request.status == 'submitted'
    can_convert = purchase_request.status == 'approved'
    
    context = {
        'purchase_request': purchase_request,
        'can_edit': can_edit,
        'can_approve': can_approve, 
        'can_convert': can_convert,
    }
    return render(request, 'purchase_request_detail.html', context)
```

#### ✅ AFTER (Dynamic)
```python
def purchase_request_detail(request, pk):
    purchase_request = get_object_or_404(PurchaseRequest, pk=pk)
    
    from nomenclatures.services._status_resolver import StatusResolver
    
    # Dynamic status checks
    editable_statuses = StatusResolver.get_editable_statuses(purchase_request.document_type)
    can_edit = purchase_request.status in editable_statuses
    
    # Get approval statuses semantically
    approval_statuses = StatusResolver.get_statuses_by_semantic_type(
        purchase_request.document_type, 'approval'
    )
    can_approve = purchase_request.status in approval_statuses
    
    # Get processing statuses semantically
    processing_statuses = StatusResolver.get_statuses_by_semantic_type(
        purchase_request.document_type, 'processing'  
    )
    can_convert = purchase_request.status in processing_statuses
    
    context = {
        'purchase_request': purchase_request,
        'can_edit': can_edit,
        'can_approve': can_approve,
        'can_convert': can_convert,
    }
    return render(request, 'purchase_request_detail.html', context)
```

### 4. Business Logic in Services

#### ❌ BEFORE (Hardcoded)
```python
class PurchaseRequestService:
    @staticmethod
    def can_convert_to_order(request):
        # Hardcoded business rules
        if request.status != 'approved':
            return False
            
        if request.lines.count() == 0:
            return False
            
        return True
```

#### ✅ AFTER (Dynamic)
```python
class PurchaseRequestService:
    @staticmethod
    def can_convert_to_order(request):
        from nomenclatures.services._status_resolver import StatusResolver
        
        # Dynamic status check
        processing_statuses = StatusResolver.get_statuses_by_semantic_type(
            request.document_type, 'processing'
        )
        
        if request.status not in processing_statuses:
            return False
            
        if request.lines.count() == 0:
            return False
            
        return True
```

---

## 🌍 Multi-Language Examples

### Bulgarian Status Names

```python
# Configure Bulgarian statuses
bulgarian_config = [
    {'code': 'chernova', 'name': 'Чернова', 'is_initial': True, 'allows_editing': True},
    {'code': 'podadena', 'name': 'Подадена', 'allows_editing': False},
    {'code': 'odobrena', 'name': 'Одобрена', 'allows_editing': False},
    {'code': 'zavyrshena', 'name': 'Завършена', 'is_final': True},
    {'code': 'otkazana', 'name': 'Отказана', 'is_cancellation': True},
]

# StatusResolver automatically works with Bulgarian names
initial = StatusResolver.get_initial_status(document_type)  
# Returns: "chernova"

final_statuses = StatusResolver.get_final_statuses(document_type)
# Returns: {"zavyrshena"}

cancellation = StatusResolver.get_cancellation_status(document_type)
# Returns: "otkazana"
```

### French Status Names

```python
# Configure French statuses
french_config = [
    {'code': 'brouillon', 'name': 'Brouillon', 'is_initial': True},
    {'code': 'soumis', 'name': 'Soumis'},  
    {'code': 'approuve', 'name': 'Approuvé'},
    {'code': 'termine', 'name': 'Terminé', 'is_final': True},
    {'code': 'annule', 'name': 'Annulé', 'is_cancellation': True},
]

# StatusResolver works with French names too!
initial = StatusResolver.get_initial_status(document_type)
# Returns: "brouillon"
```

---

## 🔍 Semantic Type Resolution

The `get_statuses_by_semantic_type()` method uses intelligent pattern matching to group statuses by their semantic meaning.

### Available Semantic Types

#### 1. 'approval' - Statuses related to approval workflow
```python
approval_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'approval')

# Matches statuses containing: 'submit', 'pending', 'review', 'approval'
# Examples: 'submitted', 'pending_approval', 'under_review', 'awaiting_approval'
# Bulgarian: 'podadena', 'na_pregled'
```

#### 2. 'processing' - Statuses ready for processing
```python
processing_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'processing')

# Matches statuses containing: 'approved', 'confirmed', 'ready', 'processing'  
# Examples: 'approved', 'confirmed', 'ready_for_fulfillment'
# Bulgarian: 'odobrena', 'potvyrdena'
```

#### 3. 'completion' - Statuses indicating completion
```python
completion_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'completion')

# Matches statuses containing: 'complete', 'finish', 'final', 'closed'
# Examples: 'completed', 'finalized', 'closed'
# Bulgarian: 'zavyrshena', 'finalizirana'
```

#### 4. 'rejection' - Statuses indicating rejection
```python
rejection_statuses = StatusResolver.get_statuses_by_semantic_type(document_type, 'rejection')

# Matches statuses containing: 'reject', 'deny', 'decline', 'refused'
# Examples: 'rejected', 'denied', 'declined'  
# Bulgarian: 'otkazan', 'otklonen'
```

### Custom Semantic Matching

```python
# You can extend semantic matching by modifying the patterns in _status_resolver.py
def get_statuses_by_semantic_type(document_type, semantic_type):
    # Add custom semantic types here
    if semantic_type == 'quality_control':
        patterns = ['quality', 'inspect', 'test', 'verify']
        # Match logic...
```

---

## ⚡ Performance Optimization

### Caching Strategy

StatusResolver implements intelligent caching:

```python
class StatusResolver:
    CACHE_TIMEOUT = 3600  # 1 hour
    
    @staticmethod
    def get_initial_status(document_type):
        # Results are cached for 1 hour per document type
        cache_key = f"initial_status_{document_type.id}"
        # ... caching logic
```

### Cache Management

```python
# Clear cache for specific document type
StatusResolver.clear_cache(document_type=purchase_request_type)

# Clear all status resolution cache
StatusResolver.clear_cache()

# Cache is automatically invalidated when:
# - DocumentTypeStatus objects are saved/deleted
# - DocumentStatus objects are modified
```

### Batch Operations

```python
# For bulk operations, cache results
def process_multiple_documents(documents):
    # Cache status lookups for efficiency
    status_cache = {}
    
    for document in documents:
        doc_type_id = document.document_type.id
        
        if doc_type_id not in status_cache:
            status_cache[doc_type_id] = {
                'editable': StatusResolver.get_editable_statuses(document.document_type),
                'final': StatusResolver.get_final_statuses(document.document_type),
            }
        
        # Use cached results
        cache = status_cache[doc_type_id]
        can_edit = document.status in cache['editable']
        is_final = document.status in cache['final']
        
        # Process document...
```

---

## 🧪 Testing Patterns

### Unit Tests

```python
class StatusResolverTestCase(TestCase):
    def setUp(self):
        # Create test document type
        self.doc_type = DocumentType.objects.create(
            name='Test Document',
            app_name='test',
            type_key='test_doc'
        )
        
        # Create test statuses
        self.draft = DocumentStatus.objects.create(code='draft', name='Draft')
        self.submitted = DocumentStatus.objects.create(code='submitted', name='Submitted')
        
        # Configure workflow
        DocumentTypeStatus.objects.create(
            document_type=self.doc_type,
            status=self.draft,
            is_initial=True,
            allows_editing=True
        )
        
    def test_initial_status_resolution(self):
        """Test that initial status is resolved correctly"""
        initial = StatusResolver.get_initial_status(self.doc_type)
        self.assertEqual(initial, 'draft')
        
    def test_editable_statuses(self):
        """Test that editable statuses are resolved correctly"""
        editable = StatusResolver.get_editable_statuses(self.doc_type)
        self.assertIn('draft', editable)
        
    def test_caching(self):
        """Test that results are properly cached"""
        # First call
        result1 = StatusResolver.get_initial_status(self.doc_type)
        
        # Should be cached now
        with self.assertNumQueries(0):
            result2 = StatusResolver.get_initial_status(self.doc_type)
            
        self.assertEqual(result1, result2)
```

### Integration Tests

```python
class DocumentOperationsTestCase(TestCase):
    def test_bulgarian_status_workflow(self):
        """Test complete workflow with Bulgarian status names"""
        # Create Bulgarian statuses
        chernova = DocumentStatus.objects.create(code='chernova', name='Чернова')
        podadena = DocumentStatus.objects.create(code='podadena', name='Подадена')
        
        # Configure workflow
        DocumentTypeStatus.objects.create(
            document_type=self.purchase_request_type,
            status=chernova,
            is_initial=True,
            allows_editing=True
        )
        
        # Test document creation with Bulgarian initial status
        request = PurchaseRequest(document_type=self.purchase_request_type)
        service = DocumentService(document=request, user=self.user)
        result = service.create()
        
        self.assertTrue(result.ok)
        self.assertEqual(request.status, 'chernova')
        
        # Test status transition
        result = service.transition_to('podadena')
        self.assertTrue(result.ok)
        self.assertEqual(request.status, 'podadena')
```

---

## 🚨 Error Handling

### Graceful Degradation

StatusResolver includes comprehensive error handling:

```python
def get_initial_status(document_type) -> Optional[str]:
    try:
        # Try to get from configuration
        initial_config = DocumentTypeStatus.objects.filter(
            document_type=document_type,
            is_initial=True,
            is_active=True
        ).first()
        
        return initial_config.status.code if initial_config else 'draft'
        
    except Exception as e:
        logger.error(f"Error getting initial status: {e}")
        return 'draft'  # Safe fallback
```

### Common Error Scenarios

#### 1. Missing Configuration
```python
# Handle missing DocumentTypeStatus configuration
def safe_status_check(document, status_type='editable'):
    try:
        if status_type == 'editable':
            statuses = StatusResolver.get_editable_statuses(document.document_type)
        else:
            statuses = StatusResolver.get_final_statuses(document.document_type)
            
        return document.status in statuses
        
    except Exception as e:
        logger.warning(f"Status resolution failed: {e}")
        # Fallback to basic checks
        if status_type == 'editable':
            return document.status in ['draft', 'pending']
        else:
            return document.status in ['completed', 'finalized']
```

#### 2. Import Errors
```python
# Handle cases where StatusResolver might not be available
def get_document_permissions(document, user):
    try:
        from nomenclatures.services._status_resolver import can_edit_in_status
        can_edit = can_edit_in_status(document)
    except ImportError:
        # Fallback when StatusResolver not available
        can_edit = document.status in ['draft', 'pending']
        
    return {'can_edit': can_edit}
```

---

## 📚 Advanced Patterns

### 1. Status Transition Validation

```python
def validate_status_transition(document, from_status, to_status):
    """Validate that a status transition is allowed"""
    
    # Get all configured statuses in order
    from nomenclatures.services._status_resolver import StatusResolver
    
    next_statuses = StatusResolver.get_next_possible_statuses(
        document.document_type, 
        from_status
    )
    
    if to_status not in next_statuses:
        return False, f"Cannot transition from {from_status} to {to_status}"
        
    # Additional business rules...
    return True, "Transition allowed"
```

### 2. Workflow Progress Calculation

```python
def calculate_workflow_progress(document):
    """Calculate how far along the document is in its workflow"""
    
    from nomenclatures.services._status_resolver import StatusResolver
    
    # Get all configured statuses in order
    all_configs = DocumentTypeStatus.objects.filter(
        document_type=document.document_type,
        is_active=True
    ).order_by('sort_order')
    
    total_steps = all_configs.count()
    current_step = 0
    
    for i, config in enumerate(all_configs):
        if config.status.code == document.status:
            current_step = i + 1
            break
    
    progress_percentage = (current_step / total_steps) * 100 if total_steps > 0 else 0
    
    return {
        'current_step': current_step,
        'total_steps': total_steps,  
        'progress_percentage': progress_percentage,
        'is_complete': StatusResolver.is_status_in_role(
            document.document_type, 
            document.status, 
            'final'
        )
    }
```

### 3. Custom Status Validators

```python
class StatusValidator:
    """Custom validator for specific business rules"""
    
    @staticmethod
    def validate_purchase_request_transition(request, to_status):
        """Purchase request specific validation"""
        
        from nomenclatures.services._status_resolver import StatusResolver
        
        # Check if transitioning to processing status
        processing_statuses = StatusResolver.get_statuses_by_semantic_type(
            request.document_type, 'processing'
        )
        
        if to_status in processing_statuses:
            # Business rule: Must have lines
            if not request.lines.exists():
                return False, "Cannot process request without lines"
                
            # Business rule: Must have estimated costs
            lines_without_price = request.lines.filter(estimated_price__isnull=True)
            if lines_without_price.exists():
                return False, "All lines must have estimated prices"
        
        return True, "Validation passed"
```

---

## 🎯 Best Practices

### 1. Always Use Try/Catch
```python
# Good: Always handle potential failures
try:
    from nomenclatures.services._status_resolver import StatusResolver
    editable = StatusResolver.get_editable_statuses(document.document_type)
    can_edit = document.status in editable
except Exception:
    # Fallback logic
    can_edit = document.status in ['draft', 'pending']
```

### 2. Cache Results in Loops
```python
# Good: Cache status lookups for performance
def process_documents(documents):
    # Cache results to avoid repeated database queries
    status_cache = {}
    
    for document in documents:
        doc_type_id = document.document_type.id
        if doc_type_id not in status_cache:
            status_cache[doc_type_id] = StatusResolver.get_editable_statuses(
                document.document_type
            )
        
        can_edit = document.status in status_cache[doc_type_id]
        # ... process document
```

### 3. Use Semantic Types When Possible
```python
# Good: Use semantic types for business logic
approval_statuses = StatusResolver.get_statuses_by_semantic_type(
    document_type, 'approval'
)

# Better than hardcoded lists
# Bad: approval_statuses = ['submitted', 'pending_review', 'awaiting_approval']
```

### 4. Provide Meaningful Fallbacks
```python
# Good: Meaningful fallbacks based on context
def get_next_action(document):
    try:
        next_statuses = StatusResolver.get_next_possible_statuses(
            document.document_type, 
            document.status
        )
        return next_statuses[0] if next_statuses else None
    except Exception:
        # Context-aware fallback
        if document.status == 'draft':
            return 'submitted'  # Logical next step
        elif document.status == 'submitted':
            return 'approved'   # Logical next step
        return None
```

---

## 📞 Support

For questions about StatusResolver usage:

1. **Check the documentation:** This guide covers most common use cases
2. **Look at examples:** `test_bulgarian_statuses.py` has comprehensive examples
3. **Check the codebase:** Existing services show proper usage patterns
4. **Enable debug logging:** Set log level to DEBUG for detailed information

```python
import logging
logging.getLogger('nomenclatures.services._status_resolver').setLevel(logging.DEBUG)
```

---

**Remember:** The goal of StatusResolver is to eliminate hardcoded status names and make your application work with any status configuration. Always prefer dynamic resolution over hardcoded status strings!