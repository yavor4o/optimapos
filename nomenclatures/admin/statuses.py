# nomenclatures/admin/statuses.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from ..models.statuses import DocumentStatus, DocumentTypeStatus


@admin.register(DocumentStatus)
class DocumentStatusAdmin(admin.ModelAdmin):
    """Admin for Document Statuses"""

    list_display = [
        'code',
        'name',
        'color_display',
        'allow_edit',
        'allow_delete',
        'is_system',
        'is_active',
        'sort_order'
    ]

    list_filter = [
        'is_active',
        'is_system',
        'allow_edit',
        'allow_delete',
    ]

    search_fields = [
        'code',
        'name',
        'description'
    ]

    list_editable = [
        'allow_edit',
        'allow_delete',
        'is_active',
        'sort_order'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'description')
        }),
        (_('Permissions'), {
            'fields': ('allow_edit', 'allow_delete')
        }),
        (_('UI Settings'), {
            'fields': ('color', 'icon', 'badge_class')
        }),
        (_('System'), {
            'fields': ('is_system', 'is_active', 'sort_order')
        }),
    )

    def color_display(self, obj):
        """Display color as badge"""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            obj.color,
            obj.code
        )

    color_display.short_description = _('Status Display')

    def get_readonly_fields(self, request, obj=None):
        """System statuses have readonly code"""
        if obj and obj.is_system:
            return ['code', 'is_system']
        return ['is_system']


class DocumentTypeStatusInline(admin.TabularInline):
    """Inline for DocumentType status configuration"""
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
        """Order by sort_order"""
        qs = super().get_queryset(request)
        return qs.order_by('sort_order')


