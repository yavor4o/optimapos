# nomenclatures/urls.py
from django.urls import path, include
from . import views


app_name = 'nomenclatures'

urlpatterns = [
    # Product Classifications
    path('product-groups/', include([
        path('', views.ProductGroupListView.as_view(), name='product_groups'),
        path('create/', views.ProductGroupCreateView.as_view(), name='product_groups_create'),
        path('<int:pk>/modal/', views.ProductGroupDetailModalView.as_view(), name='product_groups_detail_modal'),  # ← Правилно
        path('<int:pk>/edit/', views.ProductGroupUpdateView.as_view(), name='product_groups_edit'),
        path('<int:pk>/delete/', views.ProductGroupDeleteView.as_view(), name='product_groups_delete'),
        path('<int:pk>/move/', views.ProductGroupMoveView.as_view(), name='product_groups_move'),
    ])),

    # Brands (future)
    path('brands/', include([
        path('', views.BrandListView.as_view(), name='brands'),
        path('create/', views.BrandCreateView.as_view(), name='brands_create'),

        path('<int:pk>/edit/', views.BrandUpdateView.as_view(), name='brands_edit'),
        path('<int:pk>/delete/', views.BrandDeleteView.as_view(), name='brands_delete'),
    ])),

    # Product Types (future)
    path('product-types/', include([
        path('', views.ProductTypeListView.as_view(), name='product_types'),
        path('create/', views.ProductTypeCreateView.as_view(), name='product_types_create'),
        path('<int:pk>/edit/', views.ProductTypeUpdateView.as_view(), name='product_types_edit'),
        path('<int:pk>/delete/', views.ProductTypeDeleteView.as_view(), name='product_types_delete'),
    ])),

    # Financial Settings (future)
    path('currencies/', include([
        path('', views.CurrencyListView.as_view(), name='currencies'),
        path('create/', views.CurrencyCreateView.as_view(), name='currencies_create'),
        path('<int:pk>/', views.CurrencyDetailView.as_view(), name='currencies_detail'),
        path('<int:pk>/edit/', views.CurrencyUpdateView.as_view(), name='currencies_edit'),
        path('<int:pk>/delete/', views.CurrencyDeleteView.as_view(), name='currencies_delete'),
    ])),

    path('tax-groups/', include([
        path('', views.TaxGroupListView.as_view(), name='tax_groups'),
        path('create/', views.TaxGroupCreateView.as_view(), name='tax_groups_create'),
        path('<int:pk>/', views.TaxGroupDetailView.as_view(), name='tax_groups_detail'),
        path('<int:pk>/edit/', views.TaxGroupUpdateView.as_view(), name='tax_groups_edit'),
        path('<int:pk>/delete/', views.TaxGroupDeleteView.as_view(), name='tax_groups_delete'),
    ])),

    path('price-groups/', include([
        path('', views.PriceGroupListView.as_view(), name='price_groups'),
        path('create/', views.PriceGroupCreateView.as_view(), name='price_groups_create'),
        path('<int:pk>/', views.PriceGroupDetailView.as_view(), name='price_groups_detail'),
        path('<int:pk>/edit/', views.PriceGroupUpdateView.as_view(), name='price_groups_edit'),
        path('<int:pk>/delete/', views.PriceGroupDeleteView.as_view(), name='price_groups_delete'),
    ])),

    # Document Types (future)
    path('document-types/', include([
        path('', views.DocumentTypeListView.as_view(), name='document_types'),
        path('create/', views.DocumentTypeCreateView.as_view(), name='document_types_create'),
        path('<int:pk>/', views.DocumentTypeDetailView.as_view(), name='document_types_detail'),
        path('<int:pk>/edit/', views.DocumentTypeUpdateView.as_view(), name='document_types_edit'),
        path('<int:pk>/delete/', views.DocumentTypeDeleteView.as_view(), name='document_types_delete'),
    ])),

    # Workflow Settings (future)
    path('workflow-settings/', views.WorkflowSettingsView.as_view(), name='workflow_settings'),
]