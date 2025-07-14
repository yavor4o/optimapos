# purchases/services/__init__.py - NEW CLEAN STRUCTURE

"""
Purchases services package - Refactored for separate document workflows

NEW Services:
- RequestService: Purchase Request operations
- OrderService: Purchase Order operations
- DeliveryService: Delivery Receipt operations
- WorkflowService: Cross-document workflow management
"""

from .request_service import RequestService
from .order_service import OrderService
from .delivery_service import DeliveryService
from .workflow_service import WorkflowService
from .analytics_service import AnalyticsService

__all__ = [
    'RequestService',
    'OrderService',
    'DeliveryService',
    'WorkflowService',
    'AnalyticsService',  # NEW - replaces old PurchaseService
]

# Version info
__version__ = '2.0.0'