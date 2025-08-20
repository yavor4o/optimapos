# nomenclatures/models/__init__.py - FIXED COMPLETE VERSION
"""
Nomenclatures models package - ПЪЛНО СИНХРОНИЗИРАНА ВЕРСИЯ

Архитектура:
- base_nomenclature.py: Базови класове и managers
- documents.py: DocumentType (CLEAN REFACTORED)
- statuses.py: DocumentStatus, DocumentTypeStatus (NEW)
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
from .base_nomenclature import BaseNomenclature, ActiveManager

# Documents & Workflow
from .documents import DocumentType, DocumentTypeManager, get_document_type_by_key

# Statuses - FIXED: правилен import
from .statuses import DocumentStatus, DocumentTypeStatus

# Approvals - FIXED: с правилно error handling
try:
    from .approvals import ApprovalRule, ApprovalLog, ApprovalRuleManager
    HAS_APPROVAL_MODELS = True
except ImportError:
    ApprovalRule = None
    ApprovalLog = None
    ApprovalRuleManager = None
    HAS_APPROVAL_MODELS = False

# Numbering - FIXED: с правилно error handling
try:
    from .numbering import (
        NumberingConfiguration,
        NumberingConfigurationManager,
        LocationNumberingAssignment,
        UserNumberingPreference,
        generate_document_number,
        get_numbering_config_for_document
    )
    HAS_NUMBERING_MODELS = True
except ImportError:
    NumberingConfiguration = None
    NumberingConfigurationManager = None
    LocationNumberingAssignment = None
    UserNumberingPreference = None
    generate_document_number = None
    get_numbering_config_for_document = None
    HAS_NUMBERING_MODELS = False

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
# EXPORT DEFINITION - FIXED COMPLETE VERSION
# =====================
__all__ = [
    # Base
    'BaseNomenclature',
    'ActiveManager',

    # Documents & Workflow
    'DocumentType',
    'DocumentTypeManager',
    'get_document_type_by_key',

    # Statuses - FIXED: добавени
    'DocumentStatus',
    'DocumentTypeStatus',

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

# FIXED: Add conditional exports with proper completion
if HAS_APPROVAL_MODELS:
    __all__.extend([
        'ApprovalRule',
        'ApprovalLog',
        'ApprovalRuleManager'
    ])

if HAS_NUMBERING_MODELS:
    __all__.extend([
        'NumberingConfiguration',
        'NumberingConfigurationManager',
        'LocationNumberingAssignment',
        'UserNumberingPreference',
        'generate_document_number',
        'get_numbering_config_for_document'
    ])

# =====================
# CONVENIENCE IMPORTS (за лесно debugging)
# =====================

def get_available_models():
    """Get info about available models for debugging"""
    info = {
        'base_models': ['BaseNomenclature', 'ActiveManager'],
        'document_models': ['DocumentType', 'DocumentStatus', 'DocumentTypeStatus'],
        'approval_models': HAS_APPROVAL_MODELS,
        'numbering_models': HAS_NUMBERING_MODELS,
        'product_models': ['ProductGroup', 'Brand', 'ProductType'],
        'financial_models': ['Currency', 'ExchangeRate', 'TaxGroup', 'PriceGroup'],
        'operational_models': ['UnitOfMeasure', 'PaymentType']
    }
    return info

# =====================
# VERSION INFO
# =====================
__version__ = '4.0.0'  # FIXED COMPLETE VERSION
__author__ = 'Your Company'

# Export version for external use
__all__.extend(['__version__', 'get_available_models'])