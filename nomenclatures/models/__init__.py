# nomenclatures/models/__init__.py - COMPLETE VERSION
"""
Nomenclatures models package - СИНХРОНИЗИРАНА ВЕРСИЯ

Архитектура:
- base.py: Базови класове и managers
- documents.py: DocumentType (CLEAN REFACTORED)
- approvals.py: ApprovalRule и ApprovalLog (SIMPLIFIED)
- numbering.py: NumberingConfiguration system (NEW)
- product.py: ProductGroup, Brand, ProductType
- financial.py: Currency, ExchangeRate, TaxGroup
- operational.py: UnitOfMeasure, PaymentType
"""

# =====================
# IMPORT ORDER - всички импорти преди __all__
# =====================

# Base imports
from .base import BaseNomenclature, ActiveManager

# Documents & Workflow
from .documents import DocumentType, DocumentTypeManager, get_document_type_by_key

# Approvals - FIXED: добавени в импортите
try:
    from .approvals import ApprovalRule, ApprovalLog, ApprovalRuleManager
except ImportError:
    ApprovalRule = None
    ApprovalLog = None
    ApprovalRuleManager = None

# Numbering - NEW: добавен в импортите
try:
    from .numbering import (
        NumberingConfiguration,
        LocationNumberingAssignment,
        UserNumberingPreference,
        generate_document_number,
        get_numbering_config_for_document
    )
except ImportError:
    NumberingConfiguration = None
    LocationNumberingAssignment = None
    UserNumberingPreference = None
    generate_document_number = None
    get_numbering_config_for_document = None

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
    'get_document_type_by_key',

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

# Add conditional exports
if ApprovalRule:
    __all__.extend(['ApprovalRule', 'ApprovalLog', 'ApprovalRuleManager'])

if NumberingConfiguration:
    __all__.extend([
        'NumberingConfiguration',
        'LocationNumberingAssignment',
        'UserNumberingPreference',
        'generate_document_number',
        'get_numbering_config_for_document'
    ])

# =====================
# METADATA
# =====================
__version__ = '3.0.0'  # DOCUMENT-SERVICE INTEGRATED VERSION
__author__ = 'Your Company'
__description__ = 'Nomenclatures models with DocumentService integration'

# =====================
# PACKAGE VALIDATION - DEBUG РЕЖИМ
# =====================
import sys

if 'runserver' in sys.argv or 'test' in sys.argv:
    # Валидираме че всички импорти в __all__ наистина съществуват
    _missing_imports = []
    for name in __all__:
        if name not in globals() or globals()[name] is None:
            _missing_imports.append(name)

    if _missing_imports:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"nomenclatures.models.__init__.py: Missing or None imports: {_missing_imports}"
        )
        # Remove missing from __all__ to prevent import errors
        __all__ = [name for name in __all__ if name not in _missing_imports]