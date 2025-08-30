"""
Decimal utilities for OptimaPOS - Bulgarian tax law compliant

ВАЖНО: Спазва изискванията на българското данъчно законодателство:
- Наредба № 3/2006 за ДДС изчисления  
- ЗДДС - Закон за данък върху добавената стойност
- Счетоводни стандарти за точност на изчислението

НОВА ВЕРСИЯ: Използва конфигурируема точност от базата данни
"""

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

# Import configuration functions (with fallback for when models aren't loaded)
try:
    from core.models.decimal_config import get_decimal_config, get_quantizer_string
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    logger.info("Decimal configuration models not available, using hardcoded defaults")

# Currency-aware imports (with fallback)
try:
    from nomenclatures.models.financial import Currency
    CURRENCY_MODEL_AVAILABLE = True
except ImportError:
    CURRENCY_MODEL_AVAILABLE = False
    logger.info("Currency model not available, using fixed precision")

# =============================================================================
# BULGARIAN TAX LAW CONSTANTS
# =============================================================================

# ДДС изчисления - Наредба № 3/2006
TAX_DECIMAL_PLACES = 2  # ЗАДЪЛЖИТЕЛНО 2 знака за данъчна основа
TAX_ROUNDING = ROUND_HALF_UP  # Стандартно търговско закръгляне

# Парични суми - счетоводни стандарти  
CURRENCY_DECIMAL_PLACES = 2
CURRENCY_ROUNDING = ROUND_HALF_UP

# Количества - практика в търговията
QUANTITY_DECIMAL_PLACES = 3  # До kg/литри с грамове/ml
QUANTITY_ROUNDING = ROUND_HALF_UP

# Проценти - стандартна точност
PERCENTAGE_DECIMAL_PLACES = 2
PERCENTAGE_ROUNDING = ROUND_HALF_UP

# Cost prices - по-висока точност за калкулации
COST_DECIMAL_PLACES = 4  # За по-точни средни цени
COST_ROUNDING = ROUND_HALF_UP


# =============================================================================
# CURRENCY-AWARE HELPER FUNCTIONS
# =============================================================================

def get_default_currency():
    """
    Получава базовата валута от системата.
    
    Returns:
        Currency или None: Базовата валута
    """
    try:
        if CURRENCY_MODEL_AVAILABLE:
            return Currency.objects.filter(is_base=True).first()
        else:
            logger.debug("Currency model not available, returning None")
            return None
    except Exception as e:
        logger.error(f"Error getting default currency: {e}")
        return None


def get_currency_decimal_places(currency=None) -> int:
    """
    Получава decimal places за дадена валута.
    
    Args:
        currency: Currency instance или None за default
        
    Returns:
        int: Брой decimal places
    """
    try:
        if currency and hasattr(currency, 'decimal_places'):
            return currency.decimal_places
        
        # Fallback to default currency
        default_currency = get_default_currency()
        if default_currency and hasattr(default_currency, 'decimal_places'):
            return default_currency.decimal_places
            
        # Ultimate fallback
        return CURRENCY_DECIMAL_PLACES
        
    except Exception as e:
        logger.error(f"Error getting currency decimal places: {e}")
        return CURRENCY_DECIMAL_PLACES


# =============================================================================
# CORE ROUNDING FUNCTIONS - Bulgarian Tax Compliant & Currency-Aware
# =============================================================================

def round_currency(amount: Union[Decimal, str, float, int], 
                  currency=None,
                  places: Optional[int] = None,
                  rounding: str = CURRENCY_ROUNDING) -> Decimal:
    """
    Currency-aware закръгляване на парични суми според българските счетоводни стандарти.
    
    NEW: Supports Currency model integration - automatically uses currency.decimal_places
    
    Args:
        amount: Сумата за закръгляване
        currency: Currency instance (опционално - използва базовата валута)
        places: Брой decimal места (override - по подразбиране от валутата)
        rounding: Стратегия за закръгляване (по подразбиране ROUND_HALF_UP)
        
    Returns:
        Decimal: Закръглена сума с правилната точност за валутата
        
    Example:
        >>> round_currency(12.3456)  # Uses default currency
        Decimal('12.35')
        >>> round_currency(12.3456, currency=eur_currency)  # EUR might have 2 places
        Decimal('12.35') 
        >>> round_currency(12.3456, currency=jpy_currency)  # JPY might have 0 places
        Decimal('12')
    """
    try:
        if amount is None:
            return Decimal('0.00')
            
        # Determine decimal places
        if places is None:
            places = get_currency_decimal_places(currency)
            
        decimal_amount = Decimal(str(amount))
        quantizer = Decimal('0.' + '0' * places) if places > 0 else Decimal('1')
        
        result = decimal_amount.quantize(quantizer, rounding=rounding)
        
        currency_code = currency.code if currency else 'DEFAULT'
        logger.debug(f"Currency rounding ({currency_code}): {amount} -> {result} (places={places})")
        return result
        
    except Exception as e:
        logger.error(f"Currency rounding failed for {amount}: {e}")
        # Safe fallback based on places or default
        fallback_places = places if places is not None else 2
        return Decimal('0.' + '0' * fallback_places)


