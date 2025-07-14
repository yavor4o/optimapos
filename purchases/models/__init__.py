# purchases/models/__init__.py - UPDATED FROM OLD COMPATIBILITY

"""
Purchases models - import all from NEW organized structure

MIGRATION from old structure:
OLD: PurchaseDocument (one model for REQ/ORD/GRN/INV)
NEW: PurchaseRequest, PurchaseOrder, DeliveryReceipt (separate models)

For backward compatibility, some imports are mapped:
- PurchaseDocument → use PurchaseRequest, PurchaseOrder, or DeliveryReceipt
- PurchaseDocumentLine → use PurchaseRequestLine, PurchaseOrderLine, or DeliveryLine
"""

# Import all models from the NEW organized structure
from .base import (
    DocumentManager,
    LineManager,
    BaseDocument,
    BaseDocumentLine
)

from .document_types import (
    DocumentType
)

from .requests import (
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestManager,
    PurchaseRequestLineManager
)

from .orders import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderManager,
    PurchaseOrderLineManager
)

from .deliveries import (
    DeliveryReceipt,
    DeliveryLine,
    DeliveryReceiptManager,
    DeliveryLineManager
)

# BACKWARD COMPATIBILITY ALIASES
# Deprecated - use specific models instead
PurchaseDocument = PurchaseRequest  # Default mapping for old code
PurchaseDocumentLine = PurchaseRequestLine  # Default mapping for old code

# Note: Old PurchaseAuditLog is removed - use core.SystemAuditLog instead

# Export everything for compatibility
__all__ = [
    # Base classes
    'DocumentManager',
    'LineManager',
    'BaseDocument',
    'BaseDocumentLine',

    # Document types
    'DocumentType',

    # NEW models (use these)
    'PurchaseRequest',
    'PurchaseRequestLine',
    'PurchaseRequestManager',
    'PurchaseRequestLineManager',
    'PurchaseOrder',
    'PurchaseOrderLine',
    'PurchaseOrderManager',
    'PurchaseOrderLineManager',
    'DeliveryReceipt',
    'DeliveryLine',
    'DeliveryReceiptManager',
    'DeliveryLineManager',

    # DEPRECATED aliases (will be removed)
    'PurchaseDocument',  # → Use PurchaseRequest/PurchaseOrder/DeliveryReceipt
    'PurchaseDocumentLine',  # → Use PurchaseRequestLine/PurchaseOrderLine/DeliveryLine
]

# Version info
__version__ = '2.0.0'
__author__ = 'Your Company'

# Module configuration
default_app_config = 'purchases.apps.PurchasesConfig'

# MIGRATION NOTICE
import warnings


def _deprecated_import_warning(old_name, new_names):
    warnings.warn(
        f"{old_name} is deprecated. Use {new_names} instead.",
        DeprecationWarning,
        stacklevel=3
    )


# Override __getattr__ to show deprecation warnings
def __getattr__(name):
    if name == 'PurchaseDocument':
        _deprecated_import_warning(
            'PurchaseDocument',
            'PurchaseRequest, PurchaseOrder, or DeliveryReceipt'
        )
        return PurchaseRequest
    elif name == 'PurchaseDocumentLine':
        _deprecated_import_warning(
            'PurchaseDocumentLine',
            'PurchaseRequestLine, PurchaseOrderLine, or DeliveryLine'
        )
        return PurchaseRequestLine
    elif name == 'PurchaseAuditLog':
        _deprecated_import_warning(
            'PurchaseAuditLog',
            'core.SystemAuditLog'
        )
        # Return None since it's completely removed
        return None

    raise AttributeError(f"module 'purchases.models' has no attribute '{name}'")