# core/interfaces/__init__.py
"""
Core interfaces package - All service interfaces

АРХИТЕКТУРА: Централизиран регистър на всички интерфейси в системата
"""

# Document interfaces
from .document_interface import IDocumentService
from .approval_interface import IApprovalService

# Business entity interfaces
from .inventory_interface import IInventoryService, IMovementService
from .pricing_interface import IPricingService
from .partner_interface import ISupplierService, ICustomerService, IPartner
from .vat_interface import IVATCalculationService

# NEW: Location interface за pricing dependency resolution
from .location_interface import ILocation

__all__ = [
    # Document system
    'IDocumentService',
    'IApprovalService',

    # Inventory system
    'IInventoryService',
    'IMovementService',

    # Pricing system
    'IPricingService',

    # Partners system
    'ISupplierService',
    'ICustomerService',

    # Financial system
    'IVATCalculationService',

    # Foundation interface
    'ILocation',  # NEW

    'IPartner',
]

# Version info
__version__ = '1.1.0'  # UPDATED за ILocation
__author__ = 'Your Company'


# Development helper
def get_available_interfaces():
    """Helper за development - показва всички налични интерфейси"""
    return {
        'document': ['IDocumentService', 'IApprovalService'],
        'inventory': ['IInventoryService', 'IMovementService'],
        'pricing': ['IPricingService'],
        'partners': ['ISupplierService', 'ICustomerService'],
        'financial': ['IVATCalculationService'],
        'foundation': ['ILocation']
    }