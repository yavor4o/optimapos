# purchases/admin.py - FIXED COMPLETE ADMIN

from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)


# =================================================================
# INLINE ADMINS - FIXED WITH NEW FIELDS
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'product', 'requested_quantity', 'unit',
        'estimated_price',  'unit_price', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount'  # ✅ FULL VAT fields
    ]
    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()

        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()

        # Recalculate totals
        if form.instance.pk and hasattr(form.instance, 'recalculate_totals'):
            form.instance.recalculate_totals()


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'product', 'ordered_quantity', 'unit',
        'entered_price', 'unit_price', 'discount_percent', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount'
    ]
    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'product', 'received_quantity', 'unit',
        'entered_price', 'unit_price', 'discount_percent', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount',
        'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


# =================================================================
# PURCHASE REQUEST ADMIN - FIXED
# =================================================================

# REPLACE PurchaseRequestAdmin - CORRECT VERSION

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'supplier', 'status', 'urgency_display',
        'lines_count', 'estimated_total_display', 'total_display', 'created_at'  # ✅ Both estimated and calculated
    ]

    list_filter = ['status', 'urgency_level', 'supplier', 'location']
    search_fields = ['document_number', 'supplier__name']

    readonly_fields = [
        'document_number', 'document_type', 'status',
        'subtotal', 'vat_total', 'total',  # ✅ CORRECT: PurchaseRequest HAS these fields!
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'prices_entered_with_vat')  # ✅ VAT control
        }),
        ('Document Info', {
            'fields': ('document_type', 'document_number', 'status'),
            'classes': ('collapse',)
        }),
        ('Request Details', {
            'fields': ('urgency_level', 'request_type', 'requested_by')
        }),
        ('Financial Totals', {  # ✅ CORRECT: Request IS financial!
            'fields': ('subtotal', 'vat_total', 'total'),
            'classes': ('collapse',)
        }),
        ('Justification', {
            'fields': ('business_justification', 'expected_usage'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseRequestLineInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.requested_by = request.user
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def urgency_display(self, obj):
        if obj.urgency_level == 'high':
            return format_html('<span style="color: #F44336;">🔥 High</span>')
        elif obj.urgency_level == 'medium':
            return format_html('<span style="color: #FF9800;">⚡ Medium</span>')
        else:
            return format_html('<span style="color: #4CAF50;">📋 Normal</span>')

    urgency_display.short_description = 'Urgency'

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = 'Lines'

    def estimated_total_display(self, obj):
        # Legacy estimated calculation
        try:
            total = sum(
                (getattr(line, 'estimated_price', 0) or 0) * (getattr(line, 'requested_quantity', 0) or 0)
                for line in obj.lines.all()
            )
            return float(total)
        except Exception:
            return '-'

    estimated_total_display.short_description = 'Estimated'

    def total_display(self, obj):
        # VAT-calculated total
        return float(obj.total)

    total_display.short_description = 'VAT Total'






# =================================================================
# PURCHASE ORDER ADMIN - FIXED
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'supplier', 'status_display', 'is_urgent',
        'lines_count', 'total_display', 'expected_delivery_date'  # ✅ FIXED: total_display
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier_confirmed', 'supplier',
        'location', 'expected_delivery_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference'
    ]

    readonly_fields = [
        'document_number', 'document_type', 'status',
        'subtotal', 'discount_total', 'vat_total', 'total',  # ✅ FIXED: total
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'status', 'is_urgent', 'prices_entered_with_vat')  # ✅ ADDED VAT control
        }),
        ('Order Details', {
            'fields': (
                'document_date', 'expected_delivery_date',
                'supplier_order_reference', 'supplier_confirmed'
            )
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),  # ✅ FIXED: total
            'classes': ('collapse',)
        }),
        ('Source Information', {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        ('Payment Information', {
            'fields': ('is_paid', 'payment_date', 'payment_method'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('document_number', 'document_type', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseOrderLineInline]

    def status_display(self, obj):
        # ✅ FIXED: Safe status display
        try:
            status_value = obj.status
            status_label = obj.get_status_display() if hasattr(obj, 'get_status_display') else status_value.title()
        except:
            status_value = 'unknown'
            status_label = 'Unknown'

        colors = {
            'draft': '#757575',
            'confirmed': '#4CAF50',
            'sent': '#2196F3',
            'delivered': '#FF9800',
            'completed': '#9C27B0',
            'unknown': '#9E9E9E'
        }
        color = colors.get(status_value, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, status_label
        )

    status_display.short_description = 'Status'

    def lines_count(self, obj):
        return format_html('<strong>{}</strong>', obj.lines.count())

    lines_count.short_description = 'Lines'

    def total_display(self, obj):
        # ✅ FIXED: Use total instead of grand_total
        return format_html('<strong>{:.2f} лв</strong>', float(obj.total))

    total_display.short_description = 'Total'


# =================================================================
# DELIVERY RECEIPT ADMIN - FIXED
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status_display',
        'lines_count', 'total_display', 'quality_status', 'received_by'  # ✅ FIXED: total_display
    ]

    list_filter = [
        'status', 'has_quality_issues', 'has_variances', 'quality_checked',
        'delivery_date', 'supplier', 'location'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number'
    ]

    readonly_fields = [
        'document_number', 'document_type', 'status',
        'subtotal', 'discount_total', 'vat_total', 'total',  # ✅ FIXED: total
        'received_at', 'processed_at',
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'status', 'prices_entered_with_vat')  # ✅ ADDED VAT control
        }),
        ('Delivery Details', {
            'fields': (
                'delivery_date', 'delivery_note_number', 'external_reference',
                'vehicle_info', 'driver_name', 'driver_phone'
            )
        }),
        ('Quality Control', {
            'fields': (
                'quality_checked', 'has_quality_issues', 'quality_inspector',
                'quality_notes'
            )
        }),
        ('Variances', {
            'fields': ('has_variances',),
            'classes': ('collapse',)
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),  # ✅ FIXED: total
            'classes': ('collapse',)
        }),
        ('Payment Information', {
            'fields': ('is_paid', 'payment_date', 'payment_method'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': (
                'document_number', 'document_type', 'received_at', 'processed_at',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [DeliveryLineInline]

    def status_display(self, obj):
        # ✅ FIXED: Safe status display
        try:
            status_value = obj.status
            status_label = obj.get_status_display() if hasattr(obj, 'get_status_display') else status_value.title()
        except:
            status_value = 'unknown'
            status_label = 'Unknown'

        colors = {
            'draft': '#757575',
            'delivered': '#FF9800',
            'received': '#2196F3',
            'processed': '#9C27B0',
            'completed': '#4CAF50',
            'unknown': '#9E9E9E'
        }
        color = colors.get(status_value, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, status_label
        )

    status_display.short_description = 'Status'

    def lines_count(self, obj):
        return format_html('<strong>{}</strong>', obj.lines.count())

    lines_count.short_description = 'Lines'

    def total_display(self, obj):
        # ✅ FIXED: Use total instead of grand_total
        return format_html('<strong>{:.2f} лв</strong>', float(obj.total))

    total_display.short_description = 'Total'

    def quality_status(self, obj):
        if obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues</span>')
        elif obj.quality_checked:
            return format_html('<span style="color: green;">✅ OK</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')

    quality_status.short_description = 'Quality'


# =================================================================
# LINE MODELS ADMIN - FIXED
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'entered_price', 'unit_price', 'gross_amount'  # ✅ FIXED: added entered_price
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'entered_price', 'unit_price', 'discount_percent', 'gross_amount'  # ✅ FIXED
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'received_quantity',
        'entered_price', 'unit_price', 'gross_amount', 'quality_approved', 'batch_number'  # ✅ FIXED
    ]

    list_filter = [
        'quality_approved', 'document__status', 'document__supplier'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number',
        'document__document_number'
    ]

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']