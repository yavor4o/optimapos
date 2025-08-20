# purchases/admin/deliveries.py

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from ..models import DeliveryReceipt, DeliveryLine


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = (
        'line_number',
        'product',
        'received_quantity',
        'unit',
        'unit_price',
        'get_expected_quantity',  # <-- КОРЕКЦИЯ
        'get_variance_quantity',  # <-- КОРЕКЦИЯ
        'batch_number',
        'expiry_date'
    )

    readonly_fields = (
        'get_expected_quantity',  # <-- КОРЕКЦИЯ
        'get_variance_quantity'  # <-- КОРЕКЦИЯ
    )

    @admin.display(description='Expected Qty')
    def get_expected_quantity(self, obj):
        # obj тук е инстанция на DeliveryLine
        if obj and hasattr(obj, 'expected_quantity'):
            # Проверяваме дали полето съществува, преди да го достъпим
            return obj.expected_quantity
        return "N/A"

    @admin.display(description='Variance')
    def get_variance_quantity(self, obj):
        if obj and hasattr(obj, 'variance_quantity'):
            return obj.variance_quantity
        return "N/A"


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = (
        'document_number', 'supplier', 'delivery_date', 'status', 'quality_status', 'total'
    )
    list_filter = ('status', 'quality_status', 'supplier', 'location', 'delivery_date')
    search_fields = ('document_number', 'supplier__name', 'supplier_delivery_reference')
    readonly_fields = (
        'document_number', 'status', 'created_by', 'created_at',
        'updated_by', 'updated_at', 'source_order', 'quality_checked_by', 'quality_checked_at'
    )

    inlines = [DeliveryLineInline]
    actions = ['process_quality_control_action', 'create_movements_action']

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        if instances and hasattr(instances[0].document, 'recalculate_totals'):
            document = instances[0].document
            document.recalculate_totals()
            if hasattr(document, 'update_source_order_status'):
                document.update_source_order_status()
        super().save_formset(request, form, formset, change)

    # --- ADMIN ACTIONS ---
    @admin.action(description='Process Quality Control (Approve All)')
    def process_quality_control_action(self, request, queryset):
        for delivery in queryset:
            try:
                delivery.approve_all_quality(user=request.user)
                self.message_user(request, f"Successfully processed QC for {delivery.document_number}.",
                                  messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Error processing QC for {delivery.document_number}: {e}", messages.ERROR)

    @admin.action(description='Create Inventory Movements from selected deliveries')
    def create_movements_action(self, request, queryset):
        for delivery in queryset:
            try:
                movements_count = delivery.create_inventory_movements(user=request.user)
                self.message_user(request, f"Created {movements_count} movements for {delivery.document_number}.",
                                  messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Error creating movements for {delivery.document_number}: {e}",
                                  messages.ERROR)