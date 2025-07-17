# purchases/admin.py - ПОПРАВЕН С APPROVALSERVICE

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone

# НОВИ IMPORTS
from nomenclatures.services.approval_service import ApprovalService
from nomenclatures.admin.dynamic_actions import DynamicApprovalMixin

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine,
)


# =================================================================
# INLINE ADMINS (СЪЩИТЕ)
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'estimated_price', 'usage_description'
    ]
    readonly_fields = ['line_number']
    exclude = ['quantity']  # Скрий quantity от админа

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


# =================================================================
# PURCHASE REQUEST ADMIN - ПОПРАВЕН
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(DynamicApprovalMixin, admin.ModelAdmin):
    """Purchase Request Admin с ApprovalService интеграция"""

    list_display = [
        'document_number', 'requested_by', 'supplier', 'status_display',
        'urgency_display', 'lines_count', 'estimated_total', 'workflow_status_display'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'supplier',
        'location', 'created_at', 'approved_at'
    ]

    search_fields = [
        'document_number', 'requested_by__username', 'requested_by__first_name',
        'requested_by__last_name', 'supplier__name', 'business_justification'
    ]

    date_hierarchy = 'created_at'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'approved_at',
        'converted_at', 'request_analytics', 'workflow_status_display'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'requested_by', 'supplier', 'location',
                'status', 'urgency_level', 'request_type'
            )
        }),
        (_('Justification'), {
            'fields': (
                'business_justification', 'expected_usage'
            )
        }),
        (_('Approval Information'), {
            'fields': (
                'approved_by', 'approved_at', 'rejection_reason',
                'converted_to_order', 'converted_at', 'converted_by'
            ),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('request_analytics', 'workflow_status_display'),
            'classes': ('collapse',)
        }),
    )

    # ✅ НОВИ ACTIONS С APPROVALSERVICE
    def get_actions(self, request):
        """Override за да добавим ApprovalService actions"""
        actions = super().get_actions(request)  # Това вече включва DynamicApprovalMixin actions

        # Добавяме специфични purchase actions
        actions.update({
            'submit_for_approval': (self.submit_for_approval_action, 'submit_for_approval',
                                    'Submit selected requests for approval'),
            'quick_approve': (self.quick_approve_action, 'quick_approve',
                              'Quick approve selected requests'),
            'convert_to_orders': (self.convert_to_orders_action, 'convert_to_orders',
                                  'Convert approved requests to orders'),
        })

        return actions

    def submit_for_approval_action(self, request, queryset):
        """Action за изпращане за одобрение"""
        success_count = 0
        failed_count = 0

        for document in queryset:
            try:
                result = ApprovalService.execute_transition(
                    document=document,
                    to_status='submitted',
                    user=request.user,
                    comments=f"Submitted via admin by {request.user.get_full_name()}"
                )

                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully submitted {success_count} requests for approval.')
        if failed_count:
            messages.warning(request, f'{failed_count} requests could not be submitted.')

    def quick_approve_action(self, request, queryset):
        """Action за бързо одобрение"""
        success_count = 0
        failed_count = 0

        for document in queryset:
            try:
                # Намираме най-подходящия approval преход
                available_transitions = ApprovalService.get_available_transitions(document, request.user)
                approval_transitions = [t for t in available_transitions if 'approv' in t['to_status']]

                if approval_transitions:
                    target_status = approval_transitions[0]['to_status']

                    result = ApprovalService.execute_transition(
                        document=document,
                        to_status=target_status,
                        user=request.user,
                        comments=f"Quick approved via admin by {request.user.get_full_name()}"
                    )

                    if result['success']:
                        success_count += 1
                    else:
                        failed_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully approved {success_count} requests.')
        if failed_count:
            messages.warning(request, f'{failed_count} requests could not be approved.')

    def convert_to_orders_action(self, request, queryset):
        """Action за конвертиране към поръчки"""
        success_count = 0
        failed_count = 0

        for document in queryset:
            try:
                result = ApprovalService.execute_transition(
                    document=document,
                    to_status='converted',
                    user=request.user,
                    comments=f"Converted to order via admin by {request.user.get_full_name()}"
                )

                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully converted {success_count} requests to orders.')
        if failed_count:
            messages.warning(request, f'{failed_count} requests could not be converted.')

    # ✅ DISPLAY METHODS
    def status_display(self, obj):
        """Enhanced status display"""
        status_colors = {
            'draft': 'gray',
            'submitted': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'converted': 'blue',
        }
        color = status_colors.get(obj.status, 'black')

        # Manual status display since field doesn't have choices
        status_names = {
            'draft': 'Draft',
            'submitted': 'Submitted for Approval',
            'approved': 'Approved',
            'rejected': 'Rejected',
            'converted': 'Converted to Order',
        }
        status_name = status_names.get(obj.status, obj.status.title())

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, status_name
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        """Urgency with icons"""
        urgency_icons = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🟠',
            'critical': '🔴'
        }
        icon = urgency_icons.get(obj.urgency_level, '⚪')

        # Manual urgency display
        urgency_names = {
            'low': 'Low',
            'normal': 'Normal',
            'medium': 'Medium',
            'high': 'High',
            'critical': 'Critical'
        }
        urgency_name = urgency_names.get(obj.urgency_level, obj.urgency_level.title())

        return format_html('{} {}', icon, urgency_name)

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        """Number of lines"""
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def estimated_total(self, obj):
        """Estimated total amount"""
        try:
            total = sum(
                line.estimated_price * line.requested_quantity
                for line in obj.lines.all()
                if line.estimated_price
            )
            return format_html('<strong>{:.2f} лв</strong>', float(total))
        except:
            return '-'

    estimated_total.short_description = _('Estimated Total')

    def workflow_status_display(self, obj):
        """Workflow status via ApprovalService"""
        try:
            workflow_status = ApprovalService.get_workflow_status(obj)
            available_transitions = ApprovalService.get_available_transitions(obj, None)

            if workflow_status['is_completed']:
                return format_html('<span style="color: green;">✅ Completed</span>')
            elif available_transitions:
                return format_html(
                    '<span style="color: orange;">⏳ {} actions available</span>',
                    len(available_transitions)
                )
            else:
                return format_html('<span style="color: gray;">⏸️ No actions</span>')
        except:
            return '-'

    workflow_status_display.short_description = _('Workflow Status')

    def request_analytics(self, obj):
        """Request analytics"""
        if not obj.pk:
            return "Save request first to see analytics"

        lines_count = obj.lines.count()
        total_items = sum(line.requested_quantity for line in obj.lines.all())

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.status.title()}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total Items:</strong> {total_items}",
            f"<strong>Urgency:</strong> {obj.urgency_level.title()}",
        ]

        if obj.requested_by:
            analysis_parts.append(f"<strong>Requested By:</strong> {obj.requested_by.get_full_name()}")

        if obj.approved_by:
            analysis_parts.append(f"<strong>Approved By:</strong> {obj.approved_by.get_full_name()}")

        return mark_safe('<br>'.join(analysis_parts))

    request_analytics.short_description = _('Request Analytics')


# =================================================================
# PURCHASE ORDER ADMIN (същия, без промени засега)
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Админ за поръчки - ще се оправи в следващия етап"""
    pass  # TODO: Ще се оправи след RequestService


# =================================================================
# DELIVERY ADMIN (същия, без промени засега)
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Админ за доставки - ще се оправи в следващия етап"""
    pass  # TODO: Ще се оправи след RequestService