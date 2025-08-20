# purchases/admin/__init__.py



__all__ = [
    'PurchaseRequestAdmin',
    'PurchaseOrderAdmin',
    'DeliveryReceiptAdmin',
]

from purchases.admin.deliveries import DeliveryReceiptAdmin
from purchases.admin.orders import PurchaseOrderAdmin
from purchases.admin.requests import PurchaseRequestAdmin