def round_vat_amount(amount: Union[Decimal, str, float, int]) -> Decimal:
    """
    ДДС закръгляване според Наредба № 3/2006.
    
    ВАЖНО: Българското законодателство изисква точно 2 decimal места
    с ROUND_HALF_UP стратегия за всички ДДС изчисления.
    
    Args:
        amount: ДДС сума за закръгляване
        
    Returns:
        Decimal: Закръглена ДДС сума (винаги 2 decimal места)
        
    Example:
        >>> round_vat_amount(12.345)
        Decimal('12.35')
        >>> round_vat_amount(12.344)  
        Decimal('12.34')
    """
    return round_currency(amount, places=TAX_DECIMAL_PLACES, rounding=TAX_ROUNDING)


def round_tax_base(amount: Union[Decimal, str, float, int]) -> Decimal:
    """
    Данъчна основа закръгляване според ЗДДС.
    
    Args:
        amount: Данъчна основа за закръгляване
        
    Returns:
        Decimal: Закръглена данъчна основа (2 decimal места)
    """
    return round_currency(amount, places=TAX_DECIMAL_PLACES, rounding=TAX_ROUNDING)


def round_quantity(quantity: Union[Decimal, str, float, int],
                  places: int = QUANTITY_DECIMAL_PLACES,
                  rounding: str = QUANTITY_ROUNDING) -> Decimal:
    """
    Закръгляване на количества.
    
    Args:
        quantity: Количеството за закръгляване
        places: Брой decimal места (по подразбиране 3)  
        rounding: Стратегия за закръгляване
        
    Returns:
        Decimal: Закръглено количество
        
    Example:
        >>> round_quantity(12.3456)
        Decimal('12.346')
        >>> round_quantity(5.1234)
        Decimal('5.123')
    """
    try:
        if quantity is None:
            return Decimal('0.000')
            
        decimal_qty = Decimal(str(quantity))
        quantizer = Decimal('0.' + '0' * places)
        
        result = decimal_qty.quantize(quantizer, rounding=rounding)
        
        logger.debug(f"Quantity rounding: {quantity} -> {result} (places={places})")
        return result
        
    except Exception as e:
        logger.error(f"Quantity rounding failed for {quantity}: {e}")
        return Decimal('0.000')


def round_percentage(percent: Union[Decimal, str, float, int],
                    places: int = PERCENTAGE_DECIMAL_PLACES,
                    rounding: str = PERCENTAGE_ROUNDING) -> Decimal:
    """
    Закръгляване на проценти.
    
    Args:
        percent: Процентът за закръгляване
        places: Брой decimal места (по подразбиране 2)
        rounding: Стратегия за закръгляване
        
    Returns:
        Decimal: Закръглен процент
        
    Example:
        >>> round_percentage(12.3456)
        Decimal('12.35')
        >>> round_percentage("20.789")
        Decimal('20.79')
    """
    try:
        if percent is None:
            return Decimal('0.00')
            
        decimal_percent = Decimal(str(percent))
        quantizer = Decimal('0.' + '0' * places)
        
        result = decimal_percent.quantize(quantizer, rounding=rounding)
        
        logger.debug(f"Percentage rounding: {percent} -> {result} (places={places})")
        return result
        
    except Exception as e:
        logger.error(f"Percentage rounding failed for {percent}: {e}")
        return Decimal('0.00')


def round_cost_price(cost: Union[Decimal, str, float, int],
                    places: int = COST_DECIMAL_PLACES,
                    rounding: str = COST_ROUNDING) -> Decimal:
    """
    Закръгляване на cost prices с по-висока точност за калкулации.
    
    Args:
        cost: Cost price за закръгляване
        places: Брой decimal места (по подразбиране 4)
        rounding: Стратегия за закръгляване
        
    Returns:
        Decimal: Закръглена cost price
        
    Example:
        >>> round_cost_price(12.34567)
        Decimal('12.3457')
        >>> round_cost_price("25.123456")
        Decimal('25.1235')
    """
    try:
        if cost is None:
            return Decimal('0.0000')
            
        decimal_cost = Decimal(str(cost))
        quantizer = Decimal('0.' + '0' * places)
        
        result = decimal_cost.quantize(quantizer, rounding=rounding)
        
        logger.debug(f"Cost price rounding: {cost} -> {result} (places={places})")
        return result
        
    except Exception as e:
        logger.error(f"Cost price rounding failed for {cost}: {e}")
        return Decimal('0.0000')


