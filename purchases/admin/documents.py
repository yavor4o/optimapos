# purchases/admin/documents.py - FIXED VERSION

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect

from ..models import PurchaseDocument, PurchaseDocumentLine
from ..services import DocumentService


class PurchaseDocumentLineInline(admin.TabularInline):
    """Inline for purchase document lines"""
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
    """FIXED Admin for PurchaseDocument"""

    list_display = [
        'document_number', 'document_type_badge', 'workflow_status_badge',
        'supplier', 'delivery_date', 'status_badge', 'supplier_doc_display',
        'grand_total_display', 'is_paid_badge'
    ]

    list_filter = [
        'status', 'workflow_status', 'is_paid', 'document_type',
        'supplier', 'location', 'delivery_date', 'urgency_level'
    ]

    search_fields = [
        'document_number', 'supplier_document_number', 'supplier__name',
        'external_reference', 'notes', 'order_reference'
    ]

    date_hierarchy = 'delivery_date'
    ordering = ['-delivery_date', '-document_number']
    inlines = [PurchaseDocumentLineInline]

    # FIXED: Use only fields that exist in the new model
    readonly_fields = [
        'document_number', 'grand_total', 'subtotal', 'vat_total', 'discount_total',
        'workflow_status_display', 'source_document_info', 'fulfillment_info'
    ]

    fieldsets = (
        (_('Document Info'), {
            'fields': ('document_number', 'document_date', 'delivery_date', 'document_type')
        }),
        (_('Partners & Location'), {
            'fields': ('supplier', 'location')
        }),
        (_('Reference Numbers'), {
            'fields': ('supplier_document_number', 'external_reference', 'order_reference')
        }),
        (_('Request Information'), {
            'fields': ('requested_by', 'approved_by', 'approved_at', 'urgency_level'),
            'classes': ('collapse',),
            'description': 'Information for request documents'
        }),
        (_('Order Information'), {
            'fields': ('expected_delivery_date', 'supplier_confirmed', 'supplier_confirmed_date'),
            'classes': ('collapse',),
            'description': 'Information for order documents'
        }),
        (_('Workflow'), {
            'fields': ('workflow_status_display', 'source_document_info', 'status')
        }),
        (_('Financial Summary'), {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'grand_total', 'is_paid', 'payment_date'),
            'classes': ('collapse',)
        }),
        (_('Additional Information'), {
            'fields': ('notes', 'auto_create_invoice')
        }),
        (_('Fulfillment'), {
            'fields': ('fulfillment_info',),
            'classes': ('collapse',)
        })
    )

    # Custom display methods
    def document_type_badge(self, obj):
        """Document type badge"""
        colors = {
            'REQ': '#17A2B8',  # Blue for requests
            'ORD': '#28A745',  # Green for orders
            'GRN': '#FFC107',  # Yellow for goods receipt
            'DEL': '#FD7E14',  # Orange for deliveries
            'INV': '#6F42C1'  # Purple for invoices
        }
        color = colors.get(obj.document_type.code, '#6C757D')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.document_type.code
        )

    document_type_badge.short_description = _('Type')

    def workflow_status_badge(self, obj):
        """Workflow status badge"""
        colors = {
            'req_draft': '#6C757D',
            'req_submitted': '#17A2B8',
            'req_approved': '#28A745',
            'req_rejected': '#DC3545',
            'req_converted': '#198754',
            'ord_draft': '#6C757D',
            'ord_sent': '#17A2B8',
            'ord_confirmed': '#28A745',
            'ord_in_delivery': '#FFC107',
            'ord_completed': '#198754',
            'cancelled': '#DC3545',
            'closed': '#343A40'
        }

        color = colors.get(obj.workflow_status, '#6C757D')
        display = obj.get_workflow_status_display()

        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{}</span>',
            color, display
        )

    workflow_status_badge.short_description = _('Workflow Status')

    def status_badge(self, obj):
        """Status badge"""
        colors = {
            'draft': '#6C757D',
            'confirmed': '#28A745',
            'received': '#198754',
            'cancelled': '#DC3545',
            'paid': '#0D6EFD',
            'closed': '#343A40'
        }
        color = colors.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = _('Status')

    def supplier_doc_display(self, obj):
        """Supplier document number display"""
        if obj.supplier_document_number:
            return format_html('<code>{}</code>', obj.supplier_document_number)
        return '-'

    supplier_doc_display.short_description = _('Supplier Doc')

    def grand_total_display(self, obj):
        """Grand total with currency"""
        return f"{obj.grand_total:.2f} лв"

    grand_total_display.short_description = _('Total')
    grand_total_display.admin_order_field = 'grand_total'

    def is_paid_badge(self, obj):
        """Payment status badge"""
        if obj.is_paid:
            return format_html(
                '<span style="color: #198754; font-weight: bold;">✓ Paid</span>'
            )
        else:
            return format_html(
                '<span style="color: #DC3545;">✗ Unpaid</span>'
            )

    is_paid_badge.short_description = _('Payment')

    # FIXED: Readonly field methods
    def workflow_status_display(self, obj):
        """Detailed workflow status information"""
        info_parts = [
            f"<strong>Current Status:</strong> {obj.get_workflow_status_display()}"
        ]

        if obj.is_request:
            if obj.requested_by:
                info_parts.append(
                    f"<strong>Requested by:</strong> {obj.requested_by.get_full_name() or obj.requested_by.username}")
            if obj.approved_by:
                info_parts.append(
                    f"<strong>Approved by:</strong> {obj.approved_by.get_full_name() or obj.approved_by.username}")
            if obj.approved_at:
                info_parts.append(f"<strong>Approved at:</strong> {obj.approved_at.strftime('%Y-%m-%d %H:%M')}")

        elif obj.is_order:
            if obj.expected_delivery_date:
                info_parts.append(f"<strong>Expected delivery:</strong> {obj.expected_delivery_date}")
            if obj.supplier_confirmed:
                info_parts.append(f"<strong>Supplier confirmed:</strong> {obj.supplier_confirmed_date or 'Yes'}")

        return format_html('<br>'.join(info_parts))

    workflow_status_display.short_description = _('Workflow Details')

    def source_document_info(self, obj):
        """Source document information"""
        if obj.source_document:
            url = reverse('admin:purchases_purchasedocument_change', args=[obj.source_document.pk])
            return format_html(
                'Created from: <a href="{}" target="_blank">{}</a>',
                url, obj.source_document.document_number
            )

        # Show derived documents
        derived = obj.derived_documents.all()
        if derived:
            links = []
            for doc in derived:
                url = reverse('admin:purchases_purchasedocument_change', args=[doc.pk])
                links.append(f'<a href="{url}" target="_blank">{doc.document_number}</a>')
            return format_html('Created: {}', ', '.join(links))

        return 'Original document'

    source_document_info.short_description = _('Document Chain')

    def fulfillment_info(self, obj):
        """Fulfillment information"""
        if obj.is_order:
            percentage = obj.fulfillment_percentage
            if percentage is not None:
                return f"Fulfillment: {percentage:.1f}%"

        lines_info = []
        total_lines = obj.lines.count()
        if total_lines > 0:
            lines_info.append(f"<strong>Total lines:</strong> {total_lines}")

            quality_issues = obj.lines.filter(quality_approved=False).count()
            if quality_issues > 0:
                lines_info.append(f"<strong>Quality issues:</strong> {quality_issues}")

        return format_html('<br>'.join(lines_info)) if lines_info else 'No line information'

    fulfillment_info.short_description = _('Fulfillment Info')

    # Actions
    actions = ['confirm_documents', 'receive_documents', 'mark_as_paid', 'convert_requests_to_orders']

    def confirm_documents(self, request, queryset):
        """Bulk confirmation of documents"""
        count = 0
        for doc in queryset.filter(status='draft'):
            try:
                doc.confirm(request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error confirming {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Successfully confirmed {count} documents", messages.SUCCESS)

    confirm_documents.short_description = _('Confirm selected documents')

    def receive_documents(self, request, queryset):
        """Bulk receiving of documents"""
        count = 0
        for doc in queryset.filter(status='confirmed'):
            try:
                doc.receive(request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error receiving {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Successfully received {count} documents", messages.SUCCESS)

    receive_documents.short_description = _('Receive selected documents')

    def mark_as_paid(self, request, queryset):
        """Bulk mark as paid"""
        count = 0
        for doc in queryset.filter(is_paid=False):
            try:
                doc.is_paid = True
                doc.save()
                count += 1
            except Exception as e:
                self.message_user(request, f"Error marking {doc.document_number} as paid: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Marked {count} documents as paid", messages.SUCCESS)

    mark_as_paid.short_description = _('Mark as paid')

    def convert_requests_to_orders(self, request, queryset):
        """Convert approved requests to orders"""
        count = 0
        for doc in queryset.filter(document_type__code='REQ', workflow_status='req_approved'):
            try:
                doc.convert_to_order(request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error converting {doc.document_number}: {e}", messages.ERROR)

        if count:
            self.message_user(request, f"Converted {count} requests to orders", messages.SUCCESS)

    convert_requests_to_orders.short_description = _('Convert requests to orders')

    # Enhanced form handling
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)

        if obj and obj.status != 'draft':
            readonly.extend(['supplier', 'location', 'document_type', 'document_date'])

        # Make source_document readonly always
        if obj and obj.source_document:
            readonly.extend(['source_document'])

        return readonly

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'document_type', 'created_by', 'source_document'
        ).prefetch_related('lines')

    # Custom form buttons
    def response_change(self, request, obj):
        """Custom response with workflow buttons"""
        if '_confirm' in request.POST:
            try:
                obj.confirm(request.user)
                self.message_user(request, f"Document {obj.document_number} confirmed", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {e}", messages.ERROR)
            return redirect('.')

        if '_receive' in request.POST:
            try:
                obj.receive(request.user)
                self.message_user(request, f"Document {obj.document_number} received", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {e}", messages.ERROR)
            return redirect('.')

        if '_convert_to_order' in request.POST and obj.can_be_converted_to_order:
            try:
                order = obj.convert_to_order(request.user)
                self.message_user(request, f"Converted to order {order.document_number}", messages.SUCCESS)
                return redirect('admin:purchases_purchasedocument_change', order.pk)
            except Exception as e:
                self.message_user(request, f"Error: {e}", messages.ERROR)
            return redirect('.')

        return super().response_change(request, obj)