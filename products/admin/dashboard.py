# products/admin/dashboard.py - ADMIN DASHBOARD WIDGETS

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse

from ..models import Product, ProductLifecycleChoices
from ..services import ProductLifecycleService


class ProductDashboardMixin:
    """Mixin for adding dashboard functionality to product admin"""

    def get_dashboard_stats(self):
        """Get stats for admin dashboard"""
        return ProductLifecycleService.get_lifecycle_statistics()

    def render_lifecycle_distribution(self):
        """Render lifecycle status distribution"""
        stats = self.get_dashboard_stats()

        html_parts = ['<div class="lifecycle-stats">']

        for status_code, data in stats['by_lifecycle'].items():
            badge_class = {
                ProductLifecycleChoices.DRAFT: 'badge-warning',
                ProductLifecycleChoices.ACTIVE: 'badge-success',
                ProductLifecycleChoices.PHASE_OUT: 'badge-info',
                ProductLifecycleChoices.DISCONTINUED: 'badge-danger'
            }.get(status_code, 'badge-secondary')

            html_parts.append(
                f'<span class="badge {badge_class}">'
                f'{data["name"]}: {data["count"]} ({data["percentage"]}%)'
                f'</span> '
            )

        html_parts.append('</div>')

        return format_html(''.join(html_parts))

    def render_attention_items(self):
        """Render items needing attention"""
        from ..services import ProductService

        attention_items = ProductService.get_products_needing_attention()

        html_parts = ['<div class="attention-items">']

        if attention_items['blocked_sales']:
            html_parts.append(
                f'<p><strong>Sales Blocked:</strong> '
                f'{len(attention_items["blocked_sales"])} products</p>'
            )

        if attention_items['blocked_purchases']:
            html_parts.append(
                f'<p><strong>Purchases Blocked:</strong> '
                f'{len(attention_items["blocked_purchases"])} products</p>'
            )

        if attention_items['draft_old']:
            html_parts.append(
                f'<p><strong>Old Drafts:</strong> '
                f'{len(attention_items["draft_old"])} products (30+ days)</p>'
            )

        html_parts.append('</div>')

        return format_html(''.join(html_parts))

# Apply dashboard mixin to ProductAdmin
# В product.py: class ProductAdmin(ProductDashboardMixin, admin.ModelAdmin):