# core/interfaces/location_interface.py - PROFESSIONAL PROTOCOL
"""
Location interface using modern Python Protocol pattern.

Following PEP 544 structural subtyping for maximum compatibility and maintainability.
Used by pricing models for location-agnostic operations.
"""

from typing import Protocol, runtime_checkable, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    # Import types only for type checking to avoid circular imports
    from django.db import models


@runtime_checkable
class ILocation(Protocol):
    """
    Location protocol for pricing and inventory systems.

    Modern structural typing approach following PEP 544.
    Any object with these attributes automatically implements this protocol.

    Used by:
    - All pricing models (ProductPrice, ProductPriceByGroup, etc.)
    - PricingService for location-agnostic operations
    - Future location types (OnlineStore, CustomerSite, etc.)

    Example implementations:
    - inventory.InventoryLocation (physical warehouses)
    - sales.OnlineStore (future - online stores)
    - partners.CustomerSite (future - customer locations)
    """

    # Core identity (required by Django models and pricing)
    pk: int
    code: str
    name: str
    is_active: bool

    # Pricing integration (required by pricing calculations)
    default_markup_percentage: Decimal

    # String representation (required by admin and debugging)
    def __str__(self) -> str: ...


# Type aliases for better code readability
LocationType = ILocation
AnyLocation = ILocation


def validate_location(obj) -> bool:
    """
    Runtime validation that object implements ILocation protocol.

    Args:
        obj: Object to validate

    Returns:
        bool: True if object has all required ILocation attributes

    Example:
        >>> location = InventoryLocation.objects.first()
        >>> validate_location(location)
        True
    """
    required_attrs = ['pk', 'code', 'name', 'is_active', 'default_markup_percentage']
    return all(hasattr(obj, attr) for attr in required_attrs)


def assert_location(obj) -> None:
    """
    Assert that object implements ILocation protocol.

    Args:
        obj: Object to validate

    Raises:
        TypeError: If object doesn't implement ILocation protocol

    Example:
        >>> assert_location(some_object)  # Raises TypeError if invalid
    """
    if not isinstance(obj, ILocation):
        raise TypeError(f"{type(obj).__name__} doesn't implement ILocation protocol")

    if not validate_location(obj):
        missing_attrs = [attr for attr in ['pk', 'code', 'name', 'is_active', 'default_markup_percentage']
                         if not hasattr(obj, attr)]
        raise TypeError(f"{type(obj).__name__} missing required attributes: {missing_attrs}")


def is_location_compatible(obj) -> bool:
    """
    Check if object is compatible with ILocation protocol (duck typing).

    More lenient than isinstance check - just checks for required attributes.

    Args:
        obj: Object to check

    Returns:
        bool: True if object can be used as ILocation
    """
    return validate_location(obj)


# Development and debugging helpers
def get_location_info(obj: ILocation) -> dict:
    """
    Get diagnostic information about a location object.

    Args:
        obj: Location object implementing ILocation

    Returns:
        dict: Location information for debugging
    """
    return {
        'type': type(obj).__name__,
        'pk': getattr(obj, 'pk', None),
        'code': getattr(obj, 'code', None),
        'name': getattr(obj, 'name', None),
        'is_active': getattr(obj, 'is_active', None),
        'default_markup_percentage': getattr(obj, 'default_markup_percentage', None),
        'validates': validate_location(obj),
        'isinstance_check': isinstance(obj, ILocation),
    }


# Version and metadata
__version__ = '2.0.0'  # Protocol version
__author__ = 'Your Company'

# Export all public API
__all__ = [
    'ILocation',
    'LocationType',
    'AnyLocation',
    'validate_location',
    'assert_location',
    'is_location_compatible',
    'get_location_info',
]