# inventory/admin.py - ПЪЛЕН ПРОФЕСИОНАЛЕН АДМИН ЗА ВСИЧКИ МОДЕЛИ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db import models
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages

from .models import (
    InventoryLocation,
    InventoryItem,
    InventoryBatch,
    InventoryMovement
)


# =================================================================
# INLINE ADMINS
# =================================================================

class InventoryItemInline(admin.TabularInline):
    """Inline за inventory items в location admin"""
    model = InventoryItem
    extra = 0
    fields = [
        'product', 'current_qty', 'reserved_qty', 'avg_cost',
        'min_stock_level', 'max_stock_level', 'last_movement_date'
    ]
    readonly_fields = ['current_qty', 'reserved_qty', 'avg_cost', 'last_movement_date']

    def has_add_permission(self, request, obj):
        return False


class InventoryBatchInline(admin.TabularInline):
    """Inline за batch-ове в product admin (не в InventoryItem)"""
    model = InventoryBatch
    extra = 0
    fields = [
        'location', 'batch_number', 'remaining_qty', 'cost_price', 'expiry_date',
        'received_date', 'is_unknown_batch'
    ]
    readonly_fields = ['received_qty', 'is_unknown_batch']


class InventoryMovementInline(admin.TabularInline):
    """Inline за movements (ще се използва в product или location admin)"""
    model = InventoryMovement
    extra = 0
    fields = [
        'movement_type', 'quantity', 'cost_price', 'batch_number',
        'movement_date', 'created_at'
    ]
    readonly_fields = ['movement_type', 'quantity', 'cost_price', 'batch_number', 'movement_date', 'created_at']
    ordering = ['-created_at']

    def has_add_permission(self, request, obj):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =================================================================
# INVENTORY LOCATION ADMIN
# =================================================================

