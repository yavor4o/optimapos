# purchases/admin/requests.py

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from ..models import PurchaseRequest, PurchaseRequestLine


class PurchaseRequestLineInline(admin.TabularInline):
    """
    Inline editor for PurchaseRequestLine.
    Allows adding/editing lines directly within a PurchaseRequest.
    """
    model = PurchaseRequestLine
    extra = 1
    fields = (
        'line_number', 'product', 'requested_quantity',
        'unit', 'estimated_price', 'get_line_total', 'notes'
    )
    readonly_fields = ('get_line_total',)

    @admin.display(description='Line Total')
    def get_line_total(self, obj):
        return obj.line_total if obj else 'N/A'


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """
    Enhanced Admin for PurchaseRequest with workflow actions.
    """
    list_display = (
        'document_number', 'supplier', 'location', 'status',
        'total_estimated_cost', 'created_by', 'created_at', 'is_converted'
    )
    list_filter = ('status', 'location', 'supplier', 'priority')
    search_fields = ('document_number', 'supplier__name', 'notes')
    readonly_fields = (
        'document_number', 'status', 'created_by', 'created_at',
        'updated_by', 'updated_at', 'approved_by', 'approved_at',
        'converted_to_order', 'converted_at', 'converted_by'
    )

    fieldsets = (
        ('General Information', {
            'fields': ('document_number', 'document_date', 'status', 'supplier', 'location','document_type')
        }),
        ('Request Details', {
            'fields': ('priority', 'required_by_date', 'notes')
        }),
        ('Approval & Conversion', {
            'fields': ('approved_by', 'approved_at', 'rejection_reason', 'converted_to_order')
        }),
        ('Audit Trail', {
            'fields': ('created_by', 'created_at', 'updated_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseRequestLineInline]
    actions = ['submit_for_approval_action', 'approve_action', 'reject_action', 'convert_to_order_action']

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        if instances and hasattr(instances[0].document, 'recalculate_totals'):
            instances[0].document.recalculate_totals()
        super().save_formset(request, form, formset, change)

    # --- ADMIN ACTIONS ---
    @admin.action(description='Submit selected requests for approval')
    def submit_for_approval_action(self, request, queryset):
        success_count = 0
        for req in queryset:
            try:
                req.submit_for_approval(user=request.user)
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error submitting {req.document_number}: {e}", messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully submitted {success_count} requests for approval.",
                              messages.SUCCESS)

    @admin.action(description='Approve selected requests')
    def approve_action(self, request, queryset):
        success_count = 0
        for req in queryset:
            try:
                req.approve(user=request.user, notes="Approved via Admin Panel")
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error approving {req.document_number}: {e}", messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully approved {success_count} requests.", messages.SUCCESS)

    @admin.action(description='Reject selected requests')
    def reject_action(self, request, queryset):
        success_count = 0
        for req in queryset:
            try:
                req.reject(user=request.user, reason="Rejected via Admin Panel")
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error rejecting {req.document_number}: {e}", messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully rejected {success_count} requests.", messages.SUCCESS)

    @admin.action(description='Convert selected requests to Purchase Orders')
    def convert_to_order_action(self, request, queryset):
        for req in queryset:
            try:
                order = req.convert_to_order(user=request.user)
                self.message_user(request,
                                  f"Successfully converted {req.document_number} to Order {order.document_number}.",
                                  messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Error converting {req.document_number}: {e}", messages.ERROR)