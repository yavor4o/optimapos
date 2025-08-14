# purchases/urls.py
from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('api/last-purchase-price/', views.last_purchase_price_api, name='last_purchase_price'),
]