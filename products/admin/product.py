# products/admin/product.py - COMPLETE WITH INLINES

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.urls import reverse
from django.utils.safestring import mark_safe
from decimal import Decimal

from ..models import Product, ProductPLU, ProductPackaging, ProductBarcode, ProductLifecycleChoices
from .actions import PRODUCT_ADMIN_ACTIONS


# === INLINE ADMIN CLASSES ===

class ProductPLUInline(admin.TabularInline):
    """Inline admin for Product PLU codes"""
    model = ProductPLU
    extra = 1
    max_num = 5

    fields = [
        'plu_code', 'is_primary', 'priority', 'description', 'is_active'
    ]

    list_editable = ['is_primary', 'priority', 'is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-priority', '-is_primary')


class ProductPackagingInline(admin.TabularInline):
    """Inline admin for Product Packaging"""
    model = ProductPackaging
    extra = 1
    max_num = 10

    fields = [
        'unit', 'conversion_factor', 'is_default_sale_unit',
        'is_default_purchase_unit', 'weight_kg', 'is_active'
    ]

    list_editable = ['conversion_factor', 'is_default_sale_unit', 'is_default_purchase_unit', 'is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('unit').order_by('conversion_factor')


class ProductBarcodeInline(admin.TabularInline):
    """Inline admin for Product Barcodes"""
    model = ProductBarcode
    extra = 1
    max_num = 10

    fields = [
        'barcode', 'barcode_type', 'packaging', 'is_primary', 'is_active'
    ]

    list_editable = ['barcode_type', 'is_primary', 'is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('packaging', 'packaging__unit').order_by('-is_primary')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter packaging options to current product"""
        if db_field.name == "packaging":
            # This will be handled by JavaScript in the admin
            kwargs["queryset"] = ProductPackaging.objects.select_related('unit')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# === CUSTOM ADMIN FILTERS ===

class LifecycleStatusFilter(admin.SimpleListFilter):
    """Filter by lifecycle status"""
    title = _('Lifecycle Status')
    parameter_name = 'lifecycle_status'

    def lookups(self, request, model_admin):
        return ProductLifecycleChoices.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lifecycle_status=self.value())
        return queryset


class BlockStatusFilter(admin.SimpleListFilter):
    """Filter by block status"""
    title = _('Block Status')
    parameter_name = 'block_status'

    def lookups(self, request, model_admin):
        return (
            ('sales_blocked', _('Sales Blocked')),
            ('purchase_blocked', _('Purchase Blocked')),
            ('both_blocked', _('Both Blocked')),
            ('not_blocked', _('Not Blocked')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sales_blocked':
            return queryset.filter(sales_blocked=True)
        elif self.value() == 'purchase_blocked':
            return queryset.filter(purchase_blocked=True)
        elif self.value() == 'both_blocked':
            return queryset.filter(sales_blocked=True, purchase_blocked=True)
        elif self.value() == 'not_blocked':
            return queryset.filter(sales_blocked=False, purchase_blocked=False)
        return queryset


class SellabilityFilter(admin.SimpleListFilter):
    """Filter by sellability"""
    title = _('Sellability')
    parameter_name = 'sellability'

    def lookups(self, request, model_admin):
        return (
            ('sellable', _('Sellable')),
            ('not_sellable', _('Not Sellable')),
            ('purchasable', _('Purchasable')),
            ('not_purchasable', _('Not Purchasable')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sellable':
            return queryset.filter(
                lifecycle_status__in=[ProductLifecycleChoices.ACTIVE, ProductLifecycleChoices.PHASE_OUT],
                sales_blocked=False
            )
        elif self.value() == 'not_sellable':
            return queryset.exclude(
                lifecycle_status__in=[ProductLifecycleChoices.ACTIVE, ProductLifecycleChoices.PHASE_OUT],
                sales_blocked=False
            )
        elif self.value() == 'purchasable':
            return queryset.filter(
                lifecycle_status__in=[ProductLifecycleChoices.ACTIVE],
                purchase_blocked=False
            )
        elif self.value() == 'not_purchasable':
            return queryset.exclude(
                lifecycle_status__in=[ProductLifecycleChoices.ACTIVE],
                purchase_blocked=False
            )
        return queryset


class StockLevelFilter(admin.SimpleListFilter):
    """Filter by stock levels (if stock system exists)"""
    title = _('Stock Level')
    parameter_name = 'stock_level'

    def lookups(self, request, model_admin):
        return (
            ('low_stock', _('Low Stock')),
            ('out_of_stock', _('Out of Stock')),
            ('overstock', _('Overstock')),
        )

    def queryset(self, request, queryset):
        # This would require integration with inventory system
        # For now, return all
        return queryset


# === MAIN PRODUCT ADMIN ===

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Enhanced Product Admin with lifecycle management"""

    list_display = [
        'code', 'name_display', 'brand', 'product_group',
        'lifecycle_status', 'lifecycle_status_display', 'restrictions_display',
        'unit_info', 'barcode_count', 'packaging_count','current_stock_qty',
    ]

    list_filter = [
        LifecycleStatusFilter, BlockStatusFilter, SellabilityFilter,
        'unit_type', 'brand', 'product_group', 'product_type',
        'track_batches', 'created_at'
    ]

    search_fields = [
        'code', 'name',
        'barcodes__barcode',
        'plu_codes__plu_code'
    ]

    list_editable = ['lifecycle_status']

    readonly_fields = [
        'created_at', 'updated_at', 'lifecycle_restrictions_info',
        'sellability_info', 'barcode_summary', 'packaging_summary'
    ]

    inlines = [ProductPLUInline, ProductPackagingInline, ProductBarcodeInline]

    actions = PRODUCT_ADMIN_ACTIONS

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'description')
        }),
        (_('Classification'), {
            'fields': ('brand', 'product_group', 'product_type'),
            'classes': ('collapse',)
        }),
        (_('Unit Configuration'), {
            'fields': ('base_unit', 'unit_type', 'tax_group')
        }),
        (_('Lifecycle & Restrictions'), {
            'fields': (
                'lifecycle_status', 'sales_blocked', 'purchase_blocked',
                'lifecycle_restrictions_info', 'sellability_info'
            ),
            'description': _('Product lifecycle and sales/purchase restrictions')
        }),
        (_('Tracking Settings'), {
            'fields': ('track_batches', 'track_serial_numbers'),
            'classes': ('collapse',)
        }),
        (_('Summaries'), {
            'fields': ('barcode_summary', 'packaging_summary','current_stock_qty','current_avg_cost','last_purchase_cost'),
            'description': _('Auto-generated summaries of related data')

        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'brand', 'product_group', 'product_type', 'base_unit', 'tax_group'
        ).prefetch_related('barcodes', 'packagings', 'plu_codes')

    # === DISPLAY METHODS ===

    def name_display(self, obj):
        """Product name with link to change page"""
        return format_html(
            '<a href="{}" style="font-weight: bold;">{}</a>',
            reverse('admin:products_product_change', args=[obj.pk]),
            obj.name
        )

    name_display.short_description = _('Product Name')
    name_display.admin_order_field = 'name'

    def lifecycle_status_display(self, obj):
        """Display lifecycle status with badge"""
        badge_class = obj.lifecycle_badge_class
        return format_html(
            '<span class="badge {}">{}</span>',
            badge_class,
            obj.get_lifecycle_status_display()
        )

    lifecycle_status_display.short_description = _('Lifecycle')
    lifecycle_status_display.admin_order_field = 'lifecycle_status'

    def restrictions_display(self, obj):
        """Display sales/purchase restrictions"""
        restrictions = []
        if obj.sales_blocked:
            restrictions.append('<span style="color: red;">🚫 Sales</span>')
        if obj.purchase_blocked:
            restrictions.append('<span style="color: red;">🚫 Purchase</span>')

        if restrictions:
            return format_html(' '.join(restrictions))
        return format_html('<span style="color: green;">✅ OK</span>')

    restrictions_display.short_description = _('Restrictions')

    def unit_info(self, obj):
        """Display unit type and base unit"""
        return format_html(
            '{} ({})',
            obj.get_unit_type_display(),
            obj.base_unit.code
        )

    unit_info.short_description = _('Unit')

    def barcode_count(self, obj):
        """Count of active barcodes"""
        count = obj.barcodes.filter(is_active=True).count()
        if count > 0:
            return format_html('<span style="color: blue;">📱 {}</span>', count)
        return format_html('<span style="color: gray;">0</span>')

    barcode_count.short_description = _('Barcodes')

    def packaging_count(self, obj):
        """Count of active packagings"""
        count = obj.packagings.filter(is_active=True).count()
        if count > 0:
            return format_html('<span style="color: green;">📦 {}</span>', count)
        return format_html('<span style="color: gray;">0</span>')

    packaging_count.short_description = _('Packagings')

    # === READONLY FIELD METHODS ===

    def lifecycle_restrictions_info(self, obj):
        """Display lifecycle restrictions"""
        info = []
        if obj.lifecycle_status == ProductLifecycleChoices.DRAFT:
            info.append('⚠️ Product is in DRAFT - not available for operations')
        elif obj.lifecycle_status == ProductLifecycleChoices.PHASE_OUT:
            info.append('📉 Product is being phased out - no new purchases')
        elif obj.lifecycle_status == ProductLifecycleChoices.DISCONTINUED:
            info.append('🛑 Product is DISCONTINUED - no sales or purchases')

        if obj.sales_blocked:
            info.append('🚫 Sales are blocked')
        if obj.purchase_blocked:
            info.append('🚫 Purchases are blocked')

        return mark_safe('<br>'.join(info)) if info else 'No restrictions'

    lifecycle_restrictions_info.short_description = _('Lifecycle Restrictions')

    def sellability_info(self, obj):
        """Display sellability analysis"""
        sellable = obj.is_sellable
        purchasable = obj.is_purchasable

        info = []
        if sellable:
            info.append('✅ Can be sold')
        else:
            info.append('❌ Cannot be sold')

        if purchasable:
            info.append('✅ Can be purchased')
        else:
            info.append('❌ Cannot be purchased')

        return mark_safe('<br>'.join(info))

    sellability_info.short_description = _('Sellability Analysis')

    def barcode_summary(self, obj):
        """Summary of barcodes"""
        barcodes = obj.barcodes.all()
        if not barcodes:
            return 'No barcodes'

        active_count = barcodes.filter(is_active=True).count()
        primary_barcode = barcodes.filter(is_primary=True).first()

        summary = f'{active_count} active barcodes'
        if primary_barcode:
            summary += f'<br>Primary: {primary_barcode.barcode}'

        return mark_safe(summary)

    barcode_summary.short_description = _('Barcode Summary')

    def packaging_summary(self, obj):
        """Summary of packagings"""
        packagings = obj.packagings.all()
        if not packagings:
            return 'No packagings (base unit only)'

        active_count = packagings.filter(is_active=True).count()
        default_sale = packagings.filter(is_default_sale_unit=True).first()
        default_purchase = packagings.filter(is_default_purchase_unit=True).first()

        summary = f'{active_count} active packagings'
        if default_sale:
            summary += f'<br>Default sale: {default_sale.unit.name}'
        if default_purchase:
            summary += f'<br>Default purchase: {default_purchase.unit.name}'

        return mark_safe(summary)

    packaging_summary.short_description = _('Packaging Summary')

    class Media:
        css = {
            'all': ('admin/css/product_admin.css',)
        }
        js = ('admin/js/product_admin.js',)