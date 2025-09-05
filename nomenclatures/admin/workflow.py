# nomenclatures/admin/workflow.py - ЛИПСВАЩ ФАЙЛ
"""
Workflow Admin - ApprovalRule & ApprovalLog

ИНТЕГРИРА:
- ApprovalRule с новите ForeignKey полета
- ApprovalLog за audit trail
- Smart filtering и display methods
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils.safestring import mark_safe

# Conditional import for models
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_APPROVAL_MODELS = True
except ImportError:
    ApprovalRule = None
    ApprovalLog = None
    HAS_APPROVAL_MODELS = False

if HAS_APPROVAL_MODELS:

    # =================================================================
    # APPROVAL RULE ADMIN - FIXED FOR NEW FIELDS
    # =================================================================

    @admin.register(ApprovalRule)
    class ApprovalRuleAdmin(admin.ModelAdmin):
        """FIXED: Admin за ApprovalRule с ForeignKey полета"""

        list_display = [
            'name',
            'document_type',
            'from_status_display',  # FIXED: използва ForeignKey
            'to_status_display',  # FIXED: използва ForeignKey
            'semantic_type_display',  # ✅ NEW: Show semantic type with styling
            'approval_level',
            'approver_display',
            'amount_range_display',
            'is_active'
        ]

        list_filter = [
            'document_type',
            'semantic_type',  # ✅ NEW: Filter by semantic type
            'approval_level',
            'approver_type',
            'is_active',
            'requires_previous_level',
            'requires_reason'
        ]

        search_fields = [
            'name',
            'description',
            'document_type__name',
            'from_status_obj__name',  # FIXED: ForeignKey search
            'to_status_obj__name',  # FIXED: ForeignKey search
        ]

        readonly_fields = [
            'created_at',
            'updated_at',
            'usage_statistics'
        ]

        fieldsets = (
            (_('Basic Information'), {
                'fields': (
                    'name',
                    'description',
                    'document_type',
                    'is_active',
                    'sort_order'
                )
            }),
            (_('Status Transition'), {  # FIXED: Section за ForeignKey полета
                'fields': (
                    'from_status_obj',
                    'to_status_obj',
                    'semantic_type',  # ✅ NEW: Semantic type configuration
                )
            }),
            (_('Approval Hierarchy'), {
                'fields': (
                    'approval_level',
                    'requires_previous_level',
                )
            }),
            (_('Approver Configuration'), {
                'fields': (
                    'approver_type',
                    'approver_user',
                    'approver_role',
                    'approver_permission',
                )
            }),
            (_('Financial Limits'), {
                'fields': (
                    'min_amount',
                    'max_amount',
                    'currency',
                )
            }),
            (_('Workflow Behavior'), {
                'fields': (
                    'requires_reason',
                    'rejection_allowed',
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

        # FIXED: Display methods за ForeignKey полета
        def from_status_display(self, obj):
            """FIXED: Показва from_status със стил"""
            if obj.from_status_obj:
                return format_html(
                    '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
                    obj.from_status_obj.color,
                    obj.from_status_obj.name
                )
            return '-'

        from_status_display.short_description = _('From Status')

        def to_status_display(self, obj):
            """FIXED: Показва to_status със стил"""
            if obj.to_status_obj:
                return format_html(
                    '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
                    obj.to_status_obj.color,
                    obj.to_status_obj.name
                )
            return '-'

        to_status_display.short_description = _('To Status')

        def semantic_type_display(self, obj):
            """✅ NEW: Показва semantic type със стил и иконки"""
            semantic_styles = {
                'submit': {'color': '#2196F3', 'icon': '📤'},  # Blue
                'approve': {'color': '#4CAF50', 'icon': '✅'},  # Green
                'reject': {'color': '#F44336', 'icon': '❌'},   # Red
                'cancel': {'color': '#FF9800', 'icon': '🚫'},   # Orange
                'return_draft': {'color': '#9C27B0', 'icon': '↩️'},  # Purple
                'generic': {'color': '#757575', 'icon': '⚙️'}   # Grey
            }
            
            style = semantic_styles.get(obj.semantic_type, semantic_styles['generic'])
            label = obj.get_semantic_type_display()
            
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 15px; font-size: 11px; font-weight: bold;">'
                '{} {}'
                '</span>',
                style['color'],
                style['icon'],
                label
            )

        semantic_type_display.short_description = _('Semantic Type')

        def approver_display(self, obj):
            """Показва approver информация"""
            return obj.get_approver_display()

        approver_display.short_description = _('Approver')

        def amount_range_display(self, obj):
            """Показва amount range"""
            if obj.max_amount:
                return f"{obj.min_amount}-{obj.max_amount} {obj.currency}"
            else:
                return f"{obj.min_amount}+ {obj.currency}"

        amount_range_display.short_description = _('Amount Range')

        def usage_statistics(self, obj):
            """Показва статистики за използване"""
            if obj.pk:
                try:
                    logs_count = ApprovalLog.objects.filter(rule=obj).count()
                    return format_html(
                        '<div>'
                        '<strong>Usage:</strong> {} times<br>'
                        '</div>',
                        logs_count
                    )
                except:
                    return 'Statistics unavailable'
            return 'New rule'

        usage_statistics.short_description = _('Usage Statistics')

        # Actions
        actions = ['activate_rules', 'deactivate_rules', 'duplicate_rules']

        def activate_rules(self, request, queryset):
            count = queryset.update(is_active=True)
            self.message_user(request, f'Activated {count} rules.')

        activate_rules.short_description = _('Activate selected rules')

        def deactivate_rules(self, request, queryset):
            count = queryset.update(is_active=False)
            self.message_user(request, f'Deactivated {count} rules.')

        deactivate_rules.short_description = _('Deactivate selected rules')

        def duplicate_rules(self, request, queryset):
            """Duplicate selected rules for easy creation"""
            count = 0
            for rule in queryset:
                rule.pk = None
                rule.name = f"{rule.name} (Copy)"
                rule.save()
                count += 1
            self.message_user(request, f'Duplicated {count} rules.')

        duplicate_rules.short_description = _('Duplicate selected rules')


    # =================================================================
    # APPROVAL LOG ADMIN
    # =================================================================

    @admin.register(ApprovalLog)
    class ApprovalLogAdmin(admin.ModelAdmin):
        """Admin за ApprovalLog - audit trail"""

        list_display = [
            'timestamp',
            'document_display',
            'action_display',
            'from_status',
            'to_status',
            'actor_display',
            'rule_display'
        ]

        list_filter = [
            'action',
            'timestamp',
            'content_type',
            'rule__document_type',
            'rule__approval_level'
        ]

        search_fields = [
            'actor__username',
            'actor__first_name',
            'actor__last_name',
            'from_status',
            'to_status',
            'comments',
            'rule__name'
        ]

        readonly_fields = [
            'timestamp',
            'content_type',
            'object_id',
            'action',
            'from_status',
            'to_status',
            'rule',
            'actor',
            'comments',
            'ip_address',
            'user_agent'
        ]

        date_hierarchy = 'timestamp'

        ordering = ['-timestamp']

        # Disable add/edit/delete (logs are immutable)
        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

        # Display methods
        def document_display(self, obj):
            """Показва документа"""
            document = obj.document
            if document:
                return format_html(
                    '<a href="/admin/{}/{}/{}/change/" target="_blank">{}</a>',
                    document._meta.app_label,
                    document._meta.model_name,
                    document.pk,
                    getattr(document, 'document_number', f'{document.__class__.__name__} #{document.pk}')
                )
            return f'Deleted {obj.content_type.name} #{obj.object_id}'

        document_display.short_description = _('Document')

        def action_display(self, obj):
            """Показва action със стил"""
            color_map = {
                'submitted': '#2196F3',  # Blue
                'approved': '#4CAF50',  # Green
                'rejected': '#F44336',  # Red
                'escalated': '#FF9800',  # Orange
                'cancelled': '#757575'  # Grey
            }
            color = color_map.get(obj.action, '#757575')

            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
                color,
                obj.get_action_display()
            )

        action_display.short_description = _('Action')

        def actor_display(self, obj):
            """Показва actor информация"""
            return obj.get_actor_display()

        actor_display.short_description = _('Actor')

        def rule_display(self, obj):
            """Показва rule информация"""
            if obj.rule:
                return format_html(
                    '<span title="{}">{}</span>',
                    obj.rule.description or obj.rule.name,
                    obj.rule.name
                )
            return '-'

        rule_display.short_description = _('Rule')

else:
    # Dummy classes if models don't exist
    class ApprovalRuleAdmin:
        pass


    class ApprovalLogAdmin:
        pass