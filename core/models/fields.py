"""
Standardized decimal field classes for OptimaPOS

These fields enforce consistent decimal precision across the entire application,
ensuring data integrity and compliance with Bulgarian accounting standards.
"""

from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal, ROUND_HALF_UP
from django.utils.translation import gettext_lazy as _
from core.utils.decimal_utils import (
    round_currency, round_quantity, round_percentage, 
    round_cost_price, round_vat_amount, validate_currency_precision,
    is_valid_vat_rate
)
import logging

logger = logging.getLogger(__name__)


class StandardizedDecimalField(models.DecimalField):
    """Base class for all standardized decimal fields"""
    
    def __init__(self, *args, **kwargs):
        # Set defaults if not provided
        if 'max_digits' not in kwargs:
            kwargs['max_digits'] = self.default_max_digits
        if 'decimal_places' not in kwargs:
            kwargs['decimal_places'] = self.default_decimal_places
            
        super().__init__(*args, **kwargs)
        
    def to_python(self, value):
        """Convert value to proper Decimal with rounding"""
        value = super().to_python(value)
        if value is not None:
            return self.round_value(value)
        return value
        
    def round_value(self, value):
        """Override in subclasses to apply specific rounding logic"""
        return value
        
    def get_db_prep_value(self, value, connection, prepared=False):
        """Ensure value is properly rounded before saving to database"""
        if value is not None:
            value = self.round_value(value)
        return super().get_db_prep_value(value, connection, prepared)


class CurrencyField(StandardizedDecimalField):
    """
    Standard currency field for OptimaPOS
    
    Uses Bulgarian accounting standards:
    - 12 digits total (up to 999,999,999.99)
    - 2 decimal places (standard currency precision)
    - ROUND_HALF_UP rounding strategy
    """
    
    default_max_digits = 12
    default_decimal_places = 2
    description = _("Currency amount (BGN)")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Amount in BGN with 2 decimal places'))
        super().__init__(*args, **kwargs)
        
    def round_value(self, value):
        """Apply currency rounding using our utilities"""
        try:
            return round_currency(value)
        except Exception as e:
            logger.error(f"Currency field rounding failed for {value}: {e}")
            return value
            
    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if value is not None:
            if not validate_currency_precision(value, max_places=2):
                raise ValidationError(
                    _('Currency amount must have at most 2 decimal places'),
                    code='invalid_precision'
                )


class CostPriceField(StandardizedDecimalField):
    """
    Cost price field with higher precision for calculations
    
    Uses 4 decimal places for internal cost calculations but rounds
    to 2 places for display/reporting to maintain consistency
    """
    
    default_max_digits = 12
    default_decimal_places = 4  # Higher precision for calculations
    description = _("Cost price with calculation precision")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Cost price with 4 decimal places for calculations'))
        super().__init__(*args, **kwargs)
        
    def round_value(self, value):
        """Apply cost price rounding using our utilities"""
        try:
            return round_cost_price(value)
        except Exception as e:
            logger.error(f"Cost price field rounding failed for {value}: {e}")
            return value
            
    def get_display_value(self, value):
        """Get display value rounded to 2 decimal places for consistency"""
        if value is not None:
            return round_currency(value)  # Round to 2 places for display
        return value


class QuantityField(StandardizedDecimalField):
    """
    Standard quantity field for OptimaPOS
    
    Uses:
    - 12 digits total (up to 999,999,999.999)
    - 3 decimal places (handles grams, ml, etc.)
    - ROUND_HALF_UP rounding strategy
    """
    
    default_max_digits = 12
    default_decimal_places = 3
    description = _("Quantity with 3 decimal precision")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Quantity with up to 3 decimal places'))
        super().__init__(*args, **kwargs)
        
    def round_value(self, value):
        """Apply quantity rounding using our utilities"""
        try:
            return round_quantity(value)
        except Exception as e:
            logger.error(f"Quantity field rounding failed for {value}: {e}")
            return value


class PercentageField(StandardizedDecimalField):
    """
    Standard percentage field for OptimaPOS
    
    Uses:
    - 5 digits total (up to 999.99%)
    - 2 decimal places
    - Validates range 0-100
    """
    
    default_max_digits = 5
    default_decimal_places = 2
    description = _("Percentage (0-100)")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Percentage value (0.00 to 100.00)'))
        super().__init__(*args, **kwargs)
        
    def round_value(self, value):
        """Apply percentage rounding using our utilities"""
        try:
            return round_percentage(value)
        except Exception as e:
            logger.error(f"Percentage field rounding failed for {value}: {e}")
            return value
            
    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if value is not None:
            if not (Decimal('0') <= value <= Decimal('100')):
                raise ValidationError(
                    _('Percentage must be between 0 and 100'),
                    code='invalid_range'
                )


class VATRateField(StandardizedDecimalField):
    """
    VAT rate field compliant with Bulgarian tax law
    
    Uses:
    - 3 digits total (0.xx format, like 0.20 for 20%)
    - 2 decimal places 
    - Validates VAT rate range (0-1)
    - Special validation for Bulgarian VAT rates
    """
    
    default_max_digits = 3
    default_decimal_places = 2
    description = _("VAT rate (0.00-1.00)")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('VAT rate as decimal (e.g., 0.20 for 20%)'))
        super().__init__(*args, **kwargs)
        
    def round_value(self, value):
        """Apply VAT rate rounding - always 2 decimal places"""
        try:
            return round_percentage(value) / 100 if value and value > 1 else round_percentage(value * 100) / 100 if value else value
        except Exception as e:
            logger.error(f"VAT rate field rounding failed for {value}: {e}")
            return value
            
    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if value is not None:
            if not is_valid_vat_rate(value):
                raise ValidationError(
                    _('VAT rate must be between 0 and 1 (e.g., 0.20 for 20%)'),
                    code='invalid_vat_rate'
                )


