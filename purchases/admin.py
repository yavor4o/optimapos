# purchases/admin.py - ПРОФЕСИОНАЛНА ВЕРСИЯ С APPROVAL SERVICE

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from django.urls import path
from django import forms

from nomenclatures.services.approval_service import ApprovalService
from .models.requests import PurchaseRequest, PurchaseRequestLine
from .models.orders import PurchaseOrder, PurchaseOrderLine
from .models.deliveries import DeliveryReceipt, DeliveryLine

# Import на ApprovalService



# =====================
# FORMS - ЗАПАЗВАМЕ СЪЩИТЕ
# =====================

class PurchaseRequestLineForm(forms.ModelForm):
    """Enhanced form for Purchase Request Lines"""

    class Meta:
        model = PurchaseRequestLine
        fields = [
            'product', 'requested_quantity', 'estimated_price',
            'usage_description', 'alternative_products', 'quality_notes',
            'batch_number', 'expiry_date', 'quality_approved', 'serial_numbers'
        ]
        widgets = {
            'usage_description': forms.Textarea(attrs={'rows': 2}),
            'alternative_products': forms.Textarea(attrs={'rows': 2}),
            'quality_notes': forms.Textarea(attrs={'rows': 2}),
            'serial_numbers': forms.Textarea(attrs={'rows': 2}),
            'requested_quantity': forms.NumberInput(attrs={'step': '0.001'}),
            'estimated_price': forms.NumberInput(attrs={'step': '0.01'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


# =====================
# DYNAMIC ADMIN ACTIONS - ПРОФЕСИОНАЛНИ
# =====================

# purchases/admin.py - ОБНОВЕН APPROVAL ACTION MIXIN

class ApprovalActionMixin:
    """Mixin for adding dynamic approval actions to admin - ИЗПОЛЗВА ФИНАЛНИЯ ApprovalService"""

    def get_actions(self, request):
        """Динамично генериране на actions според ApprovalService"""
        # Първо взимаме стандартните Django actions
        actions = super().get_actions(request)

        # Добавяме нашите approval actions
        try:
            approval_actions = self._generate_approval_actions(request)
            actions.update(approval_actions)
        except Exception as e:
            # Ако има грешка с ApprovalService, просто логваме но не счупваме admin-а
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating approval actions: {e}")

        return actions

    def _generate_approval_actions(self, request):
        """Генерира approval actions в правилния Django формат"""
        actions = {}

        # Action 1: Smart Approve с ApprovalService
        def smart_approve_action(modeladmin, request, queryset):
            """Интелигентно одобрение с ApprovalService"""

            success_count = 0
            failed_count = 0
            errors = []

            for document in queryset:
                try:
                    # Използваме ApprovalService за намиране на най-добрия преход
                    available_transitions = ApprovalService.get_available_transitions(document, request.user)

                    if not available_transitions:
                        failed_count += 1
                        errors.append(f"{getattr(document, 'document_number', 'Unknown')}: No available transitions")
                        continue

                    # Избираме най-подходящия преход (първия approval или първия общо)
                    best_transition = None

                    # Приоритет: approval преходи
                    for transition in available_transitions:
                        if 'approv' in transition['to_status'].lower():
                            best_transition = transition
                            break

                    # Ако няма approval, взимаме първия
                    if not best_transition:
                        best_transition = available_transitions[0]

                    # Изпълняваме прехода
                    result = ApprovalService.execute_transition(
                        document=document,
                        to_status=best_transition['to_status'],
                        user=request.user,
                        comments=f"Bulk smart approval via admin by {request.user.get_full_name()}"
                    )

                    if result['success']:
                        success_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"{getattr(document, 'document_number', 'Unknown')}: {result['message']}")

                except Exception as e:
                    failed_count += 1
                    errors.append(f"{getattr(document, 'document_number', 'Unknown')}: {str(e)}")

            # Показваме резултатите
            if success_count:
                messages.success(request, f'Successfully processed {success_count} documents.')

            if failed_count:
                messages.warning(request, f'{failed_count} documents could not be processed.')

                # Показваме първите няколко грешки
                for error in errors[:3]:
                    messages.error(request, error)

                if len(errors) > 3:
                    messages.info(request, f"... and {len(errors) - 3} more errors")

        smart_approve_action.short_description = "🚀 Smart Approve - ApprovalService powered"

        # Action 2: Show Workflow Status с ApprovalService
        def show_workflow_status_action(modeladmin, request, queryset):
            """Показва workflow статус с ApprovalService"""

            for document in queryset:
                try:
                    workflow_status = ApprovalService.get_workflow_status(document)
                    available_transitions = ApprovalService.get_available_transitions(document, request.user)

                    # Форматираме съобщението
                    doc_number = workflow_status.get('document_number', 'Unknown')
                    current_status = workflow_status.get('current_status', 'Unknown')

                    status_msg = f"📄 {doc_number}: {current_status}"

                    if available_transitions:
                        actions = [t['to_status'] for t in available_transitions]
                        status_msg += f" → Available: {', '.join(actions)}"
                    else:
                        status_msg += " → No actions available"

                    # Показваме и workflow levels ако има
                    levels = workflow_status.get('workflow_levels', [])
                    if levels:
                        completed_levels = [l for l in levels if l['completed']]
                        status_msg += f" | Progress: {len(completed_levels)}/{len(levels)} levels"

                    messages.info(request, status_msg)

                except Exception as e:
                    messages.error(request, f"Error for {getattr(document, 'document_number', 'Unknown')}: {str(e)}")

        show_workflow_status_action.short_description = "📊 Show workflow status (ApprovalService)"

        # Action 3: Specific Status Transitions
        def create_status_transition_action(to_status: str, display_name: str):
            """Създава action за конкретен статус преход"""

            def status_transition_action(modeladmin, request, queryset):
                success_count = 0
                failed_count = 0
                errors = []

                for document in queryset:
                    try:
                        # Проверяваме дали преходът е възможен
                        available_transitions = ApprovalService.get_available_transitions(document, request.user)

                        # Търсим конкретния преход
                        target_transition = None
                        for transition in available_transitions:
                            if transition['to_status'] == to_status:
                                target_transition = transition
                                break

                        if not target_transition:
                            failed_count += 1
                            errors.append(
                                f"{getattr(document, 'document_number', 'Unknown')}: Transition to '{to_status}' not available")
                            continue

                        # Изпълняваме прехода
                        result = ApprovalService.execute_transition(
                            document=document,
                            to_status=to_status,
                            user=request.user,
                            comments=f"Bulk {display_name.lower()} via admin"
                        )

                        if result['success']:
                            success_count += 1
                        else:
                            failed_count += 1
                            errors.append(f"{getattr(document, 'document_number', 'Unknown')}: {result['message']}")

                    except Exception as e:
                        failed_count += 1
                        errors.append(f"{getattr(document, 'document_number', 'Unknown')}: {str(e)}")

                # Резултати
                if success_count:
                    messages.success(request, f'Successfully {display_name.lower()}ed {success_count} documents.')

                if failed_count:
                    messages.warning(request, f'{failed_count} documents could not be processed.')
                    for error in errors[:3]:
                        messages.error(request, error)

            status_transition_action.short_description = f"{display_name} selected documents"
            return status_transition_action

        # Action 4: Bulk Reject с причина
        def bulk_reject_action(modeladmin, request, queryset):
            """Bulk отхвърляне - redirect към custom view"""

            # Съхраняваме IDs в session за custom view
            request.session['documents_to_reject'] = list(queryset.values_list('id', flat=True))
            request.session['rejection_model'] = queryset.model._meta.label_lower

            # Redirect към custom rejection view
            return redirect('admin:purchases_rejection_view')

        bulk_reject_action.short_description = "❌ Reject with reason (ApprovalService)"

        # Action 5: Show Approval History
        def show_approval_history_action(modeladmin, request, queryset):
            """Показва approval историята"""

            for document in queryset[:5]:  # Ограничаваме до 5 документа за четимост
                try:
                    history = ApprovalService.get_approval_history(document)
                    doc_number = getattr(document, 'document_number', 'Unknown')

                    if history:
                        history_msg = f"📋 {doc_number} History: "
                        history_items = []

                        for entry in history[-3:]:  # Последните 3 записа
                            timestamp = entry['timestamp'].strftime('%m-%d %H:%M')
                            action = entry['action']
                            actor = entry['actor']
                            history_items.append(f"{timestamp} {action} by {actor}")

                        history_msg += " | ".join(history_items)
                        messages.info(request, history_msg)
                    else:
                        messages.info(request, f"📋 {doc_number}: No approval history")

                except Exception as e:
                    messages.error(request,
                                   f"History error for {getattr(document, 'document_number', 'Unknown')}: {str(e)}")

            if queryset.count() > 5:
                messages.info(request, f"Showing history for first 5 documents (total: {queryset.count()})")

        show_approval_history_action.short_description = "📜 Show approval history"

        # Action 6: Test ApprovalService Connection
        def test_service_action(modeladmin, request, queryset):
            """Тества дали ApprovalService работи правилно"""

            test_results = []

            for document in queryset[:3]:  # Тестваме само първите 3
                try:
                    doc_number = getattr(document, 'document_number', 'Unknown')

                    # Тест 1: Get available transitions
                    transitions = ApprovalService.get_available_transitions(document, request.user)
                    test_results.append(f"✅ {doc_number}: {len(transitions)} transitions available")

                    # Тест 2: Get workflow status
                    status = ApprovalService.get_workflow_status(document)
                    levels = len(status.get('workflow_levels', []))
                    test_results.append(f"✅ {doc_number}: {levels} workflow levels configured")

                    # Тест 3: Get history
                    history = ApprovalService.get_approval_history(document)
                    test_results.append(f"✅ {doc_number}: {len(history)} history entries")

                except Exception as e:
                    test_results.append(f"❌ {getattr(document, 'document_number', 'Unknown')}: {str(e)}")

            # Показваме резултатите
            for result in test_results:
                if result.startswith('✅'):
                    messages.success(request, result)
                else:
                    messages.error(request, result)

            messages.info(request, "ApprovalService test completed!")

        test_service_action.short_description = "🔧 Test ApprovalService connection"

        # ВАЖНО: Django формат - tuple с (function, name, description)
        actions['smart_approve'] = (smart_approve_action, 'smart_approve', smart_approve_action.short_description)
        actions['show_workflow'] = (show_workflow_status_action, 'show_workflow',
                                    show_workflow_status_action.short_description)
        actions['bulk_reject'] = (bulk_reject_action, 'bulk_reject', bulk_reject_action.short_description)
        actions['show_history'] = (show_approval_history_action, 'show_history',
                                   show_approval_history_action.short_description)
        actions['test_service'] = (test_service_action, 'test_service', test_service_action.short_description)

        # Добавяме специфични статус actions (ако са налични)
        common_statuses = ['submitted', 'approved', 'regional_approved', 'central_approved']
        for status in common_statuses:
            action_func = create_status_transition_action(status, status.replace('_', ' ').title())
            actions[f'transition_to_{status}'] = (action_func, f'transition_to_{status}', action_func.short_description)

        return actions


# =====================
# CUSTOM URLS MIXIN
# =====================

class CustomWorkflowUrlsMixin:
    """Mixin за custom URLs"""

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'rejection-view/',
                self.admin_site.admin_view(self.rejection_view),
                name='purchases_rejection_view'
            ),
        ]
        return custom_urls + urls

    def rejection_view(self, request):
        """Custom view за отхвърляне с причина"""

        if request.method == 'POST':
            reason = request.POST.get('rejection_reason', '').strip()
            if not reason:
                messages.error(request, _('Rejection reason is required.'))
                return render(request, 'admin/purchases/rejection_form.html', {
                    'title': _('Reject Documents'),
                })

            # Взимаме документите от session
            document_ids = request.session.get('documents_to_reject', [])
            model_label = request.session.get('rejection_model', 'purchases.purchaserequest')

            if not document_ids:
                messages.error(request, _('No documents found to reject.'))
                return redirect('admin:purchases_purchaserequest_changelist')

            # Намираме правилния модел
            if model_label == 'purchases.purchaserequest':
                documents = PurchaseRequest.objects.filter(id__in=document_ids)
            else:
                # Може да добавите други модели тук
                documents = PurchaseRequest.objects.filter(id__in=document_ids)

            # Отхвърляме документите
            rejected_count = 0
            failed_count = 0

            for document in documents:
                try:
                    result = ApprovalService.reject_document(
                        document=document,
                        user=request.user,
                        reason=reason
                    )

                    if result['success']:
                        rejected_count += 1
                    else:
                        failed_count += 1
                        messages.error(request, f"{document.document_number}: {result['message']}")

                except Exception as e:
                    failed_count += 1
                    messages.error(request, f"{document.document_number}: {str(e)}")

            # Показваме резултатите
            if rejected_count:
                messages.success(request, _('Successfully rejected %(count)d documents.') % {'count': rejected_count})

            if failed_count:
                messages.warning(request, _('%(count)d documents could not be rejected.') % {'count': failed_count})

            # Изчистваме session
            for key in ['documents_to_reject', 'rejection_model']:
                if key in request.session:
                    del request.session[key]

            return redirect('admin:purchases_purchaserequest_changelist')

        # GET заявка - показваме формата
        document_ids = request.session.get('documents_to_reject', [])
        if not document_ids:
            messages.error(request, _('No documents found to reject.'))
            return redirect('admin:purchases_purchaserequest_changelist')

        # Взимаме документите за показване
        documents = PurchaseRequest.objects.filter(id__in=document_ids)

        context = {
            'documents': documents,
            'title': _('Reject Documents'),
            'opts': self.model._meta,
        }

        return render(request, 'admin/purchases/rejection_form.html', context)


