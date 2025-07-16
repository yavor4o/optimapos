# pricing/admin/promotions.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.db.models import Q

from ..models import PromotionalPrice


# === CUSTOM FILTERS ===

class PromotionStatusFilter(admin.SimpleListFilter):
    title = _('Promotion Status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('active', _('Currently Active')),
            ('upcoming', _('Upcoming')),
            ('expired', _('Expired')),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == 'active':
            return queryset.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            )
        elif self.value() == 'upcoming':
            return queryset.filter(
                start_date__gt=today,
                is_active=True
            )
        elif self.value() == 'expired':
            return queryset.filter(
                end_date__lt=today
            )
        return queryset


class PromotionDurationFilter(admin.SimpleListFilter):
    title = _('Duration')
    parameter_name = 'duration'

    def lookups(self, request, model_admin):
        return (
            ('1day', _('1 Day')),
            ('week', _('Week or less')),
            ('month', _('Month or less')),
            ('long', _('Longer than month')),
        )

    def queryset(self, request, queryset):
        from datetime import timedelta

        for promo in queryset:
            duration = (promo.end_date - promo.start_date).days

        if self.value() == '1day':
            return queryset.extra(
                where=["(end_date - start_date) <= 1"]
            )
        elif self.value() == 'week':
            return queryset.extra(
                where=["(end_date - start_date) <= 7"]
            )
        elif self.value() == 'month':
            return queryset.extra(
                where=["(end_date - start_date) <= 30"]
            )
        elif self.value() == 'long':
            return queryset.extra(
                where=["(end_date - start_date) > 30"]
            )
        return queryset


# === MAIN PROMOTIONAL PRICE ADMIN ===

@admin.register(PromotionalPrice)
class PromotionalPriceAdmin(admin.ModelAdmin):
    """Simple promotional price admin - без излишни глупости"""

    list_display = [
        'name', 'product', 'location', 'promotional_price',
        'start_date', 'end_date', 'is_active'
    ]

    list_filter = [
        'is_active', 'location', 'start_date', 'end_date'
    ]

    search_fields = [
        'name', 'product__code', 'product__name'
    ]

    list_editable = ['is_active']

    fieldsets = (
        (_('Basic'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Product & Location'), {
            'fields': ('location', 'product')
        }),
        (_('Pricing'), {
            'fields': ('promotional_price',)
        }),
        (_('Date Range'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Quantity Limits'), {
            'fields': ('min_quantity', 'max_quantity'),
            'classes': ('collapse',)
        }),
        (_('Customer Groups'), {
            'fields': ('customer_groups',),
            'classes': ('collapse',)
        }),
    )

    filter_horizontal = ['customer_groups']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'product', 'product__brand'
        ).prefetch_related('customer_groups')

    def product_display(self, obj):
        """Product information with brand"""
        brand_info = f" ({obj.product.brand.name})" if obj.product.brand else ""
        return f"{obj.product.code} - {obj.product.name[:25]}{brand_info}"

    product_display.short_description = _('Product')

    def promotional_price_display(self, obj):
        """Promotional price display - ПОПРАВЕНО"""
        try:
            price_value = float(obj.promotional_price) if obj.promotional_price else 0
            return format_html(
                '<strong style="color: red; font-size: 14px;">{:.2f} лв</strong>',
                price_value
            )
        except (TypeError, ValueError):
            return '-'

    def discount_analysis(self, obj):
        """Discount analysis - ПОПРАВЕНО"""
        try:
            discount_amount = obj.get_discount_amount()
            discount_percentage = obj.get_discount_percentage()

            # Конвертираме и двете към float
            amount_value = float(discount_amount) if discount_amount else 0
            percent_value = float(discount_percentage) if discount_percentage else 0

            if amount_value > 0:
                return format_html(
                    '<span style="color: green;">-{:.2f} лв<br>(-{:.1f}%)</span>',
                    amount_value, percent_value
                )
        except (TypeError, ValueError, AttributeError):
            pass

        return '-'

    promotional_price_display.short_description = _('Promo Price')

    def date_range_display(self, obj):
        """Date range with duration"""
        duration = (obj.end_date - obj.start_date).days + 1
        return format_html(
            '{} — {}<br><small>({} days)</small>',
            obj.start_date.strftime('%d.%m.%Y'),
            obj.end_date.strftime('%d.%m.%Y'),
            duration
        )

    date_range_display.short_description = _('Date Range')

    from django.utils.safestring import mark_safe

    def status_display(self, obj):
        today = timezone.now().date()
        if not obj.is_active:
            return mark_safe('<span style="color: gray;">⏸️ Inactive</span>')
        elif obj.start_date > today:
            days_until = (obj.start_date - today).days
            return mark_safe(f'<span style="color: orange;">📅 Starts in {days_until} days</span>')
        elif obj.end_date < today:
            return mark_safe('<span style="color: red;">⏰ Expired</span>')
        else:
            days_left = (obj.end_date - today).days
            return mark_safe(f'<span style="color: green;">✅ Active ({days_left} days left)</span>')

    status_display.short_description = _('Status')

    def quantity_range(self, obj):
        """Quantity restrictions display"""
        if obj.max_quantity:
            return f"{obj.min_quantity} - {obj.max_quantity}"
        else:
            return f"{obj.min_quantity}+"

    quantity_range.short_description = _('Quantity Range')

    def discount_analysis(self, obj):
        """Discount calculation from base price"""
        try:
            discount_amount = obj.get_discount_amount()
            discount_percentage = obj.get_discount_percentage()

            if discount_amount > 0:
                return format_html(
                    '<span style="color: green;">-{:.2f} лв<br>(-{:.1f}%)</span>',
                    discount_amount, discount_percentage
                )
        except:
            pass

        return '-'

    discount_analysis.short_description = _('Discount')

    def promotion_analysis(self, obj):
        """Detailed promotion analysis"""
        if not obj.pk:
            return "Save promotion first to see analysis"

        analysis_parts = [
            f"<strong>Promotion:</strong> {obj.name}",
            f"<strong>Product:</strong> {obj.product.code} - {obj.product.name}",
            f"<strong>Location:</strong> {obj.location.code} - {obj.location.name}",
            f"<strong>Promotional Price:</strong> {obj.promotional_price:.2f} лв",
            f"<strong>Date Range:</strong> {obj.start_date} to {obj.end_date}",
            f"<strong>Duration:</strong> {(obj.end_date - obj.start_date).days + 1} days",
            f"<strong>Min Quantity:</strong> {obj.min_quantity}",
        ]

        if obj.max_quantity:
            analysis_parts.append(f"<strong>Max Quantity:</strong> {obj.max_quantity}")

        if obj.customer_groups.exists():
            groups = ", ".join([g.name for g in obj.customer_groups.all()])
            analysis_parts.append(f"<strong>Customer Groups:</strong> {groups}")
        else:
            analysis_parts.append("<strong>Customer Groups:</strong> All customers")

        #