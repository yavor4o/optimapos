# purchases/admin/__init__.py - ADMIN PACKAGE INITIALIZATION
"""
Purchases Admin Package - REAL STRUCTURE

CURRENT MODULES:
- request.py: PurchaseRequest & PurchaseRequestLine admin (SYNCHRONIZED)

FEATURES:
- Synchronized with nomenclatures system
- Workflow testing interfaces
- Real-time status management
- Approval rules testing
- Bulk operations
"""

# Import ONLY existing admin classes
from purchases.admin.request import PurchaseRequestAdmin, PurchaseRequestLineInline

# Export all available admin classes
__all__ = [
    # Request admins (ONLY THESE EXIST)
    'PurchaseRequestAdmin',
    'PurchaseRequestLineInline',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'


