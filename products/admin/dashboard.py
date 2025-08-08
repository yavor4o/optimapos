# products/admin/dashboard.py - ADMIN DASHBOARD WIDGETS

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.db.models import Count, Sum, Q, F
from decimal import Decimal

from ..models import Product, ProductLifecycleChoices
from ..services import ProductLifecycleService, ProductService


class ProductDashboardMixin:
    """
    Mixin for adding dashboard functionality to product admin
    Can be added to any admin class that needs product statistics
    """

    def get_dashboard_stats(self):
        """Get comprehensive product statistics"""
        return ProductLifecycleService.get_lifecycle_statistics()

    def render_lifecycle_distribution(self, request=None):
        """Render lifecycle status distribution chart"""
        stats = self.get_dashboard_stats()

        html_parts = ['<div class="lifecycle-stats" style="margin: 10px 0;">']
        html_parts.append('<h3>📊 Lifecycle Distribution</h3>')

        for status_code, data in stats['by_lifecycle'].items():
            badge_class = {
                ProductLifecycleChoices.NEW: 'badge-info',
                ProductLifecycleChoices.ACTIVE: 'badge-success',
                ProductLifecycleChoices.PHASE_OUT: 'badge-warning',
                ProductLifecycleChoices.DISCONTINUED: 'badge-danger'
            }.get(status_code, 'badge-secondary')

            # Create progress bar
            percentage = data['percentage']
            html_parts.append(
                f'<div style="margin: 5px 0;">'
                f'<span class="badge {badge_class}" style="width: 150px; display: inline-block;">'
                f'{data["name"]}</span> '
                f'<div style="display: inline-block; width: 300px; background: #f0f0f0; height: 20px; vertical-align: middle;">'
                f'<div style="width: {percentage}%; background: #28a745; height: 100%;"></div>'
                f'</div> '
                f'<strong>{data["count"]} ({percentage}%)</strong>'
                f'</div>'
            )

        html_parts.append('</div>')
        return format_html(''.join(html_parts))

    def render_attention_items(self, request=None):
        """Render items needing attention"""
        stats = self.get_dashboard_stats()
        attention = stats.get('actionable_items', {})

        html_parts = ['<div class="attention-items" style="margin: 10px 0;">']
        html_parts.append('<h3>⚠️ Items Needing Attention</h3>')

        # Phase out with stock
        if attention.get('phase_out_with_stock'):
            html_parts.append(
                '<div class="alert alert-warning" style="padding: 10px; background: #fff3cd; border: 1px solid #ffc107; margin: 5px 0;">')
            html_parts.append(f'<strong>Phase Out with Stock:</strong><br>')
            for item in attention['phase_out_with_stock'][:5]:
                product = item['product']
                html_parts.append(
                    f'• <a href="/admin/products/product/{product.id}/change/">{product.code}</a> - '
                    f'{item["stock"]:.0f} units, value: {item["value"]:.2f}<br>'
                )
            html_parts.append('</div>')

        # Discontinued with stock
        if attention.get('discontinued_with_stock'):
            html_parts.append(
                '<div class="alert alert-danger" style="padding: 10px; background: #f8d7da; border: 1px solid #dc3545; margin: 5px 0;">')
            html_parts.append(f'<strong>Discontinued with Stock:</strong><br>')
            for item in attention['discontinued_with_stock'][:5]:
                product = item['product']
                html_parts.append(
                    f'• <a href="/admin/products/product/{product.id}/change/">{product.code}</a> - '
                    f'{item["stock"]:.0f} units, value: {item["value"]:.2f}<br>'
                )
            html_parts.append('</div>')

        # Blocked products
        blocked = stats.get('blocked_products', {})
        if blocked.get('sales_blocked', 0) > 0 or blocked.get('purchase_blocked', 0) > 0:
            html_parts.append(
                '<div class="alert alert-info" style="padding: 10px; background: #d1ecf1; border: 1px solid #17a2b8; margin: 5px 0;">')
            html_parts.append('<strong>Blocked Products:</strong><br>')
            html_parts.append(f'• Sales Blocked: {blocked.get("sales_blocked", 0)}<br>')
            html_parts.append(f'• Purchase Blocked: {blocked.get("purchase_blocked", 0)}<br>')
            html_parts.append(f'• Both Blocked: {blocked.get("both_blocked", 0)}<br>')
            html_parts.append('</div>')

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    def render_stock_summary(self, request=None):
        """
        Render stock summary across all locations
        REFACTORED: Uses InventoryItem instead of Product fields
        """
        from inventory.models import InventoryItem

        html_parts = ['<div class="stock-summary" style="margin: 10px 0;">']
        html_parts.append('<h3>📦 Stock Summary</h3>')

        # Get stock statistics
        stock_stats = InventoryItem.objects.aggregate(
            total_products=Count('product', distinct=True),
            total_quantity=Sum('current_qty'),
            total_value=Sum(F('current_qty') * F('avg_cost')),
            total_reserved=Sum('reserved_qty')
        )

        # Format numbers
        total_products = stock_stats['total_products'] or 0
        total_quantity = stock_stats['total_quantity'] or Decimal('0')
        total_value = stock_stats['total_value'] or Decimal('0')
        total_reserved = stock_stats['total_reserved'] or Decimal('0')

        html_parts.append('<table style="width: 100%;">')
        html_parts.append(
            f'<tr><td>Products with Stock:</td><td style="text-align: right;"><strong>{total_products}</strong></td></tr>'
        )
        html_parts.append(
            f'<tr><td>Total Quantity:</td><td style="text-align: right;"><strong>{total_quantity:,.0f}</strong></td></tr>'
        )
        html_parts.append(
            f'<tr><td>Reserved Quantity:</td><td style="text-align: right;"><strong>{total_reserved:,.0f}</strong></td></tr>'
        )
        html_parts.append(
            f'<tr><td>Total Stock Value:</td><td style="text-align: right;"><strong>{total_value:,.2f} лв</strong></td></tr>'
        )
        html_parts.append('</table>')

        # Top locations by value
        html_parts.append('<h4>Top Locations by Stock Value:</h4>')

        from inventory.models import InventoryLocation
        locations = InventoryLocation.objects.annotate(
            stock_value=Sum(F('inventory_items__current_qty') * F('inventory_items__avg_cost'))
        ).filter(stock_value__gt=0).order_by('-stock_value')[:5]

        html_parts.append('<table style="width: 100%;">')
        for loc in locations:
            html_parts.append(
                f'<tr><td>{loc.name}</td><td style="text-align: right;">{loc.stock_value:,.2f} лв</td></tr>'
            )
        html_parts.append('</table>')

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))


class ProductDashboard(admin.ModelAdmin):
    """
    Standalone dashboard for products
    Can be registered as a proxy model admin
    """

    change_list_template = 'admin/products/dashboard.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Override changelist to show dashboard"""
        extra_context = extra_context or {}

        # Create dashboard mixin instance
        dashboard = ProductDashboardMixin()

        # Add dashboard widgets to context
        extra_context.update({
            'title': 'Products Dashboard',
            'lifecycle_chart': dashboard.render_lifecycle_distribution(request),
            'attention_items': dashboard.render_attention_items(request),
            'stock_summary': dashboard.render_stock_summary(request),
            'stats': dashboard.get_dashboard_stats(),
        })

        return super().changelist_view(request, extra_context=extra_context)