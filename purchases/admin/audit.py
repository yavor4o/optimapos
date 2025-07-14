# purchases/admin/audit.py - FIXED VERSION

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from ..models import PurchaseAuditLog


@admin.register(PurchaseAuditLog)
class PurchaseAuditLogAdmin(admin.ModelAdmin):
    """Admin for PurchaseAuditLog - read only"""

    list_display = [
        'timestamp', 'document_link', 'action_badge', 'user_display',
        'change_summary'
    ]

    list_filter = [
        'action', 'timestamp', 'document__supplier', 'document__status'
    ]

    search_fields = [
        'document__document_number', 'user__username', 'user__first_name',
        'user__last_name', 'notes'
    ]

    date_hierarchy = 'timestamp'

    ordering = ['-timestamp']

    # FIXED: Use only fields that exist in the new model
    readonly_fields = [
        'document', 'action', 'timestamp', 'user',
        'old_status', 'new_status', 'old_workflow_status', 'new_workflow_status',
        'notes', 'ip_address', 'additional_data'
    ]

    fieldsets = (
        (_('Audit Information'), {
            'fields': ('document', 'action', 'timestamp', 'user')
        }),
        (_('Status Changes'), {
            'fields': ('old_status', 'new_status', 'old_workflow_status', 'new_workflow_status')
        }),
        (_('Additional Information'), {
            'fields': ('notes', 'ip_address', 'additional_data')
        })
    )

    # Disable all modifications
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Custom display methods
    def document_link(self, obj):
        """Link to document"""
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
        """Colored badge for action"""
        colors = {
            'created': '#28A745',
            'submitted': '#17A2B8',
            'approved': '#0D6EFD',
            'rejected': '#DC3545',
            'converted': '#FFC107',
            'sent': '#6F42C1',
            'confirmed': '#198754',
            'received': '#20C997',
            'cancelled': '#DC3545',
            'modified': '#6C757D',
            'status_changed': '#FD7E14',
            'payment_updated': '#E83E8C',
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
        """User with additional information"""
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
        """Summary of changes"""
        summary_parts = []

        # Status changes
        if obj.old_status and obj.new_status and obj.old_status != obj.new_status:
            summary_parts.append(f"Status: {obj.old_status} → {obj.new_status}")

        # Workflow status changes
        if (obj.old_workflow_status and obj.new_workflow_status and
                obj.old_workflow_status != obj.new_workflow_status):
            summary_parts.append(f"Workflow: {obj.old_workflow_status} → {obj.new_workflow_status}")

        # Notes
        if obj.notes:
            notes_preview = obj.notes[:100] + ('...' if len(obj.notes) > 100 else '')
            summary_parts.append(f"Notes: {notes_preview}")

        # Additional data preview
        if obj.additional_data:
            summary_parts.append("Additional data available")

        return format_html('<br>'.join(summary_parts)) if summary_parts else "-"

    change_summary.short_description = _('Change Summary')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'document__supplier', 'user'
        )