# nomenclatures/services/__init__.py - FIXED UNIFIED VERSION
"""
Nomenclatures business services - UNIFIED IMPORTS

MAIN ORCHESTRATOR:
- DocumentService: Central document lifecycle management

SPECIALISTS:
- ApprovalService: Approval workflow specialist
- VATCalculationService: VAT/Tax calculations

АРХИТЕКТУРЕН ПРИНЦИП:
Всички imports да минават през този файл за consistency.
"""

# =====================
# CORE SERVICES - FIXED IMPORTS
# =====================

from .document_service import DocumentService

# FIXED: Conditional import за ApprovalService
try:
    from .approval_service import ApprovalService

    HAS_APPROVAL_SERVICE = True
except ImportError:
    ApprovalService = None
    HAS_APPROVAL_SERVICE = False

# FIXED: Conditional import за VAT Service
try:
    from .vat_calculation_service import VATCalculationService

    HAS_VAT_SERVICE = True
except ImportError:
    VATCalculationService = None
    HAS_VAT_SERVICE = False

# =====================
# FUTURE SERVICES (placeholder imports)
# =====================

# FIXED: Prepared for future services
try:
    from .currency_service import CurrencyService

    HAS_CURRENCY_SERVICE = True
except ImportError:
    CurrencyService = None
    HAS_CURRENCY_SERVICE = False

try:
    from .numbering_service import NumberingService

    HAS_NUMBERING_SERVICE = True
except ImportError:
    NumberingService = None
    HAS_NUMBERING_SERVICE = False

# =====================
# UNIFIED EXPORTS - FIXED
# =====================

# Core exports (винаги налични)
__all__ = [
    'DocumentService',  # MAIN ORCHESTRATOR - винаги наличен
]

# FIXED: Conditional exports with availability info
if HAS_APPROVAL_SERVICE:
    __all__.extend(['ApprovalService'])

if HAS_VAT_SERVICE:
    __all__.extend(['VATCalculationService'])

if HAS_CURRENCY_SERVICE:
    __all__.extend(['CurrencyService'])

if HAS_NUMBERING_SERVICE:
    __all__.extend(['NumberingService'])


# =====================
# SERVICE AVAILABILITY INFO
# =====================

def get_available_services():
    """
    Get info about available services for debugging/health checks

    Returns:
        dict: Service availability status
    """
    return {
        'core_services': {
            'DocumentService': True,  # винаги наличен
        },
        'workflow_services': {
            'ApprovalService': HAS_APPROVAL_SERVICE,
        },
        'calculation_services': {
            'VATCalculationService': HAS_VAT_SERVICE,
            'CurrencyService': HAS_CURRENCY_SERVICE,
        },
        'utility_services': {
            'NumberingService': HAS_NUMBERING_SERVICE,
        },
        'total_available': len(__all__),
        'version': '4.0.0'
    }


# =====================
# CONVENIENCE FUNCTIONS - FIXED
# =====================

def is_service_available(service_name: str) -> bool:
    """
    Check if specific service is available

    Args:
        service_name: Name of service to check

    Returns:
        bool: True if service is available
    """
    return service_name in __all__


def get_main_orchestrator():
    """
    Get main document orchestrator service

    Returns:
        DocumentService: Main orchestrator (always available)
    """
    return DocumentService


def get_approval_service():
    """
    Get approval service if available

    Returns:
        ApprovalService or None: Approval service if available
    """
    return ApprovalService if HAS_APPROVAL_SERVICE else None


# =====================
# VERSION & META INFO
# =====================
__version__ = '4.0.0'  # SERVICES VERSION
__author__ = 'Your Company'

# FIXED: Add meta exports
__all__.extend([
    'get_available_services',
    'is_service_available',
    'get_main_orchestrator',
    'get_approval_service',
    '__version__'
])


# =====================
# IMPORT VALIDATION (Development helper)
# =====================

def validate_service_integrity():
    """
    Validate service imports and dependencies for development

    Returns:
        dict: Validation results
    """
    issues = []

    # DocumentService validation
    if not hasattr(DocumentService, 'create_document'):
        issues.append("DocumentService missing create_document method")

    if not hasattr(DocumentService, 'transition_document'):
        issues.append("DocumentService missing transition_document method")

    # ApprovalService validation
    if HAS_APPROVAL_SERVICE:
        if not hasattr(ApprovalService, 'authorize_transition'):
            issues.append("ApprovalService missing authorize_transition method")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'services_count': len(__all__),
        'timestamp': __import__('datetime').datetime.now().isoformat()
    }


# FIXED: Add validation to exports
__all__.extend(['validate_service_integrity'])