# core/interfaces/location_interface.py - ENHANCED VERSION
"""
Enhanced Location Interface for Document Numbering Support

НОВО: Разширен за да поддържа document-related операции
- Numbering assignments
- Document-specific settings
- Business rules per location
"""

from typing import Protocol, runtime_checkable, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from django.db import models


@runtime_checkable
class ILocation(Protocol):
    """
    Enhanced Location Protocol for complete document support

    РАЗШИРЕНИЯ:
    - Document numbering support
    - VAT calculation settings
    - Inventory behavior settings
    - Business rules per location

    IMPLEMENTATIONS:
    - inventory.InventoryLocation ✅ (existing)
    - sales.OnlineStore (future)
    - partners.CustomerSite (future)
    - hr.Office (future)
    """

    # =====================
    # CORE IDENTITY (unchanged)
    # =====================
    pk: int
    code: str
    name: str
    is_active: bool

    # =====================
    # PRICING INTEGRATION (unchanged)
    # =====================
    default_markup_percentage: Decimal

    # =====================
    # NEW: DOCUMENT SETTINGS
    # =====================
    # VAT calculation behavior
    purchase_prices_include_vat: bool
    sale_prices_include_vat: bool

    # Inventory behavior (if applicable)
    allow_negative_stock: bool

    # =====================
    # BASIC METHODS (unchanged)
    # =====================
    def __str__(self) -> str: ...


# =====================
# ENHANCED VALIDATION
# =====================

def validate_location(obj) -> bool:
    """
    Enhanced validation for document-capable locations

    НОВО: Проверява и document-related полета
    """
    # Core fields (same as before)
    core_attrs = ['pk', 'code', 'name', 'is_active', 'default_markup_percentage']

    # NEW: Document-related fields
    document_attrs = ['purchase_prices_include_vat', 'sale_prices_include_vat', 'allow_negative_stock']

    all_attrs = core_attrs + document_attrs

    return all(hasattr(obj, attr) for attr in all_attrs)


def assert_location(obj) -> None:
    """
    Enhanced assertion for document operations

    Raises:
        TypeError: If object doesn't implement enhanced ILocation
    """
    if not isinstance(obj, ILocation):
        raise TypeError(f"{type(obj).__name__} doesn't implement ILocation protocol")

    if not validate_location(obj):
        missing_attrs = []

        # Check core attributes
        core_attrs = ['pk', 'code', 'name', 'is_active', 'default_markup_percentage']
        for attr in core_attrs:
            if not hasattr(obj, attr):
                missing_attrs.append(f"{attr} (core)")

        # Check document attributes
        doc_attrs = ['purchase_prices_include_vat', 'sale_prices_include_vat', 'allow_negative_stock']
        for attr in doc_attrs:
            if not hasattr(obj, attr):
                missing_attrs.append(f"{attr} (document)")

        if missing_attrs:
            raise TypeError(f"{type(obj).__name__} missing required attributes: {missing_attrs}")


# =====================
# LOCATION CAPABILITY DETECTION
# =====================

def supports_documents(obj: ILocation) -> bool:
    """
    Check if location supports document operations

    Returns:
        bool: True if location can be used for documents
    """
    try:
        assert_location(obj)
        return True
    except TypeError:
        return False


def supports_numbering(obj: ILocation) -> bool:
    """
    Check if location supports custom numbering

    Returns:
        bool: True if location can have numbering assignments
    """
    # All ILocation implementations should support numbering
    return supports_documents(obj)


def supports_inventory(obj: ILocation) -> bool:
    """
    Check if location supports inventory operations

    Returns:
        bool: True if location can hold stock
    """
    # Check if it has inventory-specific attributes
    inventory_attrs = ['allow_negative_stock']
    return all(hasattr(obj, attr) for attr in inventory_attrs)


# =====================
# LOCATION HELPERS
# =====================

def get_location_info(obj: ILocation) -> dict:
    """
    Enhanced location information for debugging

    НОВО: Включва document capabilities
    """
    base_info = {
        'type': type(obj).__name__,
        'pk': getattr(obj, 'pk', None),
        'code': getattr(obj, 'code', None),
        'name': getattr(obj, 'name', None),
        'is_active': getattr(obj, 'is_active', None),
        'default_markup_percentage': getattr(obj, 'default_markup_percentage', None),
    }

    # NEW: Document capabilities
    document_info = {
        'purchase_prices_include_vat': getattr(obj, 'purchase_prices_include_vat', None),
        'sale_prices_include_vat': getattr(obj, 'sale_prices_include_vat', None),
        'allow_negative_stock': getattr(obj, 'allow_negative_stock', None),
    }

    # Validation results
    validation_info = {
        'validates': validate_location(obj),
        'isinstance_check': isinstance(obj, ILocation),
        'supports_documents': supports_documents(obj),
        'supports_numbering': supports_numbering(obj),
        'supports_inventory': supports_inventory(obj),
    }

    return {
        **base_info,
        'document_settings': document_info,
        'capabilities': validation_info
    }


def format_location_display(obj: ILocation) -> str:
    """
    Format location for UI display

    Returns:
        str: Human-readable location description
    """
    assert_location(obj)

    base = f"{obj.name} ({obj.code})"
    status = "Active" if obj.is_active else "Inactive"
    return f"{base} - {status}"


# =====================
# BACKWARD COMPATIBILITY
# =====================

# Keep old function names for compatibility
is_location_compatible = supports_documents
LocationType = ILocation
AnyLocation = ILocation

# Version and exports
__version__ = '2.1.0'  # Enhanced for document support
__author__ = 'Your Company'

__all__ = [
    'ILocation',
    'LocationType',
    'AnyLocation',
    'validate_location',
    'assert_location',
    'supports_documents',
    'supports_numbering',
    'supports_inventory',
    'get_location_info',
    'format_location_display',
]