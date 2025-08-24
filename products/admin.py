# products/admin.py - ПЪЛЕН ПРОФЕСИОНАЛЕН АДМИН С INVENTORY ИНТЕГРАЦИЯ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q, F, Max, Min
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from decimal import Decimal

from .models import (
    Product,
    ProductPackaging,
    ProductBarcode,
    ProductPLU
)


# =================================================================
# INVENTORY INTEGRATION MIXINS
# =================================================================

class InventoryInfoMixin:
    """Mixin за добавяне на inventory информация към product админ"""

    def get_inventory_summary(self, obj):
        """Обобщена информация за inventory"""
        try:
            from inventory.models import InventoryItem

            items = InventoryItem.objects.filter(product=obj)

            if not items.exists():
                return {
                    'total_stock': Decimal('0'),
                    'total_reserved': Decimal('0'),
                    'available_stock': Decimal('0'),
                    'locations_count': 0,
                    'total_value': Decimal('0'),
                    'negative_locations': 0,
                    'last_movement': None
                }

            summary = items.aggregate(
                total_stock=Sum('current_qty'),
                total_reserved=Sum('reserved_qty'),
                total_value=Sum(F('current_qty') * F('avg_cost')),
                locations_count=Count('id'),
                negative_locations=Count('id', filter=Q(current_qty__lt=0)),
                last_movement=Max('last_movement_date')
            )

            total_stock = summary.get('total_stock') or Decimal('0')
            total_reserved = summary.get('total_reserved') or Decimal('0')

            return {
                'total_stock': total_stock,
                'total_reserved': total_reserved,
                'available_stock': total_stock - total_reserved,
                'total_value': summary.get('total_value') or Decimal('0'),
                'locations_count': summary.get('locations_count') or 0,
                'negative_locations': summary.get('negative_locations') or 0,
                'last_movement': summary.get('last_movement')
            }
        except ImportError:
            return None

    def get_inventory_locations(self, obj):
        """Списък локации където има stock"""
        try:
            from inventory.models import InventoryItem

            return InventoryItem.objects.filter(
                product=obj,
                current_qty__gt=0
            ).select_related('location').order_by('-current_qty')[:5]
        except ImportError:
            return []


# =================================================================
# CUSTOM FILTERS
# =================================================================

class ProductStockFilter(admin.SimpleListFilter):
    title = _('Stock Status')
    parameter_name = 'stock_status'

    def lookups(self, request, model_admin):
        return (
            ('with_stock', _('With Stock')),
            ('no_stock', _('No Stock')),
            ('negative', _('Negative Stock')),
            ('reserved', _('Has Reserved Stock')),
        )

    def queryset(self, request, queryset):
        try:
            from inventory.models import InventoryItem

            if self.value() == 'with_stock':
                product_ids = InventoryItem.objects.filter(
                    current_qty__gt=0
                ).values_list('product_id', flat=True).distinct()
                return queryset.filter(id__in=product_ids)

            elif self.value() == 'no_stock':
                with_stock = InventoryItem.objects.filter(
                    current_qty__gt=0
                ).values_list('product_id', flat=True).distinct()
                return queryset.exclude(id__in=with_stock)

            elif self.value() == 'negative':
                product_ids = InventoryItem.objects.filter(
                    current_qty__lt=0
                ).values_list('product_id', flat=True).distinct()
                return queryset.filter(id__in=product_ids)

            elif self.value() == 'reserved':
                product_ids = InventoryItem.objects.filter(
                    reserved_qty__gt=0
                ).values_list('product_id', flat=True).distinct()
                return queryset.filter(id__in=product_ids)

        except ImportError:
            pass

        return queryset


class ProductLifecycleFilter(admin.SimpleListFilter):
    title = _('Lifecycle Status')
    parameter_name = 'lifecycle_status'

    def lookups(self, request, model_admin):
        from .models import ProductLifecycleChoices
        return ProductLifecycleChoices.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lifecycle_status=self.value())
        return queryset


