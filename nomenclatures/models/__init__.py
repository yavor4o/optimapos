# nomenclatures/models/__init__.py - COMPLETE FIXED VERSION
"""
Nomenclatures models package - COMPLETE WITH BaseDocument

НОВO: BaseDocument и mixins moved from purchases
"""

# =====================
# IMPORT ORDER - всички импорти преди __all__
# =====================

# Base imports


# NEW: Base document imports
from .base_document import (
    BaseDocument,
    BaseDocumentLine,
    DocumentManager,
    LineManager
)
from .base_nomenclature import BaseNomenclature, ActiveManager

# Documents & Workflow
from .documents import DocumentType, DocumentTypeManager, get_document_type_by_key

# Statuses
from .statuses import DocumentStatus, DocumentTypeStatus

# Approvals - with error handling
try:
    from .approvals import ApprovalRule, ApprovalLog, ApprovalRuleManager
    HAS_APPROVAL_MODELS = True
except ImportError:
    ApprovalRule = None
    ApprovalLog = None
    ApprovalRuleManager = None
    HAS_APPROVAL_MODELS = False

# Numbering - with error handling
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
# EXPORT DEFINITION - COMPLETE
# =====================
__all__ = [
    # Base
    'BaseNomenclature',
    'ActiveManager',

    # NEW: Base Document classes
    'BaseDocument',
    'BaseDocumentLine',
    'DocumentManager',
    'LineManager',

    # Documents & Workflow
    'DocumentType',
    'DocumentTypeManager',
    'get_document_type_by_key',

    # Statuses
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

# Conditional exports
if HAS_APPROVAL_MODELS:
    __all__.extend(['ApprovalRule', 'ApprovalLog', 'ApprovalRuleManager'])

if HAS_NUMBERING_MODELS:
    __all__.extend([
        'NumberingConfiguration', 'NumberingConfigurationManager',
        'LocationNumberingAssignment', 'UserNumberingPreference',
        'generate_document_number', 'get_numbering_config_for_document'
    ])