@admin.register(InventoryLocation)
class InventoryLocationAdmin(admin.ModelAdmin):
    """Админ за складови локации"""

    list_display = [
        'code', 'name', 'location_type', 'batch_tracking_mode',
        'allow_negative_stock', 'items_count', 'total_stock_value',
        'is_active'
    ]

    list_filter = [
        'location_type', 'batch_tracking_mode', 'allow_negative_stock',
        'is_active'
    ]

    search_fields = ['code', 'name', 'description']

    list_editable = ['is_active']

    ordering = ['code']

    readonly_fields = [
        'created_at', 'updated_at', 'location_statistics',
        'batch_tracking_info', 'stock_summary'
    ]

    inlines = [InventoryItemInline]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code', 'name', 'location_type', 'description',
                'is_active'
            )
        }),
        (_('Batch Tracking Settings'), {
            'fields': (
                'batch_tracking_mode', 'batch_expiry_tracking',
                'batch_tracking_info'
            ),
            'classes': ('collapse',)
        }),
        (_('Stock Management'), {
            'fields': (
                'allow_negative_stock', 'enable_cycle_counting',
                'auto_reorder_enabled'
            )
        }),
        (_('Contact Information'), {
            'fields': (
                'address', 'phone', 'email', 'manager'
            ),
            'classes': ('collapse',)
        }),
        (_('Pricing Settings'), {
            'fields': (
                'default_markup_percentage', 'purchase_prices_include_vat',
                'sales_prices_include_vat'
            ),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': (
                'created_at', 'updated_at', 'location_statistics',
                'stock_summary'
            ),
            'classes': ('collapse',)
        })
    )

    def items_count(self, obj):
        """Брой продукти на локацията"""
        count = obj.inventory_items.count()
        if count == 0:
            return mark_safe('<span style="color: gray;">0</span>')

        url = reverse('admin:inventory_inventoryitem_changelist')
        return mark_safe(
            '<a href="{}?location__id__exact={}">{} products</a>'.format(url, obj.id, count)
        )

    items_count.short_description = _('Products')

    def total_stock_value(self, obj):
        """Обща стойност на склада"""
        total = obj.inventory_items.aggregate(
            total=Sum('current_qty') * Sum('avg_cost')
        )['total'] or 0

        if total == 0:
            return mark_safe('<span style="color: gray;">0.00 лв</span>')

        return mark_safe(
            '<span style="font-weight: bold; color: green;">{:.2f} лв</span>'.format(total)
        )

    total_stock_value.short_description = _('Stock Value')

    def location_statistics(self, obj):
        """Статистики за локацията"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        stats = {
            'items_count': obj.inventory_items.count(),
            'with_stock': obj.inventory_items.filter(current_qty__gt=0).count(),
            'low_stock': obj.inventory_items.filter(
                current_qty__lte=models.F('min_stock_level'),
                min_stock_level__gt=0,
                current_qty__gt=0
            ).count(),
            'negative_stock': obj.inventory_items.filter(current_qty__lt=0).count(),
            'batches_count': obj.inventory_batches.count() if hasattr(obj, 'inventory_batches') else 0,
            'expired_batches': obj.inventory_batches.filter(
                expiry_date__lt=timezone.now().date(),
                remaining_qty__gt=0
            ).count() if hasattr(obj, 'inventory_batches') else 0
        }

        html_parts = ['<div style="font-family: monospace;">']
        html_parts.append('📦 Общо продукти: <strong>{}</strong><br>'.format(stats["items_count"]))
        html_parts.append('✅ С наличност: <strong>{}</strong><br>'.format(stats["with_stock"]))

        if stats['low_stock'] > 0:
            html_parts.append(
                '⚠️ Ниска наличност: <strong style="color: orange;">{}</strong><br>'.format(stats["low_stock"]))

        if stats['negative_stock'] > 0:
            html_parts.append(
                '❌ Отрицателна наличност: <strong style="color: red;">{}</strong><br>'.format(stats["negative_stock"]))

        if stats['batches_count'] > 0:
            html_parts.append('📋 Партиди: <strong>{}</strong><br>'.format(stats["batches_count"]))

        if stats['expired_batches'] > 0:
            html_parts.append(
                '⏰ Изтекли партиди: <strong style="color: red;">{}</strong><br>'.format(stats["expired_batches"]))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    location_statistics.short_description = _('Statistics')

    def batch_tracking_info(self, obj):
        """Информация за batch tracking"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        mode_colors = {
            'DISABLED': 'gray',
            'OPTIONAL': 'blue',
            'ENFORCED': 'green'
        }

        color = mode_colors.get(obj.batch_tracking_mode, 'black')
        mode_text = obj.get_batch_tracking_mode_display()

        html_parts = []
        html_parts.append('<span style="color: {}; font-weight: bold;">{}</span><br>'.format(color, mode_text))

        if obj.batch_expiry_tracking:
            html_parts.append('<span style="color: green;">✓ Проследяване на срока</span><br>')
        else:
            html_parts.append('<span style="color: orange;">⚠ Без проследяване на срока</span><br>')

        return mark_safe(''.join(html_parts))

    batch_tracking_info.short_description = _('Batch Tracking')

    def stock_summary(self, obj):
        """Обобщение на склада"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        from django.db.models import Sum, Count

        summary = obj.inventory_items.aggregate(
            total_products=Count('id'),
            total_qty=Sum('current_qty'),
            total_reserved=Sum('reserved_qty'),
            total_value=Sum(models.F('current_qty') * models.F('avg_cost'))
        )

        html_parts = []
        html_parts.append(
            '<div style="font-family: monospace; background: #f8f9fa; padding: 10px; border-radius: 5px;">')
        html_parts.append('📊 <strong>Обобщение склад {}</strong><br><br>'.format(obj.code))
        html_parts.append('Продукти: <strong>{}</strong><br>'.format(summary["total_products"] or 0))
        html_parts.append('Общо количество: <strong>{:.3f}</strong><br>'.format(summary["total_qty"] or 0))
        html_parts.append('Резервирано: <strong>{:.3f}</strong><br>'.format(summary["total_reserved"] or 0))
        html_parts.append('Налично: <strong>{:.3f}</strong><br>'.format(
            (summary["total_qty"] or 0) - (summary["total_reserved"] or 0)))
        html_parts.append('Стойност: <strong>{:.2f} лв</strong>'.format(summary["total_value"] or 0))
        html_parts.append('</div>')

        return mark_safe(''.join(html_parts))

    stock_summary.short_description = _('Stock Summary')


# =================================================================
# INVENTORY ITEM ADMIN
# =================================================================

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """Админ за inventory items (кеширани количества)"""

    list_display = [
        'product_info', 'location', 'stock_status', 'quantities_display',
        'cost_info', 'stock_levels', 'last_movement_date'
    ]

    list_filter = [
        'location', 'location__location_type',
        ('last_movement_date', admin.DateFieldListFilter),
        ('product__product_type', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'product__code', 'product__name', 'product__barcode',
        'location__code', 'location__name'
    ]

    readonly_fields = [
        'current_qty', 'reserved_qty', 'avg_cost', 'last_movement_date',
        'updated_at', 'availability_info', 'cost_analysis', 'movement_history'
    ]

    ordering = ['location', 'product']

    # Премахваме inline-овете защото нямат правилна FK връзка
    # inlines = [InventoryBatchInline, InventoryMovementInline]

    fieldsets = (
        (_('Product & Location'), {
            'fields': ('product', 'location')
        }),
        (_('Current Stock'), {
            'fields': (
                'current_qty', 'reserved_qty', 'availability_info'
            )
        }),
        (_('Cost Information'), {
            'fields': (
                'avg_cost', 'last_purchase_cost', 'last_purchase_date',
                'last_sale_price', 'last_sale_date', 'cost_analysis'
            ),
            'classes': ('collapse',)
        }),
        (_('Stock Management'), {
            'fields': ('min_stock_level', 'max_stock_level')
        }),
        (_('System Information'), {
            'fields': (
                'last_movement_date', 'updated_at', 'movement_history'
            ),
            'classes': ('collapse',)
        })
    )

    def product_info(self, obj):
        """Информация за продукта"""
        html_parts = []
        html_parts.append('<strong>{}</strong><br>'.format(obj.product.code))
        html_parts.append('<span style="font-size: 0.9em;">{}</span>'.format(obj.product.name[:50]))

        if hasattr(obj.product, 'barcode') and obj.product.barcode:
            html_parts.append(
                '<br><span style="font-size: 0.8em; color: gray;">🏷️ {}</span>'.format(obj.product.barcode))

        return mark_safe(''.join(html_parts))

    product_info.short_description = _('Product')

    def stock_status(self, obj):
        """Статус на склада"""
        if obj.current_qty <= 0:
            if obj.current_qty < 0:
                return mark_safe(
                    '<span style="background: #ffebee; color: #c62828; padding: 2px 6px; border-radius: 3px;">'
                    '❌ Отрицателна'
                    '</span>'
                )
            else:
                return mark_safe(
                    '<span style="background: #fafafa; color: #616161; padding: 2px 6px; border-radius: 3px;">'
                    '⚪ Няма'
                    '</span>'
                )

        # Проверка за ниска наличност
        if obj.min_stock_level > 0 and obj.current_qty <= obj.min_stock_level:
            return mark_safe(
                '<span style="background: #fff3e0; color: #ef6c00; padding: 2px 6px; border-radius: 3px;">'
                '⚠️ Ниска'
                '</span>'
            )

        return mark_safe(
            '<span style="background: #e8f5e8; color: #2e7d32; padding: 2px 6px; border-radius: 3px;">'
            '✅ Налична'
            '</span>'
        )

    stock_status.short_description = _('Status')

    def quantities_display(self, obj):
        """Показване на количествата"""
        available = obj.current_qty - obj.reserved_qty

        html_parts = []
        html_parts.append('<div style="font-family: monospace;">')
        html_parts.append('📦 <strong>{:.3f}</strong><br>'.format(obj.current_qty))

        if obj.reserved_qty > 0:
            html_parts.append('🔒 <span style="color: orange;">{:.3f}</span><br>'.format(obj.reserved_qty))
            html_parts.append('✅ <strong style="color: green;">{:.3f}</strong>'.format(available))
        else:
            html_parts.append('✅ <strong style="color: green;">{:.3f}</strong>'.format(available))

        html_parts.append('</div>')

        return mark_safe(''.join(html_parts))

    quantities_display.short_description = _('Qty (Current/Reserved/Available)')

    def cost_info(self, obj):
        """Информация за цени"""
        if obj.avg_cost == 0:
            return mark_safe('<span style="color: gray;">Няма данни</span>')

        html_parts = []
        html_parts.append('<div style="font-family: monospace;">')
        html_parts.append('💰 <strong>{:.4f} лв</strong><br>'.format(obj.avg_cost))

        if obj.last_purchase_cost:
            html_parts.append('📈 {:.4f} лв'.format(obj.last_purchase_cost))
            if obj.last_purchase_date:
                html_parts.append(
                    '<br><span style="font-size: 0.8em; color: gray;">({})</span>'.format(obj.last_purchase_date))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    cost_info.short_description = _('Cost (Avg/Last Purchase)')

    def stock_levels(self, obj):
        """Показване на лимитите"""
        html_parts = ['<div style="font-family: monospace; font-size: 0.9em;">']

        if obj.min_stock_level > 0:
            html_parts.append('⬇️ {:.3f}'.format(obj.min_stock_level))
        else:
            html_parts.append('⬇️ -')

        html_parts.append(' | ')

        if obj.max_stock_level > 0:
            html_parts.append('⬆️ {:.3f}'.format(obj.max_stock_level))
        else:
            html_parts.append('⬆️ -')

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    stock_levels.short_description = _('Min | Max')

    def availability_info(self, obj):
        """Подробна информация за наличността"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        available = obj.current_qty - obj.reserved_qty

        html = '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
        html += f'📊 <strong>Детайли за наличността</strong><br><br>'
        html += f'Общо количество: <strong>{obj.current_qty:.3f}</strong><br>'
        html += f'Резервирано: <strong>{obj.reserved_qty:.3f}</strong><br>'
        html += f'Налично за продажба: <strong style="color: green;">{available:.3f}</strong><br><br>'

        # Статус спрямо лимитите
        if obj.min_stock_level > 0:
            html += f'Минимум: <strong>{obj.min_stock_level:.3f}</strong>'
            if obj.current_qty <= obj.min_stock_level:
                html += ' <span style="color: red;">⚠️ Под лимита!</span>'
            html += '<br>'

        if obj.max_stock_level > 0:
            html += f'Максимум: <strong>{obj.max_stock_level:.3f}</strong>'
            if obj.current_qty >= obj.max_stock_level:
                html += ' <span style="color: orange;">⚠️ Над лимита!</span>'
            html += '<br>'

        html += '</div>'
        return mark_safe(html)

    availability_info.short_description = _('Availability Details')

    def cost_analysis(self, obj):
        """Анализ на разходите"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">')
        html_parts.append('💰 <strong>Анализ на разходите</strong><br><br>')

        if obj.avg_cost > 0:
            stock_value = obj.current_qty * obj.avg_cost
            html_parts.append('Средна цена: <strong>{:.4f} лв</strong><br>'.format(obj.avg_cost))
            html_parts.append('Стойност на склада: <strong>{:.2f} лв</strong><br><br>'.format(stock_value))

        if obj.last_purchase_cost:
            html_parts.append('Последна покупна цена: <strong>{:.4f} лв</strong><br>'.format(obj.last_purchase_cost))
            if obj.last_purchase_date:
                html_parts.append('Дата: {}<br>'.format(obj.last_purchase_date))

            if obj.avg_cost > 0:
                diff = obj.last_purchase_cost - obj.avg_cost
                diff_pct = (diff / obj.avg_cost) * 100
                if diff > 0:
                    html_parts.append(
                        '<span style="color: red;">📈 +{:.4f} лв ({:+.1f}%)</span><br>'.format(diff, diff_pct))
                elif diff < 0:
                    html_parts.append(
                        '<span style="color: green;">📉 {:.4f} лв ({:+.1f}%)</span><br>'.format(diff, diff_pct))
            html_parts.append('<br>')

        if obj.last_sale_price:
            html_parts.append('Последна продажна цена: <strong>{:.2f} лв</strong><br>'.format(obj.last_sale_price))
            if obj.last_sale_date:
                html_parts.append('Дата: {}<br>'.format(obj.last_sale_date))

            if obj.avg_cost > 0:
                margin = obj.last_sale_price - obj.avg_cost
                margin_pct = (margin / obj.last_sale_price) * 100
                html_parts.append(
                    'Марж: <strong style="color: blue;">{:.2f} лв ({:.1f}%)</strong>'.format(margin, margin_pct))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    cost_analysis.short_description = _('Cost Analysis')

    def movement_history(self, obj):
        """История на движенията"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        movements = obj.product.inventory_movements.filter(
            location=obj.location
        ).order_by('-created_at')[:5]

        if not movements:
            return 'Няма движения'

        html_parts = []
        html_parts.append('<div style="font-family: monospace; font-size: 0.9em;">')
        html_parts.append('<strong>Последни 5 движения:</strong><br><br>')

        for movement in movements:
            direction = "➡️" if movement.is_incoming else "⬅️"
            date_str = movement.movement_date.strftime('%d.%m.%y')

            html_parts.append(
                '{} {:.3f} - {}'.format(direction, movement.quantity, movement.get_movement_type_display()))
            html_parts.append(' <span style="color: gray;">({})</span><br>'.format(date_str))

        html_parts.append('<br>')
        url = reverse('admin:inventory_inventorymovement_changelist')
        html_parts.append(
            '<a href="{}?location__id__exact={}&product__id__exact={}">Виж всички движения</a>'.format(url,
                                                                                                       obj.location.id,
                                                                                                       obj.product.id))
        html_parts.append('</div>')

        return mark_safe(''.join(html_parts))

    movement_history.short_description = _('Recent Movements')