# =================================================================
# INLINE ADMINS
# =================================================================

class ProductPackagingInline(admin.TabularInline):
    model = ProductPackaging
    extra = 1
    max_num = 10

    fields = [
        'unit', 'conversion_factor', 'is_default_sale_unit',
        'is_default_purchase_unit', 'weight_kg', 'is_active'
    ]

    readonly_fields = []

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('unit').order_by('conversion_factor')


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1
    max_num = 10

    fields = [
        'barcode', 'barcode_type', 'packaging', 'is_primary', 'is_active'
    ]

    readonly_fields = []

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'packaging', 'packaging__unit'
        ).order_by('-is_primary')


class ProductPLUInline(admin.TabularInline):
    model = ProductPLU
    extra = 1
    max_num = 5

    fields = [
        'plu_code', 'is_primary', 'priority', 'description', 'is_active'
    ]

    readonly_fields = []

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-priority', '-is_primary')


# =================================================================
# MAIN PRODUCT ADMIN
# =================================================================

@admin.register(Product)
class ProductAdmin(InventoryInfoMixin, admin.ModelAdmin):
    """Главен админ за продуктите с inventory интеграция"""

    list_display = [
        'product_info', 'lifecycle_badge', 'type_info', 'unit_info',
        'stock_summary', 'tracking_info', 'restrictions_info'
    ]

    list_filter = [
        ProductLifecycleFilter,
        ProductStockFilter,
        'unit_type',
        'track_batches',
        'requires_expiry_date',
        'sales_blocked',
        'purchase_blocked',
        ('product_type', admin.RelatedOnlyFieldListFilter),
        ('product_group', admin.RelatedOnlyFieldListFilter),
        ('tax_group', admin.RelatedOnlyFieldListFilter)
    ]

    search_fields = [
        'code', 'name', 'description',
        'barcodes__barcode', 'plu_codes__plu_code'
    ]

    list_editable = []

    ordering = ['code']

    readonly_fields = [
        'created_at', 'updated_at', 'total_inventory_summary',
        'locations_summary', 'barcode_summary', 'packaging_summary',
        'recent_movements'
    ]

    inlines = [ProductPackagingInline, ProductBarcodeInline, ProductPLUInline]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code', 'name', 'description', 'lifecycle_status'
            )
        }),
        (_('Classification'), {
            'fields': (
                'product_type', 'product_group', 'brand', 'tax_group'
            )
        }),
        (_('Units & Measurement'), {
            'fields': (
                'base_unit', 'unit_type'
            )
        }),
        (_('Tracking Settings'), {
            'fields': (
                'track_batches', 'track_serial_numbers', 'requires_expiry_date'
            ),
            'description': _('Configure how this product is tracked in inventory')
        }),
        (_('Sales & Purchase Controls'), {
            'fields': (
                'sales_blocked', 'purchase_blocked', 'allow_negative_sales'
            )
        }),
        (_('Inventory Summary'), {
            'fields': (
                'total_inventory_summary', 'locations_summary'
            ),
            'classes': ('collapse',)
        }),
        (_('Product Configuration'), {
            'fields': (
                'barcode_summary', 'packaging_summary'
            ),
            'classes': ('collapse',)
        }),
        (_('Recent Activity'), {
            'fields': (
                'recent_movements',
            ),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': (
                'created_at', 'updated_at', 'created_by'
            ),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Оптимизирани заявки"""
        return super().get_queryset(request).select_related(
            'product_type', 'product_group', 'brand', 'tax_group',
            'base_unit', 'created_by'
        ).prefetch_related(
            'barcodes', 'plu_codes', 'packagings'
        )

    def product_info(self, obj):
        """Основна информация за продукта"""
        html_parts = []
        html_parts.append('<div style="font-family: sans-serif;">')
        html_parts.append('<strong style="font-size: 1.1em; color: #1976d2;">{}</strong><br>'.format(obj.code))
        html_parts.append('<span style="font-size: 0.95em;">{}</span>'.format(obj.name[:50]))

        # Показва primary barcode ако има
        primary_barcode = obj.barcodes.filter(is_primary=True, is_active=True).first()
        if primary_barcode:
            html_parts.append(
                '<br><span style="font-size: 0.85em; color: #666;">🏷️ {}</span>'.format(primary_barcode.barcode))

        # Показва primary PLU ако има
        primary_plu = obj.plu_codes.filter(is_primary=True, is_active=True).first()
        if primary_plu:
            html_parts.append(
                '<br><span style="font-size: 0.85em; color: #666;">⚖️ PLU: {}</span>'.format(primary_plu.plu_code))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    product_info.short_description = _('Product Info')

    def lifecycle_badge(self, obj):
        """Бадж за статуса на продукта"""
        colors = {
            'NEW': '#4CAF50',
            'ACTIVE': '#2196F3',
            'PHASE_OUT': '#FF9800',
            'DISCONTINUED': '#F44336',
            'ARCHIVED': '#757575'
        }

        icons = {
            'NEW': '✨',
            'ACTIVE': '✅',
            'PHASE_OUT': '⚠️',
            'DISCONTINUED': '❌',
            'ARCHIVED': '📦'
        }

        color = colors.get(obj.lifecycle_status, '#757575')
        icon = icons.get(obj.lifecycle_status, '❓')

        return mark_safe(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 0.85em; font-weight: bold;">'
            '{} {}</span>'.format(color, icon, obj.get_lifecycle_status_display())
        )

    lifecycle_badge.short_description = _('Status')

    def type_info(self, obj):
        """Информация за типа продукт"""
        html_parts = []

        if obj.product_type:
            html_parts.append('<strong>{}</strong><br>'.format(obj.product_type.name))

        if obj.product_group:
            html_parts.append('<small style="color: #666;">{}</small><br>'.format(obj.product_group.name))

        if obj.brand:
            html_parts.append('<small style="color: #1976d2;">🏢 {}</small>'.format(obj.brand.name))

        return mark_safe(''.join(html_parts)) if html_parts else '-'

    type_info.short_description = _('Type & Brand')

    def unit_info(self, obj):
        """Информация за мерните единици"""
        html_parts = []
        html_parts.append('<div style="font-family: monospace; font-size: 0.9em;">')

        # Base unit
        html_parts.append('📏 <strong>{}</strong><br>'.format(obj.base_unit.code))

        # Unit type с иконка
        type_icons = {
            'PIECE': '🔢',
            'WEIGHT': '⚖️',
            'VOLUME': '🥤',
            'LENGTH': '📐'
        }
        icon = type_icons.get(obj.unit_type, '❓')
        html_parts.append('{} {}'.format(icon, obj.get_unit_type_display()))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    unit_info.short_description = _('Unit Info')

    def stock_summary(self, obj):
        """Обобщение на складовите наличности"""
        inventory = self.get_inventory_summary(obj)

        if not inventory:
            return mark_safe('<span style="color: gray;">Няма inventory данни</span>')

        html_parts = []
        html_parts.append('<div style="font-family: monospace; font-size: 0.9em;">')

        # Total stock
        total_stock = inventory.get('total_stock', Decimal('0'))
        stock_color = 'green' if total_stock > 0 else ('red' if total_stock < 0 else 'gray')
        html_parts.append('📦 <strong style="color: {};">{:.3f}</strong><br>'.format(stock_color, total_stock))

        # Reserved stock
        total_reserved = inventory.get('total_reserved', Decimal('0'))
        if total_reserved > 0:
            html_parts.append('🔒 <span style="color: orange;">{:.3f}</span><br>'.format(total_reserved))

        # Locations
        locations_count = inventory.get('locations_count', 0)
        html_parts.append('🏢 {} локации<br>'.format(locations_count))

        # Value
        total_value = inventory.get('total_value', Decimal('0'))
        if total_value > 0:
            html_parts.append('💰 <span style="color: blue;">{:.2f} лв</span>'.format(total_value))

        # Negative locations warning
        negative_locations = inventory.get('negative_locations', 0)
        if negative_locations > 0:
            html_parts.append('<br>⚠️ <span style="color: red;">{} отрицателни</span>'.format(negative_locations))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    stock_summary.short_description = _('Stock')

    def tracking_info(self, obj):
        """Информация за проследяването"""
        badges = []

        if obj.track_batches:
            badges.append(
                '<span style="background: #4CAF50; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">📋 Партиди</span>')

        if obj.track_serial_numbers:
            badges.append(
                '<span style="background: #2196F3; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">🔢 Серийни</span>')

        if obj.requires_expiry_date:
            badges.append(
                '<span style="background: #FF9800; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">⏰ Срок</span>')

        return mark_safe('<br>'.join(badges)) if badges else '-'

    tracking_info.short_description = _('Tracking')

    def restrictions_info(self, obj):
        """Информация за ограниченията"""
        restrictions = []

        if obj.sales_blocked:
            restrictions.append(
                '<span style="background: #f44336; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">🚫 Продажби</span>')

        if obj.purchase_blocked:
            restrictions.append(
                '<span style="background: #f44336; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">🚫 Покупки</span>')

        if obj.allow_negative_sales:
            restrictions.append(
                '<span style="background: #ff9800; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">⚠️ Отриц. продажби</span>')

        return mark_safe('<br>'.join(restrictions)) if restrictions else '✅'

    restrictions_info.short_description = _('Restrictions')

    def total_inventory_summary(self, obj):
        """Подробно обобщение на inventory"""
        if not obj.pk:
            return 'Не е налично за нови продукти'

        inventory = self.get_inventory_summary(obj)
        if not inventory:
            return 'Inventory модул не е наличен'

        html_parts = []
        html_parts.append(
            '<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-family: sans-serif;">')
        html_parts.append('<h4 style="margin: 0 0 10px 0; color: #1976d2;">📊 Inventory обобщение</h4>')

        # Stock information
        total_stock = inventory.get('total_stock', Decimal('0'))
        total_reserved = inventory.get('total_reserved', Decimal('0'))
        available_stock = inventory.get('available_stock', Decimal('0'))
        locations_count = inventory.get('locations_count', 0)
        negative_locations = inventory.get('negative_locations', 0)
        total_value = inventory.get('total_value', Decimal('0'))
        last_movement = inventory.get('last_movement')

        html_parts.append('<table style="width: 100%; border-collapse: collapse; margin-bottom: 10px;">')
        html_parts.append(
            '<tr><td><strong>Общо наличност:</strong></td><td><strong>{:.3f} {}</strong></td></tr>'.format(
                total_stock, obj.base_unit.code))

        if total_reserved > 0:
            html_parts.append('<tr><td>Резервирано:</td><td style="color: orange;">{:.3f} {}</td></tr>'.format(
                total_reserved, obj.base_unit.code))
            html_parts.append(
                '<tr><td><strong>Налично:</strong></td><td><strong style="color: green;">{:.3f} {}</strong></td></tr>'.format(
                    available_stock, obj.base_unit.code))

        html_parts.append('<tr><td>Локации:</td><td>{}</td></tr>'.format(locations_count))

        if negative_locations > 0:
            html_parts.append(
                '<tr><td style="color: red;">Отрицателни локации:</td><td style="color: red;"><strong>{}</strong></td></tr>'.format(
                    negative_locations))

        if total_value > 0:
            html_parts.append(
                '<tr><td><strong>Обща стойност:</strong></td><td><strong style="color: blue;">{:.2f} лв</strong></td></tr>'.format(
                    total_value))

        html_parts.append('</table>')

        if last_movement:
            html_parts.append('<p><small>Последно движение: {}</small></p>'.format(
                last_movement.strftime('%d.%m.%Y %H:%M')))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    total_inventory_summary.short_description = _('Inventory Summary')

    def locations_summary(self, obj):
        """Обобщение по локации"""
        if not obj.pk:
            return 'Не е налично за нови продукти'

        locations = self.get_inventory_locations(obj)
        if not locations:
            return 'Няма stock в никоя локация'

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">')
        html_parts.append('<h4 style="margin: 0 0 10px 0; color: #1976d2;">🏢 Stock по локации</h4>')

        html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
        html_parts.append(
            '<tr style="background: #e3f2fd;"><th style="padding: 5px; text-align: left;">Локация</th><th style="padding: 5px; text-align: right;">Количество</th><th style="padding: 5px; text-align: right;">Стойност</th></tr>')

        for item in locations:
            stock_value = item.current_qty * item.avg_cost if item.avg_cost else 0
            html_parts.append('<tr>')
            html_parts.append('<td style="padding: 5px;"><strong>{}</strong><br><small>{}</small></td>'.format(
                item.location.code, item.location.name[:30]))
            html_parts.append(
                '<td style="padding: 5px; text-align: right; font-family: monospace;"><strong>{:.3f}</strong></td>'.format(
                    item.current_qty))
            html_parts.append(
                '<td style="padding: 5px; text-align: right; font-family: monospace;">{:.2f} лв</td>'.format(
                    stock_value))
            html_parts.append('</tr>')

        html_parts.append('</table>')

        # Link to full inventory view
        url = reverse('admin:inventory_inventoryitem_changelist')
        html_parts.append(
            '<p style="margin-top: 10px;"><a href="{}?product__id__exact={}">Виж всички локации</a></p>'.format(url,
                                                                                                                obj.id))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    locations_summary.short_description = _('Locations Summary')

    def barcode_summary(self, obj):
        """Обобщение на баркодовете"""
        if not obj.pk:
            return 'Не е налично за нови продукти'

        barcodes = obj.barcodes.filter(is_active=True).select_related('packaging')

        if not barcodes.exists():
            return 'Няма конфигурирани баркодове'

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">')
        html_parts.append('<h4 style="margin: 0 0 10px 0; color: #1976d2;">🏷️ Баркодове</h4>')

        for barcode in barcodes:
            html_parts.append('<div style="margin-bottom: 8px; padding: 8px; background: white; border-radius: 4px;">')

            # Primary badge
            if barcode.is_primary:
                html_parts.append(
                    '<span style="background: #4CAF50; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em; margin-right: 8px;">PRIMARY</span>')

            # Barcode
            html_parts.append('<strong style="font-family: monospace;">{}</strong>'.format(barcode.barcode))

            # Type
            type_icons = {
                'STANDARD': '📊',
                'WEIGHT': '⚖️',
                'INTERNAL': '🏷️'
            }
            icon = type_icons.get(barcode.barcode_type, '❓')
            html_parts.append(
                ' <span style="color: #666;">{} {}</span>'.format(icon, barcode.get_barcode_type_display()))

            # Packaging info
            if barcode.packaging:
                html_parts.append('<br><small style="color: #666;">Опаковка: {} × {}</small>'.format(
                    barcode.packaging.conversion_factor, barcode.packaging.unit.code))

            html_parts.append('</div>')

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    barcode_summary.short_description = _('Barcodes')

    def packaging_summary(self, obj):
        """Обобщение на опаковките"""
        if not obj.pk:
            return 'Не е налично за нови продукти'

        packagings = obj.packagings.filter(is_active=True).select_related('unit')

        if not packagings.exists():
            return 'Няма конфигурирани опаковки'

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">')
        html_parts.append('<h4 style="margin: 0 0 10px 0; color: #1976d2;">📦 Опаковки</h4>')

        for pkg in packagings:
            html_parts.append('<div style="margin-bottom: 8px; padding: 8px; background: white; border-radius: 4px;">')

            # Default badges
            if pkg.is_default_sale_unit:
                html_parts.append(
                    '<span style="background: #2196F3; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em; margin-right: 4px;">ПРОДАЖБА</span>')

            if pkg.is_default_purchase_unit:
                html_parts.append(
                    '<span style="background: #FF9800; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em; margin-right: 4px;">ПОКУПКА</span>')

            # Unit info
            html_parts.append('<strong>{}</strong> = <strong>{}</strong> × {}'.format(
                pkg.unit.name, pkg.conversion_factor, obj.base_unit.code))

            # Weight info
            if pkg.weight_kg:
                html_parts.append('<br><small style="color: #666;">Тегло: {} кг</small>'.format(pkg.weight_kg))

            html_parts.append('</div>')

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    packaging_summary.short_description = _('Packaging')

    def recent_movements(self, obj):
        """Скорошни движения"""
        if not obj.pk:
            return 'Не е налично за нови продукти'

        try:
            from inventory.models import InventoryMovement

            movements = InventoryMovement.objects.filter(
                product=obj
            ).select_related('location', 'created_by').order_by('-created_at')[:10]

            if not movements.exists():
                return 'Няма движения'

            html_parts = []
            html_parts.append('<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">')
            html_parts.append('<h4 style="margin: 0 0 10px 0; color: #1976d2;">📈 Скорошни движения</h4>')

            for movement in movements:
                direction = "➡️" if movement.is_incoming else "⬅️"
                date_str = movement.created_at.strftime('%d.%m %H:%M')

                html_parts.append('<div style="margin-bottom: 5px; font-size: 0.9em;">')
                html_parts.append(
                    '{} <strong>{:.3f}</strong> {} @ {} <small style="color: #666;">({} - {})</small>'.format(
                        direction,
                        movement.quantity,
                        movement.get_movement_type_display(),
                        movement.location.code,
                        date_str,
                        movement.created_by.username if movement.created_by else 'система'
                    ))
                html_parts.append('</div>')

            # Link to full movement history
            url = reverse('admin:inventory_inventorymovement_changelist')
            html_parts.append(
                '<p style="margin-top: 10px;"><a href="{}?product__id__exact={}">Виж всички движения</a></p>'.format(
                    url, obj.id))

            html_parts.append('</div>')
            return mark_safe(''.join(html_parts))

        except ImportError:
            return 'Inventory модул не е наличен'

    recent_movements.short_description = _('Recent Movements')


# =================================================================
# PACKAGING ADMIN
# =================================================================

@admin.register(ProductPackaging)
class ProductPackagingAdmin(admin.ModelAdmin):
    """Админ за опаковки на продуктите"""

    list_display = [
        'product_display', 'unit', 'conversion_display', 'type_badges',
        'physical_properties', 'is_active'
    ]

    list_filter = [
        'is_active',
        'is_default_sale_unit',
        'is_default_purchase_unit',
        'allow_sale',
        'allow_purchase',
        'unit',
        ('product__product_type', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'product__code',
        'product__name',
        'unit__code',
        'unit__name'
    ]

    list_editable = ['is_active']

    fieldsets = (
        (_('Product & Unit'), {
            'fields': ('product', 'unit', 'conversion_factor')
        }),
        (_('Usage Settings'), {
            'fields': (
                ('allow_purchase', 'allow_sale'),
                ('is_default_purchase_unit', 'is_default_sale_unit')
            )
        }),
        (_('Physical Properties'), {
            'fields': (
                'weight_kg',
                'volume_m3',
                ('length_cm', 'width_cm', 'height_cm')
            ),
            'classes': ('collapse',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        })
    )

    def product_display(self, obj):
        """Показва продукта с линк"""
        return mark_safe(
            '<a href="/admin/products/product/{}/change/">{} - {}</a>'.format(
                obj.product.id, obj.product.code, obj.product.name[:30]
            )
        )

    product_display.short_description = _('Product')

    def conversion_display(self, obj):
        """Показва конверсията"""
        return mark_safe(
            '<strong style="font-family: monospace;">{} {} = {} {}</strong>'.format(
                1, obj.unit.code, obj.conversion_factor, obj.product.base_unit.code
            )
        )

    conversion_display.short_description = _('Conversion')

    def type_badges(self, obj):
        """Показва типовете използване"""
        badges = []

        if obj.is_default_sale_unit:
            badges.append(
                '<span style="background: #2196F3; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">ПРОДАЖБА</span>')
        elif obj.allow_sale:
            badges.append(
                '<span style="background: #64B5F6; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">продажба</span>')

        if obj.is_default_purchase_unit:
            badges.append(
                '<span style="background: #FF9800; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">ПОКУПКА</span>')
        elif obj.allow_purchase:
            badges.append(
                '<span style="background: #FFB74D; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">покупка</span>')

        return mark_safe('<br>'.join(badges)) if badges else '-'

    type_badges.short_description = _('Usage Type')

    def physical_properties(self, obj):
        """Показва физическите свойства"""
        props = []

        if obj.weight_kg:
            props.append('⚖️ {} кг'.format(obj.weight_kg))

        if obj.volume_m3:
            props.append('📦 {} м³'.format(obj.volume_m3))

        if obj.length_cm and obj.width_cm and obj.height_cm:
            props.append('📏 {}×{}×{} см'.format(obj.length_cm, obj.width_cm, obj.height_cm))

        return mark_safe('<br>'.join(props)) if props else '-'

    physical_properties.short_description = _('Properties')


# =================================================================
# BARCODE ADMIN
# =================================================================

@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    """Админ за баркодове на продуктите"""

    list_display = [
        'barcode', 'product_display', 'barcode_type_display',
        'packaging_display', 'is_primary', 'is_active'
    ]

    list_filter = [
        'barcode_type',
        'is_primary',
        'is_active',
        ('product__product_type', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'barcode',
        'product__code',
        'product__name'
    ]

    list_editable = ['is_primary', 'is_active']

    fieldsets = (
        (_('Barcode Information'), {
            'fields': ('barcode', 'barcode_type', 'product')
        }),
        (_('Packaging Link'), {
            'fields': ('packaging',),
            'description': _('Optional: Link to specific packaging')
        }),
        (_('Settings'), {
            'fields': ('is_primary', 'is_active')
        })
    )

    def product_display(self, obj):
        """Показва информация за продукта"""
        return mark_safe(
            '<a href="/admin/products/product/{}/change/">{}</a><br><small>{}</small>'.format(
                obj.product.id, obj.product.code, obj.product.name[:40]
            )
        )

    product_display.short_description = _('Product')

    def barcode_type_display(self, obj):
        """Показва типа баркод с иконка"""
        icons = {
            'STANDARD': '📊',
            'WEIGHT': '⚖️',
            'INTERNAL': '🏷️'
        }
        icon = icons.get(obj.barcode_type, '❓')

        return mark_safe('{} {}'.format(icon, obj.get_barcode_type_display()))

    barcode_type_display.short_description = _('Type')

    def packaging_display(self, obj):
        """Показва опаковката ако е свързана"""
        if obj.packaging:
            return mark_safe(
                '{} × {}'.format(obj.packaging.conversion_factor, obj.packaging.unit.code)
            )
        return '-'

    packaging_display.short_description = _('Packaging')


# =================================================================
# PLU ADMIN
# =================================================================

@admin.register(ProductPLU)
class ProductPLUAdmin(admin.ModelAdmin):
    """Админ за PLU кодове на продуктите"""

    list_display = [
        'plu_code', 'product_display', 'is_primary', 'priority',
        'description', 'weight_product_check', 'is_active'
    ]

    list_filter = [
        'is_primary',
        'is_active',
        'priority',
        ('product__product_type', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'plu_code',
        'product__code',
        'product__name',
        'description'
    ]

    list_editable = ['is_primary', 'priority', 'is_active']

    fieldsets = (
        (_('PLU Information'), {
            'fields': ('plu_code', 'product', 'description')
        }),
        (_('Settings'), {
            'fields': ('is_primary', 'priority', 'is_active')
        })
    )

    def product_display(self, obj):
        """Показва продукта с индикатор за тегло"""
        weight_icon = '⚖️' if obj.product.unit_type == 'WEIGHT' else '❌'
        return mark_safe(
            '{} <a href="/admin/products/product/{}/change/">{}</a><br><small>{}</small>'.format(
                weight_icon, obj.product.id, obj.product.code, obj.product.name[:40]
            )
        )

    product_display.short_description = _('Product')

    def weight_product_check(self, obj):
        """Проверява дали продукта е за теглене"""
        if obj.product.unit_type == 'WEIGHT':
            return mark_safe('<span style="color: green;">✅ Weight Product</span>')
        else:
            return mark_safe('<span style="color: red;">❌ Not Weight Product</span>')

    weight_product_check.short_description = _('Valid for Weight')


# =================================================================
# ADMIN ACTIONS
# =================================================================

def activate_products(modeladmin, request, queryset):
    """Активиране на избрани продукти"""
    from .models import ProductLifecycleChoices
    updated = queryset.update(lifecycle_status=ProductLifecycleChoices.ACTIVE)
    messages.success(request, 'Активирани {} продукта'.format(updated))


activate_products.short_description = "Активирай избраните продукти"


def deactivate_products(modeladmin, request, queryset):
    """Деактивиране на избрани продукти"""
    from .models import ProductLifecycleChoices
    updated = queryset.update(lifecycle_status=ProductLifecycleChoices.DISCONTINUED)
    messages.success(request, 'Деактивирани {} продукта'.format(updated))


deactivate_products.short_description = "Деактивирай избраните продукти"


def block_sales(modeladmin, request, queryset):
    """Блокиране на продажбите"""
    updated = queryset.update(sales_blocked=True)
    messages.success(request, 'Блокирани продажби за {} продукта'.format(updated))


block_sales.short_description = "Блокирай продажби за избраните продукти"


def unblock_sales(modeladmin, request, queryset):
    """Отблокиране на продажбите"""
    updated = queryset.update(sales_blocked=False)
    messages.success(request, 'Отблокирани продажби за {} продукта'.format(updated))


unblock_sales.short_description = "Отблокирай продажби за избраните продукти"


def enable_batch_tracking(modeladmin, request, queryset):
    """Включване на batch tracking"""
    updated = queryset.update(track_batches=True)
    messages.success(request, 'Включено batch tracking за {} продукта'.format(updated))


enable_batch_tracking.short_description = "Включи batch tracking за избраните продукти"


def disable_batch_tracking(modeladmin, request, queryset):
    """Изключване на batch tracking"""
    updated = queryset.update(track_batches=False)
    messages.success(request, 'Изключено batch tracking за {} продукта'.format(updated))


disable_batch_tracking.short_description = "Изключи batch tracking за избраните продукти"


def export_products_csv(modeladmin, request, queryset):
    """Експорт на продуктите в CSV"""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Code', 'Name', 'Product Type', 'Unit Type', 'Base Unit',
        'Lifecycle Status', 'Sales Blocked', 'Purchase Blocked',
        'Track Batches', 'Requires Expiry', 'Created At'
    ])

    for product in queryset:
        writer.writerow([
            product.code,
            product.name,
            product.product_type.name if product.product_type else '',
            product.get_unit_type_display(),
            product.base_unit.code,
            product.get_lifecycle_status_display(),
            'Да' if product.sales_blocked else 'Не',
            'Да' if product.purchase_blocked else 'Не',
            'Да' if product.track_batches else 'Не',
            'Да' if product.requires_expiry_date else 'Не',
            product.created_at.strftime('%d.%m.%Y %H:%M')
        ])

    return response


export_products_csv.short_description = "Експорт в CSV"

# Добавяне на actions към админите
ProductAdmin.actions = [
    activate_products, deactivate_products, block_sales, unblock_sales,
    enable_batch_tracking, disable_batch_tracking, export_products_csv
]