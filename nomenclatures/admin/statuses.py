# nomenclatures/admin/statuses.py - ФИКСИРАН И РАЗШИРЕН
"""
Statuses Admin - DocumentStatus & DocumentTypeStatus

ФИКСИРАНО:
- Пълен DocumentStatusAdmin
- Подобрен DocumentTypeStatusInline
- Smart display methods и filtering
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from django.utils.safestring import mark_safe

from ..models import DocumentStatus, DocumentTypeStatus


# =================================================================
# DOCUMENT STATUS ADMIN - НОВА ВЕРСИЯ
# =================================================================

@admin.register(DocumentStatus)
class DocumentStatusAdmin(admin.ModelAdmin):
    """FIXED: Пълен админ за DocumentStatus"""

    list_display = [
        'name',
        'code',
        'color_display',
        'icon_display',
        'permissions_display',
        'usage_count',
        'is_system',
        'is_active'
    ]

    list_filter = [
        'is_active',
        'is_system',
        'allow_edit',
        'allow_delete'
    ]

    search_fields = [
        'name',
        'code',
        'description'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'usage_statistics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code',
                'name',
                'description',
                'is_active',
                'sort_order'
            )
        }),
        (_('Visual Settings'), {
            'fields': (
                'color',
                'icon',
                'badge_class'
            )
        }),
        (_('Permissions'), {
            'fields': (
                'allow_edit',
                'allow_delete'
            )
        }),
        (_('System'), {
            'fields': (
                'is_system',
            )
        }),
        (_('Audit'), {
            'fields': (
                'created_at',
                'updated_at',
                'usage_statistics'
            ),
            'classes': ('collapse',)
        }),
    )

    # Display methods
    def color_display(self, obj):
        """Показва цвета като preview"""
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc; border-radius: 3px; display: inline-block; margin-right: 5px;"></div>{}',
            obj.color,
            obj.color
        )

    color_display.short_description = _('Color')

    def icon_display(self, obj):
        """Показва иконата"""
        if obj.icon:
            return format_html(
                '<i class="{}" style="font-size: 16px;"></i> {}',
                obj.icon,
                obj.icon
            )
        return '-'

    icon_display.short_description = _('Icon')

    def permissions_display(self, obj):
        """Показва permissions като badges"""
        badges = []
        if obj.allow_edit:
            badges.append('<span class="badge badge-success">Edit</span>')
        if obj.allow_delete:
            badges.append('<span class="badge badge-danger">Delete</span>')

        if badges:
            return format_html(' '.join(badges))
        return format_html('<span class="badge badge-secondary">Read Only</span>')

    permissions_display.short_description = _('Permissions')

    def usage_count(self, obj):
        """Показва в колко document types се използва"""
        count = obj.type_configurations.count()
        return format_html(
            '<span title="Used in {} document types">{}</span>',
            count,
            count
        )

    usage_count.short_description = _('Usage')

    def usage_statistics(self, obj):
        """Подробна статистика за използване"""
        if obj.pk:
            document_types = obj.type_configurations.select_related('document_type').all()
            if document_types:
                html = '<strong>Used in Document Types:</strong><ul>'
                for config in document_types:
                    flags = []
                    if config.is_initial:
                        flags.append('Initial')
                    if config.is_final:
                        flags.append('Final')
                    if config.is_cancellation:
                        flags.append('Cancellation')

                    flag_str = f" ({', '.join(flags)})" if flags else ""
                    html += f'<li>{config.document_type.name}{flag_str}</li>'
                html += '</ul>'
                return format_html(html)
            else:
                return 'Not used yet'
        return 'New status'

    usage_statistics.short_description = _('Usage Details')

    # Actions
    actions = ['activate_statuses', 'deactivate_statuses', 'duplicate_statuses']

    def activate_statuses(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'Activated {count} statuses.')

    activate_statuses.short_description = _('Activate selected statuses')

    def deactivate_statuses(self, request, queryset):
        # Не деактивирай system статуси
        system_count = queryset.filter(is_system=True).count()
        if system_count:
            self.message_user(request, f'Cannot deactivate {system_count} system statuses.', level='warning')

        count = queryset.filter(is_system=False).update(is_active=False)
        self.message_user(request, f'Deactivated {count} statuses.')

    deactivate_statuses.short_description = _('Deactivate selected statuses')

    def duplicate_statuses(self, request, queryset):
        count = 0
        for status in queryset:
            if not status.is_system:  # Не дублирай system статуси
                status.pk = None
                status.code = f"{status.code}_COPY"
                status.name = f"{status.name} (Copy)"
                status.is_system = False
                status.save()
                count += 1

        self.message_user(request, f'Duplicated {count} statuses.')

    duplicate_statuses.short_description = _('Duplicate selected statuses')


# =================================================================
# DOCUMENT TYPE STATUS INLINE - ПОДОБРЕНА ВЕРСИЯ
# =================================================================

class DocumentTypeStatusInline(admin.TabularInline):
    """FIXED: Подобрена inline за конфигуриране на статуси"""
    model = DocumentTypeStatus
    extra = 1
    min_num = 1  # Поне един статус е нужен

    fields = [
        'status',
        'custom_name',
        'is_initial',
        'is_final',
        'is_cancellation',
        'sort_order',
        'is_active'
    ]

    autocomplete_fields = ['status']

    def get_queryset(self, request):
        """Подреди по sort_order"""
        qs = super().get_queryset(request)
        return qs.select_related('status').order_by('sort_order', 'status__name')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Филтрирай статусите - показвай само активни"""
        if db_field.name == "status":
            kwargs["queryset"] = DocumentStatus.objects.filter(is_active=True).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# =================================================================
