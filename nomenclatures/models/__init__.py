# =====================================================
# ФАЙЛ 6: nomenclatures/models/__init__.py - UPDATED
# =====================================================

# nomenclatures/models/__init__.py - UPDATED WITH BaseDocument
"""
Nomenclatures models package - UPDATED WITH BaseDocument

НОВO: BaseDocument и mixins moved from purchases
"""

# =====================
# IMPORT ORDER - всички импорти преди __all__
# =====================

# Base imports
from .base import BaseNomenclature, ActiveManager

# NEW: Base document imports
from .base_document import (
    BaseDocument,
    BaseDocumentLine,
    DocumentManager,
    LineManager
)

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
# EXPORT DEFINITION - UPDATED
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

# =====================================================
# ФАЙЛ 7: nomenclatures/__init__.py - UPDATED
# =====================================================

# nomenclatures/__init__.py - UPDATED
"""
Nomenclatures package - UPDATED WITH BaseDocument & MIXINS

НОВO: 
- BaseDocument moved from purchases
- Mixins package added
"""

# Re-export key classes for convenience
from .models import (
    BaseDocument,
    BaseDocumentLine,
    DocumentType,
    DocumentStatus,
    DocumentTypeStatus,
)

# NEW: Export mixins
from .mixins import (
    FinancialMixin,
    PaymentMixin,
    DeliveryMixin,
    FinancialLineMixin,
)

__all__ = [
    # Base Document classes
    'BaseDocument',
    'BaseDocumentLine',

    # Document configuration
    'DocumentType',
    'DocumentStatus',
    'DocumentTypeStatus',

    # Mixins
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',
]

# Version info
__version__ = '2.0.0'  # UPDATED для BaseDocument integration
__author__ = 'Your Company'