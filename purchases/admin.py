# purchases/admin.py - CORRECTED VERSION
"""
Admin класове коригирани според реалните полета в моделите
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from decimal import Decimal

from .models import (

    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)
from .models.requests import PurchaseRequestLine, PurchaseRequest


# ================================================================================
# PURCHASE REQUEST
# ================================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    """Inline за PurchaseRequest lines"""
    model = PurchaseRequestLine
    extra = 1

    fields = (
        'line_number',
        'product',
        'requested_quantity',
        'unit',
        'estimated_price',  # Вместо entered_price за requests
        'suggested_supplier',
        'priority',
        'item_justification',
    )

    readonly_fields = ('line_number',)
    autocomplete_fields = ['product', 'suggested_supplier']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('product', 'suggested_supplier')


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Admin за PurchaseRequest"""

    list_display = (
        'document_number',
        'supplier',
        'location',
        'status',
        'urgency_level',  # Има в модела
        'requested_by',  # Има в модела
        'created_at',
    )

    list_filter = (
        'status',
        'urgency_level',  # Има в модела
        'location',
        'created_at',
    )

    search_fields = (
        'document_number',
        'supplier__name',
        'supplier__code',
        'requested_by__username',

    )

    readonly_fields = (
        'document_number',
        'status',
        'created_by',
        'created_at',
        'updated_by',
        'updated_at',
        'approved_by',
        'approved_at',
        'converted_to_order',
        'converted_at',
        'converted_by',
    )

    fieldsets = (
        (_('Document Info'), {
            'fields': (
                'document_number',
                'status',
                'document_type',
            )
        }),
        (_('Request Details'), {
            'fields': (
                'supplier',
                'location',
                'urgency_level',
                'request_type',
                'requested_by',
            )
        }),
        (_('Justification'), {
            'fields': (

                'expected_usage',

            )
        }),
        (_('Approval'), {
            'fields': (
                'approval_required',
                'approved_by',
                'approved_at',
                'rejection_reason',
            ),
            'classes': ('collapse',)
        }),
        (_('Conversion'), {
            'fields': (
                'converted_to_order',
                'converted_at',
                'converted_by',
            ),
            'classes': ('collapse',)
        }),
        (_('System'), {
            'fields': (
                'created_by',
                'created_at',
                'updated_by',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseRequestLineInline]
    autocomplete_fields = ['supplier', 'location', 'requested_by']
    date_hierarchy = 'created_at'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            if not obj.requested_by:
                obj.requested_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Standalone admin за PurchaseRequestLine"""

    list_display = (
        'line_number',
        'document',
        'product',
        'requested_quantity',
        'estimated_price',
        'priority',
    )

    list_filter = (
        'priority',
        'document__status',
    )

    search_fields = (
        'document__document_number',
        'product__name',
        'product__code',
    )

    readonly_fields = ('line_number',)

    fieldsets = (
        (_('Document'), {
            'fields': ('document', 'line_number')
        }),
        (_('Product'), {
            'fields': (
                'product',
                'requested_quantity',
                'unit',
            )
        }),
        (_('Pricing'), {
            'fields': (
                'estimated_price',
            )
        }),
        (_('Additional'), {
            'fields': (
                'suggested_supplier',
                'priority',
                'item_justification',
            )
        }),
    )

    autocomplete_fields = ['document', 'product', 'suggested_supplier']


# ================================================================================
# PURCHASE ORDER
# ================================================================================

class PurchaseOrderLineInline(admin.TabularInline):
    """Inline за PurchaseOrder lines"""
    model = PurchaseOrderLine
    extra = 0

    fields = (
        'line_number',
        'product',
        'ordered_quantity',
        'confirmed_quantity',
        'unit',
        'unit_price',
        'vat_rate',
        'line_subtotal',
        'line_total',
        'delivered_quantity',
        'delivery_status',
    )

    readonly_fields = (
        'line_number',
        'delivered_quantity',
        'delivery_status',
        'line_subtotal',
        'line_total',
    )

    autocomplete_fields = ['product']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Admin за PurchaseOrder"""

    list_display = (
        'document_number',
        'supplier',
        'location',
        'status',
        'expected_delivery_date',  # Има в модела
        'total',
        'delivery_status',  # Има в модела
        'created_by',
    )

    list_filter = (
        'status',
        'delivery_status',  # Има в модела
        'location',
        'expected_delivery_date',  # Има в модела
        'created_at',
    )

    search_fields = (
        'document_number',
        'supplier__name',
        'supplier__code',
        'supplier_order_reference',
    )

    readonly_fields = (
        'document_number',
        'status',
        'delivery_status',
        'subtotal',
        'vat_total',
        'discount_total',
        'total',
        'created_by',
        'created_at',
        'updated_by',
        'updated_at',
    )

    fieldsets = (
        (_('Document Info'), {
            'fields': (
                'document_number',
                'status',
                'delivery_status',
                'document_type',
                'source_request',
            )
        }),
        (_('Supplier & Dates'), {
            'fields': (
                'supplier',
                'location',
                'document_date',
                'expected_delivery_date',
                'supplier_order_reference',
            )
        }),
        (_('Order Details'), {
            'fields': (
                'order_method',
                'is_urgent',
                'supplier_confirmed',
                'confirmation_date',
                'external_reference',
            )
        }),
        (_('Financial'), {
            'fields': (
                'prices_entered_with_vat',
                'payment_terms',
                'subtotal',
                'discount_total',
                'vat_total',
                'total',
            )
        }),
        (_('Notes'), {
            'fields': (
                'notes',
                'internal_notes',
            )
        }),
        (_('System'), {
            'fields': (
                'created_by',
                'created_at',
                'updated_by',
                'updated_at',
                'sent_at',
                'sent_by',
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseOrderLineInline]
    autocomplete_fields = ['supplier', 'location', 'source_request']
    date_hierarchy = 'expected_delivery_date'  # Има в модела

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()
        formset.save_m2m()

        # Recalculate totals
        if formset.model == PurchaseOrderLine:
            form.instance.recalculate_totals()


# ================================================================================
# DELIVERY RECEIPT
# ================================================================================

class DeliveryLineInline(admin.TabularInline):
    """Inline за DeliveryReceipt lines"""
    model = DeliveryLine
    extra = 0

    fields = (
        'line_number',
        'product',
        'received_quantity',
        'expected_quantity',
        'variance_quantity',
        'unit',
        'unit_price',
        'line_total',
        'batch_number',
        'expiry_date',
    )

    readonly_fields = (
        'line_number',
        'variance_quantity',
        'line_total',
    )

    autocomplete_fields = ['product']


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Admin за DeliveryReceipt"""

    list_display = (
        'document_number',
        'supplier',
        'location',
        'status',
        'delivery_date',
        'quality_checked',  # Има в модела
        'total',
        'created_by',
    )

    list_filter = (
        'status',
        'quality_checked',  # Има в модела
        'has_quality_issues',  # Има в модела
        'location',
        'delivery_date',
        'created_at',
    )

    search_fields = (
        'document_number',
        'supplier__name',
        'delivery_note_number',
        'driver_name',
    )

    readonly_fields = (
        'document_number',
        'status',
        'subtotal',
        'vat_total',
        'total',
        'created_by',
        'created_at',
        'updated_by',
        'updated_at',
        'received_at',
        'processed_at',
    )

    fieldsets = (
        (_('Document Info'), {
            'fields': (
                'document_number',
                'status',
                'document_type',
                'creation_type',
            )
        }),
        (_('Delivery Info'), {
            'fields': (
                'supplier',
                'location',
                'delivery_date',
                'delivery_note_number',
                'external_reference',
            )
        }),
        (_('Transport'), {
            'fields': (
                'vehicle_info',
                'driver_name',
                'driver_phone',
            )
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_checked',
                'has_quality_issues',
                'has_variances',
                'quality_inspector',
                'quality_notes',
            )
        }),
        (_('Financial'), {
            'fields': (
                'prices_entered_with_vat',
                'subtotal',
                'vat_total',
                'total',
            )
        }),
        (_('Processing'), {
            'fields': (
                'received_by',
                'received_at',
                'processed_by',
                'processed_at',
            ),
            'classes': ('collapse',)
        }),
        (_('System'), {
            'fields': (
                'created_by',
                'created_at',
                'updated_by',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [DeliveryLineInline]
    autocomplete_fields = ['supplier', 'location']
    date_hierarchy = 'delivery_date'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()
        formset.save_m2m()

        # Recalculate totals
        if formset.model == DeliveryLine:
            form.instance.recalculate_totals()

            # Update order delivery status if linked
            for line in instances:
                if hasattr(line, 'source_order_line') and line.source_order_line:
                    line.source_order_line.update_delivery_status()