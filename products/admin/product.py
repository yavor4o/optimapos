# products/admin/product.py - REFACTORED

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.urls import reverse
from django.utils.safestring import mark_safe
from decimal import Decimal

from ..models import Product, ProductPLU, ProductPackaging, ProductBarcode, ProductLifecycleChoices
from ..services import ProductLifecycleService, ProductValidationService


# === CUSTOM FILTERS ===

class LifecycleStatusFilter(admin.SimpleListFilter):
    """Custom filter for lifecycle status with counts"""
    title = _('Lifecycle Status')
    parameter_name = 'lifecycle'

    def lookups(self, request, model_admin):
        """Return filter options with counts"""
        lookups = []
        for status, label in ProductLifecycleChoices.choices:
            count = Product.objects.filter(lifecycle_status=status).count()
            lookups.append((status, f'{label} ({count})'))
        return lookups

    def queryset(self, request, queryset):
        """Filter queryset"""
        if self.value():
            return queryset.filter(lifecycle_status=self.value())
        return queryset


class StockStatusFilter(admin.SimpleListFilter):
    """Filter products by stock status"""
    title = _('Stock Status')
    parameter_name = 'stock_status'

    def lookups(self, request, model_admin):
        return (
            ('in_stock', _('In Stock')),
            ('low_stock', _('Low Stock (<10)')),
            ('no_stock', _('No Stock')),
            ('negative', _('Negative Stock')),
        )

    def queryset(self, request, queryset):
        """Filter based on stock levels from InventoryItem"""
        from inventory.models import InventoryItem

        if self.value() == 'in_stock':
            product_ids = InventoryItem.objects.filter(
                current_qty__gt=10
            ).values_list('product_id', flat=True).distinct()
            return queryset.filter(id__in=product_ids)

        elif self.value() == 'low_stock':
            product_ids = InventoryItem.objects.filter(
                current_qty__gt=0,
                current_qty__lte=10
            ).values_list('product_id', flat=True).distinct()
            return queryset.filter(id__in=product_ids)

        elif self.value() == 'no_stock':
            # Products with no InventoryItem records or qty=0
            with_stock = InventoryItem.objects.filter(
                current_qty__gt=0
            ).values_list('product_id', flat=True).distinct()
            return queryset.exclude(id__in=with_stock)

        elif self.value() == 'negative':
            product_ids = InventoryItem.objects.filter(
                current_qty__lt=0
            ).values_list('product_id', flat=True).distinct()
            return queryset.filter(id__in=product_ids)

        return queryset


# === INLINE ADMIN CLASSES ===

