# nomenclatures/admin/financial.py
"""
Financial Nomenclatures Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Max
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from ..models import Currency, ExchangeRate, TaxGroup, PriceGroup


# =======================
# EXCHANGE RATE INLINE
# =======================

class ExchangeRateInline(admin.TabularInline):
    """Inline за валутни курсове в Currency админа"""
    model = ExchangeRate
    extra = 1
    readonly_fields = ['created_at', 'created_by']
    fields = ['date', 'central_rate', 'buy_rate', 'sell_rate', 'units', 'is_active']
    ordering = ['-date']

    def get_queryset(self, request):
        # Показва само последните 5 курса
        return super().get_queryset(request).order_by('-date')[:5]


# =======================
# CURRENCY ADMIN
# =======================

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'symbol',
        'base_currency_badge',
        'decimal_places',
        'latest_rate_info',
        'is_active'
    ]

    list_filter = ['is_base', 'is_active', 'decimal_places']
    search_fields = ['code', 'name', 'symbol']
    ordering = ['-is_base', 'code']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'symbol')
        }),
        (_('Configuration'), {
            'fields': ('is_base', 'decimal_places', 'is_active')
        }),
    )

    inlines = [ExchangeRateInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            latest_rate_date=Max('rates__date'),
            rates_count=Count('rates')
        )

    def base_currency_badge(self, obj):
        """Badge за базова валута"""
        if obj.is_base:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;">BASE</span>'
            )
        return '-'

    base_currency_badge.short_description = _('Base Currency')
    base_currency_badge.admin_order_field = 'is_base'

    def latest_rate_info(self, obj):
        """Информация за последния курс"""
        latest_date = getattr(obj, 'latest_rate_date', None)
        rates_count = getattr(obj, 'rates_count', 0)

        if obj.is_base:
            return format_html('<em>{}</em>', _('Base currency'))

        if not latest_date:
            return format_html(
                '<span style="color: #dc3545;">{}</span>',
                _('No rates')
            )

        # Проверяваме дали курсът е актуален (не по-стар от 7 дни)
        days_old = (timezone.now().date() - latest_date).days

        if days_old > 7:
            color = '#dc3545'  # red
            status = _('Outdated')
        elif days_old > 3:
            color = '#ffc107'  # yellow
            status = _('Old')
        else:
            color = '#28a745'  # green
            status = _('Current')

        return format_html(
            '<span style="color: {};">{}</span><br>'
            '<small>{} ({} rates)</small>',
            color, status, latest_date, rates_count
        )

    latest_rate_info.short_description = _('Latest Rate')

    def save_model(self, request, obj, form, change):
        """Автоматично uppercase на code"""
        if obj.code:
            obj.code = obj.code.upper()
        super().save_model(request, obj, form, change)


# =======================
# EXCHANGE RATE ADMIN
# =======================

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency',
        'date',
        'central_rate_display',
        'buy_rate',
        'sell_rate',
        'units',
        'rate_age_badge',
        'is_active'
    ]

    list_filter = [
        'currency',
        'date',
        'is_active',
        ('date', admin.DateFieldListFilter)
    ]

    search_fields = ['currency__code', 'currency__name']
    ordering = ['-date', 'currency__code']
    date_hierarchy = 'date'

    readonly_fields = ['created_at', 'created_by']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('currency', 'date', 'units')
        }),
        (_('Rates'), {
            'fields': ('central_rate', 'buy_rate', 'sell_rate')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Audit'), {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def central_rate_display(self, obj):
        """Показва централния курс с форматиране"""
        return format_html(
            '<strong>{:.6f}</strong>',
            obj.central_rate
        )

    central_rate_display.short_description = _('Central Rate')
    central_rate_display.admin_order_field = 'central_rate'

    def rate_age_badge(self, obj):
        """Badge показващ възрастта на курса"""
        days_old = (timezone.now().date() - obj.date).days

        if days_old == 0:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">TODAY</span>'
            )
        elif days_old <= 3:
            return format_html(
                '<span style="background-color: #17a2b8; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">{} DAYS</span>',
                days_old
            )
        elif days_old <= 7:
            return format_html(
                '<span style="background-color: #ffc107; color: black; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">{} DAYS</span>',
                days_old
            )
        else:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">OLD ({} days)</span>',
                days_old
            )

    rate_age_badge.short_description = _('Age')

    def save_model(self, request, obj, form, change):
        """Записва кой потребител е създал курса"""
        if not change:  # Ново създаване
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# =======================
# TAX GROUP ADMIN
# =======================

@admin.register(TaxGroup)
class TaxGroupAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'rate_display',
        'tax_type_badge',
        'default_badge',
        'reverse_charge_badge',
        'is_active'
    ]

    list_filter = [
        'tax_type',
        'is_default',
        'is_reverse_charge',
        'is_active'
    ]

    search_fields = ['code', 'name']
    ordering = ['-is_default', 'rate', 'name']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'rate', 'tax_type')
        }),
        (_('Special Settings'), {
            'fields': ('is_default', 'is_reverse_charge')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
    )

    def rate_display(self, obj):
        """Показва ставката с процент"""
        return format_html(
            '<strong style="font-size: 13px;">{:.2f}%</strong>',
            obj.rate
        )

    rate_display.short_description = _('Rate')
    rate_display.admin_order_field = 'rate'

    def tax_type_badge(self, obj):
        """Badge за типа данък"""
        colors = {
            'VAT': '#007bff',
            'EXCISE': '#dc3545',
            'OTHER': '#6c757d'
        }
        color = colors.get(obj.tax_type, '#6c757d')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_tax_type_display()
        )

    tax_type_badge.short_description = _('Type')
    tax_type_badge.admin_order_field = 'tax_type'

    def default_badge(self, obj):
        """Badge за данъчна група по подразбиране"""
        if obj.is_default:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">DEFAULT</span>'
            )
        return '-'

    default_badge.short_description = _('Default')
    default_badge.admin_order_field = 'is_default'

    def reverse_charge_badge(self, obj):
        """Badge за reverse charge"""
        if obj.is_reverse_charge:
            return format_html(
                '<span style="background-color: #fd7e14; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">RC</span>'
            )
        return '-'

    reverse_charge_badge.short_description = _('Reverse Charge')
    reverse_charge_badge.admin_order_field = 'is_reverse_charge'


# =======================
# PRICE GROUP ADMIN
# =======================

@admin.register(PriceGroup)
class PriceGroupAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'discount_display',
        'price_type_badge',
        'customer_count',
        'is_active'
    ]

    list_filter = [
        'price_type',
        'is_active'
    ]

    search_fields = ['code', 'name']
    ordering = ['name']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'price_type')
        }),
        (_('Discount Settings'), {
            'fields': ('default_discount_percent',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Ако има връзка към customers
        try:
            return qs.annotate(customer_count_ann=Count('customer', distinct=True))
        except:
            return qs

    def discount_display(self, obj):
        """Показва отстъпката"""
        if obj.default_discount_percent and obj.default_discount_percent > 0:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">{:.1f}%</span>',
                obj.default_discount_percent
            )
        return '-'

    discount_display.short_description = _('Discount')
    discount_display.admin_order_field = 'default_discount_percent'

    def price_type_badge(self, obj):
        """Badge за типа цена"""
        colors = {
            'RETAIL': '#007bff',
            'WHOLESALE': '#28a745',
            'VIP': '#dc3545',
            'SPECIAL': '#fd7e14'
        }
        color = colors.get(obj.price_type, '#6c757d')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_price_type_display()
        )

    price_type_badge.short_description = _('Type')
    price_type_badge.admin_order_field = 'price_type'

    def customer_count(self, obj):
        """Брой клиенти в тази ценова група"""
        try:
            count = getattr(obj, 'customer_count_ann', 0)
            if count > 0:
                return format_html('<strong>{}</strong>', count)
            return '0'
        except:
            return '-'

    customer_count.short_description = _('Customers')