# nomenclatures/admin/operational.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from django.db.models import Count, Q
from ..models import UnitOfMeasure, PaymentType, POSLocation


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'symbol',
        'unit_type_badge',
        'decimals_info',
        'product_count',
        'is_active'
    ]
    list_filter = ['unit_type', 'allow_decimals', 'is_active']
    search_fields = ['code', 'name', 'symbol']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'symbol', 'unit_type')
        }),
        (_('Decimal Settings'), {
            'fields': ('allow_decimals', 'decimal_places'),
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Анотираме с брой продукти
        return qs.annotate(
            product_count_ann=Count('product', distinct=True)
        )

    def product_count(self, obj):
        """Брой продукти с тази мерна единица"""
        count = getattr(obj, 'product_count_ann', 0)
        if count > 0:
            return format_html('<strong>{}</strong>', count)
        return '0'

    product_count.short_description = _('Products')
    product_count.admin_order_field = 'product_count_ann'

    def unit_type_badge(self, obj):
        """Цветен badge за типа единица"""
        colors = {
            'PIECE': '#4CAF50',
            'WEIGHT': '#FF9800',
            'VOLUME': '#2196F3',
            'LENGTH': '#9C27B0',
            'AREA': '#795548',
        }
        color = colors.get(obj.unit_type, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_unit_type_display()
        )

    unit_type_badge.short_description = _('Type')
    unit_type_badge.admin_order_field = 'unit_type'

    def decimals_info(self, obj):
        """Информация за десетични знаци"""
        if obj.allow_decimals:
            return format_html(
                '<span style="color: green;">✓ {} decimals</span>',
                obj.decimal_places
            )
        return format_html('<span style="color: gray;">✗ No decimals</span>')

    decimals_info.short_description = _('Decimals')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields or [])
        if obj:  # Editing
            readonly.append('code')
        return readonly


@admin.register(PaymentType)
class PaymentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'reorder_link',
        'code',
        'name',
        'key_badge',
        'payment_flags',
        'limits_info',
        'transaction_count',
        'is_active'
    ]
    list_filter = ['key', 'is_cash', 'requires_reference', 'is_fiscal', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['sort_order', 'code']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'key', 'sort_order')
        }),
        (_('Payment Characteristics'), {
            'fields': (
                'is_cash',
                'requires_reference',
                'allows_change',
                'requires_approval',
                'is_fiscal'
            ),
        }),
        (_('Limits'), {
            'fields': ('min_amount', 'max_amount'),
            'description': _('Leave empty for no limits')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Анотираме с брой транзакции (ще трябва когато имаме sales)
        # return qs.annotate(
        #     transaction_count_ann=Count('sales_transactions', distinct=True)
        # )
        return qs

    def reorder_link(self, obj):
        """Линкове за преподреждане"""
        return format_html(
            '<span style="font-size: 16px;">↕</span>'
        )

    reorder_link.short_description = ''

    def key_badge(self, obj):
        """Badge за системния ключ"""
        colors = {
            'CASH': '#4CAF50',
            'CARD': '#2196F3',
            'BANK': '#FF9800',
            'VOUCHER': '#9C27B0',
            'CREDIT': '#F44336',
        }
        color = colors.get(obj.key, '#757575')

        return format_html(
            '<code style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 11px;">{}</code>',
            color,
            obj.key
        )

    key_badge.short_description = _('Key')

    def payment_flags(self, obj):
        """Флагове на плащането"""
        flags = []

        if obj.is_cash:
            flags.append('<span title="Cash" style="color: #4CAF50;">💵</span>')
        if obj.requires_reference:
            flags.append('<span title="Requires Reference" style="color: #FF9800;">📋</span>')
        if obj.allows_change:
            flags.append('<span title="Allows Change" style="color: #2196F3;">💱</span>')
        if obj.requires_approval:
            flags.append('<span title="Requires Approval" style="color: #F44336;">✅</span>')
        if not obj.is_fiscal:
            flags.append('<span title="Non-Fiscal" style="color: #9E9E9E;">🚫</span>')

        return format_html(' '.join(flags)) if flags else '-'

    payment_flags.short_description = _('Flags')

    def limits_info(self, obj):
        """Информация за лимити"""
        parts = []

        if obj.min_amount:
            parts.append(f'Min: {obj.min_amount}')
        if obj.max_amount:
            parts.append(f'Max: {obj.max_amount}')

        if parts:
            return format_html(
                '<small style="color: #666;">{}</small>',
                ' / '.join(parts)
            )
        return format_html('<small style="color: #999;">No limits</small>')

    limits_info.short_description = _('Limits')

    def transaction_count(self, obj):
        """Брой транзакции (за бъдеще)"""
        # count = getattr(obj, 'transaction_count_ann', 0)
        return '-'

    transaction_count.short_description = _('Transactions')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields or [])
        if obj:  # Editing
            readonly.extend(['code', ])
        return readonly


class POSLocationForm(forms.ModelForm):
    """Форма с валидации за POS Location"""

    class Meta:
        model = POSLocation
        fields = '__all__'

    def clean_fiscal_device_serial(self):
        """Валидация на серийния номер"""
        serial = self.cleaned_data.get('fiscal_device_serial')
        if serial:
            # Премахваме интервали и правим uppercase
            serial = serial.strip().upper()
        return serial


@admin.register(POSLocation)
class POSLocationAdmin(admin.ModelAdmin):
    form = POSLocationForm

    list_display = [
        'code',
        'name',
        'location_link',  # ПРОМЕНЕНО от inventory_location_link
        'fiscal_info',
        'working_hours',
        'status_badge',
        'session_info'
    ]
    list_filter = [
        'location',  # ПРОМЕНЕНО от inventory_location
        'is_active',
        'allow_negative_stock'
    ]
    search_fields = ['code', 'name', 'fiscal_device_serial']
    readonly_fields = ['created_at', 'updated_at', 'current_status_info']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'location',)  # ПРОМЕНЕНО от inventory_location
        }),
        (_('Location'), {
            'fields': ('address',),
            'classes': ('collapse',)
        }),
        (_('Fiscal Device'), {
            'fields': ('fiscal_device_serial', 'fiscal_device_number'),
        }),
        (_('Settings'), {
            'fields': (
                'allow_negative_stock',
                'require_customer',
                'default_customer',
                'receipt_printer'
            ),
        }),
        (_('Working Hours'), {
            'fields': ('opens_at', 'closes_at'),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('is_active', 'created_at', 'updated_at', 'current_status_info'),
            'classes': ('collapse',)
        }),
    )

    # ДОБАВЕНИ МЕТОДИ - тези липсваха и затова имаше грешка
    def location_link(self, obj):
        """Показва линк към inventory location"""
        if obj.location:
            return format_html(
                '<a href="{}">{}</a>',
                reverse('admin:inventory_inventorylocation_change', args=[obj.location.pk]),
                obj.location.name
            )
        return '-'

    location_link.short_description = _('Location')
    location_link.admin_order_field = 'location__name'

    def fiscal_info(self, obj):
        """Информация за фискалното устройство"""
        if obj.fiscal_device_serial:
            return format_html(
                '<small>{}<br/>{}</small>',
                obj.fiscal_device_serial,
                obj.fiscal_device_number or '-'
            )
        return format_html('<small style="color: #999;">No fiscal device</small>')

    fiscal_info.short_description = _('Fiscal Device')

    def working_hours(self, obj):
        """Работно време"""
        if obj.opens_at and obj.closes_at:
            return format_html(
                '<small>{} - {}</small>',
                obj.opens_at.strftime('%H:%M'),
                obj.closes_at.strftime('%H:%M')
            )
        return format_html('<small style="color: #999;">24/7</small>')

    working_hours.short_description = _('Hours')

    def status_badge(self, obj):
        """Статус badge"""
        if obj.is_active:
            if obj.is_open_now():
                return format_html(
                    '<span style="background-color: #4CAF50; color: white; '
                    'padding: 2px 6px; border-radius: 3px; font-size: 11px;">OPEN</span>'
                )
            else:
                return format_html(
                    '<span style="background-color: #FF9800; color: white; '
                    'padding: 2px 6px; border-radius: 3px; font-size: 11px;">CLOSED</span>'
                )
        return format_html(
            '<span style="background-color: #F44336; color: white; '
            'padding: 2px 6px; border-radius: 3px; font-size: 11px;">INACTIVE</span>'
        )

    status_badge.short_description = _('Status')

    def session_info(self, obj):
        """Информация за сесията"""
        # Това ще се имплементира когато имаме sales модул
        active_session = obj.get_active_session()
        if active_session:
            return format_html('<small style="color: green;">Active session</small>')
        return format_html('<small style="color: #999;">No session</small>')

    session_info.short_description = _('Session')

    def current_status_info(self, obj):
        """Детайлна информация за текущия статус"""
        if not obj.pk:
            return '-'

        parts = []

        # Статус
        if obj.is_active:
            parts.append('✅ Active')
        else:
            parts.append('❌ Inactive')

        # Работно време
        if obj.is_open_now():
            parts.append('🕐 Open now')
        else:
            parts.append('🕐 Closed now')

        # Сесия
        active_session = obj.get_active_session()
        if active_session:
            parts.append('💼 Session active')
        else:
            parts.append('💼 No session')

        return format_html('<br/>'.join(parts))

    current_status_info.short_description = _('Current Status')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields or [])
        if obj:  # Editing
            readonly.append('code')
        return readonly