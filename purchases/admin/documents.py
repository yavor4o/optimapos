# purchases/admin/documents.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect

from ..models import PurchaseDocument, PurchaseDocumentLine
from ..services import PurchaseService, DocumentService, LineService


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
    """Admin за PurchaseDocument с пълен функционалност"""

    list_display = [
        'document_number', 'supplier', 'location', 'delivery_date',
        'status_badge', 'grand_total_display', 'is_paid_badge',
        'lines_count', 'created_at'
    ]

    list_filter = [
        'status', 'is_paid', 'document_type', 'supplier', 'location',
        'delivery_date', 'created_at'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier__company_name',
        'supplier_document_number', 'external_reference', 'notes'
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
        (_('References'), {
            'fields': ('supplier_document_number', 'external_reference'),
            'classes': ('collapse',)
        }),
        (_('Status & Payment'), {
            'fields': ('status', 'is_paid', 'payment_date')
        }),
        (_('Financial Summary'), {
            'fields': ('subtotal', 'discount_amount', 'vat_amount', 'grand_total'),
            'classes': ('collapse',)
        }),
        (_('Additional Info'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('Audit'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = [
        'subtotal', 'vat_amount', 'grand_total', 'created_at', 'updated_at'
    ]

    # Custom display methods
    def status_badge(self, obj):
        """Цветен badge за статус"""
        colors = {
            'draft': '#6C757D',
            'confirmed': '#0D6EFD',
            'received': '#198754',
            'cancelled': '#DC3545',
            'paid': '#6F42C1',
            'closed': '#495057'
        }

        color = colors.get(obj.status, '#6C757D')
        display = obj.get_status_display()

        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: bold;">{}</span>',
            color, display
        )

    status_badge.short_description = _('Status')

    def is_paid_badge(self, obj):
        """Badge за плащане"""
        if obj.is_paid:
            return format_html(
                '<span style="background-color: #198754; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 11px;">PAID</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #DC3545; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 11px;">UNPAID</span>'
            )

    is_paid_badge.short_description = _('Payment')

    def grand_total_display(self, obj):
        """Форматирана обща сума"""
        return f"{obj.grand_total:.2f} лв"

    grand_total_display.short_description = _('Grand Total')
    grand_total_display.admin_order_field = 'grand_total'

    def lines_count(self, obj):
        """Брой редове"""
        return obj.lines.count()

    lines_count.short_description = _('Lines')

    def document_summary(self, obj):
        """Резюме на документа"""
        if not obj.pk:
            return "Save document first to see summary"

        lines_summary = LineService.get_lines_summary_for_document(obj)

        summary_parts = [
            f"<strong>Lines:</strong> {lines_summary.get('total_lines', 0)}",
            f"<strong>Products:</strong> {obj.lines.values('product').distinct().count()}",
            f"<strong>Total Quantity:</strong> {lines_summary.get('total_quantity', 0):.2f}",
            f"<strong>Received:</strong> {lines_summary.get('total_received', 0):.2f}",
        ]

        if lines_summary.get('lines_with_variance', 0) > 0:
            summary_parts.append(
                f"<strong style='color: #FFC107;'>Variances:</strong> {lines_summary['lines_with_variance']}"
            )

        if lines_summary.get('lines_with_quality_issues', 0) > 0:
            summary_parts.append(
                f"<strong style='color: #DC3545;'>Quality Issues:</strong> {lines_summary['lines_with_quality_issues']}"
            )

        return mark_safe('<br>'.join(summary_parts))

    document_summary.short_description = _('Document Summary')

    # Actions
    actions = [
        'confirm_documents', 'receive_documents', 'mark_as_paid',
        'recalculate_totals', 'duplicate_documents'
    ]

    def confirm_documents(self, request, queryset):
        """Bulk потвърждаване на документи"""
        draft_docs = queryset.filter(status='draft')
        if not draft_docs.exists():
            self.message_user(request, "No draft documents selected", messages.WARNING)
            return

        result = PurchaseService.bulk_confirm_documents(
            list(draft_docs.values_list('id', flat=True)),
            user=request.user
        )

        if result['success_count'] > 0:
            self.message_user(
                request,
                f"Successfully confirmed {result['success_count']} documents",
                messages.SUCCESS
            )

        if result['errors']:
            self.message_user(
                request,
                f"Errors: {'; '.join(result['errors'][:3])}",
                messages.ERROR
            )

    confirm_documents.short_description = _('Confirm selected documents')

    def receive_documents(self, request, queryset):
        """Bulk получаване на документи"""
        confirmed_docs = queryset.filter(status='confirmed')
        if not confirmed_docs.exists():
            self.message_user(request, "No confirmed documents selected", messages.WARNING)
            return

        result = PurchaseService.bulk_receive_documents(
            list(confirmed_docs.values_list('id', flat=True)),
            user=request.user
        )

        if result['success_count'] > 0:
            self.message_user(
                request,
                f"Successfully received {result['success_count']} documents",
                messages.SUCCESS
            )

        if result['errors']:
            self.message_user(
                request,
                f"Errors: {'; '.join(result['errors'][:3])}",
                messages.ERROR
            )

    receive_documents.short_description = _('Receive selected documents')

    def mark_as_paid(self, request, queryset):
        """Bulk маркиране като платени"""
        unpaid_docs = queryset.filter(is_paid=False)
        if not unpaid_docs.exists():
            self.message_user(request, "No unpaid documents selected", messages.WARNING)
            return

        result = PurchaseService.bulk_mark_paid(
            list(unpaid_docs.values_list('id', flat=True)),
            user=request.user
        )

        if result['success_count'] > 0:
            self.message_user(
                request,
                f"Marked {result['success_count']} documents as paid",
                messages.SUCCESS
            )

    mark_as_paid.short_description = _('Mark as paid')

    def recalculate_totals(self, request, queryset):
        """Преизчисляване на суми"""
        count = 0
        for doc in queryset:
            DocumentService.recalculate_document_totals(doc)
            count += 1

        self.message_user(
            request,
            f"Recalculated totals for {count} documents",
            messages.SUCCESS
        )

    recalculate_totals.short_description = _('Recalculate totals')

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
                self.message_user(request, f"Error duplicating {doc.document_number}: {str(e)}", messages.ERROR)

        if count > 0:
            self.message_user(request, f"Successfully duplicated {count} documents", messages.SUCCESS)

    duplicate_documents.short_description = _('Duplicate documents')

    # Custom views
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)

        if obj and obj.status != 'draft':
            # Не позволяваме редактиране на потвърдени документи
            readonly.extend([
                'supplier', 'location', 'document_type', 'document_date', 'delivery_date'
            ])

        return readonly

    def save_model(self, request, obj, form, change):
        if not change:  # Нов документ
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'document_type', 'created_by'
        ).prefetch_related('lines')

    # Integration с services
    def response_change(self, request, obj):
        """Custom response след промяна"""
        if '_confirm' in request.POST:
            try:
                DocumentService.process_document_workflow(obj, 'confirm', request.user)
                self.message_user(request, f"Document {obj.document_number} confirmed", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error confirming document: {str(e)}", messages.ERROR)
            return redirect('.')

        if '_receive' in request.POST:
            try:
                DocumentService.complete_document_workflow(
                    obj, 'received', request.user,
                    create_stock_movements=True, update_pricing=True
                )
                self.message_user(request, f"Document {obj.document_number} received", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error receiving document: {str(e)}", messages.ERROR)
            return redirect('.')

        return super().response_change(request, obj)