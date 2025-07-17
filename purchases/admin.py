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

class ApprovalActionMixin:
    """Mixin for adding dynamic approval actions to admin"""

    def get_actions(self, request):
        """Динамично генериране на actions според ApprovalService"""
        actions = super().get_actions(request)

        # Добавяме динамични approval actions
        approval_actions = self._generate_approval_actions(request)
        actions.update(approval_actions)

        return actions

    def _generate_approval_actions(self, request):
        """Генерира approval actions динамично"""
        actions = {}

        # Универсален approval action
        def create_universal_approval_action():
            def universal_approval_action(modeladmin, request, queryset):
                """Универсално одобрение - намира най-подходящия преход"""

                success_count = 0
                failed_count = 0
                errors = []

                for document in queryset:
                    try:
                        # Намираме възможните преходи за този потребител
                        available_transitions = ApprovalService.get_available_transitions(document, request.user)

                        if not available_transitions:
                            failed_count += 1
                            errors.append(f"{document.document_number}: No available transitions")
                            continue

                        # Взимаме първия approval преход (може да се усложни логиката)
                        approval_transitions = [t for t in available_transitions if 'approv' in t['to_status'].lower()]

                        if approval_transitions:
                            transition = approval_transitions[0]
                        else:
                            transition = available_transitions[0]

                        # Изпълняваме прехода
                        result = ApprovalService.execute_transition(
                            document=document,
                            to_status=transition['to_status'],
                            user=request.user,
                            comments=f"Bulk approval via admin by {request.user.get_full_name()}"
                        )

                        if result['success']:
                            success_count += 1
                        else:
                            failed_count += 1
                            errors.append(f"{document.document_number}: {result['message']}")

                    except Exception as e:
                        failed_count += 1
                        errors.append(f"{document.document_number}: {str(e)}")

                # Показваме резултатите
                if success_count:
                    messages.success(request,
                                     _('Successfully processed %(count)d documents.') % {'count': success_count})

                if failed_count:
                    messages.warning(request,
                                     _('%(count)d documents could not be processed.') % {'count': failed_count})

                    # Показваме първите няколко грешки
                    for error in errors[:3]:
                        messages.error(request, error)

            universal_approval_action.short_description = _('🚀 Smart Approve - Auto detect best action')
            return universal_approval_action

        # Rejection action
        def create_rejection_action():
            def rejection_action(modeladmin, request, queryset):
                """Отхвърляне на документи"""

                # Съхраняваме IDs в session за custom view
                request.session['documents_to_reject'] = list(queryset.values_list('id', flat=True))
                request.session['rejection_model'] = queryset.model._meta.label_lower

                # Redirect към custom rejection view
                return redirect('admin:purchases_rejection_view')

            rejection_action.short_description = _('❌ Reject with reason')
            return rejection_action

        # Workflow status action
        def create_workflow_status_action():
            def workflow_status_action(modeladmin, request, queryset):
                """Показва workflow статус на документите"""

                for document in queryset:
                    try:
                        workflow_status = ApprovalService.get_workflow_status(document)
                        available_transitions = ApprovalService.get_available_transitions(document, request.user)

                        # Форматираме съобщението
                        status_msg = f"📄 {document.document_number}: {workflow_status['current_status']}"

                        if available_transitions:
                            actions = [t['to_status'] for t in available_transitions]
                            status_msg += f" → Available: {', '.join(actions)}"
                        else:
                            status_msg += " → No actions available"

                        messages.info(request, status_msg)

                    except Exception as e:
                        messages.error(request, f"Error for {document.document_number}: {str(e)}")

            workflow_status_action.short_description = _('📊 Show workflow status')
            return workflow_status_action

        # Добавяме действията
        actions['universal_approval'] = create_universal_approval_action()
        actions['reject_with_reason'] = create_rejection_action()
        actions['show_workflow_status'] = create_workflow_status_action()

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

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(ApprovalActionMixin, CustomWorkflowUrlsMixin, admin.ModelAdmin):
    """Enhanced Purchase Request Admin с професионален ApprovalService"""

    list_display = [
        'document_number', 'supplier', 'status_display', 'urgency_display',
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
                'document_number', 'supplier', 'location', 'status',
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