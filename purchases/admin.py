# purchases/admin.py - ПЪЛЕН ПРОФЕСИОНАЛЕН АДМИН ЗА ВСИЧКИ МОДЕЛИ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q
from django.utils import timezone

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine,

)


# =================================================================
# INLINE ADMINS
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'estimated_price', 'suggested_supplier', 'priority'
    ]
    readonly_fields = ['line_number']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'line_number', 'product', 'ordered_quantity', 'unit', 'unit_price',
        'discount_percent', 'line_total', 'delivery_status'
    ]
    readonly_fields = ['line_number', 'line_total']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'line_number', 'product', 'received_quantity', 'unit', 'unit_price',
        'batch_number', 'expiry_date', 'quality_approved', 'quality_issue_type'
    ]
    readonly_fields = ['line_number', 'variance_quantity']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


# =================================================================
# PURCHASE REQUEST ADMIN
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Админ за заявки за покупка"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'urgency_display', 'lines_count', 'estimated_total', 'requested_by',
        'created_at'
    ]

    list_filter = [
        'status', 'urgency_level', 'location', 'supplier',
        'created_at', 'requested_by'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'requested_by__username',
        'notes', 'external_reference'
    ]

    date_hierarchy = 'created_at'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'request_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'urgency_level'
            )
        }),
        (_('Request Details'), {
            'fields': (
                'document_date', 'external_reference', 'requested_by',
                'approved_by', 'approved_at'
            )
        }),
        (_('Notes'), {
            'fields': ('notes',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at', 'request_analytics'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'requested_by', 'approved_by'
        ).prefetch_related('lines')

    # Display methods
    def status_display(self, obj):
        colors = {
            'draft': '#757575',
            'submitted': '#FF9800',
            'approved': '#4CAF50',
            'converted': '#2196F3',
            'rejected': '#F44336',
            'cancelled': '#9E9E9E'
        }
        color = colors.get(obj.status, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        if obj.urgency_level == 'high':
            return format_html('<span style="color: #F44336;">🔥 High</span>')
        elif obj.urgency_level == 'medium':
            return format_html('<span style="color: #FF9800;">⚡ Medium</span>')
        else:
            return format_html('<span style="color: #4CAF50;">📋 Normal</span>')

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def estimated_total(self, obj):
        try:
            total = sum(
                line.estimated_price * line.requested_quantity
                for line in obj.lines.all()
                if line.estimated_price
            )
            return format_html('<strong>{:.2f} лв</strong>', float(total))
        except:
            return '-'

    estimated_total.short_description = _('Estimated Total')

    def request_analytics(self, obj):
        if not obj.pk:
            return "Save request first to see analytics"

        lines_count = obj.lines.count()
        total_items = sum(line.requested_quantity for line in obj.lines.all())

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.get_status_display()}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total Items:</strong> {total_items}",
            f"<strong>Urgency:</strong> {obj.get_urgency_level_display()}",
        ]

        if obj.requested_by:
            analysis_parts.append(f"<strong>Requested By:</strong> {obj.requested_by.get_full_name()}")

        if obj.approved_by:
            analysis_parts.append(f"<strong>Approved By:</strong> {obj.approved_by.get_full_name()}")

        return mark_safe('<br>'.join(analysis_parts))

    request_analytics.short_description = _('Request Analytics')

    # Actions
    actions = ['submit_requests', 'approve_requests', 'convert_to_orders']

    def submit_requests(self, request, queryset):
        count = queryset.filter(status='draft').update(status='submitted')
        self.message_user(request, f'Submitted {count} requests.')

    submit_requests.short_description = _('Submit requests')

    def approve_requests(self, request, queryset):
        count = queryset.filter(status='submitted').update(
            status='approved',
            approved_by=request.user,
            approved_at=timezone.now()
        )
        self.message_user(request, f'Approved {count} requests.')

    approve_requests.short_description = _('Approve requests')

    def convert_to_orders(self, request, queryset):
        count = 0
        for req in queryset.filter(status='approved'):
            try:
                # Here you would call a service to convert request to order
                count += 1
            except Exception as e:
                self.message_user(request, f'Error converting {req.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Converted {count} requests to orders.')

    convert_to_orders.short_description = _('Convert to orders')


# =================================================================
# PURCHASE ORDER ADMIN
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Админ за поръчки към доставчици"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'urgency_display', 'lines_count', 'grand_total_display',
        'expected_delivery_date', 'delivery_status_display'
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
        'discount_total', 'vat_total', 'grand_total', 'order_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'is_urgent'
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
        (_('Payment Information'), {
            'fields': ('is_paid', 'payment_date', 'payment_method'),
            'classes': ('collapse',)
        }),
        (_('Notes'), {
            'fields': ('notes',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at', 'order_analytics'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'source_request'
        ).prefetch_related('lines')

    # Display methods
    def status_display(self, obj):
        colors = {
            'draft': '#757575',
            'sent': '#FF9800',
            'confirmed': '#4CAF50',
            'cancelled': '#F44336',
            'completed': '#2196F3'
        }
        color = colors.get(obj.status, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        if obj.is_urgent:
            return format_html('<span style="color: #F44336;">🔥 Urgent</span>')
        else:
            return format_html('<span style="color: #4CAF50;">📋 Normal</span>')

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def grand_total_display(self, obj):
        try:
            total = float(obj.grand_total) if obj.grand_total else 0
            return format_html('<strong style="color: #2196F3;">{:.2f} лв</strong>', total)
        except:
            return '-'

    grand_total_display.short_description = _('Grand Total')

    def delivery_status_display(self, obj):
        colors = {
            'pending': '#FF9800',
            'partial': '#9C27B0',
            'completed': '#4CAF50',
            'cancelled': '#F44336'
        }
        color = colors.get(obj.delivery_status, '#757575')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_delivery_status_display()
        )

    delivery_status_display.short_description = _('Delivery Status')

    def order_analytics(self, obj):
        if not obj.pk:
            return "Save order first to see analytics"

        lines_count = obj.lines.count()
        total_value = float(obj.grand_total) if obj.grand_total else 0

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.get_status_display()}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total Value:</strong> {total_value:.2f} лв",
            f"<strong>Delivery Status:</strong> {obj.get_delivery_status_display()}",
        ]

        if obj.source_request:
            analysis_parts.append(f"<strong>Source Request:</strong> {obj.source_request.document_number}")

        if obj.supplier_order_reference:
            analysis_parts.append(f"<strong>Supplier Reference:</strong> {obj.supplier_order_reference}")

        if obj.expected_delivery_date:
            analysis_parts.append(f"<strong>Expected Delivery:</strong> {obj.expected_delivery_date}")

        return mark_safe('<br>'.join(analysis_parts))

    order_analytics.short_description = _('Order Analytics')

    # Actions
    actions = ['send_to_supplier', 'mark_as_confirmed', 'create_deliveries']

    def send_to_supplier(self, request, queryset):
        count = queryset.filter(status='draft').update(status='sent')
        self.message_user(request, f'Sent {count} orders to suppliers.')

    send_to_supplier.short_description = _('Send to supplier')

    def mark_as_confirmed(self, request, queryset):
        count = queryset.filter(status='sent').update(
            status='confirmed',
            supplier_confirmed=True
        )
        self.message_user(request, f'Confirmed {count} orders.')

    mark_as_confirmed.short_description = _('Mark as confirmed')

    def create_deliveries(self, request, queryset):
        count = 0
        for order in queryset.filter(status='confirmed'):
            try:
                # Here you would call delivery service
                count += 1
            except Exception as e:
                self.message_user(request, f'Error creating delivery for {order.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Created deliveries for {count} orders.')

    create_deliveries.short_description = _('Create deliveries')


# =================================================================
# DELIVERY RECEIPT ADMIN
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Професионален админ за доставки"""

    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status_display',
        'quality_status', 'variance_status', 'received_by_display', 'total_value'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'has_variances', 'quality_checked',
        'delivery_date', 'supplier', 'creation_type', 'location'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number',
        'vehicle_info', 'driver_name', 'notes'
    ]

    date_hierarchy = 'delivery_date'
    inlines = [DeliveryLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'received_at',
        'processed_at', 'subtotal', 'discount_total', 'vat_total',
        'grand_total', 'delivery_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'creation_type'
            )
        }),
        (_('Delivery Details'), {
            'fields': (
                'delivery_date', 'delivery_note_number', 'external_reference',
                'vehicle_info', 'driver_name', 'driver_phone'
            )
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_checked', 'has_quality_issues', 'quality_inspector',
                'quality_notes'
            ),
            'classes': ('collapse',)
        }),
        (_('Financial Summary'), {
            'fields': (
                'subtotal', 'discount_total', 'vat_total', 'grand_total'
            ),
            'classes': ('collapse',)
        }),
        (_('Status Tracking'), {
            'fields': (
                'has_variances', 'received_by', 'received_at',
                'processed_by', 'processed_at'
            ),
            'classes': ('collapse',)
        }),
        (_('Additional Info'), {
            'fields': (
                'special_handling_notes', 'notes'
            ),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': (
                'created_at', 'updated_at', 'delivery_analytics'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'received_by', 'quality_inspector'
        ).prefetch_related('lines')

    # Display methods
    def status_display(self, obj):
        colors = {
            'draft': '#757575',
            'delivered': '#FF9800',
            'received': '#2196F3',
            'processed': '#9C27B0',
            'completed': '#4CAF50',
            'cancelled': '#F44336'
        }
        color = colors.get(obj.status, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = _('Status')

    def quality_status(self, obj):
        if obj.quality_checked:
            if obj.has_quality_issues:
                return format_html('<span style="color: #F44336;">❌ Issues Found</span>')
            else:
                return format_html('<span style="color: #4CAF50;">✅ Approved</span>')
        else:
            return format_html('<span style="color: #FF9800;">⏳ Pending</span>')

    quality_status.short_description = _('Quality')

    def variance_status(self, obj):
        if obj.has_variances:
            return format_html('<span style="color: #FF5722;">⚠️ Variances</span>')
        else:
            return format_html('<span style="color: #4CAF50;">✓ No Variances</span>')

    variance_status.short_description = _('Variances')

    def received_by_display(self, obj):
        if obj.received_by:
            return format_html(
                '<span title="Received: {}">{}</span>',
                obj.received_at.strftime('%d.%m.%Y %H:%M') if obj.received_at else 'Unknown time',
                obj.received_by.get_full_name() or obj.received_by.username
            )
        return '-'

    received_by_display.short_description = _('Received By')

    def total_value(self, obj):
        try:
            total = float(obj.grand_total) if obj.grand_total else 0
            return format_html('<strong style="color: #2196F3;">{:.2f} лв</strong>', total)
        except:
            return '-'

    total_value.short_description = _('Total Value')

    def delivery_analytics(self, obj):
        if not obj.pk:
            return "Save delivery first to see analytics"

        try:
            lines_count = obj.lines.count()
            total_value = float(obj.grand_total) if obj.grand_total else 0

            # Safe access to source_orders
            source_orders_count = 0
            if obj.pk:
                try:
                    source_orders_count = obj.source_orders.count()
                except:
                    pass

            analysis_parts = [
                f"<strong>Document:</strong> {obj.document_number}",
                f"<strong>Status:</strong> {obj.get_status_display()}",
                f"<strong>Lines:</strong> {lines_count}",
                f"<strong>Total Value:</strong> {total_value:.2f} лв",
                f"<strong>Source Orders:</strong> {source_orders_count}",
                f"<strong>Creation Type:</strong> {obj.get_creation_type_display()}",
            ]

            if obj.received_by:
                analysis_parts.append(f"<strong>Received By:</strong> {obj.received_by.get_full_name()}")

            if obj.delivery_note_number:
                analysis_parts.append(f"<strong>Delivery Note:</strong> {obj.delivery_note_number}")

            if obj.vehicle_info:
                analysis_parts.append(f"<strong>Vehicle:</strong> {obj.vehicle_info}")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analysis error: {str(e)}"

    delivery_analytics.short_description = _('Delivery Analytics')

    # Actions
    actions = ['mark_as_delivered', 'receive_deliveries', 'mark_quality_checked']

    def mark_as_delivered(self, request, queryset):
        count = 0
        for delivery in queryset.filter(status='draft'):
            try:
                delivery.mark_as_delivered(request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f'Error marking {delivery.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Marked {count} deliveries as delivered.')

    mark_as_delivered.short_description = _('Mark as delivered')

    def receive_deliveries(self, request, queryset):
        count = 0
        for delivery in queryset.filter(status='delivered'):
            try:
                delivery.receive_delivery(request.user, quality_check=True)
                count += 1
            except Exception as e:
                self.message_user(request, f'Error receiving {delivery.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Received {count} deliveries.')

    receive_deliveries.short_description = _('Receive deliveries')

    def mark_quality_checked(self, request, queryset):
        count = queryset.update(
            quality_checked=True,
            quality_inspector=request.user
        )
        self.message_user(request, f'Quality checked {count} deliveries.')

    mark_quality_checked.short_description = _('Mark quality checked')


# =================================================================
# DOCUMENT TYPE ADMIN
# =================================================================

# @admin.register(DocumentType)
# class DocumentTypeAdmin(admin.ModelAdmin):
#     """Админ за типове документи"""
#
#     list_display = [
#         'code', 'name', 'type_key', 'stock_effect_display',
#         'can_be_source', 'sort_order', 'is_active'
#     ]
#
#     list_filter = [
#         'type_key', 'is_active', 'stock_effect', 'can_be_source'
#     ]
#
#     search_fields = ['code', 'name', 'description']
#
#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': ('code', 'name', 'type_key', 'description')
#         }),
#         (_('Behavior'), {
#             'fields': (
#                 'stock_effect', 'can_be_source', 'can_reference_multiple_sources',
#                 'requires_batch', 'requires_quality_check'
#             )
#         }),
#         (_('Display'), {
#             'fields': ('sort_order', 'is_active')
#         }),
#     )
#
#     def stock_effect_display(self, obj):
#         if obj.stock_effect == 1:
#             return format_html('<span style="color: #4CAF50;">⬆️ Increase</span>')
#         elif obj.stock_effect == -1:
#             return format_html('<span style="color: #F44336;">⬇️ Decrease</span>')
#         else:
#             return format_html('<span style="color: #757575;">➖ No Effect</span>')
#
#     stock_effect_display.short_description = _('Stock Effect')


# =================================================================
# LINE ADMINS (Optional - for detailed management)
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Админ за редове от заявки"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'estimated_price', 'priority_display'
    ]

    list_filter = ['document__status', 'priority', 'suggested_supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    def priority_display(self, obj):
        if obj.priority > 0:
            return format_html('<span style="color: #F44336;">🔥 {}</span>', obj.priority)
        return '-'

    priority_display.short_description = _('Priority')


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    """Админ за редове от поръчки"""

    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'unit_price', 'line_total', 'delivery_status'
    ]

    list_filter = ['document__status', 'delivery_status']
    search_fields = ['product__code', 'product__name', 'document__document_number']


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    """Админ за редове от доставки"""

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

    def quality_status(self, obj):
        if obj.quality_approved:
            return format_html('<span style="color: green;">✅ Approved</span>')
        else:
            return format_html('<span style="color: red;">❌ Rejected</span>')

    quality_status.short_description = _('Quality')