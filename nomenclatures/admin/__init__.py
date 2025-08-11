"""
Nomenclatures admin configuration
"""

# Import all admin classes to register them
from .product import ProductGroupAdmin, BrandAdmin, ProductTypeAdmin
from .financial import CurrencyAdmin, ExchangeRateAdmin, TaxGroupAdmin, PriceGroupAdmin
from .operational import UnitOfMeasureAdmin, PaymentTypeAdmin
# from .documents import DocumentTypeAdmin

__all__ = [
    # Product
    'ProductGroupAdmin',
    'BrandAdmin',
    'ProductTypeAdmin',

    # Financial
    'CurrencyAdmin',
    'ExchangeRateAdmin',
    'TaxGroupAdmin',
    'PriceGroupAdmin',  # ✅ ДОБАВЕН

    # Operational
    'UnitOfMeasureAdmin',
    'PaymentTypeAdmin',

    # Documents


]