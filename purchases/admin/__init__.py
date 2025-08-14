# purchases/admin/__init__.py - ADMIN PACKAGE INITIALIZATION
"""
Purchases Admin Package - ORGANIZED STRUCTURE

MODULES:
- requests.py: PurchaseRequest & PurchaseRequestLine admin
- orders.py: PurchaseOrder & PurchaseOrderLine admin
- deliveries.py: DeliveryReceipt & DeliveryLine admin
- base.py: Common admin mixins and utilities

FEATURES:
- Synchronized with nomenclatures system
- Workflow testing interfaces
- Real-time status management
- Approval rules testing
- Bulk operations
"""
from .request import PurchaseRequestLineInline, PurchaseRequestAdmin

# Import all admin classes to register them automatically



# Future imports for other modules
try:
    from .orders import (
        PurchaseOrderAdmin,
        PurchaseOrderLineInline,
    )
except ImportError:
    # Orders admin not yet created
    pass

try:
    from .deliveries import (
        DeliveryReceiptAdmin,
        DeliveryLineInline,
    )
except ImportError:
    # Deliveries admin not yet created
    pass

try:
    from .base import (
        BaseDocumentAdmin,
        BaseDocumentLineInline,
        WorkflowAdminMixin,
    )
except ImportError:
    # Base admin utilities not yet created
    pass

# Export all available admin classes
__all__ = [
    # Request admins
    'PurchaseRequestAdmin',
    'PurchaseRequestLineInline',

    # Order admins (when available)
    # 'PurchaseOrderAdmin',
    # 'PurchaseOrderLineInline',

    # Delivery admins (when available)
    # 'DeliveryReceiptAdmin',
    # 'DeliveryLineInline',

    # Base utilities (when available)
    # 'BaseDocumentAdmin',
    # 'BaseDocumentLineInline',
    # 'WorkflowAdminMixin',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'