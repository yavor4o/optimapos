# purchases/admin/__init__.py - COMPLETE VERSION

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q
from django.utils import timezone

from purchases.models import PurchaseRequestLine, PurchaseOrder, PurchaseRequest, DeliveryReceipt, PurchaseOrderLine, \
    DeliveryLine, DocumentType


# === INLINE ADMINS ===

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'estimated_price', 'suggested_supplier'
    ]
    readonly_fields = ['line_number']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit')


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'line_number', 'product', 'ordered_quantity', 'unit',
        'unit_price', 'discount_percent', 'line_total'
    ]
    readonly_fields = ['line_number', 'line_total']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit')


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'line_number', 'product', 'received_quantity', 'unit',
        'unit_price', 'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['line_number']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit')


# === DOCUMENT TYPE ADMIN ===

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    """Admin for document type configuration"""

    list_display = [
        'code', 'name', 'type_key', 'stock_effect_display',
        'workflow_enabled', 'is_active'
    ]

    list_filter = ['type_key', 'stock_effect', 'is_active']
    search_fields = ['code', 'name', 'description']
    list_editable = ['is_active']

    def stock_effect_display(self, obj):
        """Stock effect with icon"""
        icons = {1: '⬆️ Increases', -1: '⬇️ Decreases', 0: '➡️ No Effect'}
        return icons.get(obj.stock_effect, '❓')

    stock_effect_display.short_description = _('Stock Effect')

    def workflow_enabled(self, obj):
        return format_html(
            '<span style="color: green;">✅</span>' if getattr(obj, 'requires_approval', False)
            else '<span style="color: gray;">-</span>'
        )

    workflow_enabled.short_description = _('Workflow')


