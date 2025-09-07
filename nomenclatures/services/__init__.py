# nomenclatures/services/__init__.py
"""
Nomenclatures Services - UNIFIED API

🎯 PRIMARY EXPORT: DocumentService (Unified Facade)
- Use DocumentService for ALL document operations
- Individual services are internal collaborators
- Backward compatibility maintained
"""

# ===================================================================
# 🎯 PRIMARY API - USE THIS FOR ALL DOCUMENT OPERATIONS
# ===================================================================

from .document_service import DocumentService

# ===================================================================
# INDIVIDUAL SERVICES - INTERNAL USE ONLY (for backward compatibility)
# ===================================================================

# Core services
from .approval_service import ApprovalService
from .creator import DocumentCreator  
from .query import DocumentQuery
from .status_manager import StatusManager
from .validator import DocumentValidator
from .vat_calculation_service import VATCalculationService
from .document_line_service import DocumentLineService

# Numbering service (optional)
try:
    from .numbering_service import NumberingService
except ImportError:
    NumberingService = None

# ===================================================================
# PUBLIC API EXPORTS
# ===================================================================

__all__ = [
    # 🎯 PRIMARY API - Use this!
    'DocumentService',
    
    # Legacy individual services (for backward compatibility)
    'ApprovalService',
    'VATCalculationService', 
    'DocumentCreator',
    'StatusManager',
    'DocumentValidator',
    'DocumentQuery',
    'DocumentLineService',
]

# Add numbering if available
if NumberingService:
    __all__.append('NumberingService')

# ===================================================================  
# CONVENIENCE FUNCTIONS - BACKWARD COMPATIBILITY
# ===================================================================

# Document lifecycle functions
from .document_service import (
    recalculate_document_lines
)

# Numbering convenience
if NumberingService:
    from .numbering_service import generate_document_number
    __all__.extend([
        'generate_document_number',
        'create_document',
        'transition_document',
        'can_edit_document', 
        'can_delete_document',
        'recalculate_document_lines'
    ])
else:
    __all__.extend([
        'create_document',
        'transition_document',
        'can_edit_document',
        'can_delete_document',
        'recalculate_document_lines'
    ])