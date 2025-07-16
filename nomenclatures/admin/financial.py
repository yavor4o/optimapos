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
        return format_html(
            '<strong>{:.4f}</strong>',
            obj.central_rate
        )

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


@admin.register(PriceGroup)
class PriceGroupAdmin(admin.ModelAdmin):
    """Admin for Price Groups - ценови групи за клиенти"""

    list_display = [
        'priority_badge', 'code', 'name', 'discount_display',
        'customer_count', 'pricing_count', 'is_active'
    ]

    list_filter = ['is_active', 'priority']
    search_fields = ['code', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'usage_statistics']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
        (_('Pricing Settings'), {
            'fields': ('default_discount_percentage', 'priority'),
            'description': _('Default discount and priority for conflict resolution')
        }),
        (_('Statistics'), {
            'fields': ('usage_statistics',),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            customer_count_ann=Count('customers', distinct=True, filter=Q(customers__is_active=True)),
            pricing_count_ann=Count('product_group_prices', distinct=True,
                                    filter=Q(product_group_prices__is_active=True))
        )

    def priority_badge(self, obj):
        """Приоритет с цветно означение"""
        if obj.priority >= 100:
            color = '#F44336'  # Червен - висок приоритет
            icon = '🔥'
        elif obj.priority >= 50:
            color = '#FF9800'  # Оранжев - среден приоритет
            icon = '⚡'
        elif obj.priority > 0:
            color = '#4CAF50'  # Зелен - нисък приоритет
            icon = '📈'
        else:
            color = '#757575'  # Сив - без приоритет
            icon = '➖'

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{} {}</span>',
            color, icon, obj.priority
        )

    priority_badge.short_description = _('Priority')
    priority_badge.admin_order_field = 'priority'

    def discount_display(self, obj):
        """Отстъпка с цветно означение"""
        if obj.default_discount_percentage > 0:
            return format_html(
                '<strong style="color: #4CAF50;">-{:.1f}%</strong>',
                obj.default_discount_percentage
            )
        return format_html('<span style="color: gray;">0%</span>')

    discount_display.short_description = _('Discount')
    discount_display.admin_order_field = 'default_discount_percentage'

    def customer_count(self, obj):
        """Брой клиенти в групата"""
        count = getattr(obj, 'customer_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: #2196F3; font-weight: bold;">{} 👥</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    customer_count.short_description = _('Customers')
    customer_count.admin_order_field = 'customer_count_ann'

    def pricing_count(self, obj):
        """Брой специални ценови правила"""
        count = getattr(obj, 'pricing_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: #9C27B0; font-weight: bold;">{} 💰</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    pricing_count.short_description = _('Price Rules')
    pricing_count.admin_order_field = 'pricing_count_ann'

    def usage_statistics(self, obj):
        """Подробна статистика за използването"""
        if not obj.pk:
            return "Save price group first to see statistics"

        stats = []

        # Клиенти
        customer_count = obj.get_customer_count()
        if customer_count > 0:
            stats.append(f"<strong>Customers:</strong> {customer_count}")

        # Ценови правила
        pricing_count = obj.get_product_count()
        if pricing_count > 0:
            stats.append(f"<strong>Special Prices:</strong> {pricing_count}")

        # Среден размер на отстъпката
        if obj.default_discount_percentage > 0:
            stats.append(f"<strong>Default Discount:</strong> {obj.default_discount_percentage:.1f}%")

        # Приоритет
        if obj.priority > 0:
            stats.append(f"<strong>Priority Level:</strong> {obj.priority}")

        if not stats:
            stats.append("No usage data available")

        return mark_safe('<br>'.join(stats))

    usage_statistics.short_description = _('Usage Statistics')

    # Actions
    actions = ['activate_price_groups', 'deactivate_price_groups', 'bulk_set_priority']

    def activate_price_groups(self, request, queryset):
        """Активиране на ценови групи"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'Activated {count} price groups.')

    activate_price_groups.short_description = _('Activate selected price groups')

    def deactivate_price_groups(self, request, queryset):
        """Деактивиране на ценови групи"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {count} price groups.')

    deactivate_price_groups.short_description = _('Deactivate selected price groups')

    def bulk_set_priority(self, request, queryset):
        """Bulk промяна на приоритет"""
        count = queryset.update(priority=50)
        self.message_user(request, f'Set priority to 50 for {count} price groups.')

    bulk_set_priority.short_description = _('Set priority to 50')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.pk:
            # При редактиране можем да правим code readonly ако има клиенти
            if obj.get_customer_count() > 0:
                readonly.append('code')
        return readonly