# =====================
# MAIN ADMIN CLASSES
# =====================
class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 0
    fields = ('line_number', 'product', 'unit', 'requested_quantity', 'estimated_price')
    readonly_fields = ()
    show_change_link = True

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(ApprovalActionMixin, CustomWorkflowUrlsMixin, admin.ModelAdmin):
    """Enhanced Purchase Request Admin с професионален ApprovalService"""
    inlines = [PurchaseRequestLineInline]
    list_display = [
       'document_type', 'document_number', 'supplier', 'status_display', 'urgency_display',
        'requested_by', 'lines_count', 'estimated_total_display',
        'workflow_status_display', 'available_actions_display', 'document_date'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'approval_required',
        'document_date', 'created_at', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'requested_by__first_name', 'requested_by__last_name'
    ]

    date_hierarchy = 'document_date'

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'estimated_total_display',
        'workflow_status_display', 'approval_chain_display'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
               'document_type', 'document_number', 'supplier', 'location', 'status',
                'document_date'
            )
        }),
        (_('Request Details'), {
            'fields': (
                'request_type', 'urgency_level', 'business_justification',
                'expected_usage'
            )
        }),
        (_('Workflow Status'), {
            'fields': (
                'workflow_status_display', 'approval_chain_display'
            ),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': (
                'created_at', 'updated_at', 'estimated_total_display'
            ),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            obj.requested_by = request.user  # <-- добави това
        super().save_model(request, obj, form, change)

    # =====================
    # DISPLAY METHODS
    # =====================

    def status_display(self, obj):
        """Colored status display"""
        colors = {
            'draft': '#6c757d',
            'submitted': '#ffc107',
            'regional_approved': '#17a2b8',
            'central_approved': '#28a745',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'converted': '#17a2b8',
            'cancelled': '#6c757d'
        }
        color = colors.get(obj.status, '#6c757d')

        display_status = obj.status.replace('_', ' ').title()

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, display_status
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        """Colored urgency display"""
        colors = {
            'low': '#28a745',
            'normal': '#6c757d',
            'high': '#ffc107',
            'critical': '#dc3545'
        }
        color = colors.get(obj.urgency_level, '#6c757d')
        return format_html(
            '<span style="color: {};">{}</span>',
            color, obj.get_urgency_level_display()
        )

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        """Number of lines in request"""
        return obj.lines.count()

    lines_count.short_description = _('Lines')

    def estimated_total_display(self, obj):
        """Display estimated total"""
        total = obj.get_estimated_total()
        if total:
            return format_html('<strong>{:.2f} BGN</strong>', total)
        return '-'

    estimated_total_display.short_description = _('Estimated Total')

    def workflow_status_display(self, obj):
        """Display workflow status using ApprovalService"""
        try:
            workflow_status = ApprovalService.get_workflow_status(obj)

            # Показваме текущия статус и прогреса
            current = workflow_status['current_status']
            levels = workflow_status['workflow_levels']

            if not levels:
                return format_html('<span style="color: gray;">No workflow defined</span>')

            # Създаваме прогрес бар
            progress_items = []
            for level in levels:
                if level['completed']:
                    progress_items.append(f"✅ {level['name']}")
                else:
                    progress_items.append(f"⏳ {level['name']}")

            progress_text = " → ".join(progress_items[:3])  # Показваме първите 3 нива

            return format_html(
                '<div title="{}"><strong>{}</strong><br><small>{}</small></div>',
                f"Current: {current}",
                current.title(),
                progress_text
            )

        except Exception as e:
            return format_html('<span style="color: red;">Error: {}</span>', str(e))

    workflow_status_display.short_description = _('Workflow Status')

    def available_actions_display(self, obj):
        """Display available actions for current user"""
        try:
            # Използваме заявката от request context
            if hasattr(self, '_current_request') and self._current_request:
                user = self._current_request.user
                transitions = ApprovalService.get_available_transitions(obj, user)

                if transitions:
                    actions = []
                    for t in transitions[:3]:  # Показваме първите 3 действия
                        action_name = t['to_status'].replace('_', ' ').title()
                        actions.append(action_name)

                    return format_html(
                        '<span style="color: blue; font-size: 0.9em;">🎯 {}</span>',
                        ', '.join(actions)
                    )
                else:
                    return format_html('<span style="color: gray; font-size: 0.9em;">No actions</span>')
            else:
                return "Login required"

        except Exception as e:
            return format_html('<span style="color: red; font-size: 0.9em;">Error</span>')

    available_actions_display.short_description = _('Available Actions')

    def approval_chain_display(self, obj):
        """Display approval chain information"""
        try:
            workflow_status = ApprovalService.get_workflow_status(obj)
            history = workflow_status['approval_history']

            if not history:
                return format_html('<em>No approval history</em>')

            history_items = []
            for entry in history[-5:]:  # Последните 5 записа
                timestamp = entry['timestamp'].strftime('%Y-%m-%d %H:%M')
                actor = entry['actor']
                action = entry['action']

                history_items.append(f"{timestamp}: {action} by {actor}")

            return format_html('<br>'.join(history_items))

        except Exception:
            return format_html('<em>Error loading history</em>')

    approval_chain_display.short_description = _('Approval Chain')

    def changelist_view(self, request, extra_context=None):
        """Override за да запазим request context"""
        self._current_request = request
        return super().changelist_view(request, extra_context)


# =====================
# ОСТАНАЛИТЕ ADMIN КЛАСОВЕ (ЗАПАЗВАМЕ СЪЩИТЕ)
# =====================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Admin for Purchase Orders"""

    list_display = [
        'document_number', 'supplier', 'status', 'is_urgent',
        'expected_delivery_date', 'grand_total_display'
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier_confirmed',
        'expected_delivery_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference'
    ]

    def grand_total_display(self, obj):
        if obj.grand_total:
            return format_html('<strong>{:.2f} BGN</strong>', obj.grand_total)
        return '-'

    grand_total_display.short_description = _('Total')


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Admin for Delivery Receipts"""

    list_display = [
        'document_number', 'supplier', 'status', 'delivery_date',
        'quality_status_display', 'grand_total_display'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'quality_checked',
        'delivery_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number'
    ]

    def grand_total_display(self, obj):
        if obj.grand_total:
            return format_html('<strong>{:.2f} BGN</strong>', obj.grand_total)
        return '-'

    grand_total_display.short_description = _('Total')

    def quality_status_display(self, obj):
        """Display quality status with icons"""
        if not obj.quality_checked:
            return format_html('<span style="color: orange;">⏳ Not Checked</span>')
        elif obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues Found</span>')
        elif obj.quality_approved:
            return format_html('<span style="color: green;">✅ Approved</span>')
        else:
            return format_html('<span style="color: red;">❌ Rejected</span>')

    quality_status_display.short_description = _('Quality Status')