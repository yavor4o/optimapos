# nomenclatures/admin/financial.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils.safestring import mark_safe

from ..models import Currency, ExchangeRate, TaxGroup, PriceGroup


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'symbol', 'is_base_badge',
        'decimal_places', 'is_active'
    ]
    list_filter = ['is_base', 'is_active', 'decimal_places']
    search_fields = ['code', 'name']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'symbol', 'is_active')
        }),
        (_('Settings'), {
            'fields': ('is_base', 'decimal_places'),
        }),
    )

    def is_base_badge(self, obj):
        if obj.is_base:
            return format_html(
                '<span style="background: #4CAF50; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">BASE</span>'
            )
        return ''

    is_base_badge.short_description = _('Base')

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = []
        if obj and obj.is_base:
            readonly_fields.append('is_base')  # Не позволяваме промяна на базовата валута
        return readonly_fields


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency', 'date', 'central_rate_display',
        'buy_rate', 'sell_rate', 'created_at'
    ]
    list_filter = ['currency', 'date']
    search_fields = ['currency__code', 'currency__name']
    date_hierarchy = 'date'
    readonly_fields = ['created_at']

    fieldsets = (
        (_('Rate Information'), {
            'fields': ('currency', 'date', 'units')
        }),
        (_('Exchange Rates'), {
            'fields': ('central_rate', 'buy_rate', 'sell_rate'),
        }),
        (_('System Info'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def central_rate_display(self, obj):
        # ПОПРАВЕНО: конвертираме към float
        try:
            rate_value = float(obj.central_rate) if obj.central_rate else 0
            return format_html(
                '<strong>{:.4f}</strong>',
                rate_value
            )
        except (TypeError, ValueError):
            return '-'

    central_rate_display.short_description = _('Central Rate')
    central_rate_display.admin_order_field = 'central_rate'

    central_rate_display.short_description = _('Central Rate')
    central_rate_display.admin_order_field = 'central_rate'


@admin.register(TaxGroup)
class TaxGroupAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'rate_display', 'tax_type_badge',
        'is_default_badge', 'product_count', 'is_active'
    ]
    list_filter = ['tax_type', 'is_default', 'is_active']
    search_fields = ['code', 'name']
    readonly_fields = ['created_at', 'updated_at', 'product_count_info']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'rate', 'tax_type', 'is_active')
        }),
        (_('Special Settings'), {
            'fields': ('is_default', 'is_reverse_charge'),
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at', 'product_count_info'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            product_count_ann=Count('product', distinct=True)
        )

    def rate_display(self, obj):
        return format_html(
            '<strong style="color: #2196F3;">{:.2f}%</strong>',
            obj.rate
        )

    rate_display.short_description = _('Rate')
    rate_display.admin_order_field = 'rate'

    def tax_type_badge(self, obj):
        colors = {
            'VAT': '#4CAF50',
            'EXCISE': '#FF9800',
            'OTHER': '#757575',
        }
        color = colors.get(obj.tax_type, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_tax_type_display()
        )

    tax_type_badge.short_description = _('Type')

    def is_default_badge(self, obj):
        if obj.is_default:
            return format_html(
                '<span style="background: #FF5722; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">DEFAULT</span>'
            )
        return ''

    is_default_badge.short_description = _('Default')

    def product_count(self, obj):
        count = getattr(obj, 'product_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">{}</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    product_count.short_description = _('Products')
    product_count.admin_order_field = 'product_count_ann'

    def product_count_info(self, obj):
        if not obj.pk:
            return "Save first to see product count"
        # Поправяме достъпа до продуктите
        try:
            count = obj.product.count() if hasattr(obj, 'product') else 0
        except:
            count = 0
        return f"{count} products using this tax group"

    product_count_info.short_description = _('Product Count')


# nomenclatures/admin/financial.py - ПОПРАВЕНИ МЕТОДИ

# nomenclatures/admin/financial.py - ПОПРАВЕНИ МЕТОДИ

@admin.register(PriceGroup)
class PriceGroupAdmin(admin.ModelAdmin):
    """Simple admin for Price Groups - без изгъзици"""

    list_display = [
        'code', 'name', 'default_discount_percentage',
        'priority', 'is_active'
    ]

    list_filter = ['is_active', 'priority']
    search_fields = ['code', 'name', 'description']
    list_editable = ['is_active']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
        (_('Pricing Settings'), {
            'fields': ('default_discount_percentage', 'priority')
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']