# =============================================================================
# ADVANCED CALCULATION FUNCTIONS
# =============================================================================

def calculate_vat_from_gross(gross_amount: Union[Decimal, str, float, int],
                           vat_rate: Union[Decimal, str, float, int]) -> dict:
    """
    Изчисляване на ДДС от брутна сума (с включен ДДС).
    
    FIXED: Избягва compound rounding errors като изчислява всичко първо,
    след това закръгля накрая.
    
    Args:
        gross_amount: Брутна сума (с ДДС)
        vat_rate: ДДС ставка (напр. 0.20 за 20%)
        
    Returns:
        dict: {
            'net_amount': Decimal,    # Нетна сума (без ДДС)
            'vat_amount': Decimal,    # ДДС сума  
            'gross_amount': Decimal   # Брутна сума (за проверка)
        }
        
    Example:
        >>> calculate_vat_from_gross(120.00, 0.20)
        {
            'net_amount': Decimal('100.00'),
            'vat_amount': Decimal('20.00'), 
            'gross_amount': Decimal('120.00')
        }
    """
    try:
        gross = Decimal(str(gross_amount))
        rate = Decimal(str(vat_rate))
        
        # Изчисли без закръгляване
        net_amount = gross / (Decimal('1') + rate)
        vat_amount = gross - net_amount
        
        # Закръгли накрая
        net_amount = round_tax_base(net_amount)
        vat_amount = round_vat_amount(vat_amount)
        calculated_gross = net_amount + vat_amount
        
        return {
            'net_amount': net_amount,
            'vat_amount': vat_amount,
            'gross_amount': calculated_gross
        }
        
    except Exception as e:
        logger.error(f"VAT from gross calculation failed for {gross_amount}, {vat_rate}: {e}")
        return {
            'net_amount': Decimal('0.00'),
            'vat_amount': Decimal('0.00'), 
            'gross_amount': Decimal('0.00')
        }


def calculate_vat_from_net(net_amount: Union[Decimal, str, float, int],
                         vat_rate: Union[Decimal, str, float, int]) -> dict:
    """
    Изчисляване на ДДС от нетна сума (без ДДС).
    
    FIXED: Избягва compound rounding errors като не закръгля net_amount преди
    изчисляването на VAT.
    
    Args:
        net_amount: Нетна сума (без ДДС)
        vat_rate: ДДС ставка (напр. 0.20 за 20%)
        
    Returns:
        dict: Същото като calculate_vat_from_gross
        
    Example:
        >>> calculate_vat_from_net(100.00, 0.20)
        {
            'net_amount': Decimal('100.00'),
            'vat_amount': Decimal('20.00'),
            'gross_amount': Decimal('120.00')
        }
    """
    try:
        net = Decimal(str(net_amount))  # Без закръгляване
        rate = Decimal(str(vat_rate))
        
        # Изчисли без закръгляване
        vat_amount = net * rate
        
        # Закръгли накрая
        net = round_tax_base(net)
        vat_amount = round_vat_amount(vat_amount)
        gross_amount = net + vat_amount
        
        return {
            'net_amount': net,
            'vat_amount': vat_amount,
            'gross_amount': gross_amount
        }
        
    except Exception as e:
        logger.error(f"VAT from net calculation failed for {net_amount}, {vat_rate}: {e}")
        return {
            'net_amount': Decimal('0.00'),
            'vat_amount': Decimal('0.00'),
            'gross_amount': Decimal('0.00')
        }


