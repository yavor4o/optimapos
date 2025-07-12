# pricing/admin/prices.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import F
from django.utils.safestring import mark_safe

from ..models import ProductPrice, ProductPriceByGroup, ProductStepPrice


# === CUSTOM FILTERS ===

class PricingMethodFilter(admin.SimpleListFilter):
    title = _('Pricing Method')
    parameter_name = 'pricing_method'

    def lookups(self, request, model_admin):
        return (
            ('FIXED', _('Fixed Price')),
            ('MARKUP', _('Markup on Cost')),
            ('AUTO', _('Auto (Location Default)')),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(pricing_method=self.value())
        return queryset


class PriceRangeFilter(admin.SimpleListFilter):
    title = _('Price Range')
    parameter_name = 'price_range'

    def lookups(self, request, model_admin):
        return (
            ('0-10', _('0-10 BGN')),
            ('10-50', _('10-50 BGN')),
            ('50-100', _('50-100 BGN')),
            ('100+', _('Over 100 BGN')),
        )

    def queryset(self, request, queryset):
        if self.value() == '0-10':
            return queryset.filter(effective_price__lte=10)
        elif self.value() == '10-50':
            return queryset.filter(effective_price__gt=10, effective_price__lte=50)
        elif self.value() == '50-100':
            return queryset.filter(effective_price__gt=50, effective_price__lte=100)
        elif self.value() == '100+':
            return queryset.filter(effective_price__gt=100)
        return queryset


# === MAIN PRODUCT PRICE ADMIN ===

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'location', 'pricing_method_display',
        'base_price_display', 'markup_display', 'effective_price_display',
        'profit_analysis', 'last_cost_update', 'is_active'
    ]

    list_filter = [
        'is_active', 'location', 'pricing_method',
        PricingMethodFilter, PriceRangeFilter,
        'product__product_group', 'product__brand'
    ]

    search_fields = [
        'product__code', 'product__name', 'location__code', 'location__name'
    ]

    list_editable = ['is_active']

    readonly_fields = [
        'effective_price', 'created_at', 'updated_at',
        'last_cost_update', 'pricing_analysis'
    ]

    fieldsets = (
        (_('Product & Location'), {
            'fields': ('location', 'product', 'is_active')
        }),
        (_('Pricing Method'), {
            'fields': ('pricing_method',),
            'description': _('Choose how the price is calculated')
        }),
        (_('Price Settings'), {
            'fields': ('base_price', 'markup_percentage'),
            'description': _('Set either fixed price OR markup percentage')
        }),
        (_('Calculated Results'), {
            'fields': ('effective_price', 'pricing_analysis'),
            'classes': ('collapse',),
            'description': _('Automatically calculated pricing information')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at', 'last_cost_update'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'product', 'product__brand'
        )

    def product_display(self, obj):
        """Product information display"""
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = _('Product')

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

    def base_price_display(self, obj):
        """Base price display"""
        if obj.base_price:
            return format_html(
                '<strong>{:.2f} лв</strong>',
                obj.base_price
            )
        return '-'

    base_price_display.short_description = _('Base Price')

    def markup_display(self, obj):
        """Markup percentage display"""
        if obj.markup_percentage:
            return format_html(
                '<span style="color: blue;">{}%</span>',
                obj.markup_percentage
            )
        return '-'

    markup_display.short_description = _('Markup %')

    def effective_price_display(self, obj):
        """Effective price with styling"""
        return format_html(
            '<strong style="color: green;">{:.2f} лв</strong>',
            obj.effective_price
        )

    effective_price_display.short_description = _('Final Price')

    def profit_analysis(self, obj):
        """Profit margin and markup analysis"""
        try:
            cost_price = obj.get_current_cost_price()
            if cost_price > 0:
                margin = obj.get_profit_margin()
                markup_amount = obj.get_markup_amount()

                return format_html(
                    'Cost: {:.2f}<br>Profit: {:.2f}<br>Margin: {:.1f}%',
                    cost_price, markup_amount, margin
                )
        except:
            pass

        return '-'

    profit_analysis.short_description = _('Profit Analysis')

    def pricing_analysis(self, obj):
        """Detailed pricing analysis"""
        if not obj.pk:
            return "Save price record first to see analysis"

        try:
            cost_price = obj.get_current_cost_price()
            margin = obj.get_profit_margin()
            markup_amount = obj.get_markup_amount()

            analysis_parts = [
                f"<strong>Pricing Method:</strong> {obj.get_pricing_method_display()}",
                f"<strong>Current Cost:</strong> {cost_price:.2f} лв",
                f"<strong>Effective Price:</strong> {obj.effective_price:.2f} лв",
                f"<strong>Profit Amount:</strong> {markup_amount:.2f} лв",
                f"<strong>Profit Margin:</strong> {margin:.1f}%"
            ]

            if obj.markup_percentage:
                analysis_parts.append(f"<strong>Markup %:</strong> {obj.markup_percentage}%")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    pricing_analysis.short_description = _('Pricing Analysis')

    # Actions
    actions = ['recalculate_prices', 'apply_markup_increase', 'sync_with_cost']

    def recalculate_prices(self, request, queryset):
        """Recalculate effective prices"""
        count = 0
        for price_record in queryset:
            price_record.calculate_effective_price()
            price_record.save(update_fields=['effective_price'])
            count += 1

        self.message_user(request, f'Recalculated {count} prices.')

    recalculate_prices.short_description = _('Recalculate effective prices')

    def apply_markup_increase(self, request, queryset):
        """Apply 5% markup increase"""
        count = queryset.filter(
            pricing_method='FIXED'
        ).update(
            base_price=F('base_price') * 1.05,
            effective_price=F('effective_price') * 1.05
        )

        self.message_user(request, f'Applied 5% increase to {count} fixed prices.')

    apply_markup_increase.short_description = _('Apply 5% price increase (fixed prices only)')

    def sync_with_cost(self, request, queryset):
        """Sync markup-based prices with current costs"""
        count = 0
        for price_record in queryset.filter(pricing_method__in=['MARKUP', 'AUTO']):
            old_price = price_record.effective_price
            price_record.calculate_effective_price()
            price_record.save(update_fields=['effective_price', 'last_cost_update'])
            count += 1

        self.message_user(request, f'Synchronized {count} markup-based prices with current costs.')

    sync_with_cost.short_description = _('Sync markup prices with current costs')


# === GROUP PRICES ADMIN ===

@admin.register(ProductPriceByGroup)
class ProductPriceByGroupAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'location', 'price_group', 'price_display',
        'min_quantity', 'discount_from_base', 'is_active'
    ]

    list_filter = [
        'is_active', 'location', 'price_group',
        'product__product_group', 'product__brand'
    ]

    search_fields = [
        'product__code', 'product__name',
        'price_group__name', 'location__code'
    ]

    list_editable = ['price', 'min_quantity', 'is_active']

    fieldsets = (
        (_('Product & Location'), {
            'fields': ('location', 'product', 'price_group')
        }),
        (_('Pricing'), {
            'fields': ('price', 'min_quantity')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'product', 'price_group'
        )

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = _('Product')

    def price_display(self, obj):
        return format_html(
            '<strong style="color: blue;">{:.2f} лв</strong>',
            obj.price
        )

    price_display.short_description = _('Group Price')

    def discount_from_base(self, obj):
        """Calculate discount from base price"""
        try:
            base_price = ProductPrice.objects.get(
                location=obj.location,
                product=obj.product,
                is_active=True
            ).effective_price

            if base_price > 0:
                discount = ((base_price - obj.price) / base_price) * 100
                if discount > 0:
                    return format_html(
                        '<span style="color: green;">-{:.1f}%</span>',
                        discount
                    )
        except ProductPrice.DoesNotExist:
            pass

        return '-'

    discount_from_base.short_description = _('Discount from Base')


# === STEP PRICES ADMIN ===

@admin.register(ProductStepPrice)
class ProductStepPriceAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'location', 'min_quantity', 'price_display',
        'discount_from_base', 'description', 'is_active'
    ]

    list_filter = [
        'is_active', 'location', 'product__product_group', 'product__brand'
    ]

    search_fields = [
        'product__code', 'product__name', 'location__code', 'description'
    ]

    list_editable = ['price', 'min_quantity', 'is_active']

    fieldsets = (
        (_('Product & Location'), {
            'fields': ('location', 'product')
        }),
        (_('Step Pricing'), {
            'fields': ('min_quantity', 'price', 'description')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'product'
        )

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = _('Product')

    def price_display(self, obj):
        return format_html(
            '<strong style="color: orange;">{:.2f} лв</strong>',
            obj.price
        )

    price_display.short_description = _('Step Price')

    def discount_from_base(self, obj):
        """Calculate discount from base price"""
        discount = obj.discount_from_base
        if discount > 0:
            return format_html(
                '<span style="color: green;">-{:.1f}%</span>',
                discount
            )
        return '-'

    discount_from_base.short_description = _('Discount from Base')