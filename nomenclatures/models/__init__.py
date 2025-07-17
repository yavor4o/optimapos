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
from .documents import DocumentType, DocumentTypeManager

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
    TaxGroup,
    PriceGroup,
    PriceGroupManager,
)

# Operational related
from .operational import (
    UnitOfMeasure,
    PaymentType,

)

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
    'PriceGroup',
    'PriceGroupManager',

    # Operational
    'UnitOfMeasure',
    'PaymentType',

    # Documents
    'DocumentType',
    'DocumentTypeManager',

]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'

# Module configuration
default_app_config = 'nomenclatures.apps.NomenclaturesConfig'