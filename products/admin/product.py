# products/admin/product.py - LIFECYCLE VERSION

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, F, Q
from django.http import HttpResponseRedirect
from django.contrib import messages

from ..models import Product, ProductPLU, ProductPackaging, ProductBarcode, ProductLifecycleChoices
from ..services.lifecycle_service import ProductLifecycleService
from ..services.validation_service import ProductValidationService


# === CUSTOM FILTERS ===

class LifecycleStatusFilter(admin.SimpleListFilter):
    title = _('Lifecycle Status')
    parameter_name = 'lifecycle_status'

    def lookups(self, request, model_admin):
        return ProductLifecycleChoices.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lifecycle_status=self.value())
        return queryset


class BlockStatusFilter(admin.SimpleListFilter):
    title = _('Block Status')
    parameter_name = 'block_status'

    def lookups(self, request, model_admin):
        return (
            ('sales_blocked', _('Sales Blocked')),
            ('purchase_blocked', _('Purchase Blocked')),
            ('any_blocked', _('Any Blocked')),
            ('not_blocked', _('Not Blocked')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sales_blocked':
            return queryset.filter(sales_blocked=True)
        elif self.value() == 'purchase_blocked':
            return queryset.filter(purchase_blocked=True)
        elif self.value() == 'any_blocked':
            return queryset.filter(Q(sales_blocked=True) | Q(purchase_blocked=True))
        elif self.value() == 'not_blocked':
            return queryset.filter(sales_blocked=False, purchase_blocked=False)
        return queryset


class SellabilityFilter(admin.SimpleListFilter):
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
            return queryset.sellable()
        elif self.value() == 'not_sellable':
            return queryset.exclude(pk__in=queryset.sellable())
        elif self.value() == 'purchasable':
            return queryset.purchasable()
        elif self.value() == 'not_purchasable':
            return queryset.exclude(pk__in=queryset.purchasable())
        return queryset


# === MAIN PRODUCT ADMIN ===

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name_display', 'brand', 'product_group',
        'lifecycle_status_display', 'restrictions_display',
        'stock_status', 'cost_info'
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

    list_editable = ['lifecycle_status']  # ← Quick edit lifecycle status

    readonly_fields = [
        'created_at', 'updated_at', 'lifecycle_restrictions_info',
        'sellability_info', 'stock_summary'
    ]

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
                'allow_negative_sales'
            ),
            'description': _('Control product availability and restrictions')
        }),
        (_('Tracking Settings'), {
            'fields': ('track_batches', 'track_serial_numbers', 'requires_expiry_date'),
            'classes': ('collapse',)
        }),
        (_('Stock & Cost Data'), {
            'fields': ('current_avg_cost', 'current_stock_qty'),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
        (_('Analysis'), {
            'fields': ('lifecycle_restrictions_info', 'sellability_info', 'stock_summary'),
            'classes': ('collapse',)
        })
    )

    actions = [
        'make_active', 'make_phase_out', 'make_discontinued',
        'block_sales', 'unblock_sales', 'block_purchases', 'unblock_purchases'
    ]

    # === DISPLAY METHODS ===

    def name_display(self, obj):
        """Product name with truncation"""
        name = obj.name[:30] + "..." if len(obj.name) > 30 else obj.name
        return format_html('<strong>{}</strong>', name)

    name_display.short_description = _('Product Name')

    def lifecycle_status_display(self, obj):
        """Lifecycle status with colored badge"""
        badge_class = obj.lifecycle_badge_class
        return format_html(
            '<span class="badge {}">{}</span>',
            badge_class,
            obj.get_lifecycle_status_display()
        )

    lifecycle_status_display.short_description = _('Lifecycle')

    def restrictions_display(self, obj):
        """Show restrictions as icons"""
        icons = []

        if obj.sales_blocked:
            icons.append('<span title="Sales Blocked" style="color: red;">🚫</span>')

        if obj.purchase_blocked:
            icons.append('<span title="Purchase Blocked" style="color: orange;">⛔</span>')

        if obj.allow_negative_sales:
            icons.append('<span title="Allows Negative Sales" style="color: blue;">➖</span>')

        if not icons:
            icons.append('<span style="color: green;">✅</span>')

        return format_html(' '.join(icons))

    restrictions_display.short_description = _('Restrictions')

    def stock_status(self, obj):
        """Stock status indicator"""
        if obj.current_stock_qty == 0:
            return format_html('<span style="color: red;">❌ No Stock</span>')
        elif obj.current_stock_qty < 10:
            return format_html('<span style="color: orange;">⚠️ Low Stock</span>')
        else:
            return format_html('<span style="color: green;">✅ In Stock</span>')

    stock_status.short_description = _('Stock')

    def cost_info(self, obj):
        """Cost information"""
        return format_html(
            '<small>{:.2f} лв<br/>Qty: {:.1f}</small>',
            obj.current_avg_cost,
            obj.current_stock_qty
        )

    cost_info.short_description = _('Cost & Qty')

    # === READONLY FIELD METHODS ===

    def lifecycle_restrictions_info(self, obj):
        """Detailed lifecycle and restrictions info"""
        if not obj.pk:
            return "Save product first"

        restrictions = ProductValidationService.get_product_restrictions(obj)

        info_parts = [
            f"<strong>Lifecycle:</strong> {restrictions['lifecycle_display']}",
            f"<strong>Sellable:</strong> {'Yes' if restrictions['is_sellable'] else 'No'}",
            f"<strong>Purchasable:</strong> {'Yes' if restrictions['is_purchasable'] else 'No'}",
        ]

        if restrictions['restrictions_summary']:
            info_parts.append(f"<strong>Restrictions:</strong> {restrictions['restrictions_summary']}")

        return mark_safe('<br/>'.join(info_parts))

    lifecycle_restrictions_info.short_description = _('Lifecycle & Restrictions')

    def sellability_info(self, obj):
        """Sellability analysis"""
        if not obj.pk:
            return "Save product first"

        can_sell, sell_reason, _ = ProductValidationService.can_sell_product(obj)
        can_purchase, purchase_reason, _ = ProductValidationService.can_purchase_product(obj)

        info_parts = [
            f"<strong>Can Sell:</strong> {'✅ Yes' if can_sell else '❌ No'}",
            f"<strong>Can Purchase:</strong> {'✅ Yes' if can_purchase else '❌ No'}",
        ]

        if not can_sell:
            info_parts.append(f"<em>Sale Issue: {sell_reason}</em>")

        if not can_purchase:
            info_parts.append(f"<em>Purchase Issue: {purchase_reason}</em>")

        return mark_safe('<br/>'.join(info_parts))

    sellability_info.short_description = _('Sellability Analysis')

    def stock_summary(self, obj):
        """Stock summary"""
        if not obj.pk:
            return "Save product first"

        summary_parts = [
            f"<strong>Current Stock:</strong> {obj.current_stock_qty}",
            f"<strong>Average Cost:</strong> {obj.current_avg_cost:.2f} лв",
            f"<strong>Stock Value:</strong> {obj.stock_value:.2f} лв",
        ]

        if obj.last_purchase_date:
            summary_parts.append(f"<strong>Last Purchase:</strong> {obj.last_purchase_date.strftime('%d.%m.%Y')}")

        if obj.last_sale_date:
            summary_parts.append(f"<strong>Last Sale:</strong> {obj.last_sale_date.strftime('%d.%m.%Y')}")

        return mark_safe('<br/>'.join(summary_parts))

    stock_summary.short_description = _('Stock Summary')

    # === ACTIONS ===

    def make_active(self, request, queryset):
        """Bulk make products active"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset), ProductLifecycleChoices.ACTIVE, request.user
        )

        success_count = results['summary']['successful_count']
        failed_count = results['summary']['failed_count']

        if success_count:
            messages.success(request, f'Made {success_count} products active.')
        if failed_count:
            messages.warning(request, f'{failed_count} products could not be made active.')

    make_active.short_description = _('Mark selected products as ACTIVE')

    def make_phase_out(self, request, queryset):
        """Bulk phase out products"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset), ProductLifecycleChoices.PHASE_OUT, request.user
        )

        success_count = results['summary']['successful_count']
        messages.success(request, f'Set {success_count} products to phase out.')

    make_phase_out.short_description = _('Mark selected products as PHASE OUT')

    def make_discontinued(self, request, queryset):
        """Bulk discontinue products"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset), ProductLifecycleChoices.DISCONTINUED, request.user
        )

        success_count = results['summary']['successful_count']
        messages.success(request, f'Discontinued {success_count} products.')

    make_discontinued.short_description = _('Mark selected products as DISCONTINUED')

    def block_sales(self, request, queryset):
        """Bulk block sales"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.block_sales(product, request.user)
            if result['success']:
                count += 1

        messages.success(request, f'Blocked sales for {count} products.')

    block_sales.short_description = _('Block sales for selected products')

    def unblock_sales(self, request, queryset):
        """Bulk unblock sales"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.unblock_sales(product, request.user)
            if result['success']:
                count += 1

        messages.success(request, f'Unblocked sales for {count} products.')

    unblock_sales.short_description = _('Unblock sales for selected products')

    def block_purchases(self, request, queryset):
        """Bulk block purchases"""
        count = queryset.filter(purchase_blocked=False).update(purchase_blocked=True)
        messages.success(request, f'Blocked purchases for {count} products.')

    block_purchases.short_description = _('Block purchases for selected products')

    def unblock_purchases(self, request, queryset):
        """Bulk unblock purchases"""
        count = queryset.filter(purchase_blocked=True).update(purchase_blocked=False)
        messages.success(request, f'Unblocked purchases for {count} products.')

    unblock_purchases.short_description = _('Unblock purchases for selected products')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # Editing existing product
            readonly.extend(['code'])  # Don't allow code changes
        return readonly