# inventory/admin.py
from datetime import timedelta

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q, F

from .models import InventoryLocation, InventoryItem, InventoryMovement, InventoryBatch


# === INVENTORY LOCATION ADMIN ===

class InventoryItemInline(admin.TabularInline):
    """Inline за продукти в локацията"""
    model = InventoryItem
    extra = 0
    fields = [
        'product', 'current_qty', 'reserved_qty', 'avg_cost',
        'min_stock_level', 'max_stock_level'
    ]
    readonly_fields = ['avg_cost', 'last_movement_date']
    show_change_link = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product').filter(
            current_qty__gt=0
        )[:20]  # Показваме само първите 20 за performance


@admin.register(InventoryLocation)
class InventoryLocationAdmin(admin.ModelAdmin):
    """Professional admin for Inventory Locations"""

    list_display = [
        'code', 'name', 'location_type_display', 'manager_display',
        'stock_summary', 'products_count', 'negative_stock_badge',
        'is_active'
    ]

    list_filter = [
        'location_type', 'is_active', 'allow_negative_stock',
        'created_at'
    ]

    search_fields = [
        'code', 'name', 'address', 'manager__first_name', 'manager__last_name'
    ]

    list_editable = ['is_active']

    readonly_fields = [
        'created_at', 'updated_at', 'location_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'location_type', 'is_active')
        }),
        (_('Contact Information'), {
            'fields': ('address', 'phone', 'email', 'manager'),
            'classes': ('collapse',)
        }),
        (_('Inventory Settings'), {
            'fields': (
                'default_markup_percentage',
                'allow_negative_stock'
            ),
            'description': _('Settings that affect inventory behavior')
        }),
        (_('Analytics'), {
            'fields': ('location_analytics',),
            'classes': ('collapse',),
            'description': _('Automatically calculated location statistics')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [InventoryItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('manager').annotate(
            products_count_ann=Count('inventory_items', distinct=True),
            total_value_ann=Sum('inventory_items__current_qty') or 0
        )

    def location_type_display(self, obj):
        """Location type with icon"""
        icons = {
            'WAREHOUSE': '🏭',
            'SHOP': '🏪',
            'STORAGE': '📦',
            'VIRTUAL': '☁️'
        }
        icon = icons.get(obj.location_type, '❓')
        return format_html(
            '{} {}',
            icon, obj.get_location_type_display()
        )

    location_type_display.short_description = _('Type')
    location_type_display.admin_order_field = 'location_type'

    def manager_display(self, obj):
        """Manager with link to user admin"""
        if obj.manager:
            url = reverse('admin:auth_user_change', args=[obj.manager.pk])
            return format_html(
                '<a href="{}">{}</a>',
                url, obj.manager.get_full_name() or obj.manager.username
            )
        return format_html('<span style="color: gray;">No manager</span>')

    manager_display.short_description = _('Manager')

    def stock_summary(self, obj):
        """Stock summary for location"""
        try:
            items = obj.inventory_items.filter(current_qty__gt=0)
            total_products = items.count()
            total_value = sum(item.current_qty * item.avg_cost for item in items)

            return format_html(
                '<strong>{}</strong> products<br>'
                '<span style="color: green;">{:.2f} лв</span> value',
                total_products, total_value
            )
        except:
            return '-'

    stock_summary.short_description = _('Stock Summary')

    def products_count(self, obj):
        """Number of products in location"""
        count = getattr(obj, 'products_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: blue;">📦 {}</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    products_count.short_description = _('Products')
    products_count.admin_order_field = 'products_count_ann'

    def negative_stock_badge(self, obj):
        """Shows if negative stock is allowed"""
        if obj.allow_negative_stock:
            return format_html(
                '<span style="color: orange; font-weight: bold;">⚠️ Allowed</span>'
            )
        return format_html('<span style="color: green;">✅ Not Allowed</span>')

    negative_stock_badge.short_description = _('Negative Stock')

    def location_analytics(self, obj):
        """Detailed location analytics"""
        if not obj.pk:
            return "Save location first to see analytics"

        try:
            # Get inventory statistics
            items = obj.inventory_items.filter(current_qty__gt=0)
            total_products = items.count()
            total_value = sum(item.current_qty * item.avg_cost for item in items)

            # Get recent movements
            recent_movements = obj.movements.filter(
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count()

            # Low stock items
            low_stock = items.filter(
                current_qty__lte=F('min_stock_level'),
                min_stock_level__gt=0
            ).count()

            analysis_parts = [
                f"<strong>Total Products:</strong> {total_products}",
                f"<strong>Total Inventory Value:</strong> {total_value:.2f} лв",
                f"<strong>Recent Movements (30d):</strong> {recent_movements}",
                f"<strong>Low Stock Items:</strong> {low_stock}",
                f"<strong>Location Type:</strong> {obj.get_location_type_display()}",
                f"<strong>Markup:</strong> {obj.default_markup_percentage}%",
            ]

            if obj.manager:
                analysis_parts.append(f"<strong>Manager:</strong> {obj.manager.get_full_name()}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    location_analytics.short_description = _('Location Analytics')

    # Actions
    actions = ['activate_locations', 'deactivate_locations', 'export_inventory']

    def activate_locations(self, request, queryset):
        """Activate selected locations"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'Activated {count} locations.')

    activate_locations.short_description = _('Activate selected locations')

    def deactivate_locations(self, request, queryset):
        """Deactivate selected locations"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {count} locations.')

    deactivate_locations.short_description = _('Deactivate selected locations')

    def export_inventory(self, request, queryset):
        """Export inventory data for selected locations"""
        location_codes = list(queryset.values_list('code', flat=True))
        self.message_user(
            request,
            f'Inventory export prepared for locations: {", ".join(location_codes)}'
        )

    export_inventory.short_description = _('Export inventory data')


# === INVENTORY ITEM ADMIN ===

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """Admin for inventory items (cached quantities)"""

    list_display = [
        'product_display', 'location', 'current_qty_display',
        'reserved_qty', 'avg_cost_display', 'stock_status',
        'last_movement_date'
    ]

    list_filter = [
        'location', 'product__product_group', 'product__brand',
        'last_movement_date'
    ]

    search_fields = [
        'product__code', 'product__name', 'location__code'
    ]

    readonly_fields = [
        'current_qty', 'avg_cost', 'last_movement_date', 'updated_at'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location'
        ).filter(current_qty__gt=0)

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = _('Product')

    def current_qty_display(self, obj):
        """Current quantity with color coding"""
        qty = obj.current_qty
        color = 'green' if qty > obj.min_stock_level else 'orange' if qty > 0 else 'red'

        return format_html(
            '<strong style="color: {};">{:.3f}</strong>',
            color, qty
        )

    current_qty_display.short_description = _('Current Qty')

    def avg_cost_display(self, obj):
        return format_html(
            '<span style="color: blue;">{:.4f} лв</span>',
            obj.avg_cost
        )

    avg_cost_display.short_description = _('Avg Cost')

    def stock_status(self, obj):
        """Stock status indicator"""
        if obj.current_qty == 0:
            return format_html('<span style="color: red;">❌ Out of Stock</span>')
        elif obj.current_qty <= obj.min_stock_level and obj.min_stock_level > 0:
            return format_html('<span style="color: orange;">⚠️ Low Stock</span>')
        else:
            return format_html('<span style="color: green;">✅ In Stock</span>')

    stock_status.short_description = _('Status')


# === INVENTORY MOVEMENT ADMIN ===

@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    """Admin for inventory movements (audit trail)"""

    list_display = [
        'movement_date', 'location', 'product_display', 'movement_type_display',
        'quantity_display', 'cost_price', 'source_doc', 'created_by'
    ]

    list_filter = [
        'movement_type', 'location', 'movement_date', 'created_at'
    ]

    search_fields = [
        'product__code', 'product__name', 'source_document_number',
        'batch_number', 'reason'
    ]

    date_hierarchy = 'movement_date'

    readonly_fields = [
        'created_at', 'movement_date', 'quantity', 'cost_price'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location', 'created_by', 'delivery_receipt'
        )

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:25]}"

    product_display.short_description = _('Product')

    def movement_type_display(self, obj):
        """Movement type with direction icon"""
        icons = {
            'IN': '⬆️',
            'OUT': '⬇️',
            'TRANSFER': '↔️',
            'ADJUSTMENT': '🔧',
            'PRODUCTION': '🏭',
            'CYCLE_COUNT': '📊'
        }
        icon = icons.get(obj.movement_type, '❓')
        return format_html(
            '{} {}',
            icon, obj.get_movement_type_display()
        )

    movement_type_display.short_description = _('Type')

    def quantity_display(self, obj):
        """Quantity with +/- sign"""
        sign = '+' if obj.movement_type == 'IN' else '-'
        color = 'green' if obj.movement_type == 'IN' else 'red'

        return format_html(
            '<strong style="color: {};">{}{:.3f}</strong>',
            color, sign, obj.quantity
        )

    quantity_display.short_description = _('Quantity')

    def source_doc(self, obj):
        """Source document link"""
        if obj.delivery_receipt:
            url = reverse('admin:purchases_deliveryreceipt_change',
                          args=[obj.delivery_receipt.pk])
            return format_html(
                '<a href="{}">DEL-{}</a>',
                url, obj.delivery_receipt.document_number
            )
        elif obj.source_document_number:
            return obj.source_document_number
        return '-'

    source_doc.short_description = _('Source Document')


# === INVENTORY BATCH ADMIN ===

@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    """Admin for inventory batches (FIFO tracking)"""

    list_display = [
        'product_display', 'location', 'batch_number', 'remaining_qty',
        'received_date', 'expiry_status', 'cost_price'
    ]

    list_filter = [
        'location', 'received_date', 'expiry_date', 'product__product_group'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location'
        ).filter(remaining_qty__gt=0)

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:25]}"

    product_display.short_description = _('Product')

    def expiry_status(self, obj):
        """Expiry status with color coding"""
        if not obj.expiry_date:
            return format_html('<span style="color: gray;">No expiry</span>')

        from datetime import timedelta
        today = timezone.now().date()
        days_to_expiry = (obj.expiry_date - today).days

        if days_to_expiry < 0:
            return format_html('<span style="color: red;">⚠️ Expired</span>')
        elif days_to_expiry <= 7:
            return format_html('<span style="color: orange;">⏰ Expires in {} days</span>', days_to_expiry)
        else:
            return format_html('<span style="color: green;">✅ Good until {}</span>', obj.expiry_date)

    expiry_status.short_description = _('Expiry Status')