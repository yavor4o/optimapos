# products/models/__init__.py
"""
Products models package
"""

# Base classification
from .base import ProductType, ProductGroup, Brand

# Core product models
from .products import Product, ProductPLU

# Packaging & Barcodes
from .packaging import ProductPackaging, ProductBarcode

__all__ = [
    # Base
    'ProductType',
    'ProductGroup',
    'Brand',

    # Core
    'Product',
    'ProductPLU',

    # Packaging
    'ProductPackaging',
    'ProductBarcode',
]
