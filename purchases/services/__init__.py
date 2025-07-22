# purchases/services/__init__.py - FINAL CORRECT VERSION

"""
Purchases services package - Правилна структура

Services:
- RequestService: Purchase Request operations (заявки)
- OrderService: Purchase Order operations (поръчки)
- DeliveryService: Delivery Receipt operations (доставки)
- AnalyticsService: Analytics and reporting
"""

from .request_service import RequestService
from .order_service import OrderService
from .delivery_service import DeliveryService
from .analytics_service import AnalyticsService
from .vat_service import SmartVATService

__all__ = [
    'RequestService',
    'OrderService',
    'DeliveryService',
    'AnalyticsService',
    'SmartVATService'
]

# Version info
__version__ = '2.0.0'

