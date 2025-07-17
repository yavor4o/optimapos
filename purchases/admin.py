# purchases/admin.py - ПЪЛЕН ПРОФЕСИОНАЛЕН АДМИН ЗА ВСИЧКИ МОДЕЛИ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe


from .models import (
    PurchaseRequest, PurchaseRequestLine,


)


# САМО ЧАСТТА ЗА PurchaseRequest В purchases/admin.py

# =====================
# PURCHASE REQUEST INLINE
# =====================
class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'estimated_price', 'item_justification'
    ]
    readonly_fields = []

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit')


# =====================
# PURCHASE REQUEST ADMIN - DOCUMENTTYPE DRIVEN
# =====================
@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Админ за заявки за покупка - с DocumentType интеграция"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'urgency_display', 'lines_count', 'estimated_total',
        'requested_by', 'document_date'
    ]

    list_filter = [
        'status',  # Dynamic от DocumentType
        'urgency_level',
        'request_type',
        'approval_required',
        'location',
        'supplier',
        'requested_by',
        'document_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'notes', 'external_reference'
    ]

    date_hierarchy = 'document_date'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'approved_at',
        'converted_at', 'request_analytics', 'workflow_info'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_type',  # ← ДОБАВЕНО DocumentType field!
                'document_number', 'supplier', 'location', 'status'
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
                'requested_by', 'approved_by', 'approved_at',
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
        (_('System Info'), {
            'fields': (
                'created_at', 'updated_at', 'request_analytics', 'workflow_info'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'requested_by', 'approved_by',
            'document_type'  # ← DocumentType relation
        ).prefetch_related('lines')

    # =====================
    # DISPLAY METHODS - DOCUMENTTYPE AWARE
    # =====================
    def status_display(self, obj):
        """Dynamic status display based on DocumentType"""
        default_colors = {
            'draft': '#757575',
            'submitted': '#FF9800',
            'approved': '#4CAF50',
            'rejected': '#F44336',
            'converted': '#2196F3',
            'cancelled': '#9E9E9E'
        }

        color = default_colors.get(obj.status, '#757575')

        # Enhanced display with DocumentType context
        status_text = obj.get_status_display_with_context() if hasattr(obj,
                                                                       'get_status_display_with_context') else obj.status.title()

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, status_text
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        colors = {
            'low': '#4CAF50',
            'normal': '#2196F3',
            'high': '#FF9800',
            'critical': '#F44336'
        }
        icons = {
            'low': '📝',
            'normal': '📋',
            'high': '⚡',
            'critical': '🔥'
        }

        color = colors.get(obj.urgency_level, '#757575')
        icon = icons.get(obj.urgency_level, '📋')

        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_urgency_level_display()
        )

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        count = obj.lines.count()
        total_items = sum(line.requested_quantity for line in obj.lines.all())
        return format_html(
            '<strong>{}</strong> lines<br><small>{} items</small>',
            count, total_items
        )

    lines_count.short_description = _('Lines/Items')

    def estimated_total(self, obj):
        try:
            total = sum(
                line.estimated_price * line.requested_quantity
                for line in obj.lines.all()
                if line.estimated_price
            )
            if total > 0:
                return format_html('<strong style="color: #2196F3;">{:.2f} лв</strong>', float(total))
            else:
                return format_html('<span style="color: #999;">No estimate</span>')
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
            f"<strong>Status:</strong> {obj.get_status_display_with_context() if hasattr(obj, 'get_status_display_with_context') else obj.status}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total Items:</strong> {total_items}",
            f"<strong>Urgency:</strong> {obj.get_urgency_level_display()}",
        ]

        if obj.document_type:
            analysis_parts.append(f"<strong>Document Type:</strong> {obj.document_type.name}")

        if obj.requested_by:
            analysis_parts.append(f"<strong>Requested By:</strong> {obj.requested_by.get_full_name()}")

        if obj.approved_by:
            analysis_parts.append(f"<strong>Approved By:</strong> {obj.approved_by.get_full_name()}")

        return mark_safe('<br>'.join(analysis_parts))

    request_analytics.short_description = _('Request Analytics')

    def workflow_info(self, obj):
        """Show DocumentType workflow information"""
        if not obj.pk or not obj.document_type:
            return "Save request first to see workflow info"

        info_parts = []

        # Current workflow status
        if hasattr(obj, 'get_next_statuses'):
            next_statuses = obj.get_next_statuses()
            if next_statuses:
                info_parts.append(f"<strong>Next Statuses:</strong> {', '.join(next_statuses)}")

        # Available actions
        if hasattr(obj, 'get_available_actions'):
            actions = obj.get_available_actions()
            if actions:
                action_labels = [action['label'] for action in actions]
                info_parts.append(f"<strong>Available Actions:</strong> {', '.join(action_labels)}")

        # DocumentType info
        doc_type = obj.document_type
        info_parts.append(f"<strong>Document Type:</strong> {doc_type.name} ({doc_type.code})")

        if doc_type.requires_approval:
            limit_text = f" (>{doc_type.approval_limit} BGN)" if doc_type.approval_limit else ""
            info_parts.append(f"<strong>Requires Approval:</strong> Yes{limit_text}")

        return mark_safe('<br>'.join(info_parts))

    workflow_info.short_description = _('Workflow Info')

    # =====================
    # ACTIONS - DOCUMENTTYPE DRIVEN
    # =====================
    actions = ['submit_requests', 'approve_requests', 'convert_to_orders', 'cancel_requests']

    def submit_requests(self, request, queryset):
        """Submit requests for approval"""
        count = 0
        for req in queryset:
            if hasattr(req, 'can_be_submitted') and req.can_be_submitted():
                try:
                    req.submit_for_approval(request.user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error submitting {req.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Submitted {count} requests for approval.')

    submit_requests.short_description = _('Submit for approval')

    def approve_requests(self, request, queryset):
        """Approve submitted requests"""
        count = 0
        for req in queryset:
            if hasattr(req, 'can_be_approved') and req.can_be_approved():
                try:
                    req.approve(request.user, 'Approved via admin action')
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error approving {req.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Approved {count} requests.')

    approve_requests.short_description = _('Approve requests')

    def convert_to_orders(self, request, queryset):
        """Convert approved requests to orders"""
        count = 0
        for req in queryset:
            if hasattr(req, 'can_be_converted') and req.can_be_converted():
                try:
                    req.convert_to_order(request.user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error converting {req.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Converted {count} requests to orders.')

    convert_to_orders.short_description = _('Convert to orders')

    def cancel_requests(self, request, queryset):
        """Cancel requests"""
        count = 0
        for req in queryset:
            if hasattr(req, 'can_be_cancelled') and req.can_be_cancelled():
                try:
                    req.cancel(request.user, 'Cancelled via admin action')
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error cancelling {req.document_number}: {e}', level='ERROR')

        self.message_user(request, f'Cancelled {count} requests.')

    cancel_requests.short_description = _('Cancel requests')

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


# =====================
# PURCHASE REQUEST LINE ADMIN
# =====================
@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Админ за редове от заявки - enhanced version"""

    list_display = [
        'document_number', 'line_number', 'product', 'requested_quantity_display',
        'estimated_price_display', 'estimated_total_display', 'document_status'
    ]

    list_filter = [
        'document__status',  # Dynamic от DocumentType
        'document__urgency_level',
        'document__request_type',
        'product__product_group',
        'unit'
    ]

    search_fields = [
        'product__code', 'product__name', 'document__document_number',
        'item_justification'
    ]

    readonly_fields = ['estimated_total_display']

    fieldsets = (
        (_('Line Information'), {
            'fields': ('document', 'line_number', 'product', 'unit')
        }),
        (_('Quantities & Pricing'), {
            'fields': ('requested_quantity', 'estimated_price', 'estimated_total_display')
        }),
        (_('Business Details'), {
            'fields': ('item_justification', 'suggested_supplier')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'document__supplier', 'document__document_type',
            'product', 'unit'
        )

    # =====================
    # DISPLAY METHODS
    # =====================
    def document_number(self, obj):
        return obj.document.document_number

    document_number.short_description = _('Document')
    document_number.admin_order_field = 'document__document_number'

    def requested_quantity_display(self, obj):
        if obj.unit:
            return format_html(
                '<strong>{}</strong> {}',
                obj.requested_quantity, obj.unit.code
            )
        return format_html('<strong>{}</strong>', obj.requested_quantity)

    requested_quantity_display.short_description = _('Requested Qty')

    def estimated_price_display(self, obj):
        if obj.estimated_price:
            return format_html(
                '<span style="color: #2196F3;">{:.4f} лв</span>',
                float(obj.estimated_price)
            )
        return format_html('<span style="color: #999;">No estimate</span>')

    estimated_price_display.short_description = _('Est. Price')

    def estimated_total_display(self, obj):
        if obj.estimated_total:
            return format_html(
                '<strong style="color: #4CAF50;">{:.2f} лв</strong>',
                float(obj.estimated_total)
            )
        return format_html('<span style="color: #999;">-</span>')

    estimated_total_display.short_description = _('Est. Total')

    def document_status(self, obj):
        """Show document status"""
        status_colors = {
            'draft': '#757575',
            'submitted': '#FF9800',
            'approved': '#4CAF50',
            'rejected': '#F44336',
            'converted': '#2196F3',
            'cancelled': '#9E9E9E'
        }

        color = status_colors.get(obj.document.status, '#757575')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.document.status.title()
        )

    document_status.short_description = _('Doc Status')
    document_status.admin_order_field = 'document__status'