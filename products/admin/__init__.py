# products/admin/__init__.py - FIXED VERSION
"""
Products admin package - LIFECYCLE VERSION

Comprehensive admin interface for product lifecycle management
"""

# Main product admin - now with inlines
from .product import (
    ProductAdmin,
    ProductPLUInline,
    ProductPackagingInline,
    ProductBarcodeInline,
    # Custom filters
    LifecycleStatusFilter,
    BlockStatusFilter,
    SellabilityFilter,
    StockLevelFilter,
)

# Separate admins (already implemented)
from .packaging import ProductPackagingAdmin, ProductBarcodeAdmin

# Optional dashboard and actions (uncomment if using)
# from .dashboard import ProductDashboardMixin
from .actions import PRODUCT_ADMIN_ACTIONS

# Export all for Django auto-discovery
__all__ = [
    # Main admin classes
    'ProductAdmin',

    # Inline admin classes
    'ProductPLUInline',
    'ProductPackagingInline',
    'ProductBarcodeInline',

    # Separate admin classes
    'ProductPackagingAdmin',
    'ProductBarcodeAdmin',

    # Custom filters (reusable)
    'LifecycleStatusFilter',
    'BlockStatusFilter',
    'SellabilityFilter',
    'StockLevelFilter',

    # Actions
    'PRODUCT_ADMIN_ACTIONS',
]

# Metadata
__version__ = '3.0.0'  # LIFECYCLE VERSION
__admin_site__ = 'products'
__description__ = 'Product lifecycle management admin interface'

# Admin site customization
from django.contrib import admin

admin.site.site_header = 'OptimaPos Product Management'
admin.site.site_title = 'Products Admin'
admin.site.index_title = 'Product Management Dashboard'

# Add custom CSS/JS (optional)
# admin.site.extra_css = ['admin/products/css/lifecycle.css']
# admin.site.extra_js = ['admin/products/js/lifecycle.js']