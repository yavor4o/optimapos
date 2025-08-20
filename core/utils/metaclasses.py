# core/utils/metaclasses.py
"""
Core metaclass utilities for Django + ABC integration

Provides hybrid metaclasses that resolve conflicts between Django ORM
and Python abstract base classes.
"""

from abc import ABCMeta
from django.db.models.base import ModelBase


class ModelABCMeta(ModelBase, ABCMeta):
    """
    Hybrid metaclass combining Django ModelBase and Python ABCMeta.

    Allows Django models to inherit from ABC interfaces without metaclass conflicts.

    Usage:
        class IMyInterface(ABC, metaclass=ModelABCMeta):
            @abstractmethod
            def my_method(self): pass

        class MyModel(models.Model, IMyInterface):
            def my_method(self): return "implemented"

    Examples:
        - ILocation interface for pricing/inventory models
        - IDocument interface for document models
        - Any ABC that needs to be implemented by Django models
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
DjangoModelInterface = ModelABCMeta
ServiceInterface = ServiceABCMeta


def create_model_interface(interface_name: str, methods: dict):
    """
    Factory function to create model interfaces dynamically.

    Args:
        interface_name: Name of the interface class
        methods: Dict of method_name -> signature

    Returns:
        Interface class with ModelABCMeta metaclass

    Example:
        IProduct = create_model_interface('IProduct', {
            'get_price': 'def get_price(self) -> Decimal',
            'is_available': 'def is_available(self) -> bool'
        })
    """
    from abc import ABC, abstractmethod

    # Create abstract methods dynamically
    namespace = {}
    for method_name, signature in methods.items():
        # This is a simplified version - real implementation would parse signature
        namespace[method_name] = abstractmethod(lambda self: None)

    # Create the interface class
    return type(interface_name, (ABC,), namespace, metaclass=ModelABCMeta)


# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'

# Export all
__all__ = [
    'ModelABCMeta',
    'ServiceABCMeta',
    'DjangoModelInterface',
    'ServiceInterface',
    'create_model_interface'
]