# purchases/models/__init__.py - CLEAN VERSION

# Import all models from the organized structure
from .base import (
    DocumentManager,
    LineManager,
    BaseDocument,
    BaseDocumentLine,
    FinancialMixin,
    PaymentMixin,
    DeliveryMixin,
    FinancialLineMixin
)







# Export everything for Django auto-discovery
__all__ = [
    # Base classes
    'DocumentManager',
    'LineManager',
    'BaseDocument',
    'BaseDocumentLine',

    # Mixin classes
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',



]

# Version info
__version__ = '3.0.0'  # NEW CLEAN VERSION
__author__ = 'Your Company'