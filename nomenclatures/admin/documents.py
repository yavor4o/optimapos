# nomenclatures/admin/documents.py - ПРОСТ И РАБОТЕЩ
from django.contrib import admin
from ..models import DocumentType


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'app_name',
        'type_key',
        'affects_inventory',
        'requires_approval',
        'is_fiscal',
        'is_active'
    ]

    list_filter = [
        'app_name',
        'affects_inventory',
        'requires_approval',
        'is_fiscal',
        'is_active'
    ]

    search_fields = ['name', 'type_key', 'app_name']
    ordering = ['app_name', 'name']


# nomenclatures/admin/financial.py - ПРОСТ И РАБОТЕЩ
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


# nomenclatures/admin/workflow.py - ПРОСТ БЕЗ ГЛУПОСТИ
from django.contrib import admin

# Try to import models
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_MODELS = True
except ImportError:
    HAS_MODELS = False

if HAS_MODELS:
    @admin.register(ApprovalRule)
    class ApprovalRuleAdmin(admin.ModelAdmin):
        list_display = ['name', 'document_type', 'is_active']
        list_filter = ['document_type', 'is_active']
        search_fields = ['name']


    @admin.register(ApprovalLog)
    class ApprovalLogAdmin(admin.ModelAdmin):
        list_display = ['action', 'is_active']
        list_filter = ['action', 'is_active']
        readonly_fields = ['action']  # Basic readonly

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False
else:
    # Dummy classes if models don't exist
    class ApprovalRuleAdmin:
        pass


    class ApprovalLogAdmin:
        pass