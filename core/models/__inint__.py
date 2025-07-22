# core/models/__init__.py
"""
Core models package

Contains fundamental business models that affect entire system:
- Company: System-wide settings including VAT registration
"""

from .company import Company, CompanyManager

__all__ = [
    'Company',
    'CompanyManager',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'