# purchases/admin/audit.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from ..models import PurchaseAuditLog


@admin.register(PurchaseAuditLog)
class PurchaseAuditLogAdmin(admin.ModelAdmin):
    """Admin за PurchaseAuditLog - само за четене"""

    list_display = [
        'timestamp', 'document_link', 'action_badge', 'user_display',
        'field_name', 'change_summary'
    ]

    list_filter = [
        'action', 'timestamp', 'document__supplier', 'document__status'
    ]

    search_fields = [
        'document__document_number', 'user__username', 'user__first_name',
        'user__last_name', 'field_name', 'notes'
    ]

    date_hierarchy = 'timestamp'

    ordering = ['-timestamp']

    # Само за четене
    readonly_fields = [
        'document', 'action', 'timestamp', 'user', 'field_name',
        'old_value', 'new_value', 'notes'
    ]

    fieldsets = (
        (_('Audit Information'), {
            'fields': ('document', 'action', 'timestamp', 'user')
        }),
        (_('Change Details'), {
            'fields': ('field_name', 'old_value', 'new_value')
        }),
        (_('Additional Notes'), {
            'fields': ('notes',)
        })
    )

    # Забраняваме всякакви промени
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Custom display methods
    def document_link(self, obj):
        """Линк към документа"""
        if obj.document:
            url = f"/admin/purchases/purchasedocument/{obj.document.id}/change/"
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url, obj.document.document_number
            )
        return "-"

    document_link.short_description = _('Document')
    document_link.admin_order_field = 'document__document_number'

    def action_badge(self, obj):
        """Цветен badge за action"""
        colors = {
            'create': '#28A745',
            'update': '#17A2B8',
            'confirm': '#0D6EFD',
            'receive': '#198754',
            'cancel': '#DC3545',
            'price_update': '#FFC107',
        }

        color = colors.get(obj.action, '#6C757D')
        display = obj.get_action_display()

        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: bold;">{}</span>',
            color, display
        )

    action_badge.short_description = _('Action')

    def user_display(self, obj):
        """Потребител с допълнителна информация"""
        if obj.user:
            full_name = obj.user.get_full_name()
            if full_name:
                return format_html(
                    '<strong>{}</strong><br><small>{}</small>',
                    full_name, obj.user.username
                )
            else:
                return obj.user.username
        return "-"

    user_display.short_description = _('User')

    def change_summary(self, obj):
        """Резюме на промяната"""
        if obj.field_name and obj.old_value and obj.new_value:
            return format_html(
                '<strong>{}:</strong><br>'
                '<small style="color: #DC3545;">From:</small> {}<br>'
                '<small style="color: #198754;">To:</small> {}',
                obj.field_name,
                obj.old_value[:50] + ('...' if len(obj.old_value) > 50 else ''),
                obj.new_value[:50] + ('...' if len(obj.new_value) > 50 else '')
            )
        elif obj.notes:
            return obj.notes[:100] + ('...' if len(obj.notes) > 100 else '')
        else:
            return "-"

    change_summary.short_description = _('Change Summary')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'document__supplier', 'user'
        )