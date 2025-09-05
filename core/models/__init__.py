# core/models/__init__.py
"""
Core models package

Contains fundamental business models that affect entire system:
- Company: System-wide settings including VAT registration
- DecimalPrecisionConfig: Decimal precision configuration for Bulgarian tax compliance
- Field classes: Standardized decimal field definitions
"""

from .company import Company, CompanyManager
from .decimal_config import DecimalPrecisionConfig
from .fields import (
    CurrencyField, CostPriceField, QuantityField, 
    PercentageField, VATRateField, ExchangeRateField,
    currency_field, cost_field, quantity_field, 
    percentage_field, vat_rate_field
)

__all__ = [
    'Company',
    'CompanyManager',
    'DecimalPrecisionConfig',
    # Field classes
    'CurrencyField', 
    'CostPriceField',
    'QuantityField',
    'PercentageField', 
    'VATRateField',
    'ExchangeRateField',
    # Factory functions
    'currency_field',
    'cost_field', 
    'quantity_field',
    'percentage_field',
    'vat_rate_field',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'