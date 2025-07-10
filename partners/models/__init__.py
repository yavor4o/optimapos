from .base import Weekday, PartnerBase, PartnerScheduleBase

# Import supplier models
from .suppliers import (
    Supplier,
    SupplierDivision,
    SupplierDaySchedule,
    SupplierManager
)

# Import customer models
from .customers import (
    Customer,
    CustomerSite,
    CustomerDaySchedule,
    CustomerManager
)

# Export all for backward compatibility
__all__ = [
    # Base
    'Weekday',
    'PartnerBase',
    'PartnerScheduleBase',

    # Suppliers
    'Supplier',
    'SupplierDivision',
    'SupplierDaySchedule',
    'SupplierManager',

    # Customers
    'Customer',
    'CustomerSite',
    'CustomerDaySchedule',
    'CustomerManager',
]