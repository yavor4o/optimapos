# purchases/models/__init__.py - CLEAN EXPLICIT IMPORTS

"""
Purchases models package - Clean organized structure

АРХИТЕКТУРА:
- base.py: BaseDocument, mixins и managers
- requests.py: PurchaseRequest заявки (БЕЗ финансови данни)
- orders.py: PurchaseOrder поръчки (С финансови данни)
- deliveries.py: DeliveryReceipt доставки (С всички данни)

ПРИНЦИП: Explicit imports за максимална яснота
"""

# =====================
# BASE CLASSES & MIXINS
# =====================
from .base import (
    # Managers
    DocumentManager,
    LineManager,

    # Base models
    BaseDocument,
    BaseDocumentLine,

    # Mixins за различни функционалности
    FinancialMixin,  # За документи с финансови данни
    PaymentMixin,  # За документи с плащания
    DeliveryMixin,  # За документи с доставки
    FinancialLineMixin  # За редове с финансови данни
)

# =====================
# REQUEST MODELS (БЕЗ финансови данни)
# =====================
from .requests import (
    PurchaseRequest,  # Главният модел за заявки
    PurchaseRequestLine,  # Редове на заявки
    PurchaseRequestManager  # Специализиран manager
)

# =====================
# ORDER MODELS (С финансови данни)
# =====================
from .orders import (
    PurchaseOrder,  # Главният модел за поръчки
    PurchaseOrderLine,  # Редове на поръчки
    PurchaseOrderManager,  # Manager за поръчки
    PurchaseOrderLineManager  # Manager за редове
)

# =====================
# DELIVERY MODELS (С всички данни)
# =====================
from .deliveries import (
    DeliveryReceipt,  # Главният модел за доставки
    DeliveryLine,  # Редове на доставки
    DeliveryReceiptManager,  # Manager за доставки
    DeliveryLineManager  # Manager за редове
)

# =====================
# DJANGO AUTO-DISCOVERY EXPORTS
# =====================
__all__ = [
    # Base infrastructure
    'DocumentManager',
    'LineManager',
    'BaseDocument',
    'BaseDocumentLine',

    # Mixins
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',

    # Request models
    'PurchaseRequest',
    'PurchaseRequestLine',
    'PurchaseRequestManager',

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

# =====================
# PACKAGE METADATA
# =====================
__version__ = '3.2.0'  # CLEAN EXPLICIT VERSION
__author__ = 'Your Company'


# Development helper
def get_available_models():
    """Helper за development - показва всички налични модели"""
    return {
        'requests': ['PurchaseRequest', 'PurchaseRequestLine'],
        'orders': ['PurchaseOrder', 'PurchaseOrderLine'],
        'deliveries': ['DeliveryReceipt', 'DeliveryLine'],
        'base': ['BaseDocument', 'BaseDocumentLine'],
        'mixins': ['FinancialMixin', 'PaymentMixin', 'DeliveryMixin', 'FinancialLineMixin']
    }