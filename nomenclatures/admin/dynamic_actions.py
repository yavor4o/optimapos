

from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied, ValidationError

from nomenclatures.services.approval_service import ApprovalService


class DynamicApprovalMixin:
    """
    Mixin за admin класове който добавя динамични approval actions

    Автоматично генерира admin actions според ApprovalRule конфигурацията
    """

    def get_actions(self, request):
        """Override за да добавим динамични actions"""
        actions = super().get_actions(request)

        # Добавяме статичните approval actions
        actions.update(self._get_approval_actions(request))

        return actions

    def _get_approval_actions(self, request):
        """Генерира динамични approval actions"""

        # Основни actions които винаги са налични
        base_actions = {
            'dynamic_approve_documents': (
                self._create_approval_action('approve'),
                'dynamic_approve_documents',
                _('Approve selected documents (dynamic)')
            ),
            'dynamic_reject_documents': (
                self._create_approval_action('reject'),
                'dynamic_reject_documents',
                _('Reject selected documents (dynamic)')
            ),
            'show_workflow_status': (
                self._create_workflow_status_action(),
                'show_workflow_status',
                _('Show workflow status')
            )
        }

        return base_actions

    def _create_approval_action(self, action_type):
        """Създава approval action функция"""

        def approval_action(modeladmin, request, queryset):
            """Динамична approval action"""

            success_count = 0
            error_count = 0

            for document in queryset:
                try:
                    if action_type == 'approve':
                        result = self._handle_document_approval(document, request.user)
                    elif action_type == 'reject':
                        result = self._handle_document_rejection(document, request.user, request)

                    if result.get('success'):
                        success_count += 1
                        messages.success(
                            request,
                            f"{document}: {result.get('message', 'Action completed')}"
                        )
                    else:
                        error_count += 1
                        messages.error(
                            request,
                            f"{document}: {result.get('message', 'Action failed')}"
                        )

                except (PermissionDenied, ValidationError) as e:
                    error_count += 1
                    messages.error(request, f"{document}: {str(e)}")
                except Exception as e:
                    error_count += 1
                    messages.error(request, f"{document}: Unexpected error - {str(e)}")

            # Обобщение
            if success_count:
                messages.success(
                    request,
                    _('Successfully processed %(count)d documents.') % {'count': success_count}
                )

            if error_count:
                messages.warning(
                    request,
                    _('%(count)d documents could not be processed.') % {'count': error_count}
                )

        # Задаваме описанието на action-a
        action_name = f"{action_type.title()} selected documents"
        approval_action.short_description = _(action_name)

        return approval_action

    def _handle_document_approval(self, document, user):
        """
        ФИКСИРАНО: Обработва одобрението на един документ

        Добавена логика за draft → submitted случая
        """

        # СПЕЦИАЛЕН СЛУЧАЙ: draft → submitted (submit, не approval!)
        if document.status == 'draft':
            try:
                # Проверяваме дали може да се submit-не
                if not hasattr(document, 'lines') or not document.lines.exists():
                    return {
                        'success': False,
                        'message': 'Cannot submit request without lines'
                    }

                # ДИРЕКТЕН SUBMIT БЕЗ ApprovalService
                document.status = 'submitted'
                if hasattr(document, 'updated_by'):
                    document.updated_by = user
                document.save()

                return {
                    'success': True,
                    'message': f'Submitted for approval (draft → submitted)'
                }

            except Exception as e:
                return {
                    'success': False,
                    'message': f'Error submitting document: {str(e)}'
                }

    def _handle_document_rejection(self, document, user, request):
        """Обработва отхвърлянето на един документ"""

        # За rejection може да поискаме причина от потребителя
        # За простота, използваме стандартна причина
        reason = f"Rejected via admin action by {user.get_full_name()}"

        result = ApprovalService.reject_document(
            document=document,
            user=user,
            reason=reason
        )

        return result

    def _create_workflow_status_action(self):
        """Създава action за показване на workflow статус"""

        def show_workflow_status(modeladmin, request, queryset):
            """Показва workflow статуса на избраните документи"""

            for document in queryset:
                try:
                    workflow_status = ApprovalService.get_workflow_status(document)

                    # Форматираме информацията
                    status_info = [
                        f"📄 {document}",
                        f"🔄 Current Status: {workflow_status['current_status']}",
                        f"⚡ Available Actions: {workflow_status['available_transitions']}",
                        f"✅ Completed: {'Yes' if workflow_status['is_completed'] else 'No'}"
                    ]

                    # Показваме workflow нивата
                    if workflow_status['workflow_levels']:
                        status_info.append("📋 Workflow Levels:")
                        for level in workflow_status['workflow_levels']:
                            status = "✅" if level['completed'] else "⏳"
                            status_info.append(
                                f"  {status} Level {level['level']}: {level['name']} → {level['to_status']}"
                            )

                    # Показваме историята
                    if workflow_status['approval_history']:
                        status_info.append("📜 Recent History:")
                        for log in workflow_status['approval_history'][-3:]:  # Последните 3
                            status_info.append(
                                f"  🕒 {log['timestamp'].strftime('%Y-%m-%d %H:%M')} - "
                                f"{log['actor']}: {log['action']}"
                            )

                    # Показваме като info message
                    messages.info(request, "\n".join(status_info))

                except Exception as e:
                    messages.error(request, f"{document}: Error getting workflow status - {str(e)}")

        show_workflow_status.short_description = _("Show workflow status for selected documents")
        return show_workflow_status

    # =====================
    # DISPLAY METHODS FOR ADMIN LIST
    # =====================

    def workflow_status_display(self, obj):
        """
        ПОДОБРЕН: Display method за показване на workflow статус в list_display
        """
        try:
            # СПЕЦИАЛЕН СЛУЧАЙ: draft документи
            if obj.status == 'draft':
                return format_html('<span style="color: orange;">📝 Ready to Submit</span>')

            # ЗА ОСТАНАЛИТЕ: ApprovalService логика
            workflow_status = ApprovalService.get_workflow_status(obj)

            if workflow_status['is_completed']:
                return format_html('<span style="color: green;">✅ Completed</span>')
            elif workflow_status['available_transitions']:
                return format_html(
                    '<span style="color: orange;">⏳ {} actions available</span>',
                    len(workflow_status['available_transitions'])
                )
            else:
                return format_html('<span style="color: gray;">⏸️ Waiting</span>')

        except Exception:
            return format_html('<span style="color: red;">❌ Error</span>')

    workflow_status_display.short_description = _('Workflow Status')

    def available_actions_display(self, obj):
        """
        ПОДОБРЕН: Display method за показване на достъпни actions
        """
        try:
            # СПЕЦИАЛЕН СЛУЧАЙ: draft документи
            if obj.status == 'draft':
                if hasattr(obj, 'lines') and obj.lines.exists():
                    return format_html('<span style="color: blue;">📤 Can Submit</span>')
                else:
                    return format_html('<span style="color: gray;">📝 Add Lines First</span>')

            # ЗА ОСТАНАЛИТЕ: ApprovalService логика
            if hasattr(self, '_current_request') and self._current_request:
                user = self._current_request.user
                transitions = ApprovalService.get_available_transitions(obj, user)

                if transitions:
                    actions = [t['to_status'] for t in transitions]
                    return format_html(
                        '<span style="color: blue;">📋 {}</span>',
                        ', '.join(actions)
                    )
                else:
                    return format_html('<span style="color: gray;">No actions</span>')
            else:
                return "Login required"

        except Exception:
            return format_html('<span style="color: red;">Error</span>')



    available_actions_display.short_description = _('Available Actions')

    def changelist_view(self, request, extra_context=None):
        """Override за да запазим request context"""
        self._current_request = request
        return super().changelist_view(request, extra_context)


