# core/interfaces/location_interface.py
"""
Location interface for pricing and inventory systems

Uses ModelABCMeta to resolve metaclass conflicts with Django models.
"""

from abc import ABC, abstractmethod
from typing import Optional
from decimal import Decimal
from core.utils.metaclasses import ModelABCMeta


class ILocation(ABC, metaclass=ModelABCMeta):
    """
    Abstract interface for anything that can have prices and inventory.

    Uses ModelABCMeta for Django model compatibility.

    Implementations:
    - inventory.InventoryLocation (physical warehouses)
    - sales.OnlineStore (future - online stores)
    - partners.CustomerSite (future - customer locations)
    """

    @property
    @abstractmethod
    def pk(self):
        """Primary key of the location"""
        pass

    @property
    @abstractmethod
    def code(self) -> str:
        """Unique location code"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Location name"""
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Whether location is active"""
        pass

    @property
    @abstractmethod
    def default_markup_percentage(self) -> Optional[Decimal]:
        """Default markup for this location (can be None)"""
        pass

    def __str__(self) -> str:
        """String representation"""
        return f"{self.code} - {self.name}"


# Validation helpers
def validate_location(obj) -> bool:
    """
    Validate that object implements ILocation interface

    Args:
        obj: Object to validate

    Returns:
        bool: True if valid ILocation implementation
    """
    required_attrs = ['pk', 'code', 'name', 'is_active', 'default_markup_percentage']
    return all(hasattr(obj, attr) for attr in required_attrs)


def assert_location(obj) -> None:
    """
    Assert that object implements ILocation interface

    Args:
        obj: Object to validate

    Raises:
        TypeError: If object doesn't implement ILocation
    """
    if not isinstance(obj, ILocation):
        raise TypeError(f"{type(obj).__name__} must implement ILocation interface")

    if not validate_location(obj):
        raise TypeError(f"{type(obj).__name__} missing required ILocation attributes")


# Type alias for function signatures
LocationType = ILocation