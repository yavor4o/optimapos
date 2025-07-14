"""
Nomenclatures models package

Организация:
- base.py: Базови класове и managers
- product.py: ProductGroup, Brand, ProductType
- financial.py: Currency, ExchangeRate, TaxGroup
- operational.py: UnitOfMeasure, PaymentType, POSLocation
"""

# Base imports
from .base import BaseNomenclature, ActiveManager

# Product related
from .product import (
    ProductGroup,
    Brand,
    ProductType
)

# Financial related
from .financial import (
    Currency,
    ExchangeRate,
    TaxGroup
)

# Operational related
from .operational import (
    UnitOfMeasure,
    PaymentType,

)

# Експортираме всичко за лесен достъп
__all__ = [
    # Base
    'BaseNomenclature',
    'ActiveManager',

    # Product
    'ProductGroup',
    'Brand',
    'ProductType',

    # Financial
    'Currency',
    'ExchangeRate',
    'TaxGroup',

    # Operational
    'UnitOfMeasure',
    'PaymentType',
    'POSLocation',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'

# Module configuration
default_app_config = 'nomenclatures.apps.NomenclaturesConfig'