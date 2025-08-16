# nomenclatures/views/__init__.py
"""
Nomenclatures Views Package

АРХИТЕКТУРА:
- product.py: Views за Product Groups, Brands, Product Types
- financial.py: Views за Currency, Tax Groups, Price Groups
- documents.py: Views за Document Types
- workflow.py: Views за Workflow Settings

ПРИНЦИП: Всички views са клас базирани CBV с професионални mixins
"""

from .product import (
    # Product Groups
    ProductGroupListView,
    ProductGroupDetailView,
    ProductGroupCreateView,
    ProductGroupUpdateView,
    ProductGroupDeleteView,

    # Brands (future implementation)
    BrandListView,
    BrandDetailView,
    BrandCreateView,
    BrandUpdateView,
    BrandDeleteView,

    # Product Types (future implementation)
    ProductTypeListView,
    ProductTypeDetailView,
    ProductTypeCreateView,
    ProductTypeUpdateView,
    ProductTypeDeleteView,
)

from .financial import (
    # Currency (future implementation)
    CurrencyListView,
    CurrencyDetailView,
    CurrencyCreateView,
    CurrencyUpdateView,
    CurrencyDeleteView,

    # Tax Groups (future implementation)
    TaxGroupListView,
    TaxGroupDetailView,
    TaxGroupCreateView,
    TaxGroupUpdateView,
    TaxGroupDeleteView,

    # Price Groups (future implementation)
    PriceGroupListView,
    PriceGroupDetailView,
    PriceGroupCreateView,
    PriceGroupUpdateView,
    PriceGroupDeleteView,
)

from .documents import (
    # Document Types (future implementation)
    DocumentTypeListView,
    DocumentTypeDetailView,
    DocumentTypeCreateView,
    DocumentTypeUpdateView,
    DocumentTypeDeleteView,
)

from .workflow import (
    # Workflow Settings (future implementation)
    WorkflowSettingsView,
)

# Export all views for Django URL routing
__all__ = [
    # Product views
    'ProductGroupListView', 'ProductGroupDetailView', 'ProductGroupCreateView',
    'ProductGroupUpdateView', 'ProductGroupDeleteView',
    'BrandListView', 'BrandDetailView', 'BrandCreateView', 'BrandUpdateView', 'BrandDeleteView',
    'ProductTypeListView', 'ProductTypeDetailView', 'ProductTypeCreateView',
    'ProductTypeUpdateView', 'ProductTypeDeleteView',

    # Financial views
    'CurrencyListView', 'CurrencyDetailView', 'CurrencyCreateView', 'CurrencyUpdateView', 'CurrencyDeleteView',
    'TaxGroupListView', 'TaxGroupDetailView', 'TaxGroupCreateView', 'TaxGroupUpdateView', 'TaxGroupDeleteView',
    'PriceGroupListView', 'PriceGroupDetailView', 'PriceGroupCreateView', 'PriceGroupUpdateView',
    'PriceGroupDeleteView',

    # Document views
    'DocumentTypeListView', 'DocumentTypeDetailView', 'DocumentTypeCreateView',
    'DocumentTypeUpdateView', 'DocumentTypeDeleteView',

    # Workflow views
    'WorkflowSettingsView',
]