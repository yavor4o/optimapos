

from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied, ValidationError

from nomenclatures.services.approval_service import ApprovalService
from purchases.services import WorkflowService


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
        ✅ COMPLETE: Handle document approval with conversion support
        """
        try:
            # 1. Проверка за нужда от одобрение
            if document.document_type and document.document_type.requires_approval:
                amount = (
                        getattr(document, 'grand_total', None)
                        or (document.get_estimated_total() if hasattr(document, 'get_estimated_total') else None)
                )

                if document.needs_approval(amount):
                    # 1.1 Вземаме всички възможни преходи за потребителя
                    transitions = ApprovalService.get_available_transitions(document, user)
                    if not transitions:
                        return {
                            'success': False,
                            'message': 'Document requires approval but no applicable transition was found.'
                        }

                    # 1.2 Избираме най-подходящия преход
                    selected_transition = self._select_best_transition(transitions, document.status)

                    # 1.3 ✅ SPECIAL HANDLING за conversion
                    if selected_transition['to_status'] == 'converted':
                        return self._handle_conversion_transition(document, selected_transition, user)

                    # 1.4 Изпълняваме обикновен approval transition
                    return ApprovalService.execute_transition(
                        document=document,
                        to_status=selected_transition['to_status'],
                        user=user,
                        comments=f"Via rule: {selected_transition['rule'].name}"
                    )

            # 2. Ако не се изисква одобрение — следваме DocumentType transitions
            next_statuses = document.get_next_statuses()
            if not next_statuses:
                return {
                    'success': False,
                    'message': f'No allowed transitions from status "{document.status}"'
                }

            # 2.1 Smart selection за DocumentType transitions
            target_status = self._select_best_next_status(next_statuses, document.status)

            # 2.2 ✅ SPECIAL HANDLING за conversion
            if target_status == 'converted':
                return self._handle_conversion_transition(document, {'to_status': target_status}, user)

            # 2.3 Валидация
            if not document.can_transition_to(target_status):
                return {
                    'success': False,
                    'message': f'Transition from "{document.status}" to "{target_status}" not allowed.'
                }

            if hasattr(document, 'lines') and not document.lines.exists():
                return {
                    'success': False,
                    'message': 'Cannot submit document without lines.'
                }



            return WorkflowService.transition_document(
                document=document,
                to_status=target_status,
                user=user,
                comments="Via admin approval action"
                )

        except Exception as e:
            return {
                'success': False,
                'message': f'Error during approval: {str(e)}'
            }

    def _select_best_transition(self, transitions, current_status):
        """
        ✅ FLEXIBLE: Избира transition според sort_order
        """
        if len(transitions) == 1:
            return transitions[0]

        # Просто връщаме първия по sort_order (най-малко = най-висок приоритет)
        return sorted(transitions, key=lambda t: t['rule'].sort_order)[0]

    def _select_best_next_status(self, next_statuses, current_status):
        """
        ✅ FLEXIBLE: Избира статус без hardcoded keywords
        """
        if len(next_statuses) == 1:
            return next_statuses[0]

        # 1. Изключваме final statuses (обикновено са деструктивни)
        document_type = getattr(self, 'model', None)
        if document_type and hasattr(document_type, '_meta'):
            try:
                # Опитваме се да намерим document_type от първия обект
                first_obj = document_type.objects.first()
                if first_obj and hasattr(first_obj, 'document_type'):
                    final_statuses = getattr(first_obj.document_type, 'final_statuses', [])
                    non_final = [s for s in next_statuses if s not in final_statuses]
                    if non_final:
                        return non_final[0]
            except:
                pass

        # 2. Fallback: просто първия статус
        return next_statuses[0]

    def _handle_conversion_transition(self, document, transition, user):
        """
        ✅ NEW: Special handling for conversion to order
        """
        try:
            # Use the model's built-in conversion method
            if hasattr(document, 'convert_to_order'):
                order = document.convert_to_order(user)
                return {
                    'success': True,
                    'message': f'Converted to order: {order.document_number}'
                }
            else:
                return {
                    'success': False,
                    'message': 'Document does not support conversion to order'
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Conversion error: {str(e)}'
            }

    def _evaluate_auto_approve_conditions(self, document, document_amount, user):
        """
        ✅ НОВА ФУНКЦИЯ: Evaluates DocumentType auto_approve_conditions

        Returns True if document meets auto-approve criteria
        """
        try:
            conditions = document.document_type.auto_approve_conditions
            if not conditions:
                return False

            # ✅ Amount-based conditions
            if 'max_amount' in conditions:
                max_amount = conditions['max_amount']
                if document_amount and document_amount > max_amount:
                    return False

            if 'min_amount' in conditions:
                min_amount = conditions['min_amount']
                if not document_amount or document_amount < min_amount:
                    return False

            # ✅ User-based conditions
            if 'user_roles' in conditions:
                required_roles = conditions['user_roles']
                user_roles = list(user.groups.values_list('name', flat=True))
                if not any(role in user_roles for role in required_roles):
                    return False

            if 'user_permissions' in conditions:
                required_permissions = conditions['user_permissions']
                if not all(user.has_perm(perm) for perm in required_permissions):
                    return False

            # ✅ Document-based conditions
            if 'required_fields' in conditions:
                required_fields = conditions['required_fields']
                for field in required_fields:
                    if not getattr(document, field, None):
                        return False

            if 'supplier_whitelist' in conditions:
                allowed_suppliers = conditions['supplier_whitelist']
                if hasattr(document, 'supplier') and document.supplier:
                    supplier_code = getattr(document.supplier, 'code', str(document.supplier))
                    if supplier_code not in allowed_suppliers:
                        return False

            # ✅ Time-based conditions
            if 'working_hours_only' in conditions and conditions['working_hours_only']:
                from datetime import datetime
                now = datetime.now()
                if now.weekday() >= 5 or now.hour < 9 or now.hour > 17:  # Weekend or outside 9-17
                    return False

            return True  # All conditions passed!

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error evaluating auto approve conditions: {e}")
            return False

    def _execute_auto_approve(self, document, user):
        """
        ✅ НОВА ФУНКЦИЯ: Executes auto-approval transition
        """
        try:
            # Find the best approval target status
            next_statuses = document.get_next_statuses()

            # Look for approval completion statuses
            approval_complete_keywords = ['approved', 'confirmed', 'accepted']
            target_status = None

            for keyword in approval_complete_keywords:
                for status in next_statuses:
                    if keyword in status.lower():
                        target_status = status
                        break
                if target_status:
                    break

            # Fallback to first non-cancellation status
            if not target_status:
                non_cancellation = [s for s in next_statuses if 'cancel' not in s.lower()]
                target_status = non_cancellation[0] if non_cancellation else next_statuses[0]

            # Execute the transition
            old_status = document.status
            document.status = target_status

            # Set auto-approval fields
            if hasattr(document, 'approved_by'):
                document.approved_by = user
            if hasattr(document, 'approved_at'):
                document.approved_at = timezone.now()
            if hasattr(document, 'updated_by'):
                document.updated_by = user

            document.save()

            return {
                'success': True,
                'message': f'Auto-approved: {old_status} → {target_status} (meets auto-approve conditions)'
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error during auto-approval: {str(e)}'
            }

    def _handle_document_rejection(self, document, user, request):
        """
        ФИКСИРАНО: Configuration-driven rejection handling
        """

        try:
            # ✅ ДИНАМИЧНО: Намери rejection статус от DocumentType
            current_status = document.status
            next_statuses = document.get_next_statuses()

            # Търси rejection статус
            rejection_status = None
            rejection_keywords = ['reject', 'denied', 'declined']

            for keyword in rejection_keywords:
                for status in next_statuses:
                    if keyword in status.lower():
                        rejection_status = status
                        break
                if rejection_status:
                    break

            if not rejection_status:
                return {
                    'success': False,
                    'message': f'No rejection status available from "{current_status}"'
                }

            # ✅ ВАЛИДАЦИЯ: Проверка дали transition е разрешен
            if not document.can_transition_to(rejection_status):
                return {
                    'success': False,
                    'message': f'Transition to "{rejection_status}" not allowed by DocumentType'
                }

            # ✅ ИЗПЪЛНЕНИЕ: Rejection
            old_status = document.status
            document.status = rejection_status

            # Set rejection fields if available
            if hasattr(document, 'rejected_by'):
                document.rejected_by = user
            if hasattr(document, 'rejected_at'):
                document.rejected_at = timezone.now()
            if hasattr(document, 'rejection_reason'):
                document.rejection_reason = f"Rejected via admin action by {user.get_full_name()}"
            if hasattr(document, 'updated_by'):
                document.updated_by = user

            document.save()

            return {
                'success': True,
                'message': f'Document rejected: {old_status} → {rejection_status}'
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error processing rejection: {str(e)}'
            }

    # ФИКС НА ADMIN ACTION - nomenclatures/admin/dynamic_actions.py
    # Намери метода create_workflow_status_action и промени:

    def _create_workflow_status_action(self):
        """Създава action за показване на workflow статус"""

        def show_workflow_status(modeladmin, request, queryset):
            """Показва workflow статуса на избраните документи"""

            for document in queryset:
                try:
                    # ✅ ФИКСВАНО: Вземи workflow status БЕЗ available_transitions
                    workflow_status = ApprovalService.get_workflow_status(document)

                    # ✅ ФИКСВАНО: Вземи available_transitions с user отделно
                    available_transitions = ApprovalService.get_available_transitions(document, request.user)

                    # Форматираме информацията
                    status_info = [
                        f"📄 {document}",
                        f"🔄 Current Status: {workflow_status['current_status']}",
                        f"⚡ Available Actions: {len(available_transitions)}",  # ✅ ФИКСВАНО
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

                    # ✅ НОВОВЪВЕДЕНО: Показваме достъпните действия за този user
                    if available_transitions:
                        status_info.append("🎯 Available Actions:")
                        for transition in available_transitions:
                            status_info.append(
                                f"  → {transition['to_status']} (Level {transition['level']}: {transition['name']})"
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

        show_workflow_status.short_description = "Show workflow status for selected documents"
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