# purchases/services/__init__.py - FINAL VERSION WITH ALL SERVICES

"""
Purchases services package - Complete VAT-aware structure

Services:
- RequestService: Purchase Request operations with VAT awareness
- OrderService: Purchase Order operations with VAT calculations
- DeliveryService: Delivery Receipt operations with VAT processing
- AnalyticsService: Analytics and reporting
- SmartVATService: Core VAT calculations and processing
- VATIntegrationService: Cross-document VAT workflow operations
"""

from .request_service import RequestService
from .order_service import OrderService
from .delivery_service import DeliveryService
from .analytics_service import AnalyticsService
from .vat_service import SmartVATService
from .vat_integration_service import VATIntegrationService

__all__ = [
    'RequestService',
    'OrderService',
    'DeliveryService',
    'AnalyticsService',
    'SmartVATService',
    'VATIntegrationService'
]

# Version info
__version__ = '3.0.0'  # VAT-AWARE VERSION