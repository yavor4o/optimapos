# products/admin/__init__.py

"""
Products admin package
Exports all admin classes for registration
"""

# Import main admin classes
from .product import ProductAdmin
from .packaging import ProductPackagingAdmin, ProductBarcodeAdmin, ProductPLUAdmin

# Import dashboard functionality
from .dashboard import ProductDashboardMixin, ProductDashboard

# Import reusable actions
from .actions import (
    PRODUCT_ADMIN_ACTIONS,
    make_products_active,
    make_products_phase_out,
    make_products_discontinued,
    block_product_sales,
    unblock_product_sales,
    block_product_purchases,
    unblock_product_purchases,
    export_products_csv,
    export_stock_report,
    validate_products,
    enable_batch_tracking,
    disable_batch_tracking,
)

# Export everything
__all__ = [
    # Main admins
    'ProductAdmin',
    'ProductPackagingAdmin',
    'ProductBarcodeAdmin',
    'ProductPLUAdmin',

    # Dashboard
    'ProductDashboardMixin',
    'ProductDashboard',

    # Actions
    'PRODUCT_ADMIN_ACTIONS',
    'make_products_active',
    'make_products_phase_out',
    'make_products_discontinued',
    'block_product_sales',
    'unblock_product_sales',
    'block_product_purchases',
    'unblock_product_purchases',
    'export_products_csv',
    'export_stock_report',
    'validate_products',
    'enable_batch_tracking',
    'disable_batch_tracking',
]