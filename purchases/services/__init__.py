# purchases/services/__init__.py - NEW STRUCTURE

from .request_service import RequestService
from .order_service import OrderService
from .delivery_service import DeliveryService
from .workflow_service import WorkflowService

# Legacy imports for backward compatibility
from .legacy_document_service import DocumentService  # Deprecated, use specific services

__all__ = [
    'RequestService',
    'OrderService',
    'DeliveryService',
    'WorkflowService',

    # Legacy (будет удален)
    'DocumentService',
]