# === PURCHASE REQUEST ADMIN ===

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Professional admin for Purchase Requests"""

    list_display = [
        'document_number', 'supplier', 'status_display', 'urgency_display',
        'requested_by', 'total_amount', 'approval_status', 'conversion_status',
        'document_date'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'approval_required',
        'document_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'requested_by__first_name', 'requested_by__last_name'
    ]

    date_hierarchy = 'document_date'

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'converted_at',
        'request_analytics'
    ]

    fieldsets = (
        (_('Document Information'), {
            'fields': ('document_number', 'supplier', 'location', 'document_date')
        }),
        (_('Request Details'), {
            'fields': (
                'request_type', 'urgency_level', 'business_justification',
                'expected_usage'
            )
        }),
        (_('Approval Workflow'), {
            'fields': (
                'status', 'approval_required', 'requested_by',
                'approved_by', 'approved_at', 'rejection_reason'
            ),
            'classes': ('collapse',)
        }),
        (_('Conversion Tracking'), {
            'fields': ('converted_to_order', 'converted_at', 'converted_by'),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('request_analytics',),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [PurchaseRequestLineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'requested_by', 'approved_by'
        ).prefetch_related('lines')

    def status_display(self, obj):
        """Status with color coding"""
        colors = {
            'draft': 'gray',
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'cancelled': 'red',
            'converted': 'blue'
        }
        color = colors.get(obj.status, 'gray')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        """Urgency with appropriate styling"""
        icons = {
            'normal': '📝',
            'urgent': '⚡',
            'emergency': '🚨'
        }
        colors = {
            'normal': 'gray',
            'urgent': 'orange',
            'emergency': 'red'
        }

        icon = icons.get(obj.urgency_level, '📝')
        color = colors.get(obj.urgency_level, 'gray')

        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_urgency_level_display()
        )

    urgency_display.short_description = _('Urgency')

    def total_amount(self, obj):
        """Calculate total estimated amount"""
        total = sum(
            line.estimated_price * line.requested_quantity
            for line in obj.lines.all()
            if line.estimated_price
        )
        return format_html(
            '<strong>{:.2f} лв</strong>',
            total
        ) if total > 0 else '-'

    total_amount.short_description = _('Est. Total')

    def approval_status(self, obj):
        """Approval status badge"""
        if not obj.approval_required:
            return format_html('<span style="color: gray;">Not Required</span>')
        elif obj.approved_by:
            return format_html('<span style="color: green;">✅ Approved</span>')
        elif obj.status == 'rejected':
            return format_html('<span style="color: red;">❌ Rejected</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')

    approval_status.short_description = _('Approval')

    def conversion_status(self, obj):
        """Conversion status"""
        if obj.converted_to_order:
            url = reverse('admin:purchases_purchaseorder_change',
                          args=[obj.converted_to_order.pk])
            return format_html(
                '<a href="{}">✅ ORD-{}</a>',
                url, obj.converted_to_order.document_number
            )
        elif obj.status == 'approved':
            return format_html('<span style="color: orange;">Ready to Convert</span>')
        else:
            return format_html('<span style="color: gray;">-</span>')

    conversion_status.short_description = _('Conversion')

    def request_analytics(self, obj):
        """Detailed request analytics"""
        if not obj.pk:
            return "Save request first to see analytics"

        try:
            lines_count = obj.lines.count()
            estimated_total = sum(
                line.estimated_price * line.requested_quantity
                for line in obj.lines.all()
                if line.estimated_price
            )

            analysis_parts = [
                f"<strong>Request Type:</strong> {obj.get_request_type_display()}",
                f"<strong>Lines Count:</strong> {lines_count}",
                f"<strong>Estimated Total:</strong> {estimated_total:.2f} лв",
                f"<strong>Requested By:</strong> {obj.requested_by.get_full_name()}",
                f"<strong>Days Since Created:</strong> {(timezone.now().date() - obj.document_date).days}",
            ]

            if obj.approved_by:
                analysis_parts.append(f"<strong>Approved By:</strong> {obj.approved_by.get_full_name()}")

            if obj.converted_to_order:
                analysis_parts.append(f"<strong>Converted To:</strong> ORD-{obj.converted_to_order.document_number}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    request_analytics.short_description = _('Request Analytics')

    # Actions
    actions = ['approve_requests', 'convert_to_orders', 'mark_as_draft']

    def approve_requests(self, request, queryset):
        """Approve selected requests"""
        count = 0
        for req in queryset.filter(status='pending'):
            try:
                if hasattr(req, 'approve'):
                    req.approve(request.user)
                    count += 1
            except:
                pass

        self.message_user(request, f'Approved {count} requests.')

    approve_requests.short_description = _('Approve selected requests')

    def convert_to_orders(self, request, queryset):
        """Convert approved requests to orders"""
        count = 0
        for req in queryset.filter(status='approved'):
            try:
                if hasattr(req, 'convert_to_order'):
                    req.convert_to_order()
                    count += 1
            except:
                pass

        self.message_user(request, f'Converted {count} requests to orders.')

    convert_to_orders.short_description = _('Convert to purchase orders')


# === PURCHASE ORDER ADMIN ===

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Professional admin for Purchase Orders"""

    list_display = [
        'document_number', 'supplier', 'status_display', 'urgent_badge',
        'order_total', 'delivery_status_display', 'expected_delivery_date',
        'days_until_delivery'
    ]

    list_filter = [
        'status', 'delivery_status', 'is_urgent', 'supplier_confirmed',
        'expected_delivery_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference',
        'delivery_terms'
    ]

    date_hierarchy = 'expected_delivery_date'

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'sent_to_supplier_at',
        'order_analytics'
    ]

    fieldsets = (
        (_('Order Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'document_date',
                'expected_delivery_date'
            )
        }),
        (_('Order Details'), {
            'fields': (
                'is_urgent', 'order_method', 'delivery_terms',
                'payment_terms', 'special_conditions'
            )
        }),
        (_('Supplier Communication'), {
            'fields': (
                'status', 'supplier_confirmed', 'supplier_order_reference',
                'sent_to_supplier_at', 'sent_by'
            ),
            'classes': ('collapse',)
        }),
        (_('Source Tracking'), {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('order_analytics',),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [PurchaseOrderLineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'source_request', 'sent_by'
        ).prefetch_related('lines')

    def status_display(self, obj):
        """Status with color coding"""
        colors = {
            'draft': 'gray',
            'sent': 'orange',
            'confirmed': 'green',
            'partially_received': 'blue',
            'received': 'green',
            'cancelled': 'red'
        }
        color = colors.get(obj.status, 'gray')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def urgent_badge(self, obj):
        """Urgent order badge"""
        if obj.is_urgent:
            return format_html('<span style="color: red; font-weight: bold;">🚨 URGENT</span>')
        return ''

    urgent_badge.short_description = _('Priority')

    def order_total(self, obj):
        """Calculate order total"""
        total = sum(line.line_total for line in obj.lines.all())
        return format_html(
            '<strong>{:.2f} лв</strong>',
            total
        ) if total > 0 else '-'

    order_total.short_description = _('Order Total')

    def delivery_status_display(self, obj):
        """Delivery status with progress"""
        colors = {
            'pending': 'orange',
            'partial': 'blue',
            'completed': 'green',
            'cancelled': 'red'
        }
        icons = {
            'pending': '⏳',
            'partial': '📦',
            'completed': '✅',
            'cancelled': '❌'
        }

        color = colors.get(obj.delivery_status, 'gray')
        icon = icons.get(obj.delivery_status, '❓')

        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_delivery_status_display()
        )

    delivery_status_display.short_description = _('Delivery')

    def days_until_delivery(self, obj):
        """Days until expected delivery"""
        if not obj.expected_delivery_date:
            return '-'

        today = timezone.now().date()
        days = (obj.expected_delivery_date - today).days

        if days < 0:
            return format_html('<span style="color: red;">⚠️ {} days overdue</span>', abs(days))
        elif days == 0:
            return format_html('<span style="color: orange;">📅 Today</span>')
        elif days <= 3:
            return format_html('<span style="color: orange;">⏰ {} days</span>', days)
        else:
            return format_html('<span style="color: green;">📅 {} days</span>', days)

    days_until_delivery.short_description = _('Delivery In')

    def order_analytics(self, obj):
        """Detailed order analytics"""
        if not obj.pk:
            return "Save order first to see analytics"

        try:
            lines_count = obj.lines.count()
            order_total = sum(line.line_total for line in obj.lines.all())

            analysis_parts = [
                f"<strong>Order Method:</strong> {obj.order_method or 'Standard'}",
                f"<strong>Lines Count:</strong> {lines_count}",
                f"<strong>Order Total:</strong> {order_total:.2f} лв",
                f"<strong>Supplier Confirmed:</strong> {'Yes' if obj.supplier_confirmed else 'No'}",
            ]

            if obj.source_request:
                analysis_parts.append(f"<strong>From Request:</strong> REQ-{obj.source_request.document_number}")

            if obj.sent_to_supplier_at:
                analysis_parts.append(
                    f"<strong>Sent Date:</strong> {obj.sent_to_supplier_at.strftime('%Y-%m-%d %H:%M')}")

            if obj.supplier_order_reference:
                analysis_parts.append(f"<strong>Supplier Ref:</strong> {obj.supplier_order_reference}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    order_analytics.short_description = _('Order Analytics')

    # Actions
    actions = ['send_to_supplier', 'mark_as_confirmed', 'create_delivery_receipts']

    def send_to_supplier(self, request, queryset):
        """Send orders to supplier"""
        count = 0
        for order in queryset.filter(status='draft'):
            try:
                if hasattr(order, 'send_to_supplier'):
                    order.send_to_supplier()
                    count += 1
            except:
                pass

        self.message_user(request, f'Sent {count} orders to suppliers.')

    send_to_supplier.short_description = _('Send to supplier')

    def mark_as_confirmed(self, request, queryset):
        """Mark orders as confirmed by supplier"""
        count = 0
        for order in queryset.filter(status='sent'):
            try:
                if hasattr(order, 'confirm_by_supplier'):
                    order.confirm_by_supplier(request.user)
                    count += 1
            except:
                pass

        self.message_user(request, f'Confirmed {count} orders.')

    mark_as_confirmed.short_description = _('Mark as confirmed by supplier')


# === DELIVERY RECEIPT ADMIN ===


# === DELIVERY RECEIPT ADMIN ===

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Professional admin for Delivery Receipts"""

    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status_display',
        'quality_status', 'variance_status', 'received_by', 'total_value'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'has_variances', 'quality_checked',
        'delivery_date', 'supplier', 'creation_type'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number',
        'vehicle_info', 'driver_name'
    ]

    date_hierarchy = 'delivery_date'

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'received_at',
        'processed_at', 'delivery_analytics'
    ]

    fieldsets = (
        (_('Delivery Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'delivery_date',
                'delivery_note_number'
            )
        }),
        (_('Delivery Details'), {
            'fields': (
                'creation_type', 'vehicle_info', 'driver_name', 'driver_phone',
                'special_handling_notes'
            )
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_checked', 'has_quality_issues', 'quality_inspector',
                'quality_notes'
            ),
            'classes': ('collapse',)
        }),
        (_('Variance Tracking'), {
            'fields': ('has_variances', 'variance_notes'),
            'classes': ('collapse',)
        }),
        (_('Processing'), {
            'fields': (
                'status', 'received_by', 'received_at', 'processed_at'
            ),
            'classes': ('collapse',)
        }),
        (_('Source Orders'), {
            'fields': ('source_orders',),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('delivery_analytics',),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    filter_horizontal = ['source_orders']
    inlines = [DeliveryLineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'received_by', 'quality_inspector'
        ).prefetch_related('lines', 'source_orders')

    def status_display(self, obj):
        """Status with color coding"""
        colors = {
            'draft': 'gray',
            'received': 'blue',
            'quality_checked': 'orange',
            'processed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(obj.status, 'gray')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def quality_status(self, obj):
        """Quality check status"""
        if not obj.quality_checked:
            return format_html('<span style="color: orange;">⏳ Pending</span>')
        elif obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues Found</span>')
        else:
            return format_html('<span style="color: green;">✅ Passed</span>')

    quality_status.short_description = _('Quality')

    def variance_status(self, obj):
        """Variance status"""
        if obj.has_variances:
            return format_html('<span style="color: orange;">⚠️ Variances</span>')
        else:
            return format_html('<span style="color: green;">✅ As Ordered</span>')

    variance_status.short_description = _('Variance')

    def total_value(self, obj):
        """Calculate total delivery value"""
        total = sum(line.line_total for line in obj.lines.all())
        return format_html(
            '<strong>{:.2f} лв</strong>',
            total
        ) if total > 0 else '-'

    total_value.short_description = _('Total Value')

    def delivery_analytics(self, obj):
        """Detailed delivery analytics"""
        if not obj.pk:
            return "Save delivery first to see analytics"

        try:
            lines_count = obj.lines.count()
            total_value = sum(line.line_total for line in obj.lines.all())
            source_orders_count = obj.source_orders.count()

            analysis_parts = [
                f"<strong>Creation Type:</strong> {obj.get_creation_type_display()}",
                f"<strong>Lines Count:</strong> {lines_count}",
                f"<strong>Total Value:</strong> {total_value:.2f} лв",
                f"<strong>Source Orders:</strong> {source_orders_count}",
                f"<strong>Received By:</strong> {obj.received_by.get_full_name() if obj.received_by else 'N/A'}",
            ]

            if obj.delivery_note_number:
                analysis_parts.append(f"<strong>Delivery Note:</strong> {obj.delivery_note_number}")

            if obj.vehicle_info:
                analysis_parts.append(f"<strong>Vehicle:</strong> {obj.vehicle_info}")

            if obj.quality_inspector:
                analysis_parts.append(f"<strong>Quality Inspector:</strong> {obj.quality_inspector.get_full_name()}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    delivery_analytics.short_description = _('Delivery Analytics')

    # Actions
    actions = ['process_deliveries', 'mark_quality_checked', 'create_inventory_movements']

    def process_deliveries(self, request, queryset):
        """Process selected deliveries"""
        count = 0
        for delivery in queryset.filter(status='received'):
            try:
                if hasattr(delivery, 'process_delivery'):
                    delivery.process_delivery(request.user)
                    count += 1
            except Exception as e:
                self.message_user(request, f'Error processing {delivery.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Processed {count} deliveries.')

    process_deliveries.short_description = _('Process deliveries')

    def mark_quality_checked(self, request, queryset):
        """Mark deliveries as quality checked"""
        count = queryset.update(
            quality_checked=True,
            quality_inspector=request.user
        )
        self.message_user(request, f'Marked {count} deliveries as quality checked.')

    mark_quality_checked.short_description = _('Mark as quality checked')

    def create_inventory_movements(self, request, queryset):
        """Create inventory movements without direct FK"""
        count = 0
        for delivery in queryset.filter(status='processed'):
            try:
                # Използвай service вместо direct FK
                from inventory.services import MovementService

                for line in delivery.lines.all():
                    MovementService.create_incoming_movement(
                        location=delivery.location,
                        product=line.product,
                        quantity=line.received_qty,
                        cost_price=line.unit_cost,
                        source_document_type='PURCHASE',
                        source_document_number=delivery.document_number,
                        # ✅ БЕЗ delivery_receipt=delivery
                    )
                count += 1
            except Exception as e:
                pass

    create_inventory_movements.short_description = _('Create inventory movements')


# === DOCUMENT LINE ADMINS (Optional - for detailed management) ===



@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    """Admin for order lines"""

    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'unit_price', 'line_total', 'delivery_status'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    def delivery_status(self, obj):
        if hasattr(obj, 'received_quantity') and obj.received_quantity:
            if obj.received_quantity >= obj.ordered_quantity:
                return format_html('<span style="color: green;">✅ Delivered</span>')
            else:
                return format_html('<span style="color: orange;">📦 Partial</span>')
        else:
            return format_html('<span style="color: gray;">Pending</span>')

    delivery_status.short_description = _('Delivery')



# Customize admin site header and title
admin.site.site_header = _('OptimaPos Purchase Management')
admin.site.site_title = _('OptimaPos Admin')
admin.site.index_title = _('Purchase Management Dashboard')

# Group models in admin index
admin.site.app_index_template = 'admin/purchases/app_index.html'  # Custom template if needed


def variance_status(self, obj):
    """Variance status"""
    if obj.has_variances:
        return format_html('<span style="color: orange;">⚠️ Variances</span>')
    else:
        return format_html('<span style="color: green;">✅ As Ordered</span>')


variance_status.short_description = _('Variance')


def total_value(self, obj):
    """Calculate total delivery value"""
    total = sum(line.line_total for line in obj.lines.all())
    return format_html(
        '<strong>{:.2f} лв</strong>',
        total
    ) if total > 0 else '-'


total_value.short_description = _('Total Value')


def delivery_analytics(self, obj):
    """Detailed delivery analytics"""
    if not obj.pk:
        return "Save delivery first to see analytics"

    try:
        lines_count = obj.lines.count()
        total_value = sum(line.line_total for line in obj.lines.all())
        source_orders_count = obj.source_orders.count()

        analysis_parts = [
            f"<strong>Creation Type:</strong> {obj.get_creation_type_display()}",
            f"<strong>Lines Count:</strong> {lines_count}",
            f"<strong>Total Value:</strong> {total_value:.2f} лв",
            f"<strong>Source Orders:</strong> {source_orders_count}",
            f"<strong>Received By:</strong> {obj.received_by.get_full_name() if obj.received_by else 'N/A'}",
        ]

        if obj.delivery_note_number:
            analysis_parts.append(f"<strong>Delivery Note:</strong> {obj.delivery_note_number}")

        if obj.vehicle_info:
            analysis_parts.append(f"<strong>Vehicle:</strong> {obj.vehicle_info}")

        if obj.quality_inspector:
            analysis_parts.append(f"<strong>Quality Inspector:</strong> {obj.quality_inspector.get_full_name()}")

        return mark_safe('<br>'.join(analysis_parts))

    except Exception as e:
        return f"Analysis error: {str(e)}"


delivery_analytics.short_description = _('Delivery Analytics')

# Actions
actions = ['process_deliveries', 'mark_quality_checked', 'create_inventory_movements']


def process_deliveries(self, request, queryset):
    """Process selected deliveries"""
    count = 0
    for delivery in queryset.filter(status='received'):
        try:
            if hasattr(delivery, 'process_delivery'):
                delivery.process_delivery(request.user)
                count += 1
        except Exception as e:
            self.message_user(request, f'Error processing {delivery.document_number}: {e}', level='ERROR')

    self.message_user(request, f'Processed {count} deliveries.')


process_deliveries.short_description = _('Process deliveries')


def mark_quality_checked(self, request, queryset):
    """Mark deliveries as quality checked"""
    count = queryset.update(
        quality_checked=True,
        quality_inspector=request.user
    )
    self.message_user(request, f'Marked {count} deliveries as quality checked.')


mark_quality_checked.short_description = _('Mark as quality checked')


# === DOCUMENT LINE ADMINS (Optional - for detailed management) ===



@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    """Admin for delivery lines"""

    list_display = [
        'document', 'line_number', 'product', 'received_quantity',
        'unit_price', 'quality_status', 'batch_number', 'expiry_date'
    ]

    list_filter = [
        'quality_approved', 'document__status', 'document__supplier',
        'expiry_date'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number',
        'document__document_number'
    ]

    def get_queryset(self, request):  # ← ДОБАВИ def и правилни параметри
        return super().get_queryset(request).select_related('product', 'unit')

    def quality_status(self, obj):
        if obj.quality_approved:
            return format_html('<span style="color: green;">✅ Approved</span>')
        else:
            return format_html('<span style="color: red;">❌ Rejected</span>')

    quality_status.short_description = _('Quality')
    # ← ИЗТРИЙ ТОЗИ РЕД: get_queryset(request).select_related('product', 'unit')




# === PURCHASE REQUEST ADMIN ===





@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Admin for request lines"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'estimated_price', 'conversion_status'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    def conversion_status(self, obj):
        if obj.converted_to_order_line:
            return format_html('<span style="color: green;">✅ Converted</span>')
        else:
            return format_html('<span style="color: gray;">Not Converted</span>')

    conversion_status.short_description = _('Conversion')






def get_queryset(self, request):
    return super().get_queryset(request).select_related(
        'supplier', 'location', 'requested_by', 'approved_by'
    ).prefetch_related('lines')


def status_display(self, obj):
    """Status with color coding"""
    colors = {
        'draft': 'gray',
        'pending': 'orange',
        'approved': 'green',
        'rejected': 'red',
        'cancelled': 'red',
        'converted': 'blue'
    }
    color = colors.get(obj.status, 'gray')

    return format_html(
        '<span style="color: {}; font-weight: bold;">{}</span>',
        color, obj.get_status_display()
    )


status_display.short_description = _('Status')


def urgency_display(self, obj):
    """Urgency with appropriate styling"""
    icons = {
        'normal': '📝',
        'urgent': '⚡',
        'emergency': '🚨'
    }
    colors = {
        'normal': 'gray',
        'urgent': 'orange',
        'emergency': 'red'
    }

    icon = icons.get(obj.urgency_level, '📝')
    color = colors.get(obj.urgency_level, 'gray')

    return format_html(
        '<span style="color: {};">{} {}</span>',
        color, icon, obj.get_urgency_level_display()
    )


urgency_display.short_description = _('Urgency')


def total_amount(self, obj):
    """Calculate total estimated amount"""
    total = sum(
        line.estimated_price * line.requested_quantity
        for line in obj.lines.all()
        if line.estimated_price
    )
    return format_html(
        '<strong>{:.2f} лв</strong>',
        total
    ) if total > 0 else '-'


total_amount.short_description = _('Est. Total')


def approval_status(self, obj):
    """Approval status badge"""
    if not obj.approval_required:
        return format_html('<span style="color: gray;">Not Required</span>')
    elif obj.approved_by:
        return format_html('<span style="color: green;">✅ Approved</span>')
    elif obj.status == 'rejected':
        return format_html('<span style="color: red;">❌ Rejected</span>')
    else:
        return format_html('<span style="color: orange;">⏳ Pending</span>')


approval_status.short_description = _('Approval')


def conversion_status(self, obj):
    """Conversion status"""
    if obj.converted_to_order:
        url = reverse('admin:purchases_purchaseorder_change',
                      args=[obj.converted_to_order.pk])
        return format_html(
            '<a href="{}">✅ ORD-{}</a>',
            url, obj.converted_to_order.document_number
        )
    elif obj.status == 'approved':
        return format_html('<span style="color: orange;">Ready to Convert</span>')
    else:
        return format_html('<span style="color: gray;">-</span>')


conversion_status.short_description = _('Conversion')


def request_analytics(self, obj):
    """Detailed request analytics"""
    if not obj.pk:
        return "Save request first to see analytics"

    try:
        lines_count = obj.lines.count()
        estimated_total = sum(
            line.estimated_price * line.requested_quantity
            for line in obj.lines.all()
            if line.estimated_price
        )

        analysis_parts = [
            f"<strong>Request Type:</strong> {obj.get_request_type_display()}",
            f"<strong>Lines Count:</strong> {lines_count}",
            f"<strong>Estimated Total:</strong> {estimated_total:.2f} лв",
            f"<strong>Requested By:</strong> {obj.requested_by.get_full_name()}",
            f"<strong>Days Since Created:</strong> {(timezone.now().date() - obj.document_date).days}",
        ]

        if obj.approved_by:
            analysis_parts.append(f"<strong>Approved By:</strong> {obj.approved_by.get_full_name()}")

        if obj.converted_to_order:
            analysis_parts.append(f"<strong>Converted To:</strong> ORD-{obj.converted_to_order.document_number}")

        return mark_safe('<br>'.join(analysis_parts))

    except Exception as e:
        return f"Analysis error: {str(e)}"


request_analytics.short_description = _('Request Analytics')

# Actions
actions = ['approve_requests', 'convert_to_orders', 'mark_as_draft']


def approve_requests(self, request, queryset):
    """Approve selected requests"""
    count = 0
    for req in queryset.filter(status='pending'):
        if req.can_be_approved():
            req.approve(request.user)
            count += 1

    self.message_user(request, f'Approved {count} requests.')


approve_requests.short_description = _('Approve selected requests')


def convert_to_orders(self, request, queryset):
    """Convert approved requests to orders"""
    count = 0
    for req in queryset.filter(status='approved'):
        if req.can_be_converted():
            req.convert_to_order()
            count += 1

    self.message_user(request, f'Converted {count} requests to orders.')


convert_to_orders.short_description = _('Convert to purchase orders')


# === PURCHASE ORDER ADMIN ===

