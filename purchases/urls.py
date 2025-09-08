# purchases/urls.py
from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    # Dashboard
    path('', views.PurchasesIndexView.as_view(), name='index'),
    
    # Delivery Receipts
    path('deliveries/', views.DeliveryReceiptListView.as_view(), name='delivery_list'),
    path('deliveries/create/', views.DeliveryReceiptCreateView.as_view(), name='delivery_create'),
    path('deliveries/<int:pk>/', views.DeliveryReceiptDetailView.as_view(), name='delivery_detail'),
    path('deliveries/<int:pk>/edit/', views.DeliveryReceiptUpdateView.as_view(), name='delivery_update'),
    path('deliveries/<int:pk>/action/', views.DeliveryReceiptActionView.as_view(), name='delivery_action'),
    
    # Delivery Lines - для AJAX operations
    path('delivery-lines/<int:pk>/quality-check/', views.DeliveryLineQualityCheckView.as_view(), name='delivery_line_quality'),
    
    # Ajax endpoints
    path('ajax/product-pricing/', views.ProductPricingAjaxView.as_view(), name='ajax_product_pricing'),
]