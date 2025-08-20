# purchases/admin/orders.py

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from ..models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ('line_number', 'product', 'ordered_quantity', 'unit', 'unit_price', 'get_line_total',
              'get_delivered_quantity', 'get_remaining_quantity', 'notes')
    readonly_fields = ('get_line_total', 'get_delivered_quantity', 'get_remaining_quantity')

    @admin.display(description='Line Total')
    def get_line_total(self, obj):
        return obj.line_total if obj else 'N/A'

    @admin.display(description='Delivered Qty')
    def get_delivered_quantity(self, obj):
        return obj.delivered_quantity if obj else 'N/A'

    @admin.display(description='Remaining Qty')
    def get_remaining_quantity(self, obj):
        return obj.remaining_quantity if obj else 'N/A'


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        'document_number', 'supplier', 'status', 'delivery_status',
        'total', 'expected_delivery_date', 'is_overdue'
    )
    list_filter = ('status', 'delivery_status', 'supplier', 'location', 'is_urgent')
    search_fields = ('document_number', 'supplier__name', 'supplier_order_reference')
    readonly_fields = (
        'document_number', 'status', 'delivery_status', 'supplier_confirmed',
        'sent_by', 'sent_to_supplier_at', 'created_by', 'created_at',
        'updated_by', 'updated_at', 'source_request'
    )

    fieldsets = (
        ('General Information', {
            'fields': ('document_number', 'document_date', 'status', 'supplier', 'location', 'source_request')
        }),
        ('Order Details', {
            'fields': ('expected_delivery_date', 'is_urgent', 'notes')
        }),
        ('Supplier Interaction', {
            'fields': ('supplier_order_reference', 'supplier_confirmed', 'supplier_confirmed_date', 'sent_by',
                       'sent_to_supplier_at')
        }),
        ('Financials', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total')
        }),
        ('Audit Trail', {
            'fields': ('created_by', 'created_at', 'updated_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseOrderLineInline]
    actions = ['send_to_supplier_action', 'confirm_order_action', 'create_delivery_action']

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
    @admin.action(description='Send selected orders to supplier')
    def send_to_supplier_action(self, request, queryset):
        success_count = 0
        for order in queryset:
            try:
                order.send_to_supplier(user=request.user)
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error sending {order.document_number}: {e}", messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully sent {success_count} orders.", messages.SUCCESS)

    @admin.action(description='Mark selected orders as Confirmed by supplier')
    def confirm_order_action(self, request, queryset):
        success_count = 0
        for order in queryset:
            try:
                order.confirm_order(user=request.user, supplier_reference="Confirmed via Admin")
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error confirming {order.document_number}: {e}", messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully confirmed {success_count} orders.", messages.SUCCESS)

    @admin.action(description='Create Delivery Receipts from selected orders')
    def create_delivery_action(self, request, queryset):
        for order in queryset:
            try:
                delivery = order.create_delivery(user=request.user)
                self.message_user(request,
                                  f"Created Delivery {delivery.document_number} from Order {order.document_number}.",
                                  messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Error creating delivery for {order.document_number}: {e}", messages.ERROR)