"""
Nomenclatures admin configuration
"""

# Import all admin classes to register them
from .product import ProductGroupAdmin, BrandAdmin, ProductTypeAdmin
from .financial import CurrencyAdmin, ExchangeRateAdmin, TaxGroupAdmin
from .operational import UnitOfMeasureAdmin, PaymentTypeAdmin, POSLocationAdmin

__all__ = [
    # Product
    'ProductGroupAdmin',
    'BrandAdmin',
    'ProductTypeAdmin',

    # Financial
    'CurrencyAdmin',
    'ExchangeRateAdmin',
    'TaxGroupAdmin',

    # Operational
    'UnitOfMeasureAdmin',
    'PaymentTypeAdmin',
    'POSLocationAdmin',
]