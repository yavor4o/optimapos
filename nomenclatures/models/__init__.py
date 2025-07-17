# nomenclatures/models/__init__.py
"""
Nomenclatures models package

Организация:
- base.py: Базови класове и managers
- documents.py: DocumentType и workflow система
- approvals.py: ApprovalRule и ApprovalLog (NEW)
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

    # Documents & Workflow
    'DocumentType',
    'DocumentTypeManager',
    'ApprovalRule',    # NEW
    'ApprovalLog',     # NEW

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
]

# Version info
__version__ = '2.0.0'  # APPROVAL SYSTEM VERSION
__author__ = 'Your Company'

from .approvals import ApprovalRule, ApprovalLog

# Module configuration
default_app_config = 'nomenclatures.apps.NomenclaturesConfig'