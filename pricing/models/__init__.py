# pricing/models/__init__.py

"""
Pricing models package

Организация:
- groups.py: PriceGroup
- base_prices.py: ProductPrice (base prices per location)
- group_prices.py: ProductPriceByGroup
- step_prices.py: ProductStepPrice
- promotions.py: PromotionalPrice
"""

# Price Groups
from .groups import (
    PriceGroup,
    PriceGroupManager
)

# Base Prices
from .base_prices import (
    ProductPrice,
    ProductPriceManager
)

# Group Prices
from .group_prices import (
    ProductPriceByGroup,
    ProductPriceByGroupManager
)

# Step Prices
from .step_prices import (
    ProductStepPrice,
    ProductStepPriceManager
)

# Promotions
from .promotions import (
    PromotionalPrice,
    PromotionalPriceManager
)

# Export all
__all__ = [
    # Groups
    'PriceGroup',
    'PriceGroupManager',

    # Base Prices
    'ProductPrice',
    'ProductPriceManager',

    # Group Prices
    'ProductPriceByGroup',
    'ProductPriceByGroupManager',

    # Step Prices
    'ProductStepPrice',
    'ProductStepPriceManager',

    # Promotions
    'PromotionalPrice',
    'PromotionalPriceManager',
]

# Version info
__version__ = '1.0.0'