# DOCUMENT TYPE STATUS ADMIN (за директно редактиране)
# =================================================================

@admin.register(DocumentTypeStatus)
class DocumentTypeStatusAdmin(admin.ModelAdmin):
    """Admin за DocumentTypeStatus за advanced конфигурация"""

    list_display = [
        'document_type',
        'status_display',
        'custom_name',
        'flags_display',
        'sort_order',
        'is_active'
    ]

    list_filter = [
        'document_type',
        'is_initial',
        'is_final',
        'is_cancellation',
        'is_active'
    ]

    search_fields = [
        'document_type__name',
        'status__name',
        'status__code',
        'custom_name'
    ]

    ordering = ['document_type', 'sort_order']

    autocomplete_fields = ['document_type', 'status']

    # Display methods
    def status_display(self, obj):
        """Показва статуса със визуален стил"""
        return format_html(
            '<div style="display: flex; align-items: center;">'
            '<div style="width: 12px; height: 12px; background-color: {}; border-radius: 50%; margin-right: 8px;"></div>'
            '<span>{}</span>'
            '</div>',
            obj.status.color,
            obj.status.name
        )

    status_display.short_description = _('Status')

    def flags_display(self, obj):
        """Показва флаговете като badges"""
        badges = []
        if obj.is_initial:
            badges.append(
                '<span style="background: #4CAF50; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">INITIAL</span>')
        if obj.is_final:
            badges.append(
                '<span style="background: #F44336; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">FINAL</span>')
        if obj.is_cancellation:
            badges.append(
                '<span style="background: #FF9800; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">CANCEL</span>')

        return format_html(' '.join(badges)) if badges else '-'

    flags_display.short_description = _('Flags')

    # Actions
    actions = ['mark_as_initial', 'mark_as_final', 'mark_as_cancellation']

    def mark_as_initial(self, request, queryset):
        """Маркирай като initial статус"""
        for config in queryset:
            # Премахни initial от другите статуси за същия document type
            DocumentTypeStatus.objects.filter(
                document_type=config.document_type
            ).update(is_initial=False)
            # Задай този като initial
            config.is_initial = True
            config.save()

        self.message_user(request, f'Marked {queryset.count()} configurations as initial.')

    mark_as_initial.short_description = _('Mark as initial status')

    def mark_as_final(self, request, queryset):
        count = queryset.update(is_final=True)
        self.message_user(request, f'Marked {count} configurations as final.')

    mark_as_final.short_description = _('Mark as final status')

    def mark_as_cancellation(self, request, queryset):
        count = queryset.update(is_cancellation=True)
        self.message_user(request, f'Marked {count} configurations as cancellation.')

    mark_as_cancellation.short_description = _('Mark as cancellation status')