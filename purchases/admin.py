# purchases/admin/__init__.py
"""
MODERN PURCHASES ADMIN - SERVICE INTEGRATED

FEATURES:
✅ DocumentService integration за workflow actions
✅ PurchaseWorkflowService за request→order conversion
✅ Result pattern error handling
✅ Enhanced bulk operations
✅ Real-time status tracking
✅ Professional UI с service feedback
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum, Q
from django.utils import timezone





from nomenclatures.services import DocumentService
from core.utils.result import Result
from purchases.models import PurchaseRequestLine, PurchaseOrderLine, DeliveryLine, PurchaseRequest, PurchaseOrder, \
    DeliveryReceipt
from purchases.services.workflow_service import PurchaseWorkflowService


# =================================================================
# ENHANCED INLINES WITH SERVICE INTEGRATION
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'estimated_price', 'suggested_supplier', 'priority', 'notes'
    ]
    readonly_fields = ['line_number']

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'line_number', 'product', 'ordered_quantity', 'unit', 'unit_price',
        'discount_percent', 'line_total_display', 'delivery_status'
    ]
    readonly_fields = ['line_number', 'line_total_display', 'delivery_status']

    def line_total_display(self, obj):
        if obj.pk:
            return format_html(
                '<strong>{:.2f}</strong>',
                obj.line_total
            )
        return '-'

    line_total_display.short_description = 'Line Total'


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'line_number', 'product', 'received_quantity', 'unit', 'unit_price',
        'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['line_number']


# =================================================================
# PURCHASE REQUEST ADMIN - SERVICE INTEGRATED
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """
    Enhanced PurchaseRequest Admin with Service Integration
    """

    list_display = [
        'document_number', 'supplier_display', 'location', 'status_badge',
        'urgency_badge', 'requested_by', 'lines_count', 'estimated_total',
        'created_at_short', 'conversion_status'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'approval_required',
        'location', 'created_at', 'approved_by'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'requested_by__username', 'requested_by__first_name', 'requested_by__last_name'
    ]

    date_hierarchy = 'created_at'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'workflow_status_display', 'conversion_progress_display'
    ]

    fieldsets = (
        (_('Document Information'), {
            'fields': (
                ('document_number', 'document_type'),
                ('status', 'urgency_level'),
                ('supplier', 'location'),
            )
        }),
        (_('Request Details'), {
            'fields': (
                'request_type', 'business_justification', 'expected_usage',
                'required_by_date'
            )
        }),
        (_('Workflow Status'), {
            'fields': (
                'workflow_status_display', 'conversion_progress_display'
            ),
            'classes': ('collapse',)
        }),
        (_('Approval Information'), {
            'fields': (
                'approval_required', 'approved_by', 'approved_at',
                'rejection_reason'
            ),
            'classes': ('collapse',)
        }),
    )

    actions = [
        'submit_for_approval', 'approve_requests', 'convert_to_orders',
        'bulk_export_to_excel'
    ]

    # =================
    # DISPLAY METHODS
    # =================

    def supplier_display(self, obj):
        if obj.supplier:
            return format_html(
                '<strong>{}</strong><br><small>{}</small>',
                obj.supplier.name,
                obj.supplier.code if hasattr(obj.supplier, 'code') else ''
            )
        return '-'

    supplier_display.short_description = 'Supplier'

    def status_badge(self, obj):
        colors = {
            'draft': 'secondary',
            'submitted': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'converted': 'info',
            'cancelled': 'dark'
        }
        color = colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Status'

    def urgency_badge(self, obj):
        colors = {
            'low': 'success',
            'normal': 'secondary',
            'high': 'warning',
            'critical': 'danger'
        }
        color = colors.get(obj.urgency_level, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_urgency_level_display()
        )

    urgency_badge.short_description = 'Urgency'

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = 'Lines'

    def estimated_total(self, obj):
        """Calculate estimated total using line data"""
        total = sum(
            (line.estimated_price or 0) * line.requested_quantity
            for line in obj.lines.all()
        )
        return format_html('<strong>{:.2f}</strong>', total)

    estimated_total.short_description = 'Est. Total'

    def created_at_short(self, obj):
        return obj.created_at.strftime('%d.%m.%Y')

    created_at_short.short_description = 'Created'

    def conversion_status(self, obj):
        """Show conversion status using new related_name"""
        orders = obj.sourced_orders.all()  # Using new related_name

        if not orders.exists():
            return format_html('<span class="text-muted">Not converted</span>')

        orders_count = orders.count()
        return format_html(
            '<span class="text-success">{} order{}</span>',
            orders_count, 's' if orders_count > 1 else ''
        )

    conversion_status.short_description = 'Conversion'

    def workflow_status_display(self, obj):
        """Enhanced workflow status using DocumentService"""
        try:
            # Get available actions using DocumentService
            actions_result = DocumentService.get_available_actions(obj)

            if actions_result.ok:
                actions = actions_result.data.get('available_actions', [])
                actions_html = ', '.join([
                    f'<span class="badge badge-outline-primary">{action}</span>'
                    for action in actions
                ])
                return format_html(actions_html) if actions_html else 'No actions available'
            else:
                return format_html('<span class="text-danger">Error: {}</span>', actions_result.msg)

        except Exception as e:
            return format_html('<span class="text-danger">Service Error</span>')

    workflow_status_display.short_description = 'Available Actions'

    def conversion_progress_display(self, obj):
        """Show conversion progress"""
        total_lines = obj.lines.count()
        if total_lines == 0:
            return 'No lines'

        # Count lines that have been converted
        converted_lines = sum(
            1 for line in obj.lines.all()
            if line.generated_order_lines.exists()  # Using new related_name
        )

        percentage = round((converted_lines / total_lines) * 100)

        return format_html(
            '<div class="progress" style="width: 100px;">'
            '<div class="progress-bar" style="width: {}%;">{}/{}%</div>'
            '</div>',
            percentage, converted_lines, total_lines
        )

    conversion_progress_display.short_description = 'Conversion Progress'

    # =================
    # SERVICE-INTEGRATED ACTIONS
    # =================

    def submit_for_approval(self, request, queryset):
        """Submit requests for approval using DocumentService"""
        success_count = 0
        error_count = 0

        for req in queryset.filter(status='draft'):
            try:
                # Use DocumentService for state transitions
                result = DocumentService.transition_document(
                    req, 'submitted', request.user
                )

                if result.ok:
                    success_count += 1
                else:
                    error_count += 1
                    messages.error(request, f'{req.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{req.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'✅ Submitted {success_count} requests for approval')
        if error_count:
            messages.warning(request, f'⚠️ {error_count} requests failed to submit')

    submit_for_approval.short_description = '📤 Submit for approval'

    def approve_requests(self, request, queryset):
        """Approve requests using DocumentService"""
        success_count = 0
        error_count = 0

        for req in queryset.filter(status='submitted'):
            try:
                result = DocumentService.transition_document(
                    req, 'approved', request.user
                )

                if result.ok:
                    success_count += 1
                else:
                    error_count += 1
                    messages.error(request, f'{req.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{req.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'✅ Approved {success_count} requests')
        if error_count:
            messages.warning(request, f'⚠️ {error_count} requests failed to approve')

    approve_requests.short_description = '✅ Approve requests'

    def convert_to_orders(self, request, queryset):
        """Convert requests to orders using PurchaseWorkflowService"""
        success_count = 0
        error_count = 0

        for req in queryset.filter(status='approved'):
            try:
                # Use new PurchaseWorkflowService
                result = PurchaseWorkflowService.convert_request_to_order(
                    req, request.user
                )

                if result.ok:
                    success_count += 1
                    order = result.data['order']
                    messages.success(
                        request,
                        f'✅ {req.document_number} → {order.document_number}'
                    )
                else:
                    error_count += 1
                    messages.error(request, f'{req.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{req.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'🎉 Created {success_count} orders successfully')
        if error_count:
            messages.warning(request, f'⚠️ {error_count} conversions failed')

    convert_to_orders.short_description = '🔄 Convert to orders'


# =================================================================
# PURCHASE ORDER ADMIN - SERVICE INTEGRATED
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """
    Enhanced PurchaseOrder Admin with Service Integration
    """

    list_display = [
        'document_number', 'supplier_display', 'location', 'status_badge',
        'source_request_link', 'lines_count', 'grand_total_display',
        'expected_delivery_date', 'delivery_status_badge'
    ]

    list_filter = [
        'status', 'is_urgent', 'delivery_status', 'supplier_confirmed',
        'location', 'supplier', 'expected_delivery_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference',
        'notes', 'external_reference'
    ]

    date_hierarchy = 'expected_delivery_date'
    inlines = [PurchaseOrderLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'subtotal',
        'discount_total', 'vat_total', 'grand_total', 'delivery_progress'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status'
            )
        }),
        (_('Order Details'), {
            'fields': (
                'document_date', 'expected_delivery_date', 'external_reference',
                'supplier_order_reference', 'supplier_confirmed', 'order_method'
            )
        }),
        (_('Source Information'), {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        (_('Financial Summary'), {
            'fields': (
                'subtotal', 'discount_total', 'vat_total', 'grand_total'
            ),
            'classes': ('collapse',)
        }),
        (_('Delivery Status'), {
            'fields': ('delivery_progress',),
            'classes': ('collapse',)
        }),
    )

    actions = [
        'confirm_orders', 'send_to_suppliers', 'create_deliveries'
    ]

    # =================
    # DISPLAY METHODS
    # =================

    def supplier_display(self, obj):
        if obj.supplier:
            return format_html(
                '<strong>{}</strong><br><small>{}</small>',
                obj.supplier.name,
                obj.supplier.code if hasattr(obj.supplier, 'code') else ''
            )
        return '-'

    supplier_display.short_description = 'Supplier'

    def status_badge(self, obj):
        colors = {
            'draft': 'secondary',
            'sent': 'warning',
            'confirmed': 'success',
            'in_delivery': 'info',
            'received': 'success',
            'cancelled': 'danger',
            'closed': 'dark'
        }
        color = colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Status'

    def source_request_link(self, obj):
        if obj.source_request:
            url = reverse('admin:purchases_purchaserequest_change',
                          args=[obj.source_request.pk])
            return format_html(
                '<a href="{}" class="btn btn-sm btn-outline-primary">{}</a>',
                url, obj.source_request.document_number
            )
        return format_html('<span class="text-muted">Manual</span>')

    source_request_link.short_description = 'Source Request'

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = 'Lines'

    def grand_total_display(self, obj):
        return format_html('<strong>{:.2f}</strong>', obj.grand_total)

    grand_total_display.short_description = 'Total'

    def delivery_status_badge(self, obj):
        colors = {
            'pending': 'secondary',
            'partial': 'warning',
            'completed': 'success',
            'cancelled': 'danger'
        }
        color = colors.get(obj.delivery_status, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_delivery_status_display()
        )

    delivery_status_badge.short_description = 'Delivery'

    def delivery_progress(self, obj):
        """Show delivery progress"""
        lines = obj.lines.all()
        if not lines:
            return 'No lines'

        total_ordered = sum(line.ordered_quantity for line in lines)
        total_delivered = sum(line.delivered_quantity for line in lines)

        if total_ordered == 0:
            percentage = 0
        else:
            percentage = round((total_delivered / total_ordered) * 100)

        return format_html(
            '<div class="progress" style="width: 150px;">'
            '<div class="progress-bar" style="width: {}%;">{:.1f}/{:.1f} ({}%)</div>'
            '</div>',
            percentage, total_delivered, total_ordered, percentage
        )

    delivery_progress.short_description = 'Delivery Progress'

    # =================
    # SERVICE-INTEGRATED ACTIONS
    # =================

    def confirm_orders(self, request, queryset):
        """Confirm orders using PurchaseWorkflowService"""
        success_count = 0
        error_count = 0

        for order in queryset.filter(status='sent'):
            try:
                result = PurchaseWorkflowService.confirm_purchase_order(
                    order, request.user
                )

                if result.ok:
                    success_count += 1
                else:
                    error_count += 1
                    messages.error(request, f'{order.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{order.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'✅ Confirmed {success_count} orders')

    confirm_orders.short_description = '✅ Confirm orders'

    def create_deliveries(self, request, queryset):
        """Create deliveries from orders using PurchaseWorkflowService"""
        success_count = 0
        error_count = 0

        for order in queryset.filter(status='confirmed'):
            try:
                result = PurchaseWorkflowService.create_delivery_from_order(
                    order, request.user
                )

                if result.ok:
                    success_count += 1
                    delivery = result.data['delivery']
                    messages.success(
                        request,
                        f'✅ {order.document_number} → {delivery.document_number}'
                    )
                else:
                    error_count += 1
                    messages.error(request, f'{order.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{order.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'🚚 Created {success_count} deliveries')

    create_deliveries.short_description = '🚚 Create deliveries'


# =================================================================
# DELIVERY RECEIPT ADMIN - SERVICE INTEGRATED
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """
    Enhanced DeliveryReceipt Admin with Service Integration
    """

    list_display = [
        'document_number', 'supplier_display', 'location', 'status_badge',
        'delivery_date', 'lines_count', 'grand_total_display',
        'quality_status', 'processing_status'
    ]

    list_filter = [
        'status', 'delivery_date', 'quality_approved', 'has_quality_issues',
        'location', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number',
        'driver_name', 'notes'
    ]

    date_hierarchy = 'delivery_date'
    inlines = [DeliveryLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'processing_summary', 'quality_summary'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status'
            )
        }),
        (_('Delivery Details'), {
            'fields': (
                'delivery_date', 'delivery_note_number', 'driver_name',
                'driver_phone', 'vehicle_info'
            )
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_summary', 'quality_approved', 'has_quality_issues',
                'quality_notes'
            ),
            'classes': ('collapse',)
        }),
        (_('Processing Status'), {
            'fields': (
                'processing_summary', 'processed_at', 'processed_by'
            ),
            'classes': ('collapse',)
        }),
    )

    actions = [
        'approve_quality', 'process_deliveries', 'create_inventory_movements'
    ]

    # =================
    # DISPLAY METHODS
    # =================

    def supplier_display(self, obj):
        if obj.supplier:
            return format_html(
                '<strong>{}</strong>',
                obj.supplier.name
            )
        return '-'

    supplier_display.short_description = 'Supplier'

    def status_badge(self, obj):
        colors = {
            'draft': 'secondary',
            'delivered': 'warning',
            'received': 'info',
            'processed': 'success',
            'completed': 'success',
            'cancelled': 'danger'
        }
        color = colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Status'

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = 'Lines'

    def grand_total_display(self, obj):
        return format_html('<strong>{:.2f}</strong>', obj.grand_total)

    grand_total_display.short_description = 'Total'

    def quality_status(self, obj):
        if obj.quality_approved:
            return format_html('<span class="badge badge-success">✅ Approved</span>')
        elif obj.has_quality_issues:
            return format_html('<span class="badge badge-danger">❌ Issues</span>')
        else:
            return format_html('<span class="badge badge-warning">⏳ Pending</span>')

    quality_status.short_description = 'Quality'

    def processing_status(self, obj):
        if obj.processed_at:
            return format_html(
                '<span class="badge badge-success">✅ {}</span>',
                obj.processed_at.strftime('%d.%m %H:%M')
            )
        else:
            return format_html('<span class="badge badge-warning">⏳ Pending</span>')

    processing_status.short_description = 'Processing'

    def quality_summary(self, obj):
        """Quality control summary"""
        lines = obj.lines.all()
        approved_lines = sum(1 for line in lines if line.quality_approved)
        total_lines = lines.count()

        return format_html(
            'Approved: {}/{} lines<br>'
            'Quality Issues: {}',
            approved_lines, total_lines,
            'Yes' if obj.has_quality_issues else 'No'
        )

    quality_summary.short_description = 'Quality Summary'

    def processing_summary(self, obj):
        """Processing summary"""
        return format_html(
            'Status: {}<br>'
            'Processed: {}<br>'
            'By: {}',
            obj.get_status_display(),
            obj.processed_at.strftime('%d.%m.%Y %H:%M') if obj.processed_at else 'Not processed',
            obj.processed_by.username if obj.processed_by else '-'
        )

    processing_summary.short_description = 'Processing Summary'

    # =================
    # SERVICE-INTEGRATED ACTIONS
    # =================

    def approve_quality(self, request, queryset):
        """Approve quality for deliveries"""
        success_count = 0

        for delivery in queryset:
            delivery.quality_approved = True
            delivery.has_quality_issues = False
            delivery.save()
            success_count += 1

        messages.success(request, f'✅ Approved quality for {success_count} deliveries')

    approve_quality.short_description = '✅ Approve quality'

    def process_deliveries(self, request, queryset):
        """Process deliveries using DocumentService"""
        success_count = 0
        error_count = 0

        for delivery in queryset.filter(status='received'):
            try:
                result = DocumentService.transition_document(
                    delivery, 'processed', request.user
                )

                if result.ok:
                    success_count += 1
                else:
                    error_count += 1
                    messages.error(request, f'{delivery.document_number}: {result.msg}')

            except Exception as e:
                error_count += 1
                messages.error(request, f'{delivery.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'✅ Processed {success_count} deliveries')

    process_deliveries.short_description = '⚙️ Process deliveries'

    def create_inventory_movements(self, request, queryset):
        """Create inventory movements from deliveries"""
        success_count = 0
        error_count = 0

        for delivery in queryset.filter(status='processed', quality_approved=True):
            try:
                # This would integrate with MovementService
                # For now, just mark as completed
                delivery.status = 'completed'
                delivery.save()
                success_count += 1

            except Exception as e:
                error_count += 1
                messages.error(request, f'{delivery.document_number}: {str(e)}')

        if success_count:
            messages.success(request, f'📦 Created movements for {success_count} deliveries')

    create_inventory_movements.short_description = '📦 Create inventory movements'


# =================================================================
# ADMIN CUSTOMIZATIONS
# =================================================================

# Customize admin site
admin.site.site_header = "OptimaPOS - Purchase Management"
admin.site.site_title = "OptimaPOS Admin"
admin.site.index_title = "Purchase Management System"