# purchases/admin.py - ПЪЛЕН АДМИН ЗА ВСИЧКИ ДОКУМЕНТИ С FINANCIAL FIELDS

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
# CUSTOM FORMS
# =================================================================

class PurchaseRequestForm(forms.ModelForm):
    """Custom form за PurchaseRequest"""

    class Meta:
        model = PurchaseRequest
        fields = [
            'supplier', 'location', 'urgency_level',
            'request_type', 'business_justification', 'expected_usage',
            'requested_by'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['urgency_level'].initial = 'normal'
            self.fields['request_type'].initial = 'regular'


# =================================================================
# INLINE ADMINS - С НОВИТЕ FINANCIAL ПОЛЕТА
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'product', 'requested_quantity', 'unit',
        'estimated_price', 'unit_price', 'vat_rate', 'line_total'
    ]
    readonly_fields = ['line_total', 'unit_price', 'vat_rate']  # Auto-calculated

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0

    def save_formset(self, request, form, formset, change):
        """Това се извиква когато записваш редовете в админа"""
        # Записва редовете
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()

        # Изтрива маркираните за изтриване
        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()

        # ЕТО ТУКА Е МАГИЯТА - пресмята финансовите полета!
        if form.instance.pk:
            form.instance.recalculate_totals()


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'product', 'ordered_quantity', 'unit', 'unit_price',
        'discount_percent', 'vat_rate', 'line_total'
    ]
    readonly_fields = ['line_total', 'vat_rate']  # Auto-calculated

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'product', 'received_quantity', 'unit', 'unit_price',
        'discount_percent', 'vat_rate', 'line_total',
        'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['line_total', 'vat_rate']  # Auto-calculated

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


# =================================================================
# PURCHASE REQUEST ADMIN
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Админ за заявки за покупка"""

    form = PurchaseRequestForm

    list_display = [
        'document_number', 'supplier', 'status', 'urgency_level',
        'lines_count', 'estimated_total_display', 'grand_total_display', 'created_at'
    ]

    list_filter = ['status', 'urgency_level', 'supplier', 'location']
    search_fields = ['document_number', 'supplier__name']

    readonly_fields = [
        'document_number', 'document_type', 'status',
        'subtotal', 'vat_total', 'grand_total',  # ФИНАНСОВИ ПОЛЕТА
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location')
        }),
        ('Document Info', {
            'fields': ('document_type', 'document_number', 'status'),
            'classes': ('collapse',)
        }),
        ('Request Details', {
            'fields': ('urgency_level', 'request_type', 'requested_by')
        }),
        ('Financial Totals', {
            'fields': ('subtotal', 'vat_total', 'grand_total'),
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

    def lines_count(self, obj):
        return obj.lines.count()

    lines_count.short_description = 'Lines'

    def estimated_total_display(self, obj):
        total = obj.get_estimated_total()
        if total:
            return total
        return '-'

    estimated_total_display.short_description = 'Estimated Total'

    def grand_total_display(self, obj):
        return  obj.grand_total

    grand_total_display.short_description = 'Grand Total'


# =================================================================
# PURCHASE ORDER ADMIN
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Админ за поръчки към доставчици"""

    list_display = [
        'document_number', 'supplier', 'status', 'is_urgent',
        'lines_count', 'grand_total_display', 'expected_delivery_date'
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
        'subtotal', 'discount_total', 'vat_total', 'grand_total',  # ФИНАНСОВИ
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'status', 'is_urgent')
        }),
        ('Order Details', {
            'fields': (
                'document_date', 'expected_delivery_date',
                'supplier_order_reference', 'supplier_confirmed'
            )
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'grand_total'),
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

    def lines_count(self, obj):
        return obj.lines.count()

    lines_count.short_description = 'Lines'

    def grand_total_display(self, obj):
        return format_html('<strong>{:.2f} лв</strong>', obj.grand_total)

    grand_total_display.short_description = 'Grand Total'


# =================================================================
# DELIVERY RECEIPT ADMIN
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Админ за доставки"""

    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status',
        'lines_count', 'grand_total_display', 'quality_status', 'received_by'
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
        'subtotal', 'discount_total', 'vat_total', 'grand_total',  # ФИНАНСОВИ
        'received_at', 'processed_at',
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'status')
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
            'fields': ('subtotal', 'discount_total', 'vat_total', 'grand_total'),
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

    def lines_count(self, obj):
        return obj.lines.count()

    lines_count.short_description = 'Lines'

    def grand_total_display(self, obj):
        return obj.grand_total

    grand_total_display.short_description = 'Grand Total'

    def quality_status(self, obj):
        if obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues</span>')
        elif obj.quality_checked:
            return format_html('<span style="color: green;">✅ OK</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')

    quality_status.short_description = 'Quality'


# =================================================================
# LINE MODELS ADMIN (Optional - за директно управление)
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Директен админ за редове от заявки"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'estimated_price', 'unit_price', 'line_total'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['line_total', 'unit_price', 'vat_rate']


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    """Директен админ за редове от поръчки"""

    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'unit_price', 'discount_percent', 'line_total'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['line_total', 'vat_rate']


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    """Директен админ за редове от доставки"""

    list_display = [
        'document', 'line_number', 'product', 'received_quantity',
        'unit_price', 'line_total', 'quality_approved', 'batch_number'
    ]

    list_filter = [
        'quality_approved', 'document__status', 'document__supplier'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number',
        'document__document_number'
    ]

    readonly_fields = ['line_total', 'vat_rate']