# =================================================================
# INVENTORY BATCH ADMIN
# =================================================================

@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    """Админ за inventory batch-ове"""

    list_display = [
        'batch_info', 'location', 'product', 'quantities_display',
        'cost_price', 'expiry_status', 'received_date'
    ]

    list_filter = [
        'location', 'is_unknown_batch',
        ('expiry_date', admin.DateFieldListFilter),
        ('received_date', admin.DateFieldListFilter),
    ]

    search_fields = [
        'batch_number', 'product__code', 'product__name',
        'location__code', 'original_source'
    ]

    readonly_fields = [
        'created_at', 'updated_at', 'batch_analytics',
        'conversion_info', 'consumption_rate'
    ]

    ordering = ['-received_date', 'expiry_date']

    fieldsets = (
        (_('Batch Information'), {
            'fields': (
                'batch_number', 'location', 'product', 'is_unknown_batch',
                'original_source'
            )
        }),
        (_('Quantities'), {
            'fields': ('received_qty', 'remaining_qty')
        }),
        (_('Dates'), {
            'fields': ('received_date', 'expiry_date', 'conversion_date')
        }),
        (_('Cost'), {
            'fields': ('cost_price',)
        }),
        (_('Analytics'), {
            'fields': ('batch_analytics', 'conversion_info', 'consumption_rate'),
            'classes': ('collapse',)
        }),
        (_('System'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def batch_info(self, obj):
        """Информация за партидата"""
        html_parts = ['<strong>{}</strong><br>'.format(obj.batch_number)]

        if obj.is_unknown_batch:
            html_parts.append(
                '<span style="background: #fff3e0; color: #ef6c00; padding: 1px 4px; border-radius: 2px; font-size: 0.8em;">UNKNOWN</span>')

        return mark_safe(''.join(html_parts))

    batch_info.short_description = _('Batch')

    def quantities_display(self, obj):
        """Показване на количествата"""
        consumed = obj.received_qty - obj.remaining_qty
        consumption_pct = (consumed / obj.received_qty * 100) if obj.received_qty > 0 else 0

        html_parts = []
        html_parts.append('<div style="font-family: monospace; font-size: 0.9em;">')
        html_parts.append('📦 Получено: <strong>{:.3f}</strong><br>'.format(obj.received_qty))
        html_parts.append('✅ Налично: <strong style="color: green;">{:.3f}</strong><br>'.format(obj.remaining_qty))
        html_parts.append('📤 Използвано: {:.3f} ({:.1f}%)'.format(consumed, consumption_pct))
        html_parts.append('</div>')

        return mark_safe(''.join(html_parts))

    quantities_display.short_description = _('Received/Remaining/Used')

    def expiry_status(self, obj):
        """Статус на срока на годност"""
        if not obj.expiry_date:
            return mark_safe('<span style="color: gray;">Няма срок</span>')

        today = timezone.now().date()
        days_to_expiry = (obj.expiry_date - today).days

        if days_to_expiry < 0:
            return mark_safe(
                '<span style="background: #ffebee; color: #c62828; padding: 2px 6px; border-radius: 3px;">'
                '❌ Изтекъл (-{} дни)'
                '</span>'.format(abs(days_to_expiry))
            )
        elif days_to_expiry <= 7:
            return mark_safe(
                '<span style="background: #fff3e0; color: #ef6c00; padding: 2px 6px; border-radius: 3px;">'
                '⚠️ {} дни'
                '</span>'.format(days_to_expiry)
            )
        elif days_to_expiry <= 30:
            return mark_safe(
                '<span style="background: #fff8e1; color: #f57c00; padding: 2px 6px; border-radius: 3px;">'
                '📅 {} дни'
                '</span>'.format(days_to_expiry)
            )
        else:
            return mark_safe(
                '<span style="background: #e8f5e8; color: #2e7d32; padding: 2px 6px; border-radius: 3px;">'
                '✅ {} дни'
                '</span>'.format(days_to_expiry)
            )

    expiry_status.short_description = _('Expiry Status')

    def batch_analytics(self, obj):
        """Аналитика за партидата"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        consumed = obj.received_qty - obj.remaining_qty
        consumption_pct = (consumed / obj.received_qty * 100) if obj.received_qty > 0 else 0

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">')
        html_parts.append('📊 <strong>Аналитика партида {}</strong><br><br>'.format(obj.batch_number))

        # Количествена информация
        html_parts.append('Получено количество: <strong>{:.3f}</strong><br>'.format(obj.received_qty))
        html_parts.append('Оставащо количество: <strong>{:.3f}</strong><br>'.format(obj.remaining_qty))
        html_parts.append('Използвано: <strong>{:.3f}</strong> ({:.1f}%)<br><br>'.format(consumed, consumption_pct))

        # Стойност
        if obj.cost_price > 0:
            total_value = obj.remaining_qty * obj.cost_price
            html_parts.append('Цена за единица: <strong>{:.4f} лв</strong><br>'.format(obj.cost_price))
            html_parts.append('Стойност на останалото: <strong>{:.2f} лв</strong><br><br>'.format(total_value))

        # Срок на годност
        if obj.expiry_date:
            today = timezone.now().date()
            days_to_expiry = (obj.expiry_date - today).days

            if days_to_expiry < 0:
                html_parts.append(
                    '⚠️ <strong style="color: red;">Изтекъл преди {} дни!</strong><br>'.format(abs(days_to_expiry)))
            elif days_to_expiry <= 30:
                html_parts.append(
                    '⏰ <strong style="color: orange;">Изтича след {} дни</strong><br>'.format(days_to_expiry))
            else:
                html_parts.append('✅ Срок: <strong>{} дни</strong><br>'.format(days_to_expiry))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    batch_analytics.short_description = _('Batch Analytics')

    def conversion_info(self, obj):
        """Информация за конверсия"""
        if not obj.conversion_date:
            return 'Няма информация за конверсия'

        html_parts = ['🔄 Конвертирано на: <strong>{}</strong><br>'.format(obj.conversion_date)]
        if obj.original_source:
            html_parts.append('Източник: {}'.format(obj.original_source))

        return mark_safe(''.join(html_parts))

    conversion_info.short_description = _('Conversion Info')

    def consumption_rate(self, obj):
        """Скорост на потребление"""
        if not obj.received_date or obj.remaining_qty == obj.received_qty:
            return 'Няма потребление'

        days_since_received = (timezone.now().date() - obj.received_date.date()).days
        if days_since_received == 0:
            return 'Получено днес'

        consumed = obj.received_qty - obj.remaining_qty
        daily_rate = consumed / days_since_received

        if obj.remaining_qty > 0 and daily_rate > 0:
            days_remaining = obj.remaining_qty / daily_rate
            html_parts = []
            html_parts.append('📈 Дневно потребление: <strong>{:.3f}</strong><br>'.format(daily_rate))
            html_parts.append('🗓️ Очаквано изчерпване: <strong>{:.0f} дни</strong>'.format(days_remaining))

            # Предупреждение ако ще се изчерпи преди срока на годност
            if obj.expiry_date:
                days_to_expiry = (obj.expiry_date - timezone.now().date()).days
                if days_remaining > days_to_expiry:
                    html_parts.append('<br><span style="color: red;">⚠️ Ще изтече преди да се изчерпи!</span>')

            return mark_safe(''.join(html_parts))

        return 'Потребено: {:.3f} за {} дни'.format(consumed, days_since_received)

    consumption_rate.short_description = _('Consumption Rate')


# =================================================================
# INVENTORY MOVEMENT ADMIN
# =================================================================

@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    """Админ за inventory movements - само четене"""

    list_display = [
        'movement_info', 'product_info', 'location', 'quantity_display',
        'cost_price', 'document_info', 'movement_date', 'created_by'
    ]

    list_filter = [
        'movement_type', 'location',
        ('movement_date', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
        'created_by',
    ]

    search_fields = [
        'product__code', 'product__name', 'location__code',
        'batch_number', 'source_document_number', 'reason'
    ]

    readonly_fields = [
        'movement_type', 'quantity', 'cost_price', 'product', 'location',
        'from_location', 'to_location', 'batch_number', 'expiry_date',
        'serial_number', 'source_document_type', 'source_document_number',
        'source_document_line_id', 'movement_date', 'reason',
        'created_at', 'created_by', 'movement_analysis'
    ]

    ordering = ['-created_at']

    date_hierarchy = 'movement_date'

    fieldsets = (
        (_('Movement Details'), {
            'fields': (
                'movement_type', 'product', 'location', 'from_location', 'to_location'
            )
        }),
        (_('Quantities & Cost'), {
            'fields': ('quantity', 'cost_price')
        }),
        (_('Batch Information'), {
            'fields': ('batch_number', 'expiry_date', 'serial_number'),
            'classes': ('collapse',)
        }),
        (_('Source Document'), {
            'fields': (
                'source_document_type', 'source_document_number',
                'source_document_line_id'
            ),
            'classes': ('collapse',)
        }),
        (_('Additional Info'), {
            'fields': ('movement_date', 'reason')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'created_by', 'movement_analysis'),
            'classes': ('collapse',)
        })
    )

    def has_add_permission(self, request):
        """Забрана за добавяне - движенията се създават автоматично"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Забрана за изтриване - движенията са audit trail"""
        return False

    def movement_info(self, obj):
        """Информация за движението"""
        direction_icons = {
            'IN': '➡️',
            'OUT': '⬅️',
            'TRANSFER': '🔄',
            'ADJUSTMENT': '⚖️',
            'PRODUCTION': '🏭',
            'CYCLE_COUNT': '📋'
        }

        icon = direction_icons.get(obj.movement_type, '❓')
        type_display = obj.get_movement_type_display()

        return mark_safe(
            '<span style="font-size: 1.2em;">{}</span><br><span style="font-size: 0.9em;">{}</span>'.format(icon,
                                                                                                            type_display)
        )

    movement_info.short_description = _('Type')

    def product_info(self, obj):
        """Информация за продукта"""
        html_parts = []
        html_parts.append('<strong>{}</strong><br>'.format(obj.product.code))
        html_parts.append('<span style="font-size: 0.9em;">{}</span>'.format(obj.product.name[:40]))

        if obj.batch_number:
            html_parts.append('<br><span style="font-size: 0.8em; color: blue;">🏷️ {}</span>'.format(obj.batch_number))

        return mark_safe(''.join(html_parts))

    product_info.short_description = _('Product')

    def quantity_display(self, obj):
        """Показване на количеството - като отделен метод"""
        return mark_safe(
            '<strong style="font-size: 1.1em; font-family: monospace;">{:.3f}</strong>'.format(obj.quantity)
        )

    quantity_display.short_description = _('Quantity')

    def document_info(self, obj):
        """Информация за документа източник"""
        if not obj.source_document_type:
            return mark_safe('<span style="color: gray;">Няма</span>')

        html_parts = ['<strong>{}</strong><br>'.format(obj.source_document_type)]

        if obj.source_document_number:
            html_parts.append('<span style="font-size: 0.9em;">{}</span>'.format(obj.source_document_number))

        if obj.source_document_line_id:
            html_parts.append(
                '<br><span style="font-size: 0.8em; color: gray;">Ред #{}</span>'.format(obj.source_document_line_id))

        return mark_safe(''.join(html_parts))

    document_info.short_description = _('Source Document')

    def movement_analysis(self, obj):
        """Анализ на движението"""
        if not obj.pk:
            return 'Не е налично за нови записи'

        html_parts = []
        html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">')
        html_parts.append('📊 <strong>Анализ движение #{}</strong><br><br>'.format(obj.id))

        # Основна информация
        direction = "Входящо" if obj.is_incoming else "Изходящо"
        html_parts.append('Направление: <strong>{}</strong><br>'.format(direction))
        html_parts.append('Тип: <strong>{}</strong><br>'.format(obj.get_movement_type_display()))
        html_parts.append('Продукт: <strong>{} - {}</strong><br>'.format(obj.product.code, obj.product.name))
        html_parts.append('Количество: <strong>{:.3f}</strong><br>'.format(obj.quantity))
        html_parts.append('Единична цена: <strong>{:.4f} лв</strong><br>'.format(obj.cost_price))

        # Обща стойност
        total_value = obj.quantity * obj.cost_price
        html_parts.append('Обща стойност: <strong>{:.2f} лв</strong><br><br>'.format(total_value))

        # Локации
        html_parts.append('Локация: <strong>{} - {}</strong><br>'.format(obj.location.code, obj.location.name))
        if obj.from_location:
            html_parts.append('От локация: <strong>{}</strong><br>'.format(obj.from_location.code))
        if obj.to_location:
            html_parts.append('До локация: <strong>{}</strong><br>'.format(obj.to_location.code))

        # Времеви данни
        html_parts.append('<br>Дата движение: <strong>{}</strong><br>'.format(obj.movement_date))
        html_parts.append('Създадено: <strong>{}</strong><br>'.format(obj.created_at.strftime("%d.%m.%Y %H:%M")))

        if obj.created_by:
            html_parts.append('Създадено от: <strong>{}</strong><br>'.format(obj.created_by.username))

        # Допълнителна информация
        if obj.reason:
            html_parts.append('<br>Причина: <em>{}</em><br>'.format(obj.reason))

        html_parts.append('</div>')
        return mark_safe(''.join(html_parts))

    movement_analysis.short_description = _('Movement Analysis')


# =================================================================
# ADMIN ACTIONS
# =================================================================

def recalculate_inventory_items(modeladmin, request, queryset):
    """Преизчисляване на inventory items"""
    count = 0
    for item in queryset:
        try:
            # Тук би трябвало да има service метод за преизчисляване
            # За момента само се записва обекта за trigger на update
            item.save()
            count += 1
        except Exception as e:
            messages.error(request, f'Грешка при {item}: {e}')

    messages.success(request, f'Преизчислени {count} записа')


recalculate_inventory_items.short_description = "Преизчисли избраните inventory items"


def export_stock_report(modeladmin, request, queryset):
    """Експорт на складова справка"""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stock_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Location', 'Product Code', 'Product Name', 'Current Qty',
        'Reserved Qty', 'Available Qty', 'Avg Cost', 'Stock Value'
    ])

    for item in queryset:
        available = item.current_qty - item.reserved_qty
        stock_value = item.current_qty * item.avg_cost

        writer.writerow([
            item.location.code,
            item.product.code,
            item.product.name,
            item.current_qty,
            item.reserved_qty,
            available,
            item.avg_cost,
            stock_value
        ])

    return response


export_stock_report.short_description = "Експорт на складова справка"

# Добавяне на actions към admin класовете
InventoryItemAdmin.actions = [recalculate_inventory_items, export_stock_report]