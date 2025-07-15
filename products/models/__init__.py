# products/models/__init__.py
"""
Products models package - LIFECYCLE VERSION

Архитектура:
- Използва nomenclatures за класификация (Brand, ProductGroup, ProductType)
- products.py: Product модел с lifecycle + ProductPLU
- packaging.py: ProductPackaging + ProductBarcode
"""

# Core product models
from .products import Product, ProductPLU, ProductLifecycleChoices

# Packaging & Barcodes
from .packaging import ProductPackaging, ProductBarcode

# Export всичко за лесен достъп
__all__ = [
    # Основни модели
    'Product',
    'ProductPLU',
    'ProductLifecycleChoices',

    # Опаковки и баркодове
    'ProductPackaging',
    'ProductBarcode',
]

# Версия и мета информация
__version__ = '3.0.0'  # LIFECYCLE VERSION
__author__ = 'Your Company'