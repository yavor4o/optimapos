# pricing/admin/packaging.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe

from ..models import PackagingPrice


@admin.register(PackagingPrice)
class PackagingPriceAdmin(admin.ModelAdmin):
    list_display = [
        'packaging_display', 'location', 'pricing_method_display',
        'price_display', 'unit_price_display', 'savings_display', 'is_active'
    ]

    list_filter = [
        'is_active', 'location', 'pricing_method',
        'packaging__product__product_group', 'packaging__product__brand',
        'packaging__unit'
    ]

    search_fields = [
        'packaging__product__code', 'packaging__product__name',
        'location__code', 'packaging__unit__name'
    ]

    list_editable = ['is_active']

    readonly_fields = ['created_at', 'updated_at', 'packaging_analysis']

    fieldsets = (
        (_('Packaging & Location'), {
            'fields': ('location', 'packaging', 'is_active')
        }),
        (_('Pricing Method'), {
            'fields': ('pricing_method',),
            'description': _('Choose how the packaging price is calculated')
        }),
        (_('Price Settings'), {
            'fields': ('price', 'markup_percentage', 'discount_percentage'),
            'description': _('Set price directly OR use markup/discount percentages')
        }),
        (_('Analysis'), {
            'fields': ('packaging_analysis',),
            'classes': ('collapse',),
            'description': _('Automatically calculated packaging information')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'packaging', 'packaging__product',
            'packaging__unit', 'packaging__product__base_unit'
        )

    def packaging_display(self, obj):
        """Packaging information display"""
        return format_html(
            '{} - {} x{}<br><small>{}</small>',
            obj.packaging.product.code,
            obj.packaging.unit.code,
            obj.packaging.conversion_factor,
            obj.packaging.product.name[:40]
        )

    packaging_display.short_description = _('Packaging')

    def pricing_method_display(self, obj):
        """Pricing method with icon"""
        icons = {
            'FIXED': '💰',
            'MARKUP': '📈',
            'AUTO': '🤖'
        }
        icon = icons.get(obj.pricing_method, '❓')
        return format_html(
            '{} {}',
            icon, obj.get_pricing_method_display()
        )

    pricing_method_display.short_description = _('Method')

    def price_display(self, obj):
        """Packaging price display"""
        return format_html(
            '<strong style="color: green;">{:.2f} лв</strong><br>'
            '<small>за {} {}</small>',
            obj.price,
            obj.packaging.conversion_factor,
            obj.packaging.unit.code
        )

    price_display.short_description = _('Packaging Price')

    def unit_price_display(self, obj):
        """Price per base unit"""
        unit_price = obj.get_unit_price()
        return format_html(
            '{:.4f} лв<br><small>per {}</small>',
            unit_price,
            obj.packaging.product.base_unit.code
        )

    unit_price_display.short_description = _('Unit Price')

    def savings_display(self, obj):
        """Savings compared to individual purchase"""
        savings = obj.get_savings_from_base()

        if savings['amount'] > 0:
            return format_html(
                '<span style="color: green;">💰 -{:.2f} лв<br>'
                '<small>(-{:.1f}%)</small></span>',
                savings['amount'],
                savings['percentage']
            )
        elif savings['amount'] < 0:
            return format_html(
                '<span style="color: red;">💸 +{:.2f} лв<br>'
                '<small>(+{:.1f}%)</small></span>',
                abs(savings['amount']),
                abs(savings['percentage'])
            )
        else:
            return format_html('<span style="color: gray;">No data</span>')

    savings_display.short_description = _('Savings vs Individual')

    def packaging_analysis(self, obj):
        """Detailed packaging analysis"""
        if not obj.pk:
            return "Save packaging price first to see analysis"

        info = obj.packaging_info
        savings = obj.get_savings_from_base()

        analysis_parts = [
            f"<strong>Product:</strong> {info['product_code']} - {info['product_name']}",
            f"<strong>Packaging:</strong> {info['unit_name']} x{info['conversion_factor']} {info['base_unit']}",
            f"<strong>Packaging Price:</strong> {obj.price:.2f} лв",
            f"<strong>Price per {info['base_unit']}:</strong> {obj.get_unit_price():.4f} лв",
            f"<strong>Pricing Method:</strong> {obj.get_pricing_method_display()}"
        ]

        if obj.markup_percentage:
            analysis_parts.append(f"<strong>Markup:</strong> {obj.markup_percentage}%")

        if obj.discount_percentage:
            analysis_parts.append(f"<strong>Discount:</strong> {obj.discount_percentage}%")

        if savings['individual_total'] > 0:
            analysis_parts.extend([
                f"<strong>Individual Purchase Total:</strong> {savings['individual_total']:.2f} лв",
                f"<strong>Packaging Savings:</strong> {savings['amount']:.2f} лв ({savings['percentage']:.1f}%)"
            ])

        return mark_safe('<br>'.join(analysis_parts))

    packaging_analysis.short_description = _('Packaging Analysis')

    # Actions
    actions = ['recalculate_prices', 'apply_bulk_discount', 'sync_with_base_prices']

    def recalculate_prices(self, request, queryset):
        """Recalculate packaging prices"""
        count = 0
        for packaging_price in queryset.exclude(pricing_method='FIXED'):
            packaging_price.calculate_effective_price()
            packaging_price.save(update_fields=['price'])
            count += 1

        self.message_user(request, f'Recalculated {count} packaging prices.')

    recalculate_prices.short_description = _('Recalculate non-fixed prices')

    def apply_bulk_discount(self, request, queryset):
        """Apply 5% bulk discount"""
        count = queryset.update(
            discount_percentage=models.F('discount_percentage') + 5
        )

        # Recalculate prices for AUTO method
        for obj in queryset.filter(pricing_method='AUTO'):
            obj.calculate_effective_price()
            obj.save(update_fields=['price'])

        self.message_user(request, f'Applied 5% additional discount to {count} packaging prices.')

    apply_bulk_discount.short_description = _('Apply 5% additional discount')

    def sync_with_base_prices(self, request, queryset):
        """Sync with base product prices"""
        count = 0
        for packaging_price in queryset.exclude(pricing_method='FIXED'):
            packaging_price.calculate_effective_price()
            packaging_price.save(update_fields=['price'])
            count += 1

        self.message_user(request, f'Synchronized {count} packaging prices with base prices.')

    sync_with_base_prices.short_description = _('Sync with base product prices')
