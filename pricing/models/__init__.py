# pricing/models/__init__.py

"""
Pricing models package

Организация:
- groups.py: PriceGroup
- base_prices.py: ProductPrice (base prices per location)
- group_prices.py: ProductPriceByGroup
- step_prices.py: ProductStepPrice
- promotions.py: PromotionalPrice
- packaging_prices.py: PackagingPrice
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

# Packaging Prices
from .packaging_prices import (
    PackagingPrice,
    PackagingPriceManager
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

    # Packaging Prices
    'PackagingPrice',
    'PackagingPriceManager',
]

# Version info
__version__ = '1.1.0'