class ExchangeRateField(StandardizedDecimalField):
    """
    Exchange rate field for currency conversions
    
    Uses:
    - 10 digits total
    - 6 decimal places (standard for exchange rates)
    - High precision for financial accuracy
    """
    
    default_max_digits = 10
    default_decimal_places = 6
    description = _("Exchange rate with 6 decimal precision")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Exchange rate with 6 decimal places'))
        super().__init__(*args, **kwargs)


class WeightField(StandardizedDecimalField):
    """
    Weight field in kilograms
    
    Uses:
    - 8 digits total (up to 99,999.999 kg)
    - 3 decimal places (supports grams precision)
    """
    
    default_max_digits = 8
    default_decimal_places = 3
    description = _("Weight in kilograms")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Weight in kilograms (3 decimal places)'))
        super().__init__(*args, **kwargs)


class VolumeField(StandardizedDecimalField):
    """
    Volume field in cubic meters
    
    Uses:
    - 8 digits total
    - 4 decimal places (supports milliliter precision)
    """
    
    default_max_digits = 8
    default_decimal_places = 4
    description = _("Volume in cubic meters")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Volume in cubic meters (4 decimal places)'))
        super().__init__(*args, **kwargs)


class DimensionField(StandardizedDecimalField):
    """
    Dimension field in centimeters
    
    Uses:
    - 6 digits total (up to 9999.9 cm)
    - 1 decimal place (millimeter precision)
    """
    
    default_max_digits = 6
    default_decimal_places = 1
    description = _("Dimension in centimeters")
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Dimension in centimeters (1 decimal place)'))
        super().__init__(*args, **kwargs)


# =============================================================================
# FIELD FACTORY FUNCTIONS
# =============================================================================

def currency_field(**kwargs):
    """
    Factory function for currency fields
    
    Usage:
        price = currency_field(verbose_name='Price')
        total = currency_field(null=True, blank=True)
    """
    return CurrencyField(**kwargs)


def cost_field(**kwargs):
    """
    Factory function for cost price fields
    
    Usage:
        cost_price = cost_field(verbose_name='Cost Price')
        avg_cost = cost_field(null=True, blank=True)
    """
    return CostPriceField(**kwargs)


def quantity_field(**kwargs):
    """
    Factory function for quantity fields
    
    Usage:
        quantity = quantity_field(verbose_name='Quantity')
        stock_level = quantity_field(default=0)
    """
    return QuantityField(**kwargs)


def percentage_field(**kwargs):
    """
    Factory function for percentage fields
    
    Usage:
        discount = percentage_field(verbose_name='Discount %')
        markup = percentage_field(default=0)
    """
    return PercentageField(**kwargs)


def vat_rate_field(**kwargs):
    """
    Factory function for VAT rate fields
    
    Usage:
        vat_rate = vat_rate_field(verbose_name='VAT Rate')
        tax_rate = vat_rate_field(default=Decimal('0.20'))
    """
    return VATRateField(**kwargs)


# =============================================================================
# MIGRATION HELPERS
# =============================================================================

def get_field_migration_map():
    """
    Returns mapping for migrating old fields to new standardized fields
    
    Usage in migrations:
        from core.models.fields import get_field_migration_map
        
        field_map = get_field_migration_map()
        # Use for converting existing fields
    """
    return {
        # Currency fields - standardize to 12,2
        'currency': {
            'field_class': 'core.models.fields.CurrencyField',
            'max_digits': 12,
            'decimal_places': 2
        },
        # Cost prices - keep 4 decimal places for calculations
        'cost_price': {
            'field_class': 'core.models.fields.CostPriceField', 
            'max_digits': 12,
            'decimal_places': 4
        },
        # Quantities - standardize to 12,3
        'quantity': {
            'field_class': 'core.models.fields.QuantityField',
            'max_digits': 12,
            'decimal_places': 3
        },
        # Percentages - keep 5,2
        'percentage': {
            'field_class': 'core.models.fields.PercentageField',
            'max_digits': 5,
            'decimal_places': 2
        },
        # VAT rates - use 3,2 
        'vat_rate': {
            'field_class': 'core.models.fields.VATRateField',
            'max_digits': 3,
            'decimal_places': 2
        }
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_field_precision(field_value, field_type):
    """
    Validate that a field value has the correct precision for its type
    
    Args:
        field_value: The value to validate
        field_type: Type of field ('currency', 'quantity', etc.)
        
    Returns:
        bool: True if precision is valid
    """
    if field_value is None:
        return True
        
    try:
        decimal_val = Decimal(str(field_value))
        sign, digits, exponent = decimal_val.as_tuple()
        decimal_places = -exponent if exponent < 0 else 0
        
        precision_map = {
            'currency': 2,
            'cost_price': 4, 
            'quantity': 3,
            'percentage': 2,
            'vat_rate': 2,
            'exchange_rate': 6,
            'weight': 3,
            'volume': 4,
            'dimension': 1
        }
        
        expected_places = precision_map.get(field_type, 2)
        return decimal_places <= expected_places
        
    except Exception:
        return False


# Export all field classes and utilities
__all__ = [
    # Field classes
    'StandardizedDecimalField',
    'CurrencyField', 
    'CostPriceField',
    'QuantityField',
    'PercentageField',
    'VATRateField',
    'ExchangeRateField',
    'WeightField',
    'VolumeField', 
    'DimensionField',
    
    # Factory functions
    'currency_field',
    'cost_field',
    'quantity_field',
    'percentage_field',
    'vat_rate_field',
    
    # Utilities
    'get_field_migration_map',
    'validate_field_precision'
]