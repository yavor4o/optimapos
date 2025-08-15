# purchases/admin/__init__.py - ОБНОВЕН ADMIN PACKAGE
"""
Purchases Admin Package - COMPLETE STRUCTURE

MODULES:
- request.py: PurchaseRequest & PurchaseRequestLine admin (EXISTING)
- orders.py: PurchaseOrder & PurchaseOrderLine admin (NEW!)

FEATURES:
- Synchronized with nomenclatures system
- DocumentService integration
- ApprovalService workflow testing
- MovementService integration
- Professional display methods
- Bulk operations with proper error handling
- Real-time status management
"""

# Import ALL admin classes
from purchases.admin.request import PurchaseRequestAdmin, PurchaseRequestLineInline

# NEW: Import orders admin
from purchases.admin.orders import PurchaseOrderAdmin, PurchaseOrderLineInline

# Export all available admin classes
__all__ = [
    # Request admins (EXISTING)
    'PurchaseRequestAdmin',
    'PurchaseRequestLineInline',

    # Order admins (NEW!)
    'PurchaseOrderAdmin',
    'PurchaseOrderLineInline',
]

# Version info
__version__ = '2.0.0'  # UPDATED for orders support
__author__ = 'Your Company'


# =====================
# ADMIN HEALTH CHECK (Optional development helper)
# =====================

def validate_admin_setup():
    """
    Validate admin setup for development

    Returns:
        dict: Validation results
    """
    issues = []

    # Check if all models are properly registered
    from django.contrib import admin
    from purchases.models import PurchaseRequest, PurchaseOrder

    if PurchaseRequest not in admin.site._registry:
        issues.append("PurchaseRequest not registered in admin")

    if PurchaseOrder not in admin.site._registry:
        issues.append("PurchaseOrder not registered in admin")

        # Check DocumentService integration
    try:
        from nomenclatures.services import DocumentService
        if not hasattr(DocumentService, 'get_available_actions'):
            issues.append("DocumentService missing get_available_actions method")
    except ImportError:
        issues.append("DocumentService not available")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'admin_classes_count': len(__all__),
        'timestamp': __import__('datetime').datetime.now().isoformat()
    }


# Add validation to exports (development helper)
__all__.append('validate_admin_setup')