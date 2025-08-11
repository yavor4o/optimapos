# nomenclatures/services/__init__.py - CENTRAL SERVICES
"""
Nomenclatures business services

MAIN ORCHESTRATOR:
- DocumentService: Central document lifecycle management

SPECIALISTS:
- ApprovalService: Approval workflow specialist
- CurrencyService: Currency operations 
- TaxService: Tax calculations
"""

from .document_service import DocumentService
from .approval_service import ApprovalService
from .currency_service import CurrencyService  
from .tax_service import TaxService

# Export DocumentService as main entry point
__all__ = [
    'DocumentService',    # MAIN ORCHESTRATOR
    'ApprovalService',    # Approval specialist
    'CurrencyService',
    'TaxService',
]

# Version info
__version__ = '3.0.0'  # DOCUMENT-SERVICE VERSION