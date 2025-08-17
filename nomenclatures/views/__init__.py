# nomenclatures/views/__init__.py

from .financial import *
from .documents import *

from .products import (
    ProductGroupListView,
    ProductGroupDetailModalView,
    ProductGroupCreateView,
    ProductGroupUpdateView,
    ProductGroupDeleteView,
    ProductGroupMoveView
)

# Импортираме реалните Brand views
from .products import (
    BrandListView,
    BrandCreateView,
    BrandUpdateView,
    BrandDeleteView,
    BrandDetailView,
)

from .workflow import WorkflowSettingsView

# Placeholder imports за Product Types (още не са създадени)
ProductTypeListView = ProductGroupListView
ProductTypeCreateView = ProductGroupCreateView
ProductTypeUpdateView = ProductGroupUpdateView
ProductTypeDeleteView = ProductGroupDeleteView