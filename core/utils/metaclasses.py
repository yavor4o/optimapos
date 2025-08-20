# core/utils/metaclasses.py
"""
Core metaclass utilities for Django + ABC integration

Provides hybrid metaclasses that resolve conflicts between Django ORM
and Python abstract base classes.

Used primarily for service interfaces that need strict ABC behavior.
"""

from abc import ABCMeta
from django.db.models.base import ModelBase


class ModelABCMeta(ModelBase, ABCMeta):
    """
    Hybrid metaclass combining Django ModelBase and Python ABCMeta.

    Allows Django models to inherit from ABC interfaces without metaclass conflicts.

    PRIMARY USE CASE: Service interfaces that need ABC behavior

    Usage:
        class IMyService(ABC, metaclass=ModelABCMeta):
            @abstractmethod
            def my_method(self): pass

        class MyService(IMyService):
            def my_method(self): return "implemented"

    Examples:
        - IDocumentService, IPricingService, IInventoryService
        - Any service interface that needs strict ABC validation

    NOTE: For model interfaces (like ILocation), prefer Protocol pattern
          which is more modern and doesn't require metaclass complexity.
    """
    pass


class ServiceABCMeta(ABCMeta):
    """
    Standard ABC metaclass for service interfaces.

    Use this for pure Python service classes that don't interact with Django ORM.
    This is just ABCMeta with explicit naming for clarity.

    Usage:
        class IMyService(ABC, metaclass=ServiceABCMeta):
            @abstractmethod
            def process(self): pass

        class MyService(IMyService):
            def process(self): return "done"

    Examples:
        - IDocumentService, IPricingService, IInventoryService
        - Any business logic service interface
    """
    pass


# Convenience aliases for common patterns
DjangoModelInterface = ModelABCMeta  # Keep for backward compatibility
ServiceInterface = ServiceABCMeta

# Version info
__version__ = '2.0.0'  # Updated to reflect Protocol preference
__author__ = 'Your Company'

# Export all
__all__ = [
    'ModelABCMeta',
    'ServiceABCMeta',
    'DjangoModelInterface',
    'ServiceInterface',
]

# Development notes
"""
ARCHITECTURAL GUIDELINES:

1. For MODEL interfaces (like ILocation):
   - Use Protocol pattern (modern, no metaclass conflicts)
   - Example: @runtime_checkable class ILocation(Protocol)

2. For SERVICE interfaces (like IDocumentService):
   - Use ABC pattern with ModelABCMeta if Django integration needed
   - Use ABC pattern with ServiceABCMeta for pure Python services
   - Example: class IDocumentService(ABC, metaclass=ServiceABCMeta)

3. Protocol vs ABC decision:
   - Protocol: For duck typing, structural compatibility
   - ABC: For strict contracts, explicit inheritance
"""