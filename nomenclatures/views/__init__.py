# 1. В nomenclatures/views/__init__.py - премахни ProductGroupDetailView

from .financial import *
from .documents import *
from .products import (
    ProductGroupListView,
    ProductGroupDetailModalView,   # ← Само това
    ProductGroupCreateView,
    ProductGroupUpdateView,
    ProductGroupDeleteView
)
from .workflow import WorkflowSettingsView

# Placeholder imports to avoid import errors
BrandListView = ProductGroupListView
BrandCreateView = ProductGroupCreateView
BrandUpdateView = ProductGroupUpdateView
BrandDeleteView = ProductGroupDeleteView

ProductTypeListView = ProductGroupListView
ProductTypeCreateView = ProductGroupCreateView
ProductTypeUpdateView = ProductGroupUpdateView
ProductTypeDeleteView = ProductGroupDeleteView

# НЕ импортирай ProductGroupDetailView - няма такова нещо!