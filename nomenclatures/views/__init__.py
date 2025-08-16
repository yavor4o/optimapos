# MINIMAL VERSION - избягва circular imports

from .financial import *
from .documents import *
from .products import ProductGroupListView, ProductGroupDetailView, ProductGroupCreateView, ProductGroupUpdateView, \
    ProductGroupDeleteView
from .workflow import WorkflowSettingsView

# Placeholder imports to avoid import errors
BrandListView = ProductGroupListView  # Temporary
BrandDetailView = ProductGroupDetailView
BrandCreateView = ProductGroupCreateView
BrandUpdateView = ProductGroupUpdateView
BrandDeleteView = ProductGroupDeleteView

ProductTypeListView = ProductGroupListView  # Temporary
ProductTypeDetailView = ProductGroupDetailView
ProductTypeCreateView = ProductGroupCreateView
ProductTypeUpdateView = ProductGroupUpdateView
ProductTypeDeleteView = ProductGroupDeleteView

# Future: Add proper imports when ready