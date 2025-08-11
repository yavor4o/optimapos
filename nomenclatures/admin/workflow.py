# nomenclatures/admin/workflow.py
"""
Workflow Nomenclatures Admin Configuration

Админи за approval workflow:
- ApprovalRule - правила за одобрение
- ApprovalLog - лог на одобренията
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

# Try to import approval models
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_APPROVAL_MODELS = True
except ImportError:
    HAS_APPROVAL_MODELS = False


    # Create dummy classes to prevent errors
    class ApprovalRule:
        pass


    class ApprovalLog:
        pass

# =======================
# APPROVAL LOG INLINE
# =======================

if HAS_APPROVAL_MODELS:
    class ApprovalLogInline(admin.TabularInline):
        """Inline за лог записи в ApprovalRule админа"""
        model = ApprovalLog
        extra = 0
        readonly_fields = ['created_at', 'approved_by', 'action', 'comments']
        fields = ['document_type', 'document_id', 'action', 'approved_by', 'created_at']
        ordering = ['-created_at']

        def get_queryset(self, request):
            # Показва само последните 10 лога
            return super().get_queryset(request).order_by('-created_at')[:10]

# =======================
# APPROVAL RULE ADMIN
# =======================

if HAS_APPROVAL_MODELS:
    @admin.register(ApprovalRule)
    class ApprovalRuleAdmin(admin.ModelAdmin):
        list_display = [
            'code',
            'name',
            'document_type',
            'priority_display',
            'conditions_summary',
            'approvers_info',
            'usage_stats',
            'is_active'
        ]

        list_filter = [
            'document_type',
            'priority',
            'requires_all_approvers',
            'is_active'
        ]

        search_fields = ['code', 'name', 'document_type__name']
        ordering = ['priority', 'name']

        readonly_fields = ['created_at', 'updated_at', 'usage_statistics']

        fieldsets = (
            (_('Basic Information'), {
                'fields': ('code', 'name', 'description', 'document_type')
            }),
            (_('Rule Configuration'), {
                'fields': (
                    'priority',
                    'conditions',
                    'requires_all_approvers'
                )
            }),
            (_('Approvers'), {
                'fields': ('approver_users', 'approver_groups'),
                'description': _('Select users and/or groups who can approve under this rule')
            }),
            (_('Status'), {
                'fields': ('is_active',)
            }),
            (_('Audit'), {
                'fields': ('created_at', 'updated_at', 'usage_statistics'),
                'classes': ('collapse',)
            }),
        )

        filter_horizontal = ['approver_users', 'approver_groups']
        inlines = [ApprovalLogInline] if HAS_APPROVAL_MODELS else []

        def get_queryset(self, request):
            qs = super().get_queryset(request)
            return qs.annotate(
                log_count=Count('approval_logs', distinct=True),
                recent_log_count=Count(
                    'approval_logs',
                    filter=Q(approval_logs__created_at__gte=timezone.now() - timedelta(days=30)),
                    distinct=True
                )
            )

        def priority_display(self, obj):
            """Показва приоритета с цветно форматиране"""
            colors = {
                1: '#dc3545',  # red - highest priority
                2: '#fd7e14',  # orange
                3: '#ffc107',  # yellow
                4: '#28a745',  # green
                5: '#6c757d',  # grey - lowest priority
            }

            color = colors.get(obj.priority, '#6c757d')

            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 8px; '
                'border-radius: 3px; font-weight: bold;">{}</span>',
                color, obj.priority
            )

        priority_display.short_description = _('Priority')
        priority_display.admin_order_field = 'priority'

        def conditions_summary(self, obj):
            """Обобщение на условията"""
            if not obj.conditions:
                return format_html('<em>{}</em>', _('No conditions'))

            try:
                # Опитваме се да парсираме JSON условията
                import json
                conditions = json.loads(obj.conditions) if isinstance(obj.conditions, str) else obj.conditions

                if isinstance(conditions, dict):
                    summary = []

                    if 'amount_min' in conditions:
                        summary.append(f"Min: {conditions['amount_min']}")

                    if 'amount_max' in conditions:
                        summary.append(f"Max: {conditions['amount_max']}")

                    if 'user_groups' in conditions:
                        summary.append(f"Groups: {len(conditions['user_groups'])}")

                    if 'locations' in conditions:
                        summary.append(f"Locations: {len(conditions['locations'])}")

                    return format_html('<br>'.join(summary)) if summary else _('Complex conditions')

            except:
                pass

            return format_html('<em>{}</em>', _('Custom conditions'))

        conditions_summary.short_description = _('Conditions')

        def approvers_info(self, obj):
            """Информация за одобряващите"""
            users_count = obj.approver_users.count() if hasattr(obj, 'approver_users') else 0
            groups_count = obj.approver_groups.count() if hasattr(obj, 'approver_groups') else 0

            info = []

            if users_count > 0:
                info.append(f"{users_count} users")

            if groups_count > 0:
                info.append(f"{groups_count} groups")

            if not info:
                return format_html('<span style="color: #dc3545;">{}</span>', _('No approvers'))

            approval_type = _('ALL required') if obj.requires_all_approvers else _('ANY can approve')

            return format_html(
                '{}<br><small style="color: #6c757d;">{}</small>',
                ', '.join(info), approval_type
            )

        approvers_info.short_description = _('Approvers')

        def usage_stats(self, obj):
            """Статистика за използването"""
            log_count = getattr(obj, 'log_count', 0)
            recent_count = getattr(obj, 'recent_log_count', 0)

            if log_count == 0:
                return format_html('<span style="color: #6c757d;">{}</span>', _('Not used'))

            return format_html(
                '<strong>{}</strong> total<br>'
                '<small>{} this month</small>',
                log_count, recent_count
            )

        usage_stats.short_description = _('Usage')
        usage_stats.admin_order_field = 'log_count'

        def usage_statistics(self, obj):
            """Подробна статистика за използването"""
            if not obj.pk:
                return "Save the rule first to see statistics"

            try:
                total_logs = obj.approval_logs.count()
                approved = obj.approval_logs.filter(action='approved').count()
                rejected = obj.approval_logs.filter(action='rejected').count()

                stats = [
                    f"Total approvals: {total_logs}",
                    f"Approved: {approved}",
                    f"Rejected: {rejected}",
                ]

                if total_logs > 0:
                    approval_rate = (approved / total_logs) * 100
                    stats.append(f"Approval rate: {approval_rate:.1f}%")

                return format_html('<br>'.join(stats))

            except:
                return "Statistics not available"

        usage_statistics.short_description = _('Detailed Statistics')

# =======================
# APPROVAL LOG ADMIN
# =======================

if HAS_APPROVAL_MODELS:
    @admin.register(ApprovalLog)
    class ApprovalLogAdmin(admin.ModelAdmin):
        list_display = [
            'document_info',
            'action_badge',
            'approved_by',
            'approval_rule',
            'created_at',
            'processing_time'
        ]

        list_filter = [
            'action',
            'approval_rule',
            'document_type',
            ('created_at', admin.DateFieldListFilter),
            'approved_by'
        ]

        search_fields = [
            'document_id',
            'approved_by__username',
            'approved_by__first_name',
            'approved_by__last_name',
            'comments'
        ]

        ordering = ['-created_at']
        date_hierarchy = 'created_at'

        readonly_fields = [
            'document_type',
            'document_id',
            'approval_rule',
            'action',
            'approved_by',
            'created_at',
            'processing_time_detail'
        ]

        fieldsets = (
            (_('Document Information'), {
                'fields': ('document_type', 'document_id')
            }),
            (_('Approval Details'), {
                'fields': ('approval_rule', 'action', 'approved_by', 'created_at')
            }),
            (_('Comments'), {
                'fields': ('comments',)
            }),
            (_('Timing'), {
                'fields': ('processing_time_detail',),
                'classes': ('collapse',)
            }),
        )

        def has_add_permission(self, request):
            """Approval logs не се създават ръчно"""
            return False

        def has_change_permission(self, request, obj=None):
            """Approval logs не се редактират"""
            return False

        def document_info(self, obj):
            """Информация за документа"""
            return format_html(
                '<strong>{}</strong><br>'
                '<small>ID: {}</small>',
                obj.document_type.name if obj.document_type else 'Unknown',
                obj.document_id
            )

        document_info.short_description = _('Document')

        def action_badge(self, obj):
            """Badge за действието"""
            colors = {
                'approved': '#28a745',
                'rejected': '#dc3545',
                'pending': '#ffc107',
                'cancelled': '#6c757d'
            }

            color = colors.get(obj.action, '#6c757d')

            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 12px; font-weight: bold;">{}</span>',
                color, obj.action.upper()
            )

        action_badge.short_description = _('Action')
        action_badge.admin_order_field = 'action'

        def processing_time(self, obj):
            """Време за обработка (ако има информация)"""
            # Това може да се имплементира ако има created_at на документа
            return '-'

        processing_time.short_description = _('Processing Time')

        def processing_time_detail(self, obj):
            """Подробно време за обработка"""
            return "Processing time calculation not implemented yet"

        processing_time_detail.short_description = _('Processing Time Details')

        # =======================
        # CUSTOM ACTIONS
        # =======================

        actions = ['export_approval_report']

        @admin.action(description=_('Export approval report'))
        def export_approval_report(self, request, queryset):
            """Export approval data - placeholder"""
            self.message_user(
                request,
                _('Approval report export feature will be implemented.'),
                level='WARNING'
            )

# =======================
# CONDITIONAL REGISTRATION
# =======================

# Админите се регистрират само ако моделите съществуват
if not HAS_APPROVAL_MODELS:
    # Създаваме dummy класове за export
    class ApprovalRuleAdmin:
        pass


    class ApprovalLogAdmin:
        pass