def calculate_weighted_average_cost(quantities: list, 
                                  costs: list,
                                  round_result: bool = True) -> Decimal:
    """
    Изчисляване на средно претеглена cost price.
    
    FIXED: Добави intermediate rounding за да избегне безкрайни decimal места
    при multiplication operations.
    
    Args:
        quantities: List от количества
        costs: List от cost prices
        round_result: Да се закръгли ли резултата
        
    Returns:
        Decimal: Средна претеглена cost price
        
    Example:
        >>> calculate_weighted_average_cost([10, 20], [5.00, 7.00])
        Decimal('6.3333')  # (10*5 + 20*7) / (10+20)
    """
    try:
        if not quantities or not costs or len(quantities) != len(costs):
            return Decimal('0.0000')
            
        total_value = Decimal('0')
        total_quantity = Decimal('0')
        
        for qty, cost in zip(quantities, costs):
            qty_decimal = round_quantity(qty)
            cost_decimal = Decimal(str(cost))
            
            # Intermediate rounding за line value за да избегне твърде много decimal места
            line_value = round_cost_price(qty_decimal * cost_decimal)
            total_value += line_value
            total_quantity += qty_decimal
            
        if total_quantity == 0:
            return Decimal('0.0000')
            
        avg_cost = total_value / total_quantity
        
        # Intermediate rounding ако division създаде твърде много decimal места  
        if avg_cost.as_tuple().exponent < -6:  # Повече от 6 decimal места
            avg_cost = avg_cost.quantize(Decimal('0.000001'))  # Intermediate precision
        
        if round_result:
            avg_cost = round_cost_price(avg_cost)
            
        return avg_cost
        
    except Exception as e:
        logger.error(f"Weighted average cost calculation failed: {e}")
        return Decimal('0.0000')


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_currency_precision(amount: Decimal, max_places: int = 2) -> bool:
    """
    Валидира дали паричната сума има правилната точност.
    
    Args:
        amount: Сумата за проверка
        max_places: Максимален брой decimal места
        
    Returns:
        bool: True ако точността е правилна
    """
    try:
        # Провери decimal places
        sign, digits, exponent = amount.as_tuple()
        decimal_places = -exponent if exponent < 0 else 0
        
        return decimal_places <= max_places
        
    except Exception:
        return False


def is_valid_vat_rate(rate: Union[Decimal, str, float, int]) -> bool:
    """
    Валидира дали ДДС ставката е валидна.
    
    Args:
        rate: ДДС ставка за проверка
        
    Returns:
        bool: True ако ставката е валидна
    """
    try:
        decimal_rate = Decimal(str(rate))
        
        # ДДС ставката трябва да е между 0 и 100% (1.00)
        return Decimal('0') <= decimal_rate <= Decimal('1')
        
    except Exception:
        return False


# =============================================================================
# CONFIGURABLE ROUNDING FUNCTIONS
# =============================================================================

def round_by_context(amount: Union[Decimal, str, float, int],
                    context: str,
                    document_type_id: Optional[int] = None) -> Decimal:
    """
    Закръгляване според конфигурирания context.
    
    Използва конфигурацията от базата данни ако е налична,
    иначе използва hardcoded defaults.
    
    Args:
        amount: Сумата за закръгляване  
        context: Context типа ('currency', 'vat', 'quantity', etc.)
        document_type_id: Опционално ID на document type за специфична конфигурация
        
    Returns:
        Decimal: Закръглена сума според конфигурацията
        
    Example:
        >>> round_by_context(12.3456, 'currency')
        Decimal('12.35')  # Using configured or default 2 places
        >>> round_by_context(5.123456, 'cost_price') 
        Decimal('5.1235')  # Using configured or default 4 places
    """
    try:
        if amount is None:
            return Decimal('0')
            
        # Get configuration
        if CONFIG_AVAILABLE:
            config = get_decimal_config(context, document_type_id)
            places = config['decimal_places']
            rounding_strategy = config['rounding_strategy']
            
            logger.debug(f"Using {config['source']} config for {context}: {places} places, {rounding_strategy}")
        else:
            # Fallback to hardcoded defaults
            defaults = {
                'currency': {'places': 2, 'rounding': ROUND_HALF_UP},
                'vat': {'places': 2, 'rounding': ROUND_HALF_UP},
                'tax_base': {'places': 2, 'rounding': ROUND_HALF_UP},
                'quantity': {'places': 3, 'rounding': ROUND_HALF_UP},
                'percentage': {'places': 2, 'rounding': ROUND_HALF_UP},
                'cost_price': {'places': 4, 'rounding': ROUND_HALF_UP},
                'profit': {'places': 2, 'rounding': ROUND_HALF_UP},
                'inventory': {'places': 4, 'rounding': ROUND_HALF_UP},
            }
            
            default_config = defaults.get(context, {'places': 2, 'rounding': ROUND_HALF_UP})
            places = default_config['places']
            rounding_strategy = default_config['rounding']
            
        # Perform rounding
        decimal_amount = Decimal(str(amount))
        
        if CONFIG_AVAILABLE:
            quantizer_str = get_quantizer_string(places)
            quantizer = Decimal(quantizer_str)
        else:
            quantizer = Decimal('0.' + '0' * places) if places > 0 else Decimal('1')
        
        result = decimal_amount.quantize(quantizer, rounding=rounding_strategy)
        
        logger.debug(f"Context rounding ({context}): {amount} -> {result} (places={places})")
        return result
        
    except Exception as e:
        logger.error(f"Context rounding failed for {amount} in context {context}: {e}")
        # Safe fallback
        return ensure_decimal(amount, Decimal('0'))


