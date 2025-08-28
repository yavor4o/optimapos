# nomenclatures/services/__init__.py
"""
Nomenclatures services - Clean imports
"""

# Main services

from .approval_service import ApprovalService
from .vat_calculation_service import VATCalculationService

# New services
try:
    from .numbering_service import NumberingService
except ImportError:
    NumberingService = None

# Export all
__all__ = [

    'ApprovalService',
    'VATCalculationService',
]

# Add numbering if available
if NumberingService:
    __all__.append('NumberingService')

# Convenience functions
if NumberingService:
    from .numbering_service import generate_document_number
    __all__.append('generate_document_number')