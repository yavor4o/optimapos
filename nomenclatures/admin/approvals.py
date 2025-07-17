# nomenclatures/admin/approvals.py - ПОПРАВЕНА ВЕРСИЯ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q

from nomenclatures.models import ApprovalRule, ApprovalLog


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    """Admin interface for Approval Rules - ПОПРАВЕНА ВЕРСИЯ"""

    list_display = [
        'name', 'document_type_display', 'status_transition_display',
        'approval_level', 'amount_range_display', 'approver_display',
        'is_active_display'
    ]

    list_filter = [
        'is_active', 'document_type', 'approval_level', 'approver_type',
        'requires_previous_level', 'is_parallel'
    ]

    search_fields = [
        'name', 'description', 'from_status', 'to_status'
    ]

    ordering = ['document_type', 'approval_level', 'sort_order']

    fieldsets = [
        (_('Basic Information'), {
            'fields': [
                'name', 'description', 'is_active', 'sort_order'
            ]
        }),
        (_('Document Scope'), {
            'fields': [
                'document_type', 'content_type'
            ],
            'description': _('Define which documents this rule applies to')
        }),
        (_('Workflow Transition'), {
            'fields': [
                'from_status', 'to_status', 'approval_level'
            ]
        }),
        (_('Financial Limits'), {
            'fields': [
                'min_amount', 'max_amount', 'currency'
            ],
            'classes': ['collapse']
        }),
        (_('Approver Configuration'), {
            'fields': [
                'approver_type', 'approver_user', 'approver_role', 'approver_permission'
            ]
        }),
        (_('Workflow Control'), {
            'fields': [
                'is_parallel', 'requires_previous_level',
                'rejection_allowed', 'escalation_days'
            ],
            'classes': ['collapse']
        }),
        (_('Automation & Notifications'), {
            'fields': [
                'auto_approve_conditions', 'notify_approver', 'notify_requester'
            ],
            'classes': ['collapse']
        }),
    ]

    def document_type_display(self, obj):
        """Display document type with icon - ПОПРАВЕНА БЕЗ DESCRIPTION"""
        if obj.document_type:
            # DocumentType няма description поле - използваме само name
            return format_html(
                '<span title="Document Type: {}">{}</span>',
                obj.document_type.name,
                obj.document_type.name
            )
        elif obj.content_type:
            return format_html(
                '<em title="Fallback Content Type">{}</em>',
                obj.content_type.name
            )
        return '-'

    document_type_display.short_description = _('Document Type')

    def status_transition_display(self, obj):
        """Display status transition with arrow"""
        return format_html(
            '<span style="font-family: monospace; background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">{} → {}</span>',
            obj.from_status,
            obj.to_status
        )

    status_transition_display.short_description = _('Transition')

    def amount_range_display(self, obj):
        """Display amount range"""
        if obj.max_amount:
            return format_html(
                '<span style="font-family: monospace;">{} - {} {}</span>',
                obj.min_amount,
                obj.max_amount,
                obj.currency
            )
        else:
            return format_html(
                '<span style="font-family: monospace;">From {} {}</span>',
                obj.min_amount,
                obj.currency
            )

    amount_range_display.short_description = _('Amount Range')

    def approver_display(self, obj):
        """Display approver information"""
        # Определяме approver-а според типа
        if obj.approver_type == 'user' and obj.approver_user:
            display = obj.approver_user.get_full_name() or obj.approver_user.username
        elif obj.approver_type == 'role' and obj.approver_role:
            display = obj.approver_role.name
        elif obj.approver_type == 'permission' and obj.approver_permission:
            display = obj.approver_permission.name
        else:
            display = 'Dynamic'

        # Color code by type
        colors = {
            'user': '#007cba',
            'role': '#28a745',
            'permission': '#ffc107',
            'dynamic': '#6f42c1'
        }
        color = colors.get(obj.approver_type, '#6c757d')

        return format_html(
            '<span style="color: {}; font-weight: bold;" title="Type: {}">{}</span>',
            color,
            obj.get_approver_type_display(),
            display
        )

    approver_display.short_description = _('Approver')

    def is_active_display(self, obj):
        """Display active status with icon"""
        if obj.is_active:
            return format_html('<span style="color: green;">✅ Active</span>')
        else:
            return format_html('<span style="color: red;">❌ Inactive</span>')

    is_active_display.short_description = _('Status')

    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly after creation"""
        readonly = ['created_at', 'updated_at']

        if obj:  # Editing existing object
            readonly.extend(['document_type', 'content_type'])

        return readonly

    def save_model(self, request, obj, form, change):
        """Set created_by when creating new rule"""
        if not change:  # New object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    """Admin interface for Approval Logs (read-only)"""

    list_display = [
        'timestamp', 'actor', 'action_display', 'document_info',
        'status_transition', 'rule_info'
    ]

    list_filter = [
        'action', 'timestamp', 'content_type'
    ]

    search_fields = [
        'actor__first_name', 'actor__last_name', 'actor__username',
        'comments', 'object_id'
    ]

    ordering = ['-timestamp']

    readonly_fields = [
        'content_type', 'object_id', 'rule', 'action', 'from_status',
        'to_status', 'actor', 'comments', 'timestamp', 'ip_address', 'user_agent'
    ]

    def has_add_permission(self, request):
        """Prevent manual creation of logs"""
        return False

    def has_change_permission(self, request, obj=None):
        """Allow viewing but not editing"""
        return True

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs"""
        return False

    def action_display(self, obj):
        """Display action with color coding"""
        colors = {
            'submitted': '#6c757d',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'escalated': '#ffc107',
            'auto_approved': '#17a2b8'
        }
        color = colors.get(obj.action, '#6c757d')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )

    action_display.short_description = _('Action')

    def document_info(self, obj):
        """Display document information"""
        return format_html(
            '{} (ID: {})',
            obj.content_type.name,
            obj.object_id
        )

    document_info.short_description = _('Document')

    def status_transition(self, obj):
        """Display status transition"""
        return format_html(
            '<span style="font-family: monospace; background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">{} → {}</span>',
            obj.from_status,
            obj.to_status
        )

    status_transition.short_description = _('Transition')

    def rule_info(self, obj):
        """Display rule information"""
        if obj.rule:
            return format_html(
                '<span title="{}">{}</span>',
                obj.rule.description or 'No description',
                obj.rule.name
            )
        return '-'

    rule_info.short_description = _('Applied Rule')


# Custom admin actions
@admin.action(description=_('Activate selected approval rules'))
def activate_rules(modeladmin, request, queryset):
    """Activate selected approval rules"""
    updated = queryset.update(is_active=True)
    modeladmin.message_user(
        request,
        _('Successfully activated {} approval rules.').format(updated)
    )


@admin.action(description=_('Deactivate selected approval rules'))
def deactivate_rules(modeladmin, request, queryset):
    """Deactivate selected approval rules"""
    updated = queryset.update(is_active=False)
    modeladmin.message_user(
        request,
        _('Successfully deactivated {} approval rules.').format(updated)
    )


@admin.action(description=_('Duplicate selected approval rules'))
def duplicate_rules(modeladmin, request, queryset):
    """Create copies of selected approval rules"""
    count = 0
    for rule in queryset:
        # Create copy
        rule.pk = None
        rule.name = f"{rule.name} (Copy)"
        rule.is_active = False  # Start as inactive
        rule.created_by = request.user
        rule.save()
        count += 1

    modeladmin.message_user(
        request,
        _('Successfully created {} rule copies.').format(count)
    )


# Add actions to admin
ApprovalRuleAdmin.actions = [activate_rules, deactivate_rules, duplicate_rules]