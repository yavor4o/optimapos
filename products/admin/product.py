# products/admin/product.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, F

from ..models import Product, ProductPLU, ProductPackaging, ProductBarcode
from ..services import ProductService


# === INLINE ADMINS ===

class ProductPLUInline(admin.TabularInline):
    model = ProductPLU
    extra = 1
    fields = ['plu_code', 'is_primary', 'priority', 'description', 'is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-is_primary', '-priority')


class ProductPackagingInline(admin.TabularInline):
    model = ProductPackaging
    extra = 1
    fields = [
        'unit', 'conversion_factor', 'is_default_sale_unit',
        'is_default_purchase_unit', 'is_active'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('unit')


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1
    fields = [
        'barcode', 'barcode_type', 'packaging', 'is_primary', 'is_active'
    ]
    readonly_fields = ['barcode_type']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('packaging', 'packaging__unit')


# === CUSTOM FILTERS ===

class StockLevelFilter(admin.SimpleListFilter):
    title = _('Stock Level')
    parameter_name = 'stock_level'

    def lookups(self, request, model_admin):
        return (
            ('no_stock', _('No Stock')),
            ('low_stock', _('Low Stock (< 10)')),
            ('good_stock', _('Good Stock (10+)')),
            ('high_stock', _('High Stock (100+)')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'no_stock':
            return queryset.filter(current_stock_qty=0)
        elif self.value() == 'low_stock':
            return queryset.filter(current_stock_qty__gt=0, current_stock_qty__lt=10)
        elif self.value() == 'good_stock':
            return queryset.filter(current_stock_qty__gte=10, current_stock_qty__lt=100)
        elif self.value() == 'high_stock':
            return queryset.filter(current_stock_qty__gte=100)
        return queryset


class CostRangeFilter(admin.SimpleListFilter):
    title = _('Cost Range')
    parameter_name = 'cost_range'

    def lookups(self, request, model_admin):
        return (
            ('free', _('Free (0.00)')),
            ('cheap', _('Cheap (0.01-1.00)')),
            ('medium', _('Medium (1.01-10.00)')),
            ('expensive', _('Expensive (10.01+)')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'free':
            return queryset.filter(current_avg_cost=0)
        elif self.value() == 'cheap':
            return queryset.filter(current_avg_cost__gt=0, current_avg_cost__lte=1)
        elif self.value() == 'medium':
            return queryset.filter(current_avg_cost__gt=1, current_avg_cost__lte=10)
        elif self.value() == 'expensive':
            return queryset.filter(current_avg_cost__gt=10)
        return queryset


# === MAIN PRODUCT ADMIN ===

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name_display', 'brand', 'product_group', 'unit_type',
        'stock_status', 'cost_info', 'plu_info', 'barcodes_count', 'is_active'
    ]

    list_filter = [
        'is_active', 'unit_type', 'brand', 'product_group', 'product_type',
        'track_batches', StockLevelFilter, CostRangeFilter
    ]

    search_fields = [
        'code', 'name',
        'barcodes__barcode',
        'plu_codes__plu_code'
    ]

    list_editable = ['is_active']

    readonly_fields = [
        'created_at', 'updated_at', 'inventory_summary', 'profit_analysis'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'is_active')
        }),
        (_('Classification'), {
            'fields': ('brand', 'product_group', 'product_type'),
            'classes': ('collapse',)
        }),
        (_('Unit Configuration'), {
            'fields': ('base_unit', 'unit_type')  # REMOVED primary_plu
        }),
        (_('Settings'), {
            'fields': ('tax_group', 'track_batches')
        }),
        (_('Moving Average Cost'), {
            'fields': (
                'current_avg_cost', 'current_stock_qty',
                'last_purchase_cost', 'last_purchase_date'
            ),
            'description': _('Automatically calculated from purchase movements')
        }),
        (_('Inventory Summary'), {
            'fields': ('inventory_summary',),
            'classes': ('collapse',),
        }),
        (_('Profit Analysis'), {
            'fields': ('profit_analysis',),
            'classes': ('collapse',),
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [ProductPLUInline, ProductPackagingInline, ProductBarcodeInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'brand', 'product_group', 'product_type', 'base_unit', 'tax_group'
        ).prefetch_related('plu_codes', 'barcodes', 'packagings')

    def name_display(self, obj):
        """Truncated name with tooltip"""
        if len(obj.name) > 40:
            return format_html(
                '<span title="{}">{}</span>',
                obj.name, obj.name[:40] + '...'
            )
        return obj.name

    name_display.short_description = _('Product Name')

    def stock_status(self, obj):
        """Stock status with visual indicators"""
        qty = obj.current_stock_qty

        if qty <= 0:
            return format_html(
                '<span style="color: red;">🔴 Out of Stock</span>'
            )
        elif qty < 10:
            return format_html(
                '<span style="color: orange;">🟡 Low Stock: {}</span>',
                qty
            )
        else:
            return format_html(
                '<span style="color: green;">🟢 In Stock: {}</span>',
                qty
            )

    stock_status.short_description = _('Stock Status')

    def cost_info(self, obj):
        """Cost information display"""
        avg_cost = obj.current_avg_cost
        last_cost = obj.last_purchase_cost

        if avg_cost > 0:
            cost_info = f"Avg: {avg_cost:.2f} лв"
            if last_cost > 0 and last_cost != avg_cost:
                change = "↗️" if last_cost > avg_cost else "↘️"
                cost_info += f"<br><small>Last: {last_cost:.2f} {change}</small>"

            return format_html(cost_info)

        return format_html('<span style="color: gray;">No cost data</span>')

    cost_info.short_description = _('Cost Info')

    def plu_info(self, obj):
        """PLU codes information - using related PLU objects"""
        primary_plu = obj.plu_codes.filter(is_primary=True).first()
        other_plus = obj.plu_codes.filter(is_active=True).exclude(is_primary=True)[:3]

        plu_codes = []

        if primary_plu:
            plu_codes.append(f"<strong>{primary_plu.plu_code}</strong>")

        for plu in other_plus:
            plu_codes.append(plu.plu_code)

        if obj.plu_codes.count() > 3:
            plu_codes.append("...")

        if plu_codes:
            return format_html('<br>'.join(plu_codes))

        return format_html('<span style="color: gray;">No PLU</span>')

    plu_info.short_description = _('PLU Codes')

    def barcodes_count(self, obj):
        """Barcode count with link"""
        count = obj.barcodes.count()
        if count > 0:
            return format_html(
                '<span style="color: green;">📊 {} barcode(s)</span>',
                count
            )
        return format_html('<span style="color: red;">❌ No barcodes</span>')

    barcodes_count.short_description = _('Barcodes')

    def inventory_summary(self, obj):
        """Detailed inventory information"""
        if not obj.pk:
            return "Save product first to see inventory data"

        summary_parts = [
            f"<strong>Current Stock:</strong> {obj.current_stock_qty} {obj.base_unit.code}",
            f"<strong>Average Cost:</strong> {obj.current_avg_cost:.4f} лв",
            f"<strong>Total Value:</strong> {obj.current_stock_qty * obj.current_avg_cost:.2f} лв",
        ]

        if obj.last_purchase_date:
            summary_parts.append(f"<strong>Last Purchase:</strong> {obj.last_purchase_date}")

        if obj.track_batches:
            summary_parts.append("<strong>Batch Tracking:</strong> Enabled")

        # PLU information
        primary_plu = obj.plu_codes.filter(is_primary=True).first()
        if primary_plu:
            summary_parts.append(f"<strong>Primary PLU:</strong> {primary_plu.plu_code}")

        return mark_safe('<br>'.join(summary_parts))

    inventory_summary.short_description = _('Inventory Summary')

    def profit_analysis(self, obj):
        """Profit analysis with sample calculations"""
        if not obj.pk or obj.current_avg_cost <= 0:
            return "No cost data available for profit analysis"

        # Sample profit calculations with different margins
        cost = obj.current_avg_cost
        scenarios = [
            ("25% margin", cost / 0.75),
            ("30% margin", cost / 0.70),
            ("40% margin", cost / 0.60),
        ]

        analysis_parts = [f"<strong>Cost:</strong> {cost:.2f} лв<br>"]

        for scenario_name, sell_price in scenarios:
            profit = sell_price - cost
            markup = ((sell_price - cost) / cost) * 100

            analysis_parts.append(
                f"<strong>{scenario_name}:</strong> "
                f"Sell {sell_price:.2f} лв "
                f"(Profit: {profit:.2f} лв, Markup: {markup:.0f}%)"
            )

        return mark_safe('<br>'.join(analysis_parts))

    profit_analysis.short_description = _('Profit Analysis')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # Editing existing product
            readonly.extend(['code'])  # Don't allow code changes
        return readonly


# === RELATED MODEL ADMINS ===

@admin.register(ProductPLU)
class ProductPLUAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'plu_code', 'is_primary', 'priority', 'description', 'is_active'
    ]
    list_filter = ['is_primary', 'is_active', 'product__unit_type']
    search_fields = ['plu_code', 'product__code', 'product__name', 'description']
    list_editable = ['is_primary', 'priority', 'is_active']

    fieldsets = (
        ('PLU Information', {
            'fields': ('product', 'plu_code', 'description')
        }),
        ('Settings', {
            'fields': ('is_primary', 'priority', 'is_active')
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')


@admin.register(ProductPackaging)
class ProductPackagingAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'unit', 'conversion_factor', 'base_unit_equivalent',
        'is_default_sale_unit', 'is_default_purchase_unit', 'is_active'
    ]
    list_filter = [
        'is_default_sale_unit', 'is_default_purchase_unit', 'is_active',
        'unit', 'product__product_group'
    ]
    search_fields = ['product__code', 'product__name', 'unit__name']
    list_editable = ['conversion_factor', 'is_default_sale_unit', 'is_default_purchase_unit', 'is_active']

    fieldsets = (
        ('Product Information', {
            'fields': ('product', 'unit')
        }),
        ('Conversion', {
            'fields': ('conversion_factor',),
            'description': 'How many base units are in this packaging'
        }),
        ('Defaults', {
            'fields': ('is_default_sale_unit', 'is_default_purchase_unit')
        }),
        ('Status', {
            'fields': ('is_active',)
        })
    )

    def base_unit_equivalent(self, obj):
        """Show what this packaging equals in base units"""
        return f"= {obj.conversion_factor} {obj.product.base_unit.code}"

    base_unit_equivalent.short_description = _('Base Unit Equivalent')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit', 'product__base_unit')


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = [
        'barcode', 'product', 'barcode_type', 'packaging_info',
        'is_primary', 'quantity_represented', 'is_active'
    ]
    list_filter = [
        'barcode_type', 'is_primary', 'is_active',
        'product__unit_type', 'packaging__unit'
    ]
    search_fields = ['barcode', 'product__code', 'product__name']
    list_editable = ['is_primary', 'is_active']

    fieldsets = (
        ('Barcode Information', {
            'fields': ('product', 'barcode', 'barcode_type', 'is_primary')
        }),
        ('Packaging', {
            'fields': ('packaging',),
            'description': 'Optional: link to specific packaging size'
        }),
        ('Status', {
            'fields': ('is_active',)
        })
    )

    def packaging_info(self, obj):
        """Packaging information"""
        if obj.packaging:
            return f"{obj.packaging.unit.code} x{obj.packaging.conversion_factor}"
        return "Base unit"

    packaging_info.short_description = _('Packaging')

    def quantity_represented(self, obj):
        """Show quantity this barcode represents"""
        qty = obj.quantity_in_base_units
        base_unit = obj.product.base_unit.code
        return f"{qty} {base_unit}"

    quantity_represented.short_description = _('Represents')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'packaging', 'packaging__unit', 'product__base_unit'
        )


# === ADMIN ACTIONS ===

def calculate_inventory_value(modeladmin, request, queryset):
    """Calculate total inventory value for selected products"""
    total_value = sum(
        product.current_stock_qty * product.current_avg_cost
        for product in queryset
        if product.current_avg_cost > 0
    )

    modeladmin.message_user(
        request,
        f"Total inventory value for {queryset.count()} products: {total_value:.2f} лв"
    )


calculate_inventory_value.short_description = "Calculate inventory value for selected products"


def reset_stock_to_zero(modeladmin, request, queryset):
    """Reset stock to zero for selected products"""
    count = queryset.update(current_stock_qty=0)
    modeladmin.message_user(
        request,
        f"Reset stock to zero for {count} products"
    )


reset_stock_to_zero.short_description = "Reset stock to zero for selected products"

# Add actions to ProductAdmin
ProductAdmin.actions = [calculate_inventory_value, reset_stock_to_zero]