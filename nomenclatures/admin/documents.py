# nomenclatures/admin/documents.py - ЪПДЕЙТНАТ С НОВИ ФУНКЦИИ
"""
Documents Admin - DocumentType with integrated status management

ЪПДЕЙТНАТО:
- Интеграция с DocumentTypeStatus inline
- Smart display methods
- Workflow visualization
- Status configuration helpers
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from django.utils.safestring import mark_safe

from ..models import DocumentType
from .statuses import DocumentTypeStatusInline


# =================================================================
# DOCUMENT TYPE ADMIN - ЪПДЕЙТНАТ
# =================================================================

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    """ЪПДЕЙТНАТ: DocumentType админ с статус интеграция"""

    list_display = [
        'name',
        'app_name',
        'type_key',
        'behavior_flags_display',  # NEW: Поведенчески флагове
        'configured_statuses_display',  # NEW: Конфигурирани статуси
        'workflow_info_display',  # NEW: Workflow информация
        'is_active'
    ]

    list_filter = [
        'app_name',
        'affects_inventory',
        'requires_approval',
        'allow_edit_completed',
        'is_fiscal',
        'is_active'
    ]

    search_fields = [
        'name',
        'type_key',
        'code',
        'description'
    ]

    ordering = ['app_name', 'sort_order', 'name']

    readonly_fields = [
        'created_at',
        'updated_at',
        'workflow_summary',
        'usage_statistics'
    ]

    # ДОБАВИ INLINE ЗА СТАТУСИТЕ
    inlines = [DocumentTypeStatusInline]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code',
                'name',
                'type_key',
                'app_name',
                'description',
                'sort_order',
                'is_active'
            )
        }),
        (_('Business Behavior'), {
            'fields': (
                'affects_inventory',
                'inventory_direction',
                'auto_create_movements',
                'inventory_timing'
            )
        }),
        (_('Workflow Configuration'), {
            'fields': (
                'requires_approval',
                'allow_edit_completed'
            )
        }),
        (_('Legal & Compliance'), {
            'fields': (
                'is_fiscal',
                'auto_number'
            )
        }),
        (_('System Information'), {
            'fields': (
                'workflow_summary',
                'usage_statistics',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    # =====================
    # НОВИ DISPLAY METHODS
    # =====================

    def behavior_flags_display(self, obj):
        """NEW: Показва поведенчески флагове като badges"""
        flags = []

        if obj.affects_inventory:
            direction_map = {
                'in': '⬆️',
                'out': '⬇️',
                'both': '↕️',
                'none': '➖'
            }
            icon = direction_map.get(obj.inventory_direction, '❓')
            flags.append(
                f'<span style="background: #4CAF50; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">{icon} INVENTORY</span>')

        if obj.requires_approval:
            flags.append(
                '<span style="background: #2196F3; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">📋 APPROVAL</span>')

        if obj.allow_edit_completed:
            flags.append(
                '<span style="background: #FF9800; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">✏️ EDITABLE</span>')

        if obj.is_fiscal:
            flags.append(
                '<span style="background: #9C27B0; color: white; padding: 1px 4px; border-radius: 2px; font-size: 10px;">🧾 FISCAL</span>')

        return format_html(' '.join(flags)) if flags else '-'

    behavior_flags_display.short_description = _('Behavior')

    def configured_statuses_display(self, obj):
        """NEW: Показва конфигурираните статуси като timeline"""
        try:
            statuses = obj.type_statuses.filter(is_active=True).order_by('sort_order')[:5]
            if not statuses:
                return format_html('<span style="color: #999;">No statuses configured</span>')

            html_parts = []
            for i, config in enumerate(statuses):
                # Определи стила според флаговете
                style_parts = [f'background-color: {config.status.color}']

                if config.is_initial:
                    style_parts.append('border: 2px solid #4CAF50')
                elif config.is_final:
                    style_parts.append('border: 2px solid #F44336')
                elif config.is_cancellation:
                    style_parts.append('border: 2px solid #FF9800')
                else:
                    style_parts.append('border: 1px solid #ddd')

                style = '; '.join(style_parts)

                # Badge с име или custom име
                name = config.custom_name or config.status.name

                html_parts.append(
                    f'<span style="{style}; color: white; padding: 2px 4px; border-radius: 3px; margin-right: 2px; font-size: 10px;" title="{config.status.description or name}">{name}</span>')

                # Стрелка към следващия (освен за последния)
                if i < len(statuses) - 1:
                    html_parts.append('<span style="margin: 0 2px; color: #666;">→</span>')

            # Ако има повече от 5, покажи "..."
            total_count = obj.type_statuses.filter(is_active=True).count()
            if total_count > 5:
                html_parts.append(f'<span style="color: #999; font-size: 10px;">... +{total_count - 5} more</span>')

            return format_html(''.join(html_parts))

        except Exception as e:
            return format_html('<span style="color: #999;">Error loading statuses</span>')

    configured_statuses_display.short_description = _('Status Workflow')

    def workflow_info_display(self, obj):
        """NEW: Показва workflow информация"""
        info_parts = []

        # Брой статуси
        status_count = obj.type_statuses.filter(is_active=True).count()
        info_parts.append(f'<strong>{status_count}</strong> statuses')

        # Approval rules (ако има)
        if obj.requires_approval:
            try:
                from ..models import ApprovalRule
                rule_count = ApprovalRule.objects.filter(document_type=obj, is_active=True).count()
                info_parts.append(f'<strong>{rule_count}</strong> approval rules')
            except ImportError:
                info_parts.append('<span style="color: #999;">approval rules N/A</span>')

        # Numbering configs (ако има)
        try:
            from ..models import NumberingConfiguration
            numbering_count = NumberingConfiguration.objects.filter(document_type=obj, is_active=True).count()
            info_parts.append(f'<strong>{numbering_count}</strong> numbering configs')
        except ImportError:
            pass

        return format_html(' | '.join(info_parts))

    workflow_info_display.short_description = _('Workflow Info')

    def workflow_summary(self, obj):
        """NEW: Подробна workflow информация за readonly поле"""
        if not obj.pk:
            return 'Save document first to see workflow summary'

        html = '<div style="font-family: monospace; font-size: 12px;">'

        # Статуси
        html += '<h4>📊 Status Configuration:</h4>'
        statuses = obj.type_statuses.filter(is_active=True).order_by('sort_order')
        if statuses:
            html += '<table border="1" cellpadding="4" style="border-collapse: collapse; font-size: 11px;">'
            html += '<tr><th>Order</th><th>Status</th><th>Custom Name</th><th>Flags</th><th>Color</th></tr>'

            for config in statuses:
                flags = []
                if config.is_initial:
                    flags.append('INITIAL')
                if config.is_final:
                    flags.append('FINAL')
                if config.is_cancellation:
                    flags.append('CANCEL')

                html += f'''
                <tr>
                    <td>{config.sort_order}</td>
                    <td>{config.status.name} ({config.status.code})</td>
                    <td>{config.custom_name or '-'}</td>
                    <td>{', '.join(flags) or '-'}</td>
                    <td style="background-color: {config.status.color}; color: white; text-align: center;">{config.status.color}</td>
                </tr>
                '''
            html += '</table>'
        else:
            html += '<p style="color: #999;">No statuses configured yet.</p>'

        # Approval Rules (ако require approval)
        if obj.requires_approval:
            html += '<h4>🔐 Approval Rules:</h4>'
            try:
                from ..models import ApprovalRule
                rules = ApprovalRule.objects.filter(document_type=obj, is_active=True).order_by('approval_level')
                if rules:
                    html += '<ul>'
                    for rule in rules:
                        html += f'<li><strong>Level {rule.approval_level}:</strong> {rule.name} ({rule.from_status} → {rule.to_status})</li>'
                    html += '</ul>'
                else:
                    html += '<p style="color: #999;">No approval rules configured yet.</p>'
            except ImportError:
                html += '<p style="color: #999;">Approval rules not available.</p>'

        # Numbering
        html += '<h4>🔢 Numbering:</h4>'
        try:
            from ..models import NumberingConfiguration
            configs = NumberingConfiguration.objects.filter(document_type=obj, is_active=True)
            if configs:
                html += '<ul>'
                for config in configs:
                    html += f'<li><strong>{config.name}:</strong> {config.get_microinvest_display()}</li>'
                html += '</ul>'
            else:
                html += '<p style="color: #999;">No numbering configurations.</p>'
        except ImportError:
            html += '<p style="color: #999;">Numbering not available.</p>'

        html += '</div>'
        return format_html(html)

    workflow_summary.short_description = _('Workflow Summary')

    def usage_statistics(self, obj):
        """NEW: Статистика за използване"""
        if not obj.pk:
            return 'Save document first to see usage statistics'

        html = '<div style="font-family: monospace; font-size: 12px;">'
        html += '<h4>📈 Usage Statistics:</h4>'

        # Брой документи от този тип (ако има модели които го използват)
        html += f'<p><strong>Type Key:</strong> {obj.type_key}</p>'
        html += f'<p><strong>App:</strong> {obj.app_name}</p>'

        # ApprovalLog статистика
        try:
            from ..models import ApprovalLog
            log_count = ApprovalLog.objects.filter(rule__document_type=obj).count()
            html += f'<p><strong>Approval Actions:</strong> {log_count}</p>'
        except ImportError:
            pass

        html += '</div>'
        return format_html(html)

    usage_statistics.short_description = _('Usage Statistics')

    # =====================
    # ACTIONS
    # =====================

    actions = [
        'create_default_statuses',
        'create_basic_approval_rules',
        'duplicate_document_types'
    ]

    def create_default_statuses(self, request, queryset):
        """Action за създаване на default статуси"""
        from ..models import DocumentStatus, DocumentTypeStatus

        # Default статуси
        default_statuses = [
            {'code': 'draft', 'name': 'Draft', 'color': '#757575', 'is_initial': True},
            {'code': 'submitted', 'name': 'Submitted', 'color': '#2196F3'},
            {'code': 'approved', 'name': 'Approved', 'color': '#4CAF50'},
            {'code': 'completed', 'name': 'Completed', 'color': '#8BC34A', 'is_final': True},
            {'code': 'cancelled', 'name': 'Cancelled', 'color': '#F44336', 'is_final': True, 'is_cancellation': True},
        ]

        created_count = 0
        for doc_type in queryset:
            for i, status_data in enumerate(default_statuses):
                # Създай или намери статуса
                status, _ = DocumentStatus.objects.get_or_create(
                    code=status_data['code'],
                    defaults={
                        'name': status_data['name'],
                        'color': status_data['color']
                    }
                )

                # Създай конфигурацията
                config, created = DocumentTypeStatus.objects.get_or_create(
                    document_type=doc_type,
                    status=status,
                    defaults={
                        'sort_order': (i + 1) * 10,
                        'is_initial': status_data.get('is_initial', False),
                        'is_final': status_data.get('is_final', False),
                        'is_cancellation': status_data.get('is_cancellation', False),
                    }
                )
                if created:
                    created_count += 1

        self.message_user(request, f'Created {created_count} status configurations.')

    create_default_statuses.short_description = _('Create default statuses')

    def create_basic_approval_rules(self, request, queryset):
        """Action за създаване на basic approval rules"""
        try:
            from ..models import ApprovalRule, DocumentStatus
            from django.contrib.auth.models import Group

            created_count = 0
            for doc_type in queryset.filter(requires_approval=True):

                # Намери статусите
                draft_status = DocumentStatus.objects.filter(code='draft').first()
                submitted_status = DocumentStatus.objects.filter(code='submitted').first()
                approved_status = DocumentStatus.objects.filter(code='approved').first()

                if not all([draft_status, submitted_status, approved_status]):
                    continue

                # Managers group (create if not exists)
                managers_group, _ = Group.objects.get_or_create(name='Managers')

                # Rule 1: Draft → Submitted (anyone can submit)
                rule1, created = ApprovalRule.objects.get_or_create(
                    document_type=doc_type,
                    from_status_obj=draft_status,
                    to_status_obj=submitted_status,
                    defaults={
                        'name': f'Submit {doc_type.name}',
                        'approval_level': 1,
                        'approver_type': 'role',
                        'approver_role': managers_group,
                        'min_amount': 0,
                    }
                )
                if created:
                    created_count += 1

                # Rule 2: Submitted → Approved (managers only)
                rule2, created = ApprovalRule.objects.get_or_create(
                    document_type=doc_type,
                    from_status_obj=submitted_status,
                    to_status_obj=approved_status,
                    defaults={
                        'name': f'Approve {doc_type.name}',
                        'approval_level': 2,
                        'approver_type': 'role',
                        'approver_role': managers_group,
                        'min_amount': 0,
                        'requires_previous_level': True,
                    }
                )
                if created:
                    created_count += 1

            self.message_user(request, f'Created {created_count} approval rules.')

        except ImportError:
            self.message_user(request, 'Approval rules not available.', level='warning')

    create_basic_approval_rules.short_description = _('Create basic approval rules')

    def duplicate_document_types(self, request, queryset):
        """Action за дублиране на document types"""
        count = 0
        for doc_type in queryset:
            # Дублирай основния тип
            old_type_key = doc_type.type_key
            doc_type.pk = None
            doc_type.type_key = f"{old_type_key}_copy"
            doc_type.name = f"{doc_type.name} (Copy)"
            doc_type.save()
            count += 1

        self.message_user(request, f'Duplicated {count} document types.')

    duplicate_document_types.short_description = _('Duplicate selected document types')