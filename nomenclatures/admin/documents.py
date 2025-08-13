# nomenclatures/admin/documents.py - ОБНОВЕН
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from ..models import DocumentType
from ..models.statuses import DocumentTypeStatus


class DocumentTypeStatusInline(admin.TabularInline):
    """Inline за конфигуриране на статуси"""
    model = DocumentTypeStatus
    extra = 1

    fields = [
        'status',
        'is_initial',
        'is_final',
        'is_cancellation',
        'sort_order',
        'custom_name',
        'is_active'
    ]

    autocomplete_fields = ['status']

    def get_queryset(self, request):
        """Подреди по sort_order"""
        qs = super().get_queryset(request)
        return qs.order_by('sort_order')


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'app_name',
        'type_key',
        'affects_inventory',
        'requires_approval',
        'allow_edit_completed',  # Добави това
        'is_fiscal',
        'configured_statuses_display',  # Добави това
        'is_active'
    ]

    list_filter = [
        'app_name',
        'affects_inventory',
        'requires_approval',
        'allow_edit_completed',  # Добави това
        'is_fiscal',
        'is_active'
    ]

    search_fields = ['name', 'type_key', 'app_name']
    ordering = ['app_name', 'name']

    # ДОБАВИ INLINE ЗА СТАТУСИТЕ
    inlines = [DocumentTypeStatusInline]

    # ДОБАВИ МЕТОД ЗА ПОКАЗВАНЕ НА СТАТУСИТЕ
    def configured_statuses_display(self, obj):
        """Показва конфигурираните статуси като badges"""
        statuses = obj.get_configured_statuses()
        if not statuses:
            return format_html('<span style="color: #999;">No statuses</span>')

        html = []
        for status in statuses[:5]:  # Покажи първите 5
            config = DocumentTypeStatus.objects.filter(
                document_type=obj,
                status=status
            ).first()

            # Стил за badge
            badge_style = f'background-color: {status.color}; color: white; padding: 2px 6px; border-radius: 3px; margin-right: 4px; font-size: 11px;'

            # Маркери за специални статуси
            markers = []
            if config:
                if config.is_initial:
                    markers.append('➤')  # Начален
                if config.is_final:
                    markers.append('✓')  # Финален
                if config.is_cancellation:
                    markers.append('✗')  # Cancellation

            marker_text = ' '.join(markers)
            status_name = config.custom_name if config and config.custom_name else status.name

            html.append(
                format_html(
                    '<span style="{}">{} {}</span>',
                    badge_style,
                    status_name,
                    marker_text
                )
            )

        if statuses.count() > 5:
            html.append(
                format_html(
                    '<span style="color: #999; font-size: 11px;">+{} more</span>',
                    statuses.count() - 5
                )
            )

        return format_html(''.join(html))

    configured_statuses_display.short_description = _('Statuses')