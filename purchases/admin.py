# purchases/admin.py - МИНИМАЛЕН РАБОТЕЩ АДМИН

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import PurchaseRequest, PurchaseRequestLine

# =====================
# PURCHASE REQUEST ADMIN - BASIC
# =====================
@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Основен админ за заявки за покупка"""

    list_display = [
        'document_number', 'supplier', 'location', 'status',
        'urgency_level', 'requested_by', 'document_date'
    ]

    list_filter = [
        'status',
        'urgency_level',
        'request_type',
        'approval_required',
        'location',
        'supplier',
        'document_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'notes', 'external_reference'
    ]

    date_hierarchy = 'document_date'

    readonly_fields = [
        'document_number','status','created_at', 'approved_at', 'converted_at','requested_by'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_type', 'document_number', 'supplier', 'location', 'status'
            )
        }),
        (_('Request Details'), {
            'fields': (
                'request_type', 'urgency_level', 'document_date',
                'external_reference', 'approval_required'
            )
        }),
        (_('Business Justification'), {
            'fields': ('business_justification', 'expected_usage')
        }),
        (_('Approval Workflow'), {
            'fields': (
                 'approved_by', 'approved_at',
                'rejection_reason'
            ),
            'classes': ('collapse',)
        }),
        (_('Conversion Tracking'), {
            'fields': (
                'converted_to_order', 'converted_at', 'converted_by'
            ),
            'classes': ('collapse',)
        }),
        (_('Notes'), {
            'fields': ('notes',)
        }),

    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'requested_by', 'approved_by', 'document_type'
        )

    # =====================
    # FORM CUSTOMIZATION
    # =====================
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize foreign key fields"""
        if db_field.name == "document_type":
            # Filter to show only Purchase Request document types
            from nomenclatures.models import DocumentType
            kwargs["queryset"] = DocumentType.objects.filter(
                app_name='purchases',
                type_key='request',
                is_active=True
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Автоматично попълва user полетата"""
        # Задайте user-а ПРЕДИ save
        obj._current_user = request.user

        if not change:  # Нов документ
            obj.requested_by = request.user
            obj.created_by = request.user

        obj.updated_by = request.user

        super().save_model(request, obj, form, change)
# =====================
# PURCHASE REQUEST LINE ADMIN - BASIC
# =====================
@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Основен админ за редове от заявки"""

    list_display = [
        'document_display', 'line_number', 'product', 'requested_quantity',
        'estimated_price'
    ]

    list_filter = [
        'product__product_group',
        'unit'
    ]

    search_fields = [
        'product__code', 'product__name', 'document__document_number'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'product', 'unit'
        )

    def document_display(self, obj):
        return obj.document.document_number
    document_display.short_description = _('Document')
    document_display.admin_order_field = 'document__document_number'