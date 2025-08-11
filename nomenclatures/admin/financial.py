# nomenclatures/admin/financial.py
from django.contrib import admin
from ..models import Currency, ExchangeRate, TaxGroup, PriceGroup

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'is_base', 'decimal_places', 'is_active']
    list_filter = ['is_base', 'is_active']
    search_fields = ['code', 'name']

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['currency', 'date', 'central_rate', 'buy_rate', 'sell_rate', 'is_active']
    list_filter = ['currency', 'date', 'is_active']
    date_hierarchy = 'date'

@admin.register(TaxGroup)
class TaxGroupAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'rate', 'tax_type', 'is_default', 'is_active']
    list_filter = ['tax_type', 'is_default', 'is_active']
    search_fields = ['code', 'name']

@admin.register(PriceGroup)
class PriceGroupAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']