# products/models/__init__.py
"""
Products models package

Архитектура:
- Използва nomenclatures за класификация (Brand, ProductGroup, ProductType)
- products.py: Основен Product модел + ProductPLU
- packaging.py: ProductPackaging + ProductBarcode
"""

# Core product models
from .products import Product, ProductPLU

# Packaging & Barcodes
from .packaging import ProductPackaging, ProductBarcode

# Export всичко за лесен достъп
__all__ = [
    # Основни модели
    'Product',
    'ProductPLU',

    # Опаковки и баркодове
    'ProductPackaging',
    'ProductBarcode',
]

# Версия и мета информация
__version__ = '2.0.0'
__author__ = 'Your Company'

# App configuration
default_app_config = 'products.apps.ProductsConfig'