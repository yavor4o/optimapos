from datetime import timedelta

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from ..models import Currency, ExchangeRate, TaxGroup
from ..services import CurrencyService


class ExchangeRateInline(admin.TabularInline):
    """Inline за последните курсове на валутата"""
    model = ExchangeRate
    extra = 0
    fields = ['date', 'units', 'buy_rate', 'sell_rate', 'central_rate', 'is_active']
    readonly_fields = ['date']
    ordering = ['-date']




@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'symbol',
        'is_base_badge',
        'latest_rate',
        'is_active'
    ]
    list_filter = ['is_base', 'is_active']
    search_fields = ['code', 'name']
    readonly_fields = ['is_base_badge_large']
    inlines = [ExchangeRateInline]

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'symbol')
        }),
        (_('Settings'), {
            'fields': ('is_base', 'is_base_badge_large', 'decimal_places', 'is_active')
        }),
    )

    def is_base_badge(self, obj):
        """Badge за базова валута"""
        if obj.is_base:
            return format_html(
                '<span style="background-color: #4CAF50; color: white; '
                'padding: 3px 10px; border-radius: 3px;">BASE</span>'
            )
        return '-'

    is_base_badge.short_description = _('Base')

    def is_base_badge_large(self, obj):
        """Голям badge за детайлите"""
        if obj.is_base:
            return format_html(
                '<div style="background-color: #4CAF50; color: white; '
                'padding: 10px; border-radius: 5px; text-align: center; '
                'font-weight: bold; max-width: 200px;">BASE CURRENCY</div>'
            )
        return _('Regular currency')

    is_base_badge_large.short_description = _('Currency Status')

    def latest_rate(self, obj):
        """Последен курс"""
        if obj.is_base:
            return format_html('<span style="color: gray;">-</span>')

        try:
            rate = ExchangeRate.objects.get_rate_for_date(obj)
            return format_html(
                '{:.4f} <small style="color: gray;">({})</small>',
                rate.central_rate,
                rate.date.strftime('%d.%m.%Y')
            )
        except:
            return format_html('<span style="color: red;">No rate</span>')

    latest_rate.short_description = _('Latest Rate')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # Editing
            readonly.extend(['code', 'is_base'])
        return readonly

    def has_delete_permission(self, request, obj=None):
        """Не позволяваме изтриване на базова валута"""
        if obj and obj.is_base:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency',
        'date',
        'units',
        'buy_rate',
        'sell_rate',
        'central_rate',
        'spread_info',
        'is_active'
    ]
    list_filter = ['currency', 'date', 'is_active']
    search_fields = ['currency__code', 'currency__name']
    date_hierarchy = 'date'
    readonly_fields = ['spread_info_detail', 'created_at', 'created_by']

    fieldsets = (
        (None, {
            'fields': ('currency', 'date', 'units')
        }),
        (_('Exchange Rates'), {
            'fields': ('buy_rate', 'sell_rate', 'central_rate', 'spread_info_detail')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def spread_info(self, obj):
        """Информация за спреда"""
        spread = obj.sell_rate - obj.buy_rate
        spread_percent = (spread / obj.central_rate) * 100

        color = 'green' if spread_percent < 1 else 'orange' if spread_percent < 2 else 'red'

        return format_html(
            '<span style="color: {};">{:.4f} ({:.2f}%)</span>',
            color,
            spread,
            spread_percent
        )

    spread_info.short_description = _('Spread')

    def spread_info_detail(self, obj):
        """Детайлна информация за спреда"""
        if not obj.pk:
            return '-'

        info = CurrencyService.get_rate_spread(obj.currency, obj.date)

        return format_html(
            '<div style="background: #f0f0f0; padding: 10px; border-radius: 5px;">'
            '<strong>Buy Rate:</strong> {:.6f}<br>'
            '<strong>Sell Rate:</strong> {:.6f}<br>'
            '<strong>Spread:</strong> {:.6f} ({:.2f}%)<br>'
            '</div>',
            info['buy_rate'],
            info['sell_rate'],
            info['spread_amount'],
            info['spread_percent']
        )

    spread_info_detail.short_description = _('Spread Analysis')

    def save_model(self, request, obj, form, change):
        if not change:  # New object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        """Не позволяваме триене на исторически курсове"""
        if obj and obj.date < timezone.now().date() - timedelta(days=7):
            return False
        return super().has_delete_permission(request, obj)

    # Custom actions
    actions = ['import_bnb_rates']

    def import_bnb_rates(self, request, queryset):
        """Action за импорт на курсове от БНБ"""
        from django.utils import timezone
        imported, errors = CurrencyService.import_bnb_rates(timezone.now().date())

        if errors:
            self.message_user(
                request,
                f"Imported {imported} rates. Errors: {', '.join(errors)}",
                level='WARNING'
            )
        else:
            self.message_user(
                request,
                f"Successfully imported {imported} rates",
                level='SUCCESS'
            )

    import_bnb_rates.short_description = _('Import rates from BNB')


@admin.register(TaxGroup)
class TaxGroupAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'rate_display',
        'tax_type',
        'is_default_badge',
        'is_reverse_charge',
        'is_active'
    ]
    list_filter = ['tax_type', 'is_default', 'is_reverse_charge', 'is_active']
    search_fields = ['code', 'name']


    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'rate', 'tax_type')
        }),
        (_('Settings'), {
            'fields': ('is_default', 'is_reverse_charge', 'is_active')
        }),
    )

    def rate_display(self, obj):
        """Показва ставката с % - с проверка за валидност"""
        try:
            # Уверяваме се, че rate е число
            if obj.rate is None:
                return format_html('<span style="color: gray;">-</span>')

            # Конвертираме в float ако е необходимо
            rate_value = float(obj.rate)

            return format_html(
                '<span style="font-weight: bold; font-size: 14px;">{}</span>',
                f'{rate_value:.2f}%'
            )
        except (ValueError, TypeError, AttributeError):
            # Ако има проблем с форматирането, показваме суровата стойност
            return format_html(
                '<span style="color: red;">Invalid: {}</span>',
                str(obj.rate) if obj.rate is not None else 'None'
            )

    rate_display.short_description = _('Rate')
    rate_display.admin_order_field = 'rate'

    def is_default_badge(self, obj):
        """Badge за данък по подразбиране"""
        if obj.is_default:
            return format_html(
                '<span style="background-color: #2196F3; color: white; '
                'padding: 3px 10px; border-radius: 3px;">DEFAULT</span>'
            )
        return '-'

    is_default_badge.short_description = _('Default')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields or [])
        if obj:  # Editing
            readonly.append('code')
        return readonly

    def save_model(self, request, obj, form, change):
        # Ако се маркира като default, махаме default от другите
        if obj.is_default:
            TaxGroup.objects.exclude(pk=obj.pk).update(is_default=False)
        super().save_model(request, obj, form, change)