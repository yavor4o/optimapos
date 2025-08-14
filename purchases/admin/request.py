# purchases/admin/requests.py - SYNCHRONIZED WITH NOMENCLATURES
"""
Purchase Request Admin - ПЪЛНО СИНХРОНИЗИРАН

FEATURES:
- Live workflow testing с DocumentService
- Approval actions използващи ApprovalService
- Real-time status transitions
- DocumentType configuration display
- ApprovalRule testing interface
- Workflow history и audit trail

TESTING CAPABILITIES:
- Test всички possible transitions
- Test approval rules по user/role/amount
- Validate DocumentTypeStatus configurations
- Monitor ApprovalLog entries
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q, Prefetch
from django.utils import timezone
from django.contrib import messages
from django.urls import path, reverse
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from decimal import Decimal
import json

from purchases.models.requests import PurchaseRequestLine, PurchaseRequest


# =================================================================
# INLINE ADMIN FOR REQUEST LINES
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    """Enhanced inline for request lines with workflow info"""
    model = PurchaseRequestLine
    extra = 1

    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'entered_price', 'estimated_total_display', 'suggested_supplier',
        'priority', 'required_by_date'
    ]

    readonly_fields = ['line_number', 'estimated_total_display']

    def estimated_total_display(self, obj):
        """Display estimated total for line"""
        if obj and obj.pk:
            total = obj.get_estimated_total()
            if total:
                return format_html('<strong>{:.2f} лв</strong>', float(total))
        return '-'

    estimated_total_display.short_description = _('Est. Total')

    def get_extra(self, request, obj=None, **kwargs):
        """No extra lines for existing objects"""
        return 0 if obj else 1


# =================================================================
# MAIN PURCHASE REQUEST ADMIN
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """
    Purchase Request Admin - SYNCHRONIZED & TESTABLE

    Provides complete workflow testing interface
    """

    # =====================
    # LIST DISPLAY & FILTERS
    # =====================

    list_display = [
        'document_number_display',
        'supplier_display',
        'status_display',
        'workflow_stage_display',
        'urgency_badge',
        'estimated_total_display',
        'requested_by_display',
        'created_at_display',
        'workflow_actions'
    ]

    list_filter = [
        'status',
        'urgency_level',
        'request_type',
        'document_type',
        'requested_by',
        'created_at',
        ('converted_to_order', admin.EmptyFieldListFilter),
    ]

    search_fields = [
        'document_number',
        'supplier__name',
        'business_justification',
        'requested_by__username',
        'requested_by__first_name',
        'requested_by__last_name',
    ]

    # =====================
    # FORM ORGANIZATION
    # =====================

    fieldsets = (
        (_('Document Information'), {
            'fields': (
                ('document_number', 'document_type'),
                ('document_date', 'status'),
                ('supplier', 'location'),
            )
        }),

        (_('Request Details'), {
            'fields': (
                ('request_type', 'urgency_level'),
                'business_justification',
                'expected_usage',
            )
        }),

        (_('Requestor Information'), {
            'fields': (
                ('requested_by', 'requested_for'),
            )
        }),

        (_('Financial Summary'), {
            'fields': (
                ('subtotal', 'vat_amount'),
                ('discount_total', 'total'),
                'prices_entered_with_vat',
            ),
            'classes': ('collapse',)
        }),

        (_('Conversion Tracking'), {
            'fields': (
                ('converted_to_order', 'converted_at'),
                'converted_by',
            ),
            'classes': ('collapse',)
        }),

        (_('Workflow Information'), {
            'fields': (
                'workflow_summary_display',
                'available_actions_display',
                'approval_history_display',
            ),
            'classes': ('wide',)
        }),

        (_('System Information'), {
            'fields': (
                ('created_at', 'updated_at'),
                ('created_by', 'updated_by'),
            ),
            'classes': ('collapse',)
        })
    )

    readonly_fields = [
        'document_number',
        'created_at', 'updated_at',
        'converted_at',
        'workflow_summary_display',
        'available_actions_display',
        'approval_history_display',
    ]

    inlines = [PurchaseRequestLineInline]

    # =====================
    # CUSTOM DISPLAY METHODS
    # =====================

    def document_number_display(self, obj):
        """Enhanced document number with status color"""
        if not obj.document_number:
            return format_html('<em>Not generated</em>')

        # Get status color from nomenclatures
        try:
            from nomenclatures.services import DocumentService
            status_info = DocumentService._get_status_info(obj)
            color = status_info.get('color', '#6c757d')
        except:
            color = '#6c757d'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.document_number
        )

    document_number_display.short_description = _('Document #')
    document_number_display.admin_order_field = 'document_number'

    def supplier_display(self, obj):
        """Supplier with link"""
        if obj.supplier:
            return format_html(
                '<a href="#" title="{}">{}</a>',
                obj.supplier.name,
                obj.supplier.name[:30] + ('...' if len(obj.supplier.name) > 30 else '')
            )
        return format_html('<em style="color: #dc3545;">No Supplier</em>')

    supplier_display.short_description = _('Supplier')
    supplier_display.admin_order_field = 'supplier__name'

    def status_display(self, obj):
        """Status with nomenclatures integration"""
        try:
            from nomenclatures.services import DocumentService
            status_info = DocumentService._get_status_info(obj)

            color = status_info.get('color', '#6c757d')
            icon = status_info.get('icon', 'fas fa-circle')
            name = status_info.get('name', obj.status)

            return format_html(
                '<span style="color: {}"><i class="{}"></i> {}</span>',
                color, icon, name
            )
        except:
            return format_html(
                '<span style="color: #6c757d">{}</span>',
                obj.status.replace('_', ' ').title()
            )

    status_display.short_description = _('Status')
    status_display.admin_order_field = 'status'

    def workflow_stage_display(self, obj):
        """Current workflow stage with progress"""
        try:
            from nomenclatures.services import ApprovalService
            workflow_info = ApprovalService.get_workflow_info(obj)

            total_stages = len(workflow_info.configured_statuses)
            current_stage = 0

            for i, stage in enumerate(workflow_info.configured_statuses):
                if stage['code'] == obj.status:
                    current_stage = i + 1
                    break

            progress_percent = (current_stage / total_stages * 100) if total_stages else 0

            return format_html(
                '<div title="Stage {}/{}"><div style="background: #e9ecef; height: 8px; border-radius: 4px;"><div style="background: #28a745; height: 8px; width: {}%; border-radius: 4px;"></div></div></div>',
                current_stage, total_stages, progress_percent
            )
        except:
            return format_html('<span style="color: #6c757d;">—</span>')

    workflow_stage_display.short_description = _('Progress')

    def urgency_badge(self, obj):
        """Urgency level with color coding"""
        colors = {
            'low': '#28a745',
            'normal': '#6c757d',
            'high': '#fd7e14',
            'critical': '#dc3545'
        }

        color = colors.get(obj.urgency_level, '#6c757d')

        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_urgency_level_display().upper()
        )

    urgency_badge.short_description = _('Urgency')
    urgency_badge.admin_order_field = 'urgency_level'

    def estimated_total_display(self, obj):
        """Estimated total with formatting"""
        try:
            total = obj.get_total_estimated_cost()
            if total:
                return format_html('<strong>{:.2f} лв</strong>', float(total))
        except:
            pass
        return '—'

    estimated_total_display.short_description = _('Est. Total')

    def requested_by_display(self, obj):
        """Requester with avatar placeholder"""
        if obj.requested_by:
            name = obj.requested_by.get_full_name() or obj.requested_by.username
            return format_html(
                '<span title="{}">{}</span>',
                obj.requested_by.email or obj.requested_by.username,
                name[:20] + ('...' if len(name) > 20 else '')
            )
        return '—'

    requested_by_display.short_description = _('Requested By')
    requested_by_display.admin_order_field = 'requested_by__last_name'

    def created_at_display(self, obj):
        """Friendly date display"""
        return format_html(
            '<span title="{}">{}</span>',
            obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            obj.created_at.strftime('%d.%m.%Y')
        )

    created_at_display.short_description = _('Created')
    created_at_display.admin_order_field = 'created_at'

    def workflow_actions(self, obj):
        """Available workflow actions as buttons"""
        if not obj.pk:
            return '—'

        try:
            actions = obj.get_available_actions(user=None)  # We'll pass real user in view

            if not actions:
                return format_html('<span style="color: #6c757d;">No actions</span>')

            buttons = []
            for action in actions[:3]:  # Limit to 3 actions in list view
                style_map = {
                    'primary': '#007bff',
                    'success': '#28a745',
                    'warning': '#ffc107',
                    'danger': '#dc3545',
                    'outline-primary': '#007bff'
                }

                bg_color = style_map.get(action.get('button_style', 'primary'), '#6c757d')

                buttons.append(format_html(
                    '<a href="{}?action={}&status={}" style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; text-decoration: none; margin-right: 2px;" title="{}">{}</a>',
                    reverse('admin:purchases_purchaserequest_workflow', args=[obj.pk]),
                    action.get('action', ''),
                    action.get('status', ''),
                    bg_color,
                    action.get('reason', ''),
                    action.get('label', '')[:10]
                ))

            return format_html(''.join(buttons))

        except Exception as e:
            return format_html('<span style="color: #dc3545;">Error: {}</span>', str(e)[:20])

    workflow_actions.short_description = _('Actions')

    # =====================
    # READONLY FIELD DISPLAYS
    # =====================

    def workflow_summary_display(self, obj):
        """Complete workflow summary with testing capabilities"""
        if not obj.pk:
            return 'Save document first to see workflow information'

        html = ['<div style="font-family: monospace; font-size: 12px; line-height: 1.4;">']

        try:
            from nomenclatures.services import ApprovalService, DocumentService

            # Current status info
            html.append('<h4 style="color: #0066cc;">📋 Current Status</h4>')
            status_info = DocumentService._get_status_info(obj)
            html.append(f'<p><strong>Status:</strong> {obj.status} ({status_info.get("name", "Unknown")})</p>')
            html.append(
                f'<p><strong>Document Type:</strong> {obj.document_type.name if obj.document_type else "Not set"}</p>')

            # Workflow info
            workflow_info = ApprovalService.get_workflow_info(obj)

            html.append('<h4 style="color: #0066cc;">🔄 Available Transitions</h4>')
            if workflow_info.available_transitions:
                html.append('<ul>')
                for trans in workflow_info.available_transitions:
                    html.append(
                        f'<li><strong>{trans["to_status"]}</strong>: {trans["label"]} (Rule ID: {trans.get("rule_id", "N/A")})</li>')
                html.append('</ul>')
            else:
                html.append('<p style="color: #6c757d;">No transitions available</p>')

            # Configured statuses
            html.append('<h4 style="color: #0066cc;">⚙️ Configured Statuses</h4>')
            if workflow_info.configured_statuses:
                html.append('<ul>')
                for status in workflow_info.configured_statuses:
                    badges = []
                    if status.get('is_initial'): badges.append('INITIAL')
                    if status.get('is_final'): badges.append('FINAL')
                    if status.get('is_cancellation'): badges.append('CANCEL')

                    badge_str = f" [{', '.join(badges)}]" if badges else ""
                    html.append(
                        f'<li><span style="color: {status.get("color", "#000")}">{status["name"]}</span>{badge_str}</li>')
                html.append('</ul>')

            # Test buttons
            html.append('<h4 style="color: #0066cc;">🧪 Testing Actions</h4>')
            html.append(
                f'<a href="{reverse("admin:purchases_purchaserequest_test_workflow", args=[obj.pk])}" target="_blank" style="background: #28a745; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none;">Test Workflow</a>')
            html.append(' ')
            html.append(
                f'<a href="{reverse("admin:purchases_purchaserequest_approval_test", args=[obj.pk])}" target="_blank" style="background: #dc3545; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none;">Test Approvals</a>')

        except Exception as e:
            html.append(f'<p style="color: #dc3545;">Error loading workflow info: {e}</p>')

        html.append('</div>')
        return format_html(''.join(html))

    workflow_summary_display.short_description = _('Workflow Summary')

    def available_actions_display(self, obj):
        """Available actions with test interface"""
        if not obj.pk:
            return 'Save document first'

        try:
            actions = obj.get_available_actions(user=self.current_user if hasattr(self, 'current_user') else None)

            if not actions:
                return format_html('<span style="color: #6c757d;">No actions available</span>')

            html = ['<div style="font-family: monospace; font-size: 12px;">']

            for action in actions:
                style_colors = {
                    'primary': '#007bff', 'success': '#28a745',
                    'warning': '#ffc107', 'danger': '#dc3545'
                }

                bg_color = style_colors.get(action.get('button_style', 'primary'), '#6c757d')

                html.append(f'''
                    <div style="margin: 4px 0; padding: 6px; border-left: 3px solid {bg_color}; background: #f8f9fa;">
                        <strong>{action.get("label", "Unknown")}</strong><br>
                        <small>Action: {action.get("action", "N/A")} | Status: {action.get("status", "N/A")}</small><br>
                        <small style="color: #6c757d;">{action.get("reason", "")}</small>
                    </div>
                ''')

            html.append('</div>')
            return format_html(''.join(html))

        except Exception as e:
            return format_html('<span style="color: #dc3545;">Error: {}</span>', str(e))

    available_actions_display.short_description = _('Available Actions')

    def approval_history_display(self, obj):
        """Approval history from ApprovalLog"""
        if not obj.pk:
            return 'Save document first'

        try:
            history = obj.get_approval_history()

            if not history:
                return format_html('<span style="color: #6c757d;">No approval history</span>')

            html = ['<div style="font-family: monospace; font-size: 11px; max-height: 200px; overflow-y: auto;">']

            for entry in history[:10]:  # Last 10 entries
                timestamp = entry.get('timestamp', 'Unknown')
                actor = entry.get('actor', 'Unknown')
                action = entry.get('action', 'Unknown')
                from_status = entry.get('from_status', '')
                to_status = entry.get('to_status', '')

                html.append(f'''
                    <div style="padding: 4px; border-bottom: 1px solid #dee2e6;">
                        <strong>{action.upper()}</strong> {from_status} → {to_status}<br>
                        <small>By: {actor} | {timestamp}</small>
                    </div>
                ''')

            html.append('</div>')
            return format_html(''.join(html))

        except Exception as e:
            return format_html('<span style="color: #dc3545;">Error: {}</span>', str(e))

    approval_history_display.short_description = _('Approval History')

    # =====================
    # CUSTOM URLs & VIEWS
    # =====================

    def get_urls(self):
        """Add custom URLs for workflow testing"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/workflow/',
                self.admin_site.admin_view(self.workflow_action_view),
                name='purchases_purchaserequest_workflow'
            ),
            path(
                '<int:object_id>/test-workflow/',
                self.admin_site.admin_view(self.test_workflow_view),
                name='purchases_purchaserequest_test_workflow'
            ),
            path(
                '<int:object_id>/test-approvals/',
                self.admin_site.admin_view(self.test_approvals_view),
                name='purchases_purchaserequest_approval_test'
            ),
            path(
                'workflow-ajax/',
                self.admin_site.admin_view(self.workflow_ajax_view),
                name='purchases_purchaserequest_workflow_ajax'
            ),
        ]
        return custom_urls + urls

    def workflow_action_view(self, request, object_id):
        """Handle workflow action execution"""
        obj = self.get_object(request, object_id)
        if not obj:
            return redirect('admin:purchases_purchaserequest_changelist')

        action = request.GET.get('action')
        status = request.GET.get('status')
        comments = request.POST.get('comments', '')

        if request.method == 'POST' and action and status:
            try:
                result = obj.transition_to(status, request.user, comments)

                if result.ok:
                    messages.success(request, f'Successfully transitioned to {status}')
                else:
                    messages.error(request, f'Transition failed: {result.msg}')

            except Exception as e:
                messages.error(request, f'Error: {str(e)}')

        return redirect('admin:purchases_purchaserequest_change', object_id)

    def test_workflow_view(self, request, object_id):
        """Workflow testing interface"""
        obj = self.get_object(request, object_id)
        if not obj:
            return redirect('admin:purchases_purchaserequest_changelist')

        try:
            from nomenclatures.services import ApprovalService, DocumentService

            # Get workflow information
            workflow_info = ApprovalService.get_workflow_info(obj)
            actions = obj.get_available_actions(request.user)
            can_edit = obj.can_edit(request.user)

            # Test data
            test_data = {
                'document': obj,
                'workflow_info': workflow_info,
                'available_actions': actions,
                'can_edit': can_edit,
                'current_user': request.user,
            }

        except Exception as e:
            messages.error(request, f'Error loading workflow info: {e}')
            return redirect('admin:purchases_purchaserequest_change', object_id)

        return TemplateResponse(request, 'admin/purchases/test_workflow.html', test_data)

    def test_approvals_view(self, request, object_id):
        """Approval rules testing interface"""
        obj = self.get_object(request, object_id)
        if not obj:
            return redirect('admin:purchases_purchaserequest_changelist')

        try:
            from nomenclatures.services import ApprovalService
            from nomenclatures.models import ApprovalRule

            # Get applicable approval rules
            rules = ApprovalRule.objects.filter(
                document_type=obj.document_type,
                is_active=True
            ).order_by('approval_level', 'sort_order')

            # Test each rule
            rule_tests = []
            for rule in rules:
                can_approve = rule.can_user_approve(request.user, obj)
                rule_tests.append({
                    'rule': rule,
                    'can_approve': can_approve,
                    'user_matches': can_approve
                })

            test_data = {
                'document': obj,
                'rules': rule_tests,
                'current_user': request.user,
            }

        except Exception as e:
            messages.error(request, f'Error loading approval rules: {e}')
            return redirect('admin:purchases_purchaserequest_change', object_id)

        return TemplateResponse(request, 'admin/purchases/test_approvals.html', test_data)

    def workflow_ajax_view(self, request):
        """AJAX endpoint for real-time workflow updates"""
        if request.method != 'POST':
            return JsonResponse({'error': 'POST required'})

        try:
            data = json.loads(request.body)
            object_id = data.get('object_id')
            action = data.get('action')
            new_status = data.get('status')
            comments = data.get('comments', '')

            obj = PurchaseRequest.objects.get(pk=object_id)

            if action == 'transition':
                result = obj.transition_to(new_status, request.user, comments)

                return JsonResponse({
                    'success': result.ok,
                    'message': result.msg,
                    'new_status': obj.status,
                    'data': result.data
                })

            elif action == 'get_actions':
                actions = obj.get_available_actions(request.user)
                return JsonResponse({
                    'success': True,
                    'actions': actions
                })

            else:
                return JsonResponse({'error': 'Unknown action'})

        except Exception as e:
            return JsonResponse({'error': str(e)})

    # =====================
    # ADMIN ACTIONS
    # =====================

    actions = [
        'test_document_service',
        'test_approval_service',
        'bulk_transition',
        'generate_document_numbers',
        'validate_workflow_config'
    ]

    def test_document_service(self, request, queryset):
        """Test DocumentService on selected objects"""
        tested = 0
        errors = []

        for obj in queryset:
            try:
                # Test can_edit
                can_edit = obj.can_edit(request.user)

                # Test get_available_actions
                actions = obj.get_available_actions(request.user)

                tested += 1

            except Exception as e:
                errors.append(f'{obj.document_number}: {str(e)}')

        if errors:
            self.message_user(request, f'Tested {tested} documents. Errors: {"; ".join(errors[:5])}',
                              level=messages.WARNING)
        else:
            self.message_user(request, f'Successfully tested DocumentService on {tested} documents')

    test_document_service.short_description = _('Test DocumentService')

    def test_approval_service(self, request, queryset):
        """Test ApprovalService on selected objects"""
        tested = 0
        errors = []

        for obj in queryset:
            try:
                from nomenclatures.services import ApprovalService

                # Test workflow info
                workflow_info = ApprovalService.get_workflow_info(obj)

                # Test approval history
                history = ApprovalService.get_approval_history(obj)

                tested += 1

            except Exception as e:
                errors.append(f'{obj.document_number}: {str(e)}')

        if errors:
            self.message_user(request, f'Tested {tested} documents. Errors: {"; ".join(errors[:5])}',
                              level=messages.WARNING)
        else:
            self.message_user(request, f'Successfully tested ApprovalService on {tested} documents')

    test_approval_service.short_description = _('Test ApprovalService')

    def bulk_transition(self, request, queryset):
        """Bulk transition selected documents"""
        # This would open a form to select target status
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return redirect(f'/admin/bulk-transition/?ids={",".join(selected)}')

    bulk_transition.short_description = _('Bulk transition documents')

    def generate_document_numbers(self, request, queryset):
        """Generate document numbers for selected objects"""
        generated = 0

        for obj in queryset.filter(document_number=''):
            try:
                from nomenclatures.services import DocumentService
                number = DocumentService.generate_number_for(obj)
                obj.document_number = number
                obj.save(update_fields=['document_number'])
                generated += 1
            except Exception as e:
                self.message_user(request, f'Error generating number for {obj.pk}: {e}', level=messages.ERROR)

        self.message_user(request, f'Generated {generated} document numbers')

    generate_document_numbers.short_description = _('Generate document numbers')

    def validate_workflow_config(self, request, queryset):
        """Validate workflow configuration for selected documents"""
        validated = 0
        issues = []

        for obj in queryset:
            try:
                # Check document type
                if not obj.document_type:
                    issues.append(f'{obj.document_number}: No document type')
                    continue

                # Check configured statuses
                from nomenclatures.models import DocumentTypeStatus
                configured_statuses = DocumentTypeStatus.objects.filter(
                    document_type=obj.document_type,
                    is_active=True
                ).count()

                if configured_statuses == 0:
                    issues.append(f'{obj.document_number}: No configured statuses')

                # Check approval rules if required
                if obj.document_type.requires_approval:
                    from nomenclatures.models import ApprovalRule
                    rules_count = ApprovalRule.objects.filter(
                        document_type=obj.document_type,
                        is_active=True
                    ).count()

                    if rules_count == 0:
                        issues.append(f'{obj.document_number}: No approval rules but requires approval')

                validated += 1

            except Exception as e:
                issues.append(f'{obj.document_number}: Error - {str(e)}')

        if issues:
            self.message_user(request, f'Validated {validated} documents. Issues found: {"; ".join(issues[:5])}',
                              level=messages.WARNING)
        else:
            self.message_user(request, f'Successfully validated {validated} documents - no issues found')

    validate_workflow_config.short_description = _('Validate workflow config')

    # =====================
    # FORM CUSTOMIZATION
    # =====================

    def get_form(self, request, obj=None, **kwargs):
        """Customize form based on workflow state"""
        form = super().get_form(request, obj, **kwargs)

        # Store current user for use in display methods
        self.current_user = request.user

        if obj and obj.pk:
            # Disable editing if not allowed
            try:
                if not obj.can_edit(request.user):
                    # Make most fields readonly
                    readonly_fields = list(self.readonly_fields)
                    for field_name in ['business_justification', 'expected_usage', 'urgency_level']:
                        if field_name not in readonly_fields:
                            readonly_fields.append(field_name)

                    # Update readonly_fields temporarily
                    self.readonly_fields = readonly_fields
            except:
                pass

        return form

    def save_model(self, request, obj, form, change):
        """Enhanced save with DocumentService integration"""
        # Set user fields
        if not change:
            obj.created_by = request.user
            obj.requested_by = obj.requested_by or request.user
        obj.updated_by = request.user

        # Set document type if not set
        if not obj.document_type:
            try:
                from nomenclatures.models import get_document_type_by_key
                obj.document_type = get_document_type_by_key('purchase_request')
            except:
                pass

        # Generate document number if needed
        if not obj.document_number:
            try:
                from nomenclatures.services import DocumentService
                obj.document_number = DocumentService.generate_number_for(obj)
            except:
                obj.document_number = f"REQ-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        # Set initial status if needed
        if not obj.status and obj.document_type:
            try:
                obj.status = obj.document_type.get_initial_status_code()
            except:
                obj.status = 'draft'

        super().save_model(request, obj, form, change)

        # Log the save action
        messages.info(request, f'Document saved. Current status: {obj.status}')

    # =====================
    # LIST VIEW CUSTOMIZATION
    # =====================

    def get_queryset(self, request):
        """Optimized queryset with prefetch"""
        return super().get_queryset(request).select_related(
            'supplier', 'document_type', 'requested_by', 'converted_to_order',
            'location', 'created_by'
        ).prefetch_related(
            'lines__product',
            'lines__unit'
        )

    def changelist_view(self, request, extra_context=None):
        """Enhanced changelist with workflow statistics"""
        extra_context = extra_context or {}

        try:
            # Add workflow statistics
            from django.db.models import Count

            status_stats = PurchaseRequest.objects.values('status').annotate(
                count=Count('id')
            ).order_by('status')

            urgency_stats = PurchaseRequest.objects.values('urgency_level').annotate(
                count=Count('id')
            ).order_by('urgency_level')

            extra_context.update({
                'status_statistics': list(status_stats),
                'urgency_statistics': list(urgency_stats),
                'total_requests': PurchaseRequest.objects.count(),
                'pending_approval_count': PurchaseRequest.objects.filter(status='submitted').count(),
            })

        except Exception as e:
            messages.warning(request, f'Could not load statistics: {e}')

        return super().changelist_view(request, extra_context)