# =====================
# ENHANCED PURCHASE REQUEST ADMIN
# =====================

class DynamicPurchaseRequestAdmin(DynamicApprovalMixin, admin.ModelAdmin):
    """
    Enhanced Purchase Request Admin с динамични approval actions
    """

    list_display = [
        'document_number', 'supplier', 'status_display',
        'estimated_total_display', 'workflow_status_display',
        'available_actions_display', 'requested_by', 'document_date'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type',
        'document_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'workflow_status_display', 'approval_history_display'
    ]

    def approval_history_display(self, obj):
        """Показва approval историята"""
        if not obj.pk:
            return "Save document first"

        try:
            history = ApprovalService.get_approval_history(obj)

            if not history:
                return "No approval history"

            history_html = []
            for log in history[-5:]:  # Последните 5 записа
                history_html.append(
                    f"🕒 {log['timestamp'].strftime('%m/%d %H:%M')} - "
                    f"<strong>{log['actor']}</strong>: {log['action']} "
                    f"({log['from_status']} → {log['to_status']})"
                )

            return format_html('<br>'.join(history_html))

        except Exception as e:
            return f"Error: {str(e)}"

    approval_history_display.short_description = _('Approval History')

    def status_display(self, obj):
        """Enhanced status display with workflow context"""
        try:
            workflow_status = ApprovalService.get_workflow_status(obj)

            # Цветове според статуса
            colors = {
                'draft': '#6c757d',
                'submitted': '#ffc107',
                'regional_approved': '#28a745',
                'central_approved': '#17a2b8',
                'converted': '#007bff',
                'rejected': '#dc3545',
                'cancelled': '#6c757d'
            }

            color = colors.get(obj.status, '#6c757d')

            # Добавяме индикатор за progress
            if workflow_status['is_completed']:
                indicator = "✅"
            elif workflow_status['available_transitions']:
                indicator = "⏳"
            else:
                indicator = "⏸️"

            return format_html(
                '{} <span style="color: {}; font-weight: bold;">{}</span>',
                indicator,
                color,
                obj.status.replace('_', ' ').title()
            )

        except Exception:
            return obj.status

    status_display.short_description = _('Status')