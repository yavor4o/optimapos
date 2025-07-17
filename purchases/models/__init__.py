# purchases/models/__init__.py - CLEAN VERSION

"""
Purchases models - clean organized structure

Models:
- PurchaseRequest: Заявки за покупка (БЕЗ финансови данни)
- PurchaseOrder: Поръчки към доставчици (С финансови данни)
- DeliveryReceipt: Доставки и получаване (С всички данни)
"""

# Import all models from the organized structure
from .base import (
    DocumentManager,
    LineManager,
    BaseDocument,
    BaseDocumentLine,
    FinancialMixin,
    PaymentMixin,
    DeliveryMixin,
    FinancialLineMixin
)

# from .document_types import (
#     DocumentType
# )

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

# Export everything for Django auto-discovery
__all__ = [
    # Base classes
    'DocumentManager',
    'LineManager',
    'BaseDocument',
    'BaseDocumentLine',

    # Mixin classes
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',

    # Document types
    # 'DocumentType',

    # Request models
    'PurchaseRequest',
    'PurchaseRequestLine',
    'PurchaseRequestManager',
    'PurchaseRequestLineManager',

    # Order models
    'PurchaseOrder',
    'PurchaseOrderLine',
    'PurchaseOrderManager',
    'PurchaseOrderLineManager',

    # Delivery models
    'DeliveryReceipt',
    'DeliveryLine',
    'DeliveryReceiptManager',
    'DeliveryLineManager',
]

# Version info
__version__ = '3.0.0'  # NEW CLEAN VERSION
__author__ = 'Your Company'