class ProductPLUInline(admin.TabularInline):
    """Inline admin for Product PLU codes"""
    model = ProductPLU
    extra = 1
    max_num = 5

    fields = [
        'plu_code', 'is_primary', 'priority', 'description', 'is_active'
    ]

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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('packaging', 'packaging__unit').order_by('-is_primary')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter packaging options to current product"""
        if db_field.name == "packaging":
            # Get parent product from request
            if hasattr(request, '_obj_'):
                kwargs["queryset"] = ProductPackaging.objects.filter(
                    product=request._obj_
                ).select_related('unit')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# === MAIN PRODUCT ADMIN ===

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Enhanced Product Admin - REFACTORED
    Removed references to deleted fields (current_avg_cost, current_stock_qty)
    Added dynamic stock/cost display from InventoryItem
    """

    # === LIST VIEW ===
    list_display = [
        'code',
        'name_display',
        'brand',
        'lifecycle_status_display',
        'stock_status_display',  # Dynamic from InventoryItem
        'restrictions_display',
        'created_at',
        'is_active'
    ]

    list_filter = [
        LifecycleStatusFilter,  # Custom filter with counts
        StockStatusFilter,  # Custom stock filter
        'sales_blocked',
        'purchase_blocked',
        'brand',
        'product_group',
        'product_type',
        'track_batches',
        'created_at'
    ]

    search_fields = [
        'code',
        'name',
        'description',
        'barcodes__barcode',
        'plu_codes__plu_code'
    ]

    list_editable = []  # Removed direct editing of dynamic fields

    list_per_page = 50

    date_hierarchy = 'created_at'

    # === DETAIL VIEW ===
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
                'allow_negative_sales', 'lifecycle_info_display'
            ),
            'description': _('Product lifecycle and sales/purchase restrictions')
        }),
        (_('Tracking Settings'), {
            'fields': ('track_batches', 'track_serial_numbers', 'requires_expiry_date'),
            'classes': ('collapse',)
        }),
        (_('Stock & Cost Information'), {
            'fields': ('stock_info_display', 'cost_info_display'),
            'description': _('Real-time stock and cost data from inventory'),
            'classes': ('wide',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = [
        'created_at', 'updated_at', 'lifecycle_info_display',
        'stock_info_display', 'cost_info_display'
    ]

    inlines = [
        ProductBarcodeInline,
        ProductPackagingInline,
        ProductPLUInline
    ]

    # === ADMIN ACTIONS ===
    actions = [
        'make_products_active',
        'make_products_phase_out',
        'make_products_discontinued',
        'block_sales',
        'unblock_sales',
        'block_purchases',
        'unblock_purchases'
    ]

    # === CUSTOM DISPLAY METHODS ===

    def name_display(self, obj):
        """Product name with link"""
        return format_html(
            '<a href="{}" style="font-weight: bold;">{}</a>',
            reverse('admin:products_product_change', args=[obj.pk]),
            obj.name
        )

    name_display.short_description = _('Product Name')
    name_display.admin_order_field = 'name'

    def lifecycle_status_display(self, obj):
        """Display lifecycle status with colored badge"""
        badge_class = obj.lifecycle_badge_class
        return format_html(
            '<span class="badge {}">{}</span>',
            badge_class,
            obj.get_lifecycle_status_display()
        )

    lifecycle_status_display.short_description = _('Lifecycle')
    lifecycle_status_display.admin_order_field = 'lifecycle_status'

    def stock_status_display(self, obj):
        """
        Display total stock across all locations
        REFACTORED: Uses property instead of field
        """
        total_stock = obj.total_stock  # Uses property

        if total_stock == 0:
            return format_html('<span style="color: red;">❌ No Stock</span>')
        elif total_stock < 10:
            return format_html(
                '<span style="color: orange;">⚠️ Low ({:.0f})</span>',
                total_stock
            )
        else:
            return format_html(
                '<span style="color: green;">✅ {:.0f}</span>',
                total_stock
            )

    stock_status_display.short_description = _('Stock')

    def restrictions_display(self, obj):
        """Display restrictions with icons"""
        icons = []

        if obj.sales_blocked:
            icons.append('🚫💰')  # Sales blocked
        if obj.purchase_blocked:
            icons.append('🚫📦')  # Purchase blocked
        if obj.lifecycle_status == ProductLifecycleChoices.PHASE_OUT:
            icons.append('⬇️')  # Phasing out
        if obj.lifecycle_status == ProductLifecycleChoices.DISCONTINUED:
            icons.append('⛔')  # Discontinued

        return ' '.join(icons) if icons else '✅'

    restrictions_display.short_description = _('Status')

    def is_active(self, obj):
        """Check if product is active for operations"""
        return obj.is_sellable or obj.is_purchasable

    is_active.boolean = True
    is_active.short_description = _('Active')

    # === READONLY FIELD DISPLAYS ===

    def lifecycle_info_display(self, obj):
        """Display comprehensive lifecycle information"""
        if not obj.pk:
            return "-"

        info_parts = []

        # Current status
        info_parts.append(f"<strong>Status:</strong> {obj.get_lifecycle_status_display()}")

        # Sellability
        if obj.is_sellable:
            info_parts.append('<span style="color: green;">✅ Can Sell</span>')
        else:
            info_parts.append('<span style="color: red;">❌ Cannot Sell</span>')

        # Purchasability
        if obj.is_purchasable:
            info_parts.append('<span style="color: green;">✅ Can Purchase</span>')
        else:
            info_parts.append('<span style="color: red;">❌ Cannot Purchase</span>')

        # Restrictions
        if obj.has_restrictions:
            restrictions = ProductValidationService.get_product_restrictions(obj)
            if restrictions['restrictions_summary']:
                info_parts.append(f"<strong>Restrictions:</strong> {restrictions['restrictions_summary']}")

        return mark_safe('<br>'.join(info_parts))

    lifecycle_info_display.short_description = _('Lifecycle Information')

    def stock_info_display(self, obj):
        """
        Display stock information from InventoryItem
        REFACTORED: Complete rewrite using properties
        """
        if not obj.pk:
            return "-"

        from inventory.models import InventoryItem

        # Get stock by location
        items = InventoryItem.objects.filter(
            product=obj,
            current_qty__gt=0
        ).select_related('location')

        if not items:
            return format_html('<span style="color: gray;">No stock in any location</span>')

        html_parts = ['<table style="width: 100%;">']
        html_parts.append(
            '<tr><th>Location</th><th>Stock</th><th>Available</th><th>Reserved</th><th>Avg Cost</th></tr>'
        )

        total_qty = Decimal('0')
        total_value = Decimal('0')

        for item in items:
            html_parts.append(
                f'<tr>'
                f'<td>{item.location.code}</td>'
                f'<td style="text-align: right;">{item.current_qty:.2f}</td>'
                f'<td style="text-align: right;">{item.available_qty:.2f}</td>'
                f'<td style="text-align: right;">{item.reserved_qty:.2f}</td>'
                f'<td style="text-align: right;">{item.avg_cost:.2f}</td>'
                f'</tr>'
            )
            total_qty += item.current_qty
            total_value += item.current_qty * item.avg_cost

        # Add totals row
        html_parts.append(
            f'<tr style="font-weight: bold; border-top: 2px solid #ddd;">'
            f'<td>TOTAL</td>'
            f'<td style="text-align: right;">{total_qty:.2f}</td>'
            f'<td colspan="2"></td>'
            f'<td style="text-align: right;">Value: {total_value:.2f}</td>'
            f'</tr>'
        )

        html_parts.append('</table>')

        return mark_safe(''.join(html_parts))

    stock_info_display.short_description = _('Stock by Location')

    def cost_info_display(self, obj):
        """
        Display cost information from InventoryItem
        REFACTORED: New method showing costs by location
        """
        if not obj.pk:
            return "-"

        from inventory.models import InventoryItem

        items = InventoryItem.objects.filter(
            product=obj
        ).select_related('location')

        if not items:
            return "No cost data available"

        info_parts = []

        for item in items:
            if item.avg_cost > 0:
                info_parts.append(
                    f"<strong>{item.location.code}:</strong> "
                    f"Avg: {item.avg_cost:.2f}"
                )
                if hasattr(item, 'last_purchase_cost') and item.last_purchase_cost:
                    info_parts.append(f" | Last: {item.last_purchase_cost:.2f}")

        # Add weighted average
        weighted_avg = obj.weighted_avg_cost  # Uses property
        if weighted_avg > 0:
            info_parts.append(
                f"<br><strong>Weighted Average:</strong> {weighted_avg:.2f}"
            )

        return mark_safe('<br>'.join(info_parts)) if info_parts else "No cost data"

    cost_info_display.short_description = _('Cost Information')

    # === ADMIN ACTIONS ===

    def make_products_active(self, request, queryset):
        """Make selected products active"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset),
            ProductLifecycleChoices.ACTIVE,
            user=request.user
        )

        self.message_user(
            request,
            f"Successfully activated {results['summary']['successful_count']} products"
        )

    make_products_active.short_description = _('Make selected products ACTIVE')

    def make_products_phase_out(self, request, queryset):
        """Phase out selected products"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset),
            ProductLifecycleChoices.PHASE_OUT,
            user=request.user
        )

        self.message_user(
            request,
            f"Successfully phased out {results['summary']['successful_count']} products"
        )

    make_products_phase_out.short_description = _('PHASE OUT selected products')

    def make_products_discontinued(self, request, queryset):
        """Discontinue selected products"""
        results = ProductLifecycleService.bulk_change_lifecycle(
            list(queryset),
            ProductLifecycleChoices.DISCONTINUED,
            user=request.user
        )

        if results['summary']['failed_count'] > 0:
            self.message_user(
                request,
                f"Could not discontinue {results['summary']['failed_count']} products (may have stock)",
                level='WARNING'
            )

        if results['summary']['successful_count'] > 0:
            self.message_user(
                request,
                f"Successfully discontinued {results['summary']['successful_count']} products"
            )

    make_products_discontinued.short_description = _('DISCONTINUE selected products')

    def block_sales(self, request, queryset):
        """Block sales for selected products"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.block_sales(product, user=request.user)
            if result['success']:
                count += 1

        self.message_user(request, f"Blocked sales for {count} products")

    block_sales.short_description = _('Block sales')

    def unblock_sales(self, request, queryset):
        """Unblock sales for selected products"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.unblock_sales(product, user=request.user)
            if result['success']:
                count += 1

        self.message_user(request, f"Unblocked sales for {count} products")

    unblock_sales.short_description = _('Unblock sales')

    def block_purchases(self, request, queryset):
        """Block purchases for selected products"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.block_purchases(product, user=request.user)
            if result['success']:
                count += 1

        self.message_user(request, f"Blocked purchases for {count} products")

    block_purchases.short_description = _('Block purchases')

    def unblock_purchases(self, request, queryset):
        """Unblock purchases for selected products"""
        count = 0
        for product in queryset:
            result = ProductLifecycleService.unblock_purchases(product, user=request.user)
            if result['success']:
                count += 1

        self.message_user(request, f"Unblocked purchases for {count} products")

    unblock_purchases.short_description = _('Unblock purchases')

    # === OPTIMIZATION ===

    def get_queryset(self, request):
        """Optimize queries with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related(
            'brand', 'product_group', 'product_type',
            'base_unit', 'tax_group', 'created_by'
        ).prefetch_related(
            'barcodes', 'packagings', 'plu_codes'
        )

    def get_form(self, request, obj=None, **kwargs):
        """Store object reference for inline admins"""
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)

    # === CUSTOM CSS/JS ===

    class Media:
        css = {
            'all': ('admin/css/products.css',)
        }
        js = ('admin/js/products.js',)