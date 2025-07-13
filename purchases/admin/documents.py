# purchases/admin/documents.py - ФИНАЛЕН ЧИСТ КОД

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect

from ..models import PurchaseDocument, PurchaseDocumentLine
from ..services import DocumentService, LineService


class PurchaseDocumentLineInline(admin.TabularInline):
    """Inline за редове в purchase документ"""
    model = PurchaseDocumentLine
    extra = 1

    fields = [
        'line_number', 'product', 'quantity', 'unit', 'unit_price',
        'discount_percent', 'received_quantity', 'batch_number', 'expiry_date',
        'quality_approved', 'line_total_display'
    ]

    readonly_fields = ['line_total_display']

    def line_total_display(self, obj):
        if obj.pk:
            return f"{obj.line_total:.2f} лв"
        return "-"

    line_total_display.short_description = _('Line Total')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit')


@admin.register(PurchaseDocument)
class PurchaseDocumentAdmin(admin.ModelAdmin):
    """ФИНАЛЕН Admin за PurchaseDocument"""

    list_display = [
        'document_number', 'document_type_badge', 'supplier', 'delivery_date',
        'status_badge', 'supplier_doc_display', 'grand_total_display',
        'is_paid_badge', 'related_invoice_link'
    ]

    list_filter = [
        'status', 'is_paid', 'document_type', 'auto_create_invoice',
        'supplier', 'location', 'delivery_date'
    ]

    search_fields = [
        'document_number', 'supplier_document_number', 'supplier__name',
        'external_reference', 'notes'
    ]

    date_hierarchy = 'delivery_date'
    ordering = ['-delivery_date', '-document_number']
    inlines = [PurchaseDocumentLineInline]

    fieldsets = (
        (_('Document Info'), {
            'fields': ('document_number', 'document_date', 'delivery_date', 'document_type')
        }),
        (_('Partners & Location'), {
            'fields': ('supplier', 'location')
        }),
        (_('Reference Numbers'), {
            'fields': ('supplier_document_number', 'external_reference'),
        }),
        (_('Auto Invoice'), {
            'fields': ('auto_create_invoice',),
            'description': 'Check to automatically create invoice document from GRN'
        }),
        (_('Financial'), {
            'fields': ('subtotal', 'discount_amount', 'vat_amount', 'grand_total'),
            'classes': ('collapse',)
        }),
        (_('Payment'), {
            'fields': ('is_paid', 'payment_date'),
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ['subtotal', 'vat_amount', 'grand_total']

    actions = ['confirm_documents', 'receive_documents', 'mark_as_paid', 'duplicate_documents']

    # =====================
    # DISPLAY METHODS
    # =====================

    def document_type_badge(self, obj):
        """Цветен badge за document type"""
        colors = {
            'REQ': '#6C757D', 'ORD': '#0D6EFD', 'GRN': '#198754', 'INV': '#FD7E14'
        }
        color = colors.get(obj.document_type.code, '#6C757D')

        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.document_type.code
        )

    document_type_badge.short_description = _('Type')

    def status_badge(self, obj):
        """Цветен badge за статус"""
        colors = {
            'draft': '#6C757D', 'confirmed': '#0D6EFD',
            'received': '#198754', 'cancelled': '#DC3545'
        }
        color = colors.get(obj.status, '#6C757D')

        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = _('Status')

    def supplier_doc_display(self, obj):
        """Показва supplier document number"""
        if not obj.supplier_document_number:
            return format_html('<span style="color: #999;">-</span>')

        icon = '📄' if 'INV' in obj.supplier_document_number.upper() else '📋'
        return format_html('{} <strong>{}</strong>', icon, obj.supplier_document_number)

    supplier_doc_display.short_description = _('Supplier Doc')

    def grand_total_display(self, obj):
        """Показва общата сума"""
        return format_html('<strong style="color: #198754;">{:.2f} лв</strong>', obj.grand_total)

    grand_total_display.short_description = _('Total')

    def is_paid_badge(self, obj):
        """Badge за платен статус"""
        if obj.is_paid:
            return format_html('<span style="color: #198754;">✅ Paid</span>')
        elif obj.is_overdue_payment():
            return format_html('<span style="color: #DC3545;">⚠️ Overdue</span>')
        else:
            return format_html('<span style="color: #FFC107;">💰 Unpaid</span>')

    is_paid_badge.short_description = _('Payment')

    def related_invoice_link(self, obj):
        """Показва link към свързания документ"""
        related = obj.get_related_invoice()

        if not related:
            if (obj.document_type.code == 'GRN' and obj.auto_create_invoice and
                    obj.supplier_document_number):
                return format_html('<span style="color: #ffc107;">⏳ Auto</span>')
            return format_html('<span style="color: #999;">-</span>')

        url = reverse('admin:purchases_purchasedocument_change', args=[related.pk])
        icon = '📄' if related.document_type.code == 'INV' else '📦'
        return format_html('<a href="{}">{} {}</a>', url, icon, related.document_number)

    related_invoice_link.short_description = _('Related')

    # =====================
    # FORM CUSTOMIZATION
    # =====================

    def get_fieldsets(self, request, obj=None):
        """Показваме Auto Invoice секцията само за GRN документи"""
        fieldsets = list(self.fieldsets)

        if obj and obj.document_type.code != 'GRN':
            # Премахваме Auto Invoice секцията за не-GRN документи
            fieldsets = [fs for fs in fieldsets if fs[0] != _('Auto Invoice')]

        return fieldsets

    def save_model(self, request, obj, form, change):
        """Enhanced save с notification"""
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user

        # Запазваме информация за auto invoice
        will_create_invoice = (
                not change and obj.auto_create_invoice and
                obj.document_type.code == 'GRN' and obj.supplier_document_number
        )

        super().save_model(request, obj, form, change)

        # Notification за auto-created invoice
        if will_create_invoice:
            related = obj.get_related_invoice()
            if related:
                url = reverse('admin:purchases_purchasedocument_change', args=[related.pk])
                message = format_html(
                    'Invoice <a href="{}"><strong>{}</strong></a> was automatically created',
                    url, related.document_number
                )
                self.message_user(request, message, messages.SUCCESS)

    # =====================
    # ADMIN ACTIONS
    # =====================

    def confirm_documents(self, request, queryset):
        """Bulk потвърждаване на документи"""
        count = 0
        for doc in queryset.filter(status='draft'):
            try:
                DocumentService.process_document_workflow(doc, 'confirm', request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error confirming {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Successfully confirmed {count} documents", messages.SUCCESS)

    confirm_documents.short_description = _('Confirm selected documents')

    def receive_documents(self, request, queryset):
        """Bulk получаване на документи"""
        count = 0
        for doc in queryset.filter(status='confirmed'):
            try:
                DocumentService.process_document_workflow(
                    doc, 'receive', request.user, create_stock_movements=True
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error receiving {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Successfully received {count} documents", messages.SUCCESS)

    receive_documents.short_description = _('Receive selected documents')

    def mark_as_paid(self, request, queryset):
        """Bulk маркиране като платени"""
        count = 0
        for doc in queryset.filter(is_paid=False):
            try:
                DocumentService.process_document_workflow(doc, 'mark_paid', request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error marking {doc.document_number} as paid: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Marked {count} documents as paid", messages.SUCCESS)

    mark_as_paid.short_description = _('Mark as paid')

    def duplicate_documents(self, request, queryset):
        """Копиране на документи"""
        if queryset.count() > 5:
            self.message_user(request, "Can only duplicate up to 5 documents at once", messages.ERROR)
            return

        count = 0
        for doc in queryset:
            try:
                DocumentService.duplicate_document(doc, user=request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error duplicating {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Successfully duplicated {count} documents", messages.SUCCESS)

    duplicate_documents.short_description = _('Duplicate documents')

    # =====================
    # CUSTOM VIEWS
    # =====================

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)

        if obj and obj.status != 'draft':
            readonly.extend(['supplier', 'location', 'document_type', 'document_date'])

        return readonly

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'document_type', 'created_by'
        ).prefetch_related('lines')

    # Custom buttons в change form
    def response_change(self, request, obj):
        """Custom response с workflow buttons"""
        if '_confirm' in request.POST:
            try:
                DocumentService.process_document_workflow(obj, 'confirm', request.user)
                self.message_user(request, f"Document {obj.document_number} confirmed", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {e}", messages.ERROR)
            return redirect('.')

        if '_receive' in request.POST:
            try:
                DocumentService.process_document_workflow(
                    obj, 'receive', request.user, create_stock_movements=True
                )
                self.message_user(request, f"Document {obj.document_number} received", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {e}", messages.ERROR)
            return redirect('.')

        return super().response_change(request, obj)