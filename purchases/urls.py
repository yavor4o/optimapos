# purchases/urls.py
from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('api/last-purchase-price/', views.last_purchase_price_api, name='last_purchase_price'),
    path('order/<int:pk>/test-workflow/', views.test_order_workflow, name='test_order_workflow'),
    path('order/<int:pk>/workflow-action/', views.workflow_action, name='workflow_action'),  # НОВА ЛИНИЯ
]