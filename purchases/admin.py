# purchases/admin.py - CLEAN VERSION БЕЗ КАШОТИНА

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum
from django.utils import timezone

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine,
)

# ДОБАВИ import за WorkflowService
from purchases.services.workflow_service import WorkflowService

# Import DynamicPurchaseRequestAdmin ако го използваме
from nomenclatures.admin.dynamic_actions import DynamicPurchaseRequestAdmin


# =================================================================
# INLINE ADMINS
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'entered_price', 'suggested_supplier', 'priority'  # ✅ FIXED: entered_price
    ]
    readonly_fields = ['line_number', 'net_amount', 'vat_amount', 'gross_amount']  # ✅ NEW financial fields

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'line_number', 'product', 'ordered_quantity', 'unit', 'entered_price',  # ✅ FIXED: entered_price
        'discount_percent', 'net_amount', 'vat_amount', 'gross_amount'  # ✅ NEW financial fields
    ]
    readonly_fields = ['line_number', 'unit_price', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'line_number', 'product', 'received_quantity', 'unit', 'entered_price',  # ✅ FIXED: entered_price
        'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['line_number', 'unit_price', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


# =================================================================
# PURCHASE REQUEST ADMIN - CLEAN VERSION
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(DynamicPurchaseRequestAdmin):
    """
    Професионален admin за Purchase Requests

    Наследява DynamicPurchaseRequestAdmin за автоматични workflow actions
    + добавя специфични WorkflowService actions
    """

    list_display = [
        'document_number', 'supplier', 'status_display', 'urgency_level',
        'total_display',
        'workflow_actions_display',
        'requested_by', 'created_at'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type',
        'approval_required', 'created_at', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'requested_by__username',
        'business_justification', 'notes'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'vat_total', 'total',  # ✅ FIXED: financial fields
        'converted_to_order', 'converted_at', 'converted_by'
    ]

    fieldsets = [
        (_('Document Info'), {
            'fields': ('document_number', 'document_type', 'status', 'external_reference')
        }),
        (_('Request Details'), {
            'fields': (
                'supplier', 'location', 'request_type', 'urgency_level',
                'business_justification', 'expected_usage'
            )
        }),
        (_('Financial Summary'), {  # ✅ NEW: financial section
            'fields': ('subtotal', 'vat_total', 'total'),
            'classes': ('collapse',)
        }),
        (_('Approval Workflow'), {
            'fields': (
                'approval_required', 'requested_by', 'approved_by', 'approved_at',
                'rejection_reason'
            )
        }),
        (_('Conversion Tracking'), {
            'fields': ('converted_to_order', 'converted_at', 'converted_by'),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]

    inlines = [PurchaseRequestLineInline]

    actions = [
        'workflow_submit_requests',
        'workflow_approve_requests',
        'workflow_reject_requests',
        'show_workflow_status'
    ]

    def workflow_submit_requests(self, request, queryset):
        """Submit selected requests using WorkflowService"""
        success_count = 0
        error_count = 0

        for purchase_request in queryset:
            result = WorkflowService.transition_document(
                purchase_request, 'submitted', request.user
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {purchase_request.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"📤 Successfully submitted {success_count} requests")

        if error_count > 0:
            self.message_user(request, f"❌ Failed to submit {error_count} requests", level='ERROR')

    workflow_submit_requests.short_description = "📤 Submit via WorkflowService"


    def workflow_approve_requests(self, request, queryset):
        """Approve selected requests using WorkflowService"""
        success_count = 0
        error_count = 0

        for purchase_request in queryset:
            result = WorkflowService.transition_document(
                purchase_request, 'approved', request.user,
                comments="Approved via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {purchase_request.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"✅ Successfully approved {success_count} requests")

    workflow_approve_requests.short_description = "✅ Approve via WorkflowService"

    def workflow_reject_requests(self, request, queryset):
        """Reject selected requests using WorkflowService"""
        success_count = 0
        error_count = 0

        for purchase_request in queryset:
            result = WorkflowService.transition_document(
                purchase_request, 'rejected', request.user,
                reason="Rejected via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {purchase_request.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"❌ Successfully rejected {success_count} requests")

    workflow_reject_requests.short_description = "❌ Reject via WorkflowService"

    def show_workflow_status(self, request, queryset):
        """Show workflow status for selected documents"""
        for document in queryset:
            available_actions = WorkflowService.get_available_transitions(document, request.user)

            action_list = []
            for action in available_actions:
                status_icon = "✅" if action['can_transition'] else "❌"
                reason = f" ({action['reason']})" if action.get('reason') else ""
                action_list.append(f"{status_icon} {action['to_status']}{reason}")

            actions_text = ", ".join(action_list) if action_list else "No actions available"

            self.message_user(
                request,
                f"📋 {document.document_number} (Status: {document.status}): {actions_text}"
            )

    show_workflow_status.short_description = "📊 Show WorkflowService status"

    def workflow_actions_display(self, obj):
        """Shows available workflow actions for this document"""
        available = WorkflowService.get_available_transitions(obj, None)

        if available:
            next_actions = [a['to_status'] for a in available if a['can_transition']]
            if next_actions:
                return format_html(
                    '<span style="color: #007cba; font-weight: bold;">→ {}</span>',
                    next_actions[0]
                )
            else:
                return format_html('<span style="color: #ffc107;">⏳ Pending</span>')

        return format_html('<span style="color: #28a745;">✅ Final</span>')

    workflow_actions_display.short_description = 'Next Action (WS)'
    workflow_actions_display.admin_order_field = 'status'

    def total_display(self, obj):
        """Display financial total"""
        if hasattr(obj, 'total') and obj.total:
            return f"€{obj.total:,.2f}"
        return "-"

    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'


# =================================================================
# PURCHASE ORDER ADMIN - FIXED INHERITANCE
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):  # ✅ FIXED: Наследява admin.ModelAdmin, не DynamicPurchaseRequestAdmin!
    """Професионален admin за Purchase Orders"""

    list_display = [
        'document_number', 'supplier', 'status', 'is_urgent',
        'total_display',  # ✅ FIXED: total field
        'workflow_actions_display',  # ✅ NEW: WorkflowService actions
        'expected_delivery_date'
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier_confirmed', 'supplier',
        'location', 'expected_delivery_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'discount_total', 'vat_total', 'total'  # ✅ FIXED: total
    ]

    fieldsets = [
        (_('Document Info'), {
            'fields': ('document_number', 'document_type', 'status')
        }),
        (_('Order Details'), {
            'fields': (
                'supplier', 'location', 'is_urgent',
                'document_date', 'expected_delivery_date',
                'supplier_order_reference', 'supplier_confirmed'
            )
        }),
        (_('Financial Summary'), {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),  # ✅ FIXED
            'classes': ('collapse',)
        }),
        (_('Source Information'), {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]

    inlines = [PurchaseOrderLineInline]

    actions = [
        'workflow_confirm_orders', 'workflow_cancel_orders', 'show_workflow_status'
    ]

    # ✅ WorkflowService actions за Orders
    def workflow_confirm_orders(self, request, queryset):
        """
        ✅ SMART: Confirm orders - skip already confirmed
        """
        success_count = 0
        error_count = 0
        skipped_count = 0

        for order in queryset:
            # ✅ SMART: Skip already confirmed orders
            if order.status == 'confirmed':
                skipped_count += 1
                continue

            # Try to confirm
            result = WorkflowService.transition_document(
                order, 'confirmed', request.user,
                comments="Confirmed via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {order.document_number}: {result['message']}",
                    level='ERROR'
                )

        # Summary messages
        if success_count > 0:
            self.message_user(request, f"✅ Successfully confirmed {success_count} orders")

        if skipped_count > 0:
            self.message_user(request, f"⏭️ Skipped {skipped_count} already confirmed orders")

        if error_count > 0:
            self.message_user(request, f"❌ Failed to confirm {error_count} orders", level='ERROR')

    workflow_confirm_orders.short_description = "✅ Smart Confirm via WorkflowService"



    def workflow_cancel_orders(self, request, queryset):
        """Cancel selected orders using WorkflowService"""
        success_count = 0
        error_count = 0

        for order in queryset:
            result = WorkflowService.transition_document(
                order, 'cancelled', request.user,
                comments="Cancelled via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {order.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"❌ Successfully cancelled {success_count} orders")

    workflow_cancel_orders.short_description = "❌ Cancel via WorkflowService"

    def show_workflow_status(self, request, queryset):
        """Show workflow status for selected documents - same as requests"""
        for document in queryset:
            available_actions = WorkflowService.get_available_transitions(document, request.user)

            action_list = []
            for action in available_actions:
                status_icon = "✅" if action['can_transition'] else "❌"
                reason = f" ({action['reason']})" if action.get('reason') else ""
                action_list.append(f"{status_icon} {action['to_status']}{reason}")

            actions_text = ", ".join(action_list) if action_list else "No actions available"

            self.message_user(
                request,
                f"📋 {document.document_number} (Status: {document.status}): {actions_text}"
            )

    show_workflow_status.short_description = "📊 Show WorkflowService status"

    def workflow_actions_display(self, obj):
        """Shows available workflow actions - same as requests"""
        available = WorkflowService.get_available_transitions(obj, None)

        if available:
            next_actions = [a['to_status'] for a in available if a['can_transition']]
            if next_actions:
                return format_html(
                    '<span style="color: #007cba; font-weight: bold;">→ {}</span>',
                    next_actions[0]
                )
            else:
                return format_html('<span style="color: #ffc107;">⏳ Pending</span>')

        return format_html('<span style="color: #28a745;">✅ Final</span>')

    workflow_actions_display.short_description = 'Next Action (WS)'
    workflow_actions_display.admin_order_field = 'status'

    def total_display(self, obj):
        """Display financial total"""
        if hasattr(obj, 'total') and obj.total:
            return f"€{obj.total:,.2f}"
        return "-"

    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'


# =================================================================
# DELIVERY RECEIPT ADMIN
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Професионален admin за Delivery Receipts"""

    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status',
        'total_display',  # ✅ FIXED: total field
        'workflow_actions_display',  # ✅ NEW: WorkflowService actions
        'has_quality_issues', 'has_variances'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'has_variances', 'quality_checked',
        'delivery_date', 'supplier', 'location'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number',
        'vehicle_info', 'driver_name'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'discount_total', 'vat_total', 'total'  # ✅ FIXED: total
    ]

    fieldsets = [
        (_('Document Info'), {
            'fields': ('document_number', 'document_type', 'status')
        }),
        (_('Delivery Details'), {
            'fields': (
                'supplier', 'location', 'delivery_date',
                'delivery_note_number', 'vehicle_info', 'driver_name'
            )
        }),
        (_('Financial Summary'), {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),  # ✅ FIXED
            'classes': ('collapse',)
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_checked', 'has_quality_issues', 'quality_inspector',
                'quality_notes'
            ),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]

    inlines = [DeliveryLineInline]

    actions = [
        'workflow_receive_deliveries', 'workflow_complete_deliveries', 'show_workflow_status'
    ]

    # ✅ WorkflowService actions за Deliveries
    def workflow_receive_deliveries(self, request, queryset):
        """Mark deliveries as received using WorkflowService"""
        success_count = 0
        error_count = 0

        for delivery in queryset:
            result = WorkflowService.transition_document(
                delivery, 'received', request.user,
                comments="Received via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {delivery.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"📦 Successfully received {success_count} deliveries")

    workflow_receive_deliveries.short_description = "📦 Receive via WorkflowService"

    def workflow_complete_deliveries(self, request, queryset):
        """Complete deliveries using WorkflowService"""
        success_count = 0
        error_count = 0

        for delivery in queryset:
            result = WorkflowService.transition_document(
                delivery, 'completed', request.user,
                comments="Completed via admin bulk action"
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ {delivery.document_number}: {result['message']}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(request, f"✅ Successfully completed {success_count} deliveries")

    workflow_complete_deliveries.short_description = "✅ Complete via WorkflowService"

    # Copy workflow_actions_display и show_workflow_status методите от другите admin класове
    def workflow_actions_display(self, obj):
        """Shows available workflow actions"""
        available = WorkflowService.get_available_transitions(obj, None)

        if available:
            next_actions = [a['to_status'] for a in available if a['can_transition']]
            if next_actions:
                return format_html(
                    '<span style="color: #007cba; font-weight: bold;">→ {}</span>',
                    next_actions[0]
                )
            else:
                return format_html('<span style="color: #ffc107;">⏳ Pending</span>')

        return format_html('<span style="color: #28a745;">✅ Final</span>')

    workflow_actions_display.short_description = 'Next Action (WS)'
    workflow_actions_display.admin_order_field = 'status'

    def show_workflow_status(self, request, queryset):
        """Show workflow status for selected documents"""
        for document in queryset:
            available_actions = WorkflowService.get_available_transitions(document, request.user)

            action_list = []
            for action in available_actions:
                status_icon = "✅" if action['can_transition'] else "❌"
                reason = f" ({action['reason']})" if action.get('reason') else ""
                action_list.append(f"{status_icon} {action['to_status']}{reason}")

            actions_text = ", ".join(action_list) if action_list else "No actions available"

            self.message_user(
                request,
                f"📋 {document.document_number} (Status: {document.status}): {actions_text}"
            )

    show_workflow_status.short_description = "📊 Show WorkflowService status"

    def total_display(self, obj):
        """Display financial total"""
        if hasattr(obj, 'total') and obj.total:
            return f"€{obj.total:,.2f}"
        return "-"

    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'


# =================================================================
# LINE ADMINS - OPTIONAL
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Админ за редове от заявки"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'entered_price', 'total_display'  # ✅ FIXED: entered_price
    ]

    list_filter = ['document__status', 'suggested_supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    def total_display(self, obj):
        if hasattr(obj, 'gross_amount') and obj.gross_amount:
            return f"€{obj.gross_amount:,.2f}"
        return "-"

    total_display.short_description = 'Line Total'


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    """Админ за редове от поръчки"""

    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'entered_price', 'total_display'  # ✅ FIXED
    ]

    list_filter = ['document__status', 'delivery_status']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    def total_display(self, obj):
        if hasattr(obj, 'gross_amount') and obj.gross_amount:
            return f"€{obj.gross_amount:,.2f}"
        return "-"

    total_display.short_description = 'Line Total'


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    """Админ за редове от доставки"""

    list_display = [
        'document', 'line_number', 'product', 'received_quantity',
        'entered_price', 'quality_status', 'batch_number'  # ✅ FIXED
    ]

    list_filter = [
        'quality_approved', 'document__status', 'document__supplier',
        'expiry_date'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number',
        'document__document_number'
    ]

    def quality_status(self, obj):
        if obj.quality_approved:
            return format_html('<span style="color: green;">✅ Approved</span>')
        else:
            return format_html('<span style="color: red;">❌ Rejected</span>')

    quality_status.short_description = _('Quality')