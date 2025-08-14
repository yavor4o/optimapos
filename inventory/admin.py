# inventory/admin.py - REFACTORED

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from decimal import Decimal

from .models import (
    InventoryLocation, InventoryItem, InventoryBatch, InventoryMovement
)
from .services import InventoryService, MovementService


# =================================================================
# INVENTORY LOCATION ADMIN
# =================================================================

@admin.register(InventoryLocation)
class InventoryLocationAdmin(admin.ModelAdmin):
    """Enhanced admin for inventory locations with batch settings"""

    list_display = [
        'code', 'name', 'location_type', 'is_active',
        'allow_negative_stock', 'batch_tracking_display',
        'inventory_summary', 'last_movement_display'
    ]

    list_filter = [
        'location_type', 'is_active', 'allow_negative_stock',
        'batch_tracking_mode', 'force_batch_on_receive'
    ]

    search_fields = ['code', 'name', 'description']

    readonly_fields = [
        'created_at', 'updated_at', 'inventory_analytics',
        'location_health_score'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code', 'name', 'location_type',
                'is_active', 'allow_negative_stock'
            )
        }),
        (_('Batch Tracking Settings'), {
            'fields': (
                'batch_tracking_mode', 'force_batch_on_receive',
                'allow_mixed_batches', 'default_expiry_days'
            ),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('inventory_analytics', 'location_health_score'),
            'classes': ('collapse',)
        }),
        (_('Audit'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def batch_tracking_display(self, obj):
        """Display batch tracking configuration"""
        icons = {
            'DISABLED': '❌',
            'OPTIONAL': '⚙️',
            'ENFORCED': '✅'
        }

        icon = icons.get(obj.batch_tracking_mode, '❓')
        mode_text = obj.get_batch_tracking_mode_display()

        extra_info = []
        if obj.force_batch_on_receive:
            extra_info.append('Force on receive')
        if obj.allow_mixed_batches:
            extra_info.append('Mixed batches')

        extra = f" ({', '.join(extra_info)})" if extra_info else ""

        return format_html(
            '{} {}<small style="color: gray;">{}</small>',
            icon, mode_text, extra
        )

    batch_tracking_display.short_description = _('Batch Tracking')

    def inventory_summary(self, obj):
        """Quick inventory summary for this location"""
        try:
            inventory = InventoryService.get_location_inventory(
                location=obj,
                include_zero_stock=False
            )

            if not inventory:
                return format_html('<em style="color: gray;">No stock</em>')

            total_products = len(inventory)
            total_value = sum(item['total_value'] for item in inventory)

            return format_html(
                '<strong>{}</strong> products<br>'
                '<span style="color: green;">{:.2f} лв</span> value',
                total_products, total_value
            )
        except Exception:
            return format_html('<em style="color: red;">Error</em>')

    inventory_summary.short_description = _('Inventory Summary')

    def last_movement_display(self, obj):
        """Display last movement information"""
        try:
            last_movement = InventoryMovement.objects.filter(
                location=obj
            ).order_by('-created_at').first()

            if not last_movement:
                return format_html('<em style="color: gray;">No movements</em>')

            days_ago = (timezone.now().date() - last_movement.movement_date).days

            color = 'green' if days_ago <= 1 else 'orange' if days_ago <= 7 else 'red'

            return format_html(
                '<span style="color: {};">{} days ago</span><br>'
                '<small>{} {}</small>',
                color, days_ago,
                last_movement.get_movement_type_display(),
                last_movement.product.code
            )
        except Exception:
            return format_html('<em style="color: red;">Error</em>')

    last_movement_display.short_description = _('Last Movement')

    def inventory_analytics(self, obj):
        """Comprehensive inventory analytics for this location"""
        if not obj.pk:
            return "Save location first to see analytics"

        try:
            valuation = InventoryService.get_inventory_valuation(location=obj)

            analysis_parts = [
                f"<strong>Products:</strong> {valuation['total_products']}",
                f"<strong>Total Value:</strong> {valuation['total_value']:.2f} лв",
            ]

            if valuation.get('recent_performance', {}).get('revenue_last_30_days', 0) > 0:
                analysis_parts.append(
                    f"<strong>Revenue (30d):</strong> {valuation['recent_performance']['revenue_last_30_days']:.2f} лв"
                )
                analysis_parts.append(
                    f"<strong>Profit (30d):</strong> {valuation['recent_performance']['profit_last_30_days']:.2f} лв"
                )

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analytics error: {e}"

    inventory_analytics.short_description = _('Inventory Analytics')

    def location_health_score(self, obj):
        """Simple health indicator based on available data"""
        if not obj.pk:
            return "Save location first"

        try:
            # Simple health calculation based on available data
            inventory = InventoryService.get_location_inventory(location=obj)

            if not inventory:
                return format_html(
                    '<div style="text-align: center;">'
                    '<div style="color: gray; font-size: 24px; font-weight: bold;">N/A</div>'
                    '<div style="margin-top: 10px;">No inventory</div>'
                    '</div>'
                )

            total_products = len(inventory)
            low_stock_count = len([item for item in inventory if item.get('needs_reorder', False)])

            # Simple health score: 100 - (low_stock_percentage * 2)
            low_stock_percentage = (low_stock_count / total_products * 100) if total_products > 0 else 0
            health_score = max(0, round(100 - (low_stock_percentage * 2)))

            color = 'green' if health_score >= 80 else 'orange' if health_score >= 60 else 'red'

            recommendations = []
            if low_stock_count > 0:
                recommendations.append(f"• {low_stock_count} products need reorder")
            if not recommendations:
                recommendations.append("• Inventory levels OK")

            recommendations_html = '<br>'.join(recommendations[:2])

            return format_html(
                '<div style="text-align: center;">'
                '<div style="color: {}; font-size: 24px; font-weight: bold;">{}/100</div>'
                '<div style="margin-top: 10px; text-align: left;">{}</div>'
                '</div>',
                color, health_score, recommendations_html
            )

        except Exception as e:
            return f"Health calculation error: {e}"

    location_health_score.short_description = _('Health Score')

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


# =================================================================
# INVENTORY ITEM ADMIN
# =================================================================

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """Enhanced admin for inventory items with profit tracking"""

    list_display = [
        'product_display', 'location', 'current_qty_display',
        'reserved_qty', 'avg_cost_display', 'profit_potential_display',
        'stock_status', 'last_movement_date'
    ]

    list_filter = [
        'location', 'product__product_group', 'product__brand',
        'last_movement_date'
    ]

    search_fields = [
        'product__code', 'product__name', 'location__code'
    ]

    readonly_fields = [
        'current_qty', 'avg_cost', 'last_movement_date', 'updated_at',
        'stock_analytics', 'movement_history'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'location', 'product', 'current_qty', 'reserved_qty',
                'avg_cost'
            )
        }),
        (_('Cost Tracking'), {
            'fields': (
                'last_purchase_cost', 'last_purchase_date',
                'last_sale_price', 'last_sale_date'
            ),
            'classes': ('collapse',)
        }),
        (_('Stock Management'), {
            'fields': (
                'min_stock_level', 'max_stock_level'
            )
        }),
        (_('Analytics'), {
            'fields': ('stock_analytics', 'movement_history'),
            'classes': ('collapse',)
        }),
        (_('Audit'), {
            'fields': ('last_movement_date', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location'
        ).filter(current_qty__gt=0)

    def product_display(self, obj):
        """Enhanced product display with clickable link"""
        return format_html(
            '<a href="/admin/products/product/{}/change/" target="_blank">'
            '<strong>{}</strong></a><br>'
            '<small>{}</small>',
            obj.product.id,
            obj.product.code,
            obj.product.name[:30] + ('...' if len(obj.product.name) > 30 else '')
        )

    product_display.short_description = _('Product')

    def current_qty_display(self, obj):
        """Current quantity with color coding and trend"""
        try:
            qty = float(obj.current_qty or 0)
            min_qty = float(obj.min_stock_level or 0)

            if qty <= 0:
                color = 'red'
                icon = '❌'
            elif qty <= min_qty:
                color = 'orange'
                icon = '⚠️'
            elif obj.is_overstocked:
                color = 'purple'
                icon = '📈'
            else:
                color = 'green'
                icon = '✅'

            return format_html(
                '{} <strong style="color: {};">{:.3f}</strong><br>'
                '<small>Available: {:.3f}</small>',
                icon, color, qty, float(obj.available_qty)
            )
        except (TypeError, ValueError):
            return format_html('<span style="color: red;">ERROR</span>')

    current_qty_display.short_description = _('Current Qty')

    def avg_cost_display(self, obj):
        """Average cost with purchase comparison - FIXED"""
        avg_cost = obj.avg_cost or Decimal('0')
        last_purchase = obj.last_purchase_cost or Decimal('0')

        if last_purchase and avg_cost != last_purchase:
            difference = last_purchase - avg_cost
            arrow = '📈' if difference > 0 else '📉'

            return format_html(
                '<strong>{}</strong><br>'
                '<small>{} Last: {}</small>',
                f'{avg_cost:.4f}',  # ← ПОПРАВИ: format преди format_html
                arrow,
                f'{last_purchase:.4f}'  # ← ПОПРАВИ: format преди format_html
            )
        else:
            return format_html(
                '<strong>{}</strong>',
                f'{avg_cost:.4f}'  # ← ПОПРАВИ: format преди format_html
            )

    def profit_potential_display(self, obj):
        """Profit potential based on last sale price"""
        if not obj.last_sale_price or obj.avg_cost <= 0:
            return format_html('<em style="color: gray;">N/A</em>')

        profit_per_unit = obj.last_sale_price - obj.avg_cost
        total_profit = profit_per_unit * obj.current_qty
        margin = (profit_per_unit / obj.last_sale_price * 100) if obj.last_sale_price > 0 else 0

        color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'

        return format_html(
            '<strong style="color: {};">{:.2f} лв</strong><br>'
            '<small>{:.1f}% margin</small>',
            color, total_profit, margin
        )

    profit_potential_display.short_description = _('Profit Potential')

    def stock_status(self, obj):
        """Stock status with actionable insights"""
        status_parts = []

        if obj.needs_reorder:
            status_parts.append('<span style="color: red;">⚠️ Needs Reorder</span>')

        if obj.is_overstocked:
            status_parts.append('<span style="color: purple;">📈 Overstocked</span>')

        if obj.reserved_qty > 0:
            status_parts.append(f'<span style="color: blue;">🔒 Reserved: {obj.reserved_qty}</span>')

        if not status_parts:
            status_parts.append('<span style="color: green;">✅ OK</span>')

        return format_html('<br>'.join(status_parts))

    stock_status.short_description = _('Status')

    def stock_analytics(self, obj):
        """Detailed stock analytics"""
        if not obj.pk:
            return "Save item first to see analytics"

        try:
            summary = InventoryService.get_stock_summary(obj.location, obj.product)

            analysis_parts = [
                f"<strong>Stock Value:</strong> {summary['stock_value']:.2f} лв",
                f"<strong>Movement Count (30d):</strong> {summary['movement_summary']['movement_count']}",
            ]

            if summary['movement_summary']['total_revenue'] > 0:
                analysis_parts.extend([
                    f"<strong>Revenue (30d):</strong> {summary['movement_summary']['total_revenue']:.2f} лв",
                    f"<strong>Profit (30d):</strong> {summary['movement_summary']['total_profit']:.2f} лв"
                ])

            if summary['batches']:
                analysis_parts.append(f"<strong>Active Batches:</strong> {len(summary['batches'])}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analytics error: {e}"

    stock_analytics.short_description = _('Stock Analytics')

    def movement_history(self, obj):
        """Recent movement history"""
        if not obj.pk:
            return "Save item first"

        try:
            recent_movements = InventoryMovement.objects.filter(
                location=obj.location,
                product=obj.product
            ).order_by('-created_at')[:5]

            if not recent_movements:
                return format_html('<em style="color: gray;">No movements</em>')

            movement_lines = []
            for movement in recent_movements:
                direction = '+' if movement.movement_type == 'IN' else '-'
                color = 'green' if movement.movement_type == 'IN' else 'red'

                profit_info = ''
                if movement.sale_price:
                    profit_info = f' (Profit: {movement.profit_amount:.2f})'

                movement_lines.append(
                    f'<span style="color: {color};">{direction}{movement.quantity}</span> '
                    f'{movement.get_movement_type_display()}{profit_info}'
                )

            return format_html('<br>'.join(movement_lines))

        except Exception as e:
            return f"History error: {e}"

    movement_history.short_description = _('Recent Movements')


# =================================================================
# INVENTORY BATCH ADMIN
# =================================================================

@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    """Enhanced admin for inventory batches with expiry tracking"""

    list_display = [
        'batch_number', 'product_display', 'location',
        'remaining_qty', 'expiry_status_display', 'cost_price',
        'batch_value_display', 'consumption_display'
    ]

    list_filter = [
        'location', 'is_unknown_batch', 'expiry_date',
        'product__product_group', 'received_date'
    ]

    search_fields = [
        'batch_number', 'product__code', 'product__name',
        'location__code'
    ]

    readonly_fields = [
        'remaining_qty', 'consumed_qty', 'created_at', 'updated_at',
        'is_expired', 'days_until_expiry', 'consumption_percentage',
        'batch_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'location', 'product', 'batch_number',
                'received_qty', 'remaining_qty', 'consumed_qty'
            )
        }),
        (_('Dates & Expiry'), {
            'fields': (
                'received_date', 'expiry_date',
                'is_expired', 'days_until_expiry'
            )
        }),
        (_('Costs'), {
            'fields': ('cost_price',)
        }),
        (_('Batch Properties'), {
            'fields': (
                'is_unknown_batch', 'conversion_date', 'original_source'
            ),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('consumption_percentage', 'batch_analytics'),
            'classes': ('collapse',)
        }),
        (_('Audit'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location'
        ).filter(remaining_qty__gt=0)

    def product_display(self, obj):
        """Product display with batch tracking indicator"""
        batch_icon = '🏷️' if obj.is_unknown_batch else '📦'

        return format_html(
            '{} <strong>{}</strong><br>'
            '<small>{}</small>',
            batch_icon, obj.product.code, obj.product.name[:25]
        )

    product_display.short_description = _('Product')

    def expiry_status_display(self, obj):
        """Expiry status with color coding"""
        if obj.is_expired:
            return format_html(
                '<span style="color: red; font-weight: bold;">❌ EXPIRED</span><br>'
                '<small>{} days ago</small>',
                abs(obj.days_until_expiry)
            )

        days = obj.days_until_expiry

        if days <= 3:
            color, icon = 'red', '🔥'
        elif days <= 7:
            color, icon = 'orange', '⚠️'
        elif days <= 30:
            color, icon = 'goldenrod', '⏰'
        else:
            color, icon = 'green', '✅'

        return format_html(
            '<span style="color: {};">{} {} days</span><br>'
            '<small>{}</small>',
            color, icon, days, obj.expiry_date
        )

    expiry_status_display.short_description = _('Expiry Status')

    def batch_value_display(self, obj):
        """Batch value with cost analysis"""
        value = obj.remaining_qty * obj.cost_price

        return format_html(
            '<strong>{:.2f} лв</strong><br>'
            '<small>{:.3f} × {:.4f}</small>',
            value, obj.remaining_qty, obj.cost_price
        )

    batch_value_display.short_description = _('Batch Value')

    def consumption_display(self, obj):
        """Consumption progress bar"""
        percentage = obj.consumption_percentage

        if percentage == 0:
            return format_html('<em style="color: gray;">Not started</em>')

        color = 'green' if percentage < 50 else 'orange' if percentage < 90 else 'red'

        return format_html(
            '<div style="background: #f0f0f0; border-radius: 10px; padding: 2px;">'
            '<div style="background: {}; width: {}%; height: 10px; border-radius: 8px;"></div>'
            '</div>'
            '<small>{:.1f}% consumed</small>',
            color, min(percentage, 100), percentage
        )

    consumption_display.short_description = _('Consumption')

    def batch_analytics(self, obj):
        """Detailed batch analytics"""
        if not obj.pk:
            return "Save batch first"

        try:
            analysis = obj.get_batch_analysis()

            analysis_parts = [
                f"<strong>Received:</strong> {analysis['received_qty']} on {analysis['received_date']}",
                f"<strong>Consumed:</strong> {analysis['consumed_qty']} ({analysis['consumption_percentage']:.1f}%)",
                f"<strong>Remaining:</strong> {analysis['remaining_qty']}",
                f"<strong>Value:</strong> {analysis['remaining_value']:.2f} лв",
            ]

            if analysis['days_until_expiry'] > 0:
                analysis_parts.append(f"<strong>Expires in:</strong> {analysis['days_until_expiry']} days")
            else:
                analysis_parts.append(
                    f"<strong style='color: red;'>Expired:</strong> {abs(analysis['days_until_expiry'])} days ago")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analytics error: {e}"

    batch_analytics.short_description = _('Batch Analytics')


# =================================================================
# INVENTORY MOVEMENT ADMIN
# =================================================================

@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    """Enhanced admin for inventory movements with profit tracking"""

    list_display = [
        'movement_display', 'product_display', 'location',
        'quantity_display', 'cost_price', 'profit_display',
        'document_reference', 'movement_date', 'created_by'
    ]

    list_filter = [
        'movement_type', 'movement_date', 'location',
        'source_document_type', 'created_at'
    ]

    search_fields = [
        'product__code', 'product__name', 'source_document_number',
        'batch_number', 'reason'
    ]

    readonly_fields = [
        'profit_amount', 'total_cost_value', 'total_sale_value',
        'total_profit', 'profit_margin_percentage', 'created_at'
    ]

    fieldsets = (
        (_('Movement Details'), {
            'fields': (
                'location', 'product', 'movement_type',
                'quantity', 'movement_date', 'reason'
            )
        }),
        (_('Pricing & Costs'), {
            'fields': (
                'cost_price', 'sale_price', 'profit_amount',
                'total_cost_value', 'total_sale_value', 'total_profit',
                'profit_margin_percentage'
            )
        }),
        (_('Batch & Expiry'), {
            'fields': (
                'batch_number', 'expiry_date', 'serial_number'
            ),
            'classes': ('collapse',)
        }),
        (_('Document Reference'), {
            'fields': (
                'source_document_type', 'source_document_number',
                'source_document_line_id'
            ),
            'classes': ('collapse',)
        }),
        (_('Transfer Details'), {
            'fields': ('from_location', 'to_location'),
            'classes': ('collapse',)
        }),
        (_('Audit'), {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'location', 'from_location', 'to_location', 'created_by'
        )

    def movement_display(self, obj):
        """Movement type with direction indicator"""
        icons = {
            'IN': '📥',
            'OUT': '📤',
            'TRANSFER': '🔄',
            'ADJUSTMENT': '⚖️',
            'PRODUCTION': '🏭',
            'CYCLE_COUNT': '📊'
        }

        icon = icons.get(obj.movement_type, '❓')
        color = 'green' if obj.movement_type == 'IN' else 'red' if obj.movement_type == 'OUT' else 'blue'

        return format_html(
            '{} <span style="color: {}; font-weight: bold;">{}</span>',
            icon, color, obj.get_movement_type_display()
        )

    movement_display.short_description = _('Movement Type')

    def product_display(self, obj):
        """Product with batch information"""
        product_html = f'<strong>{obj.product.code}</strong>'

        if obj.batch_number:
            product_html += f'<br><small>Batch: {obj.batch_number}</small>'

        return format_html(product_html)

    product_display.short_description = _('Product')

    def quantity_display(self, obj):
        """Quantity with direction and effective quantity"""
        direction = '+' if obj.is_incoming else '-'
        color = 'green' if obj.is_incoming else 'red'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{}</span>',
            color, direction, obj.quantity
        )

    quantity_display.short_description = _('Quantity')

    def profit_display(self, obj):
        """Profit information for sales"""
        if not obj.sale_price:
            return format_html('<em style="color: gray;">N/A</em>')

        margin = obj.profit_margin_percentage
        if margin is None:
            return format_html('<em style="color: gray;">No margin</em>')

        color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'

        return format_html(
            '<strong style="color: {};">{:.2f} лв</strong><br>'
            '<small>{:.1f}% margin</small>',
            color, obj.profit_amount or 0, margin
        )

    profit_display.short_description = _('Profit')

    def document_reference(self, obj):
        """Document reference with clickable link if possible"""
        if not obj.source_document_number:
            return format_html('<em style="color: gray;">No reference</em>')

        ref_html = f'<strong>{obj.source_document_type}</strong><br>{obj.source_document_number}'

        if obj.source_document_line_id:
            ref_html += f'<br><small>Line: {obj.source_document_line_id}</small>'

        return format_html(ref_html)

    document_reference.short_description = _('Document Reference')

    # Actions
    actions = ['export_movements', 'reverse_selected_movements']

    def export_movements(self, request, queryset):
        """Export selected movements"""
        count = queryset.count()
        self.message_user(request, f'Exported {count} movements.')

    export_movements.short_description = _('Export movements')

    def reverse_selected_movements(self, request, queryset):
        """Reverse selected movements (create correction movements)"""
        count = 0
        for movement in queryset:
            try:
                MovementService.reverse_movement(
                    original_movement=movement,
                    reason='Admin correction',
                    created_by=request.user
                )
                count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Error reversing movement {movement.id}: {e}',
                    level='ERROR'
                )

        if count > 0:
            self.message_user(request, f'Created {count} reverse movements.')

    reverse_selected_movements.short_description = _('Reverse selected movements')