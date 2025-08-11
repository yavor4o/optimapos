# nomenclatures/admin/__init__.py - ЧИСТ БЕЗ ГЛУПОСТИ
"""
Nomenclatures admin configuration
"""

# Import all admin classes - Django auto-registers with @admin.register decorators
from .product import ProductGroupAdmin, BrandAdmin, ProductTypeAdmin
from .financial import CurrencyAdmin, ExchangeRateAdmin, TaxGroupAdmin, PriceGroupAdmin
from .operational import UnitOfMeasureAdmin, PaymentTypeAdmin
from .documents import DocumentTypeAdmin

# Conditional imports
try:
    from .workflow import ApprovalRuleAdmin, ApprovalLogAdmin
except ImportError:
    pass

__all__ = [
    'ProductGroupAdmin',
    'BrandAdmin',
    'ProductTypeAdmin',
    'CurrencyAdmin',
    'ExchangeRateAdmin',
    'TaxGroupAdmin',
    'PriceGroupAdmin',
    'UnitOfMeasureAdmin',
    'PaymentTypeAdmin',
    'DocumentTypeAdmin',
]