def get_context_config(context: str, document_type_id: Optional[int] = None) -> dict:
    """
    Получава конфигурацията за даден context.
    
    Args:
        context: Context типа 
        document_type_id: Опционално ID на document type
        
    Returns:
        dict: Конфигурационните настройки
    """
    if CONFIG_AVAILABLE:
        return get_decimal_config(context, document_type_id)
    else:
        # Hardcoded fallback
        defaults = {
            'currency': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'vat': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'tax_base': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'quantity': {'decimal_places': 3, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'percentage': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'cost_price': {'decimal_places': 4, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'profit': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
            'inventory': {'decimal_places': 4, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'},
        }
        return defaults.get(context, {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP, 'source': 'hardcoded'})


# =============================================================================
# PRECISION BRIDGING AND CHAIN CALCULATION UTILITIES
# =============================================================================

def upgrade_to_calculation_precision(amount: Union[Decimal, str, float, int],
                                   target_places: int = 4) -> Decimal:
    """
    Upgrade lower precision amount to higher precision for calculations.
    
    Полезна за смесване на 2dp currency amounts с 4dp cost calculations.
    
    Args:
        amount: Amount to upgrade
        target_places: Target decimal places (default 4 for cost calculations)
        
    Returns:
        Decimal: Amount with increased precision
        
    Example:
        >>> upgrade_to_calculation_precision(Decimal('12.35'), 4)
        Decimal('12.3500')
    """
    try:
        decimal_amount = Decimal(str(amount))
        quantizer = Decimal('0.' + '0' * target_places)
        return decimal_amount.quantize(quantizer)
    except Exception as e:
        logger.error(f"Precision upgrade failed for {amount}: {e}")
        return Decimal('0.' + '0' * target_places)


def calculate_chain(*operations) -> Decimal:
    """
    Execute multiple operations with final rounding only.
    
    Позволява chain от calculations без intermediate rounding.
    
    Args:
        *operations: Functions to execute in sequence
        
    Returns:
        Decimal: Final result
        
    Example:
        >>> calculate_chain(
        ...     lambda: Decimal('100') * Decimal('0.20'),  # VAT calculation
        ...     lambda result: result + Decimal('5'),      # Add fee
        ...     lambda result: round_currency(result)      # Final rounding
        ... )
    """
    try:
        if not operations:
            return Decimal('0')
            
        result = operations[0]()
        
        for operation in operations[1:]:
            result = operation(result)
            
        return result
        
    except Exception as e:
        logger.error(f"Chain calculation failed: {e}")
        return Decimal('0')


# =============================================================================
# CONVENIENCE FUNCTIONS  
# =============================================================================

def ensure_decimal(value: Union[Decimal, str, float, int, None],
                  default: Decimal = Decimal('0')) -> Decimal:
    """
    Осигурява че стойността е Decimal.
    
    Args:
        value: Стойност за конвертиране
        default: Стойност по подразбиране при грешка
        
    Returns:
        Decimal: Конвертираната стойност
    """
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except Exception:
        return default


# =============================================================================
# EXPORT ALL FUNCTIONS
# =============================================================================
__all__ = [
    # Core rounding functions (backward compatible + currency-aware)
    'round_currency',
    'round_vat_amount', 
    'round_tax_base',
    'round_quantity',
    'round_percentage',
    'round_cost_price',
    
    # NEW: Currency helper functions
    'get_default_currency',
    'get_currency_decimal_places',
    
    # NEW: Configurable rounding functions
    'round_by_context',
    'get_context_config',
    
    # Advanced calculations
    'calculate_vat_from_gross',
    'calculate_vat_from_net', 
    'calculate_weighted_average_cost',
    
    # Validation functions
    'validate_currency_precision',
    'is_valid_vat_rate',
    
    # Convenience functions
    'ensure_decimal',
    
    # Constants
    'TAX_DECIMAL_PLACES',
    'CURRENCY_DECIMAL_PLACES',
    'QUANTITY_DECIMAL_PLACES',
    'COST_DECIMAL_PLACES'
]