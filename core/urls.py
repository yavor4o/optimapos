# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Главна страница - Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),
]