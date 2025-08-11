# nomenclatures/models/__init__.py - FIXED VERSION
"""
Nomenclatures models package

Архитектура:
- base.py: Базови класове и managers
- documents.py: DocumentType и workflow система
- approvals.py: ApprovalRule и ApprovalLog
- product.py: ProductGroup, Brand, ProductType
- financial.py: Currency, ExchangeRate, TaxGroup
- operational.py: UnitOfMeasure, PaymentType
"""

# =====================
# IMPORT ORDER FIXED - всички импорти преди __all__
# =====================

# Base imports
from .base import BaseNomenclature, ActiveManager

# Documents & Workflow
from .documents import DocumentType, DocumentTypeManager

# Approvals - FIXED: импорт преди __all__


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

# =====================
# EXPORT DEFINITION - след всички импорти
# =====================
__all__ = [
    # Base
    'BaseNomenclature',
    'ActiveManager',

    # Documents & Workflow
    'DocumentType',
    'DocumentTypeManager',

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

# =====================
# METADATA - в края
# =====================
__version__ = '2.1.0'  # FIXED VERSION - increment
__author__ = 'Your Company'
__description__ = 'Nomenclatures models for enterprise management system'

# =====================
# PACKAGE VALIDATION - DEBUG РЕЖИМ
# =====================
import sys

if 'runserver' in sys.argv or 'test' in sys.argv:
    # Валидираме че всички импорти в __all__ наистина съществуват
    _missing_imports = []
    for name in __all__:
        if name not in globals():
            _missing_imports.append(name)

    if _missing_imports:
        raise ImportError(
            f"nomenclatures.models.__init__.py: Missing imports in __all__: {_missing_imports}"
        )