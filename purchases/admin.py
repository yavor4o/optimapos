# purchases/admin.py

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django import forms

from .models.requests import PurchaseRequest, PurchaseRequestLine
from .models.orders import PurchaseOrder, PurchaseOrderLine
from .models.deliveries import DeliveryReceipt, DeliveryLine
from .services.request_service import RequestService
from .services.workflow_service import WorkflowService


# =====================
# FORMS - БАЗИРАНИ НА РЕАЛНАТА СТРУКТУРА
# =====================

class PurchaseRequestLineForm(forms.ModelForm):
    """Enhanced form for Purchase Request Lines - ПРАВИЛНО според migration 0004"""

    class Meta:
        model = PurchaseRequestLine
        fields = [
            'product', 'requested_quantity', 'estimated_price',
            'usage_description', 'alternative_products', 'quality_notes',
            'batch_number', 'expiry_date', 'quality_approved', 'serial_numbers'
        ]
        widgets = {
            'usage_description': forms.Textarea(attrs={'rows': 2}),
            'alternative_products': forms.Textarea(attrs={'rows': 2}),
            'quality_notes': forms.Textarea(attrs={'rows': 2}),
            'serial_numbers': forms.Textarea(attrs={'rows': 2}),
            'requested_quantity': forms.NumberInput(attrs={'step': '0.001'}),
            'estimated_price': forms.NumberInput(attrs={'step': '0.01'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_requested_quantity(self):
        quantity = self.cleaned_data.get('requested_quantity')
        if quantity is None:
            raise ValidationError(_('Requested quantity is required'))
        if quantity <= 0:
            raise ValidationError(_('Requested quantity must be positive'))
        return quantity

    def clean_estimated_price(self):
        price = self.cleaned_data.get('estimated_price')
        if price is not None and price < 0:
            raise ValidationError(_('Estimated price cannot be negative'))
        return price


class PurchaseOrderLineForm(forms.ModelForm):
    """Form for Purchase Order Lines"""

    class Meta:
        model = PurchaseOrderLine
        fields = ['product', 'quantity', 'unit_price', 'discount_percent']


class DeliveryLineForm(forms.ModelForm):
    """Form for Delivery Lines"""

    class Meta:
        model = DeliveryLine
        fields = ['product', 'received_quantity', 'unit_price', 'quality_approved']


# =====================
# INLINES - АКТУАЛИЗИРАНИ ПОЛЕТА
# =====================

class PurchaseRequestLineInline(admin.TabularInline):
    """Inline for Purchase Request Lines"""

    model = PurchaseRequestLine
    form = PurchaseRequestLineForm
    extra = 1
    min_num = 1

    fields = [
        'line_number', 'product', 'requested_quantity',
        'estimated_price', 'usage_description', 'quality_approved'
    ]

    readonly_fields = ['line_number']

    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly for non-draft requests"""
        readonly = list(self.readonly_fields)

        if obj and obj.status != 'draft':
            readonly.extend(['product', 'requested_quantity', 'estimated_price'])

        return readonly


class PurchaseOrderLineInline(admin.TabularInline):
    """Inline for Purchase Order Lines"""

    model = PurchaseOrderLine
    form = PurchaseOrderLineForm
    extra = 0
    min_num = 1

    fields = ['line_number', 'product', 'quantity', 'unit_price', 'line_total_display']
    readonly_fields = ['line_number', 'line_total_display']

    def line_total_display(self, obj):
        if obj and obj.quantity and obj.unit_price:
            return format_html('<strong>{:.2f}</strong>', obj.quantity * obj.unit_price)
        return '-'

    line_total_display.short_description = _('Line Total')


class DeliveryLineInline(admin.TabularInline):
    """Inline for Delivery Lines"""

    model = DeliveryLine
    form = DeliveryLineForm
    extra = 0

    fields = [
        'line_number', 'product', 'received_quantity',
        'unit_price', 'quality_approved', 'line_total_display'
    ]
    readonly_fields = ['line_number', 'line_total_display']

    def line_total_display(self, obj):
        if obj and obj.received_quantity and obj.unit_price:
            return format_html('<strong>{:.2f}</strong>', obj.received_quantity * obj.unit_price)
        return '-'

    line_total_display.short_description = _('Line Total')


# =====================
# ADMIN ACTIONS
# =====================

@admin.action(description=_('Submit selected requests for approval'))
def submit_requests_for_approval(modeladmin, request, queryset):
    """Submit multiple requests for approval"""

    draft_requests = queryset.filter(status='draft')

    if not draft_requests.exists():
        messages.warning(request, _('No draft requests found to submit.'))
        return

    submitted_count = 0
    failed_count = 0
    errors = []

    for req in draft_requests:
        try:
            result = RequestService.submit_for_approval(req, request.user)
            if result['success']:
                submitted_count += 1
            else:
                failed_count += 1
                errors.append(f"{req.document_number}: {result['message']}")
        except Exception as e:
            failed_count += 1
            errors.append(f"{req.document_number}: {str(e)}")

    # Display results
    if submitted_count:
        messages.success(request,
                         _('Successfully submitted %(count)d requests for approval.') % {'count': submitted_count})

    if failed_count:
        messages.warning(request, _('%(count)d requests could not be submitted.') % {'count': failed_count})
        for error in errors[:3]:  # Show max 3 errors
            messages.error(request, error)


@admin.action(description=_('Approve selected requests'))
def approve_requests(modeladmin, request, queryset):
    """Approve multiple requests"""

    submitted_requests = queryset.filter(status='submitted')

    if not submitted_requests.exists():
        messages.warning(request, _('No submitted requests found to approve.'))
        return

    # Check permissions
    if not request.user.has_perm('purchases.approve_requests'):
        messages.error(request, _('You do not have permission to approve requests.'))
        return

    # Bulk approve
    result = RequestService.bulk_approve_requests(
        list(submitted_requests),
        request.user,
        notes=_("Bulk approved by %(user)s") % {'user': request.user.get_full_name()}
    )

    # Display results
    if result['approved_count']:
        messages.success(request, _('Successfully approved %(count)d requests.') % {'count': result['approved_count']})

    if result['failed_count']:
        messages.warning(request, _('%(count)d requests could not be approved.') % {'count': result['failed_count']})
        for failure in result['failed_requests'][:3]:
            messages.error(request, f"{failure['request'].document_number}: {failure['error']}")


@admin.action(description=_('Convert approved requests to orders'))
def convert_requests_to_orders(modeladmin, request, queryset):
    """Convert approved requests to purchase orders"""

    approved_requests = queryset.filter(status='approved')

    if not approved_requests.exists():
        messages.warning(request, _('No approved requests found to convert.'))
        return

    # Bulk convert
    result = RequestService.bulk_convert_to_orders(
        list(approved_requests),
        request.user
    )

    # Display results
    if result['converted_count']:
        messages.success(request, _('Successfully converted %(count)d requests to orders.') % {
            'count': result['converted_count']})

        # Show created order numbers
        order_numbers = [conv['order'].document_number for conv in result['converted_orders'][:5]]
        if order_numbers:
            messages.info(request, _('Created orders: %(orders)s') % {'orders': ', '.join(order_numbers)})

    if result['failed_count']:
        messages.warning(request, _('%(count)d requests could not be converted.') % {'count': result['failed_count']})


@admin.action(description=_('Mark as urgent'))
def mark_requests_urgent(modeladmin, request, queryset):
    """Mark requests as urgent"""

    editable_requests = queryset.filter(status__in=['draft', 'submitted'])
    updated = editable_requests.update(urgency_level='high')

    if updated:
        messages.success(request, _('Marked %(count)d requests as urgent.') % {'count': updated})
    else:
        messages.warning(request, _('No requests could be marked as urgent.'))


@admin.action(description=_('Smart process: Submit → Approve → Convert'))
def smart_process_requests(modeladmin, request, queryset):
    """Smart processing: automatically submit, approve and convert eligible requests"""

    if not request.user.has_perm('purchases.approve_requests'):
        messages.error(request, _('You need approval permissions for smart processing.'))
        return

    total_processed = 0

    # Step 1: Submit draft requests
    draft_requests = queryset.filter(status='draft')
    for req in draft_requests:
        try:
            result = RequestService.submit_for_approval(req, request.user)
            if result['success']:
                total_processed += 1
        except Exception as e:
            messages.warning(request, _('Could not submit %(doc)s: %(error)s') % {
                'doc': req.document_number, 'error': str(e)
            })

    # Step 2: Approve submitted requests
    all_submitted = queryset.filter(status='submitted')
    if all_submitted.exists():
        result = RequestService.bulk_approve_requests(
            list(all_submitted),
            request.user,
            notes=_("Smart bulk processing")
        )
        total_processed += result['approved_count']

    # Step 3: Convert approved requests
    all_approved = queryset.filter(status='approved')
    if all_approved.exists():
        result = RequestService.bulk_convert_to_orders(
            list(all_approved),
            request.user
        )
        total_processed += result['converted_count']

        if result['converted_count']:
            order_numbers = [conv['order'].document_number for conv in result['converted_orders'][:3]]
            messages.info(request, _('Created orders: %(orders)s') % {'orders': ', '.join(order_numbers)})

    if total_processed:
        messages.success(request,
                         _('Smart processed %(count)d requests through the workflow.') % {'count': total_processed})
    else:
        messages.warning(request, _('No requests were processed.'))


# =====================
# CUSTOM ADMIN MIXIN
# =====================

class CustomWorkflowAdminMixin:
    """Mixin to add custom workflow URLs and views"""

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'reject-requests/',
                self.admin_site.admin_view(self.reject_requests_view),
                name='purchases_reject_requests'
            ),
            path(
                'workflow-action/',
                self.admin_site.admin_view(self.workflow_action_view),
                name='purchases_workflow_action'
            ),
        ]
        return custom_urls + urls

    def reject_requests_view(self, request):
        """Custom view for rejecting requests with reason"""

        if request.method == 'POST':
            reason = request.POST.get('rejection_reason', '').strip()
            if not reason:
                messages.error(request, _('Rejection reason is required.'))
                return render(request, 'admin/purchases/reject_requests.html', {
                    'title': _('Reject Purchase Requests')
                })

            # Get request IDs from session
            request_ids = request.session.get('requests_to_reject', [])
            if not request_ids:
                messages.error(request, _('No requests found to reject.'))
                return redirect('admin:purchases_purchaserequest_changelist')

            # Reject requests
            requests_to_reject = PurchaseRequest.objects.filter(id__in=request_ids)
            rejected_count = 0

            for req in requests_to_reject:
                try:
                    result = RequestService.reject_request(req, request.user, reason)
                    if result['success']:
                        rejected_count += 1
                except Exception as e:
                    messages.error(request, _('Error rejecting %(doc)s: %(error)s') % {
                        'doc': req.document_number, 'error': str(e)
                    })

            if rejected_count:
                messages.success(request, _('Successfully rejected %(count)d requests.') % {'count': rejected_count})

            # Clear session
            if 'requests_to_reject' in request.session:
                del request.session['requests_to_reject']

            return redirect('admin:purchases_purchaserequest_changelist')

        # GET request - show form
        request_ids = request.session.get('requests_to_reject', [])
        if not request_ids:
            messages.error(request, _('No requests found to reject.'))
            return redirect('admin:purchases_purchaserequest_changelist')

        requests_to_reject = PurchaseRequest.objects.filter(id__in=request_ids)

        context = {
            'requests': requests_to_reject,
            'title': _('Reject Purchase Requests'),
            'opts': self.model._meta,
        }

        return render(request, 'admin/purchases/reject_requests.html', context)

    def workflow_action_view(self, request):
        """Custom view for executing workflow actions"""

        if request.method == 'POST':
            action = request.POST.get('action')
            notes = request.POST.get('notes', '')

            # Get document from session
            document_id = request.session.get('workflow_document_id')
            document_type = request.session.get('workflow_document_type')

            if not document_id or document_type != 'request':
                messages.error(request, _('Invalid workflow action request.'))
                return redirect('admin:purchases_purchaserequest_changelist')

            try:
                req = PurchaseRequest.objects.get(id=document_id)

                # Execute action
                result = WorkflowService.execute_workflow_action(
                    req, action, request.user, notes=notes
                )

                if result['success']:
                    messages.success(request, result['message'])
                else:
                    messages.error(request, result['message'])

                # Clear session
                for key in ['workflow_document_id', 'workflow_document_type']:
                    if key in request.session:
                        del request.session[key]

                return redirect('admin:purchases_purchaserequest_changelist')

            except PurchaseRequest.DoesNotExist:
                messages.error(request, _('Request not found.'))
                return redirect('admin:purchases_purchaserequest_changelist')
            except Exception as e:
                messages.error(request, _('Error executing workflow action: %(error)s') % {'error': str(e)})
                return redirect('admin:purchases_purchaserequest_changelist')

        # GET request - show workflow form
        document_id = request.session.get('workflow_document_id')
        document_type = request.session.get('workflow_document_type')

        if not document_id or document_type != 'request':
            messages.error(request, _('Invalid workflow action request.'))
            return redirect('admin:purchases_purchaserequest_changelist')

        try:
            req = PurchaseRequest.objects.get(id=document_id)
            workflow_options = WorkflowService.get_workflow_options(req)

            context = {
                'document': req,
                'workflow_options': workflow_options,
                'title': _('Workflow Actions for %(doc)s') % {'doc': req.document_number},
                'opts': self.model._meta,
            }

            return render(request, 'admin/purchases/workflow_action.html', context)

        except PurchaseRequest.DoesNotExist:
            messages.error(request, _('Request not found.'))
            return redirect('admin:purchases_purchaserequest_changelist')


# =====================
# ADMIN CLASSES
# =====================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(CustomWorkflowAdminMixin, admin.ModelAdmin):
    """Admin for Purchase Requests"""

    list_display = [
        'document_number', 'supplier', 'status_display', 'urgency_display',
        'requested_by', 'lines_count', 'estimated_total_display', 'document_date'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'approval_required',
        'document_date', 'created_at', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'business_justification',
        'requested_by__first_name', 'requested_by__last_name'
    ]

    date_hierarchy = 'document_date'

    inlines = [PurchaseRequestLineInline]

    actions = [
        submit_requests_for_approval,
        approve_requests,
        convert_requests_to_orders,
        mark_requests_urgent,
        smart_process_requests,
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'estimated_total_display',
        'approved_at', 'converted_at', 'workflow_status_display'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'document_date'
            )
        }),
        (_('Request Details'), {
            'fields': (
                'request_type', 'urgency_level', 'business_justification',
                'expected_usage'
            )
        }),
        (_('Workflow'), {
            'fields': (
                'requested_by', 'approved_by', 'approved_at',
                'rejection_reason', 'workflow_status_display'
            ),
            'classes': ('collapse',)
        }),
        (_('Conversion'), {
            'fields': (
                'converted_to_order', 'converted_at', 'converted_by'
            ),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': (
                'created_at', 'updated_at', 'estimated_total_display'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Dynamic readonly fields based on status"""
        readonly = list(self.readonly_fields)

        if obj and obj.status != 'draft':
            readonly.extend([
                'supplier', 'location', 'request_type', 'urgency_level',
                'business_justification', 'expected_usage'
            ])

        return readonly

    def status_display(self, obj):
        """Colored status display"""
        colors = {
            'draft': '#6c757d',
            'submitted': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'converted': '#17a2b8',
            'cancelled': '#6c757d'
        }
        color = colors.get(obj.status, '#6c757d')

        # Capitalize first letter of status for display
        display_status = obj.status.replace('_', ' ').title()

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, display_status
        )

    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        """Colored urgency display"""
        colors = {
            'low': '#28a745',
            'normal': '#6c757d',
            'high': '#ffc107',
            'critical': '#dc3545'
        }
        color = colors.get(obj.urgency_level, '#6c757d')
        return format_html(
            '<span style="color: {};">{}</span>',
            color, obj.get_urgency_level_display()
        )

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        """Number of lines in request"""
        return obj.lines.count()

    lines_count.short_description = _('Lines')

    def estimated_total_display(self, obj):
        """Display estimated total"""
        try:
            # Използваме директно сумиране на редовете
            total = sum(
                line.estimated_price * line.requested_quantity
                for line in obj.lines.all()
                if line.estimated_price
            )
            if total:
                return format_html('<strong>{:.2f}</strong>', total)
            return '-'
        except Exception:
            return '-'

    estimated_total_display.short_description = _('Estimated Total')

    def workflow_status_display(self, obj):
        """Display workflow status with timeline"""
        statuses = []

        if obj.created_at:
            statuses.append(f"Created: {obj.created_at.strftime('%Y-%m-%d %H:%M')}")

        if obj.status == 'submitted':
            statuses.append("⏳ Waiting for approval")
        elif obj.approved_at:
            statuses.append(f"✅ Approved: {obj.approved_at.strftime('%Y-%m-%d %H:%M')}")
        elif obj.status == 'rejected':
            statuses.append("❌ Rejected")

        if obj.converted_at:
            statuses.append(f"🔄 Converted: {obj.converted_at.strftime('%Y-%m-%d %H:%M')}")

        return format_html('<br>'.join(statuses))

    workflow_status_display.short_description = _('Workflow Status')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Admin for Purchase Orders"""

    list_display = [
        'document_number', 'supplier', 'status', 'is_urgent',
        'expected_delivery_date', 'grand_total_display'
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier_confirmed',
        'expected_delivery_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference',
        'external_reference'
    ]

    date_hierarchy = 'expected_delivery_date'
    inlines = [PurchaseOrderLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'discount_total', 'vat_total', 'grand_total'
    ]

    def grand_total_display(self, obj):
        """Display grand total"""
        if obj.grand_total:
            return format_html('<strong>{:.2f}</strong>', obj.grand_total)
        return '-'

    grand_total_display.short_description = _('Total')


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    """Admin for Delivery Receipts"""

    list_display = [
        'document_number', 'supplier', 'status', 'delivery_date',
        'quality_status_display', 'grand_total_display'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'quality_checked', 'has_variances',
        'delivery_date', 'supplier'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number'
    ]

    date_hierarchy = 'delivery_date'
    inlines = [DeliveryLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'discount_total', 'vat_total', 'grand_total'
    ]

    def grand_total_display(self, obj):
        """Display grand total"""
        if obj.grand_total:
            return format_html('<strong>{:.2f}</strong>', obj.grand_total)
        return '-'

    grand_total_display.short_description = _('Total')

    def quality_status_display(self, obj):
        """Display quality status with icons"""
        if not obj.quality_checked:
            return format_html('<span style="color: orange;">⏳ Not Checked</span>')
        elif obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues Found</span>')
        elif obj.quality_approved:
            return format_html('<span style="color: green;">✅ Approved</span>')
        else:
            return format_html('<span style="color: red;">❌ Rejected</span>')

    quality_status_display.short_description = _('Quality Status')


# =====================
# LINE ADMINS (FOR DEBUGGING)
# =====================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """Admin for Purchase Request Lines (for debugging)"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity', 'estimated_price'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__name', 'document__document_number']


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    """Admin for Purchase Order Lines (for debugging)"""

    list_display = [
        'document', 'line_number', 'product', 'quantity', 'unit_price'
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__name', 'document__document_number']


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    """Admin for Delivery Lines (for debugging)"""

    list_display = [
        'document', 'line_number', 'product', 'received_quantity', 'unit_price', 'quality_approved'
    ]

    list_filter = ['document__status', 'document__supplier', 'quality_approved']
    search_fields = ['product__name', 'document__document_number']