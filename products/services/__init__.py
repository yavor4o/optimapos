# products/services/__init__.py
"""
Products services package - LIFECYCLE VERSION

Services:
- ProductService: Basic product operations (search, lookup)
- ValidationService: Product validation logic
- LifecycleService: Lifecycle management operations
"""

from .product_service import ProductService
from .validation_service import ProductValidationService
from .lifecycle_service import ProductLifecycleService

__all__ = [
    'ProductService',           # Existing - enhanced
    'ProductValidationService', # New
    'ProductLifecycleService',  # New
]

# Version info
__version__ = '3.0.0'  # LIFECYCLE VERSION