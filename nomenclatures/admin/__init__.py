# nomenclatures/admin/__init__.py - ОБНОВЕН С NUMBERING АДМИН

"""
Nomenclatures admin configuration
"""

# Import all admin classes - Django auto-registers with @admin.register decorators
from .product import ProductGroupAdmin, BrandAdmin, ProductTypeAdmin
from .financial import CurrencyAdmin, ExchangeRateAdmin, TaxGroupAdmin, PriceGroupAdmin
from .operational import UnitOfMeasureAdmin, PaymentTypeAdmin
from .documents import DocumentTypeAdmin
from .statuses import DocumentStatusAdmin, DocumentTypeStatusInline

# ✅ НОВО: Import numbering admin
try:
    from .numbering import (
        NumberingConfigurationAdmin,
        LocationNumberingAssignmentAdmin,
        UserNumberingPreferenceAdmin
    )

    HAS_NUMBERING_ADMIN = True
except ImportError:
    HAS_NUMBERING_ADMIN = False
    print("⚠️ Numbering admin not found")

# Conditional imports
try:
    from .workflow import ApprovalRuleAdmin, ApprovalLogAdmin

    HAS_WORKFLOW_ADMIN = True
except ImportError:
    HAS_WORKFLOW_ADMIN = False

__all__ = [
    # Core nomenclatures
    'ProductGroupAdmin',
    'BrandAdmin',
    'ProductTypeAdmin',

    # Financial
    'CurrencyAdmin',
    'ExchangeRateAdmin',
    'TaxGroupAdmin',
    'PriceGroupAdmin',

    # Operational
    'UnitOfMeasureAdmin',
    'PaymentTypeAdmin',

    # Documents
    'DocumentTypeAdmin',
]

# ✅ НОВO: Add numbering admins if available
if HAS_NUMBERING_ADMIN:
    __all__.extend([
        'NumberingConfigurationAdmin',
        'LocationNumberingAssignmentAdmin',
        'UserNumberingPreferenceAdmin',
    ])

# Add workflow admins if available
if HAS_WORKFLOW_ADMIN:
    __all__.extend([
        'ApprovalRuleAdmin',
        'ApprovalLogAdmin',
    ])

print(f"✅ Nomenclatures admin loaded - Numbering: {HAS_NUMBERING_ADMIN}, Workflow: {HAS_WORKFLOW_ADMIN}")