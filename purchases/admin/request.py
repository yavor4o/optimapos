# purchases/admin/request.py - SYNCHRONIZED WITH REAL MODEL

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib import messages
from django.urls import path, reverse
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from purchases.models.requests import PurchaseRequestLine, PurchaseRequest


# =================================================================
# INLINE ADMIN FOR REQUEST LINES
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    """Enhanced inline for request lines matching real model fields"""
    model = PurchaseRequestLine
    extra = 1

    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'entered_price', 'line_total_display',
        'priority',
    ]

    readonly_fields = ['line_number', 'line_total_display']

    def line_total_display(self, obj):
        """Display total for THIS LINE"""
        if obj and obj.pk and obj.entered_price:
            total = obj.requested_quantity * obj.entered_price
            # 🔥 TEST: Върни простичък string вместо format_html
            return f"{float(total):.2f} лв"
        return '-'

    line_total_display.short_description = _('Line Total')

    def get_extra(self, request, obj=None, **kwargs):
        """No extra lines for existing objects"""
        return 0 if obj else 1


# =================================================================
# MAIN PURCHASE REQUEST ADMIN
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """
    Purchase Request Admin - SYNCHRONIZED WITH REAL MODEL

    Matches all fields from the synchronized requests.py model
    """

    # =====================
    # LIST DISPLAY & FILTERS
    # =====================

    list_display = [
        'document_number_display',
        'supplier_display',
        'status_display',
        'urgency_badge',
        'estimated_total_display',
        'requested_by_display',
        'approval_status_display',
        'created_at_display',
        'workflow_actions'
    ]

    list_filter = [
        'status',
        'urgency_level',
        'request_type',
        'document_type',
        'requested_by',
        'approval_required',
        'created_at',
        ('converted_to_order', admin.EmptyFieldListFilter),
        ('approved_by', admin.EmptyFieldListFilter),
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
    # FORM ORGANIZATION - MATCHING REAL MODEL
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
                'requested_by',
            )
        }),

        (_('Approval Information'), {
            'fields': (
                'approval_required',
                ('approved_by', 'approved_at'),
                'rejection_reason',
            ),
            'classes': ('collapse',)
        }),

        (_('Financial Summary'), {
            'fields': (
                ('subtotal', 'vat_total'),
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
    # CUSTOM DISPLAY METHODS - UPDATED FOR REAL MODEL
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
        print("🔥 STEP 1: Method called")

        try:
            print("🔥 STEP 2: Trying to get total")
            total = obj.get_estimated_total()
            print(f"🔥 STEP 3: Got total = {total}")
            print(f"🔥 STEP 4: Total type = {type(total)}")
            print(f"🔥 STEP 5: Total > 0? {total > 0}")
            print(f"🔥 STEP 6: bool(total)? {bool(total)}")

            if total:
                print("🔥 STEP 7: Total is truthy, formatting...")
                result = f"{float(total):.2f} лв"
                print(f"🔥 STEP 8: Formatted result = {result}")
                return result
            else:
                print("🔥 STEP 7: Total is falsy, returning —")
                return '—'

        except Exception as e:
            print(f"🔥 ERROR: {e}")
            import traceback
            traceback.print_exc()
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

    def approval_status_display(self, obj):
        """Approval status from model fields"""
        if obj.approved_by and obj.approved_at:
            return format_html(
                '<span style="color: #28a745;">✓ {}</span>',
                obj.approved_by.get_full_name() or obj.approved_by.username
            )
        elif obj.rejection_reason:
            return format_html('<span style="color: #dc3545;">✗ Rejected</span>')
        elif obj.approval_required:
            return format_html('<span style="color: #ffc107;">⏳ Pending</span>')
        else:
            return format_html('<span style="color: #6c757d;">N/A</span>')

    approval_status_display.short_description = _('Approval')

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
            actions = obj.get_available_actions(user=None)

            if not actions:
                return format_html('<span style="color: #6c757d;">No actions</span>')

            buttons = []
            for action in actions[:2]:  # Limit to 2 actions in list view
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
                    action.get('label', '')[:8]
                ))

            return format_html(''.join(buttons))

        except Exception as e:
            return format_html('<span style="color: #dc3545;">Error</span>')

    workflow_actions.short_description = _('Actions')

    # =====================
    # READONLY FIELD DISPLAYS - UPDATED
    # =====================

    def workflow_summary_display(self, obj):
        """Complete workflow summary with testing capabilities"""
        if not obj.pk:
            return 'Save document first to see workflow information'

        html = ['<div style="font-family: monospace; font-size: 12px; line-height: 1.4;">']

        try:
            # Current status info
            html.append('<h4 style="color: #0066cc;">📋 Current Status</h4>')
            html.append(f'<p><strong>Status:</strong> {obj.status}</p>')
            html.append(
                f'<p><strong>Document Type:</strong> {obj.document_type.name if obj.document_type else "Not set"}</p>')
            html.append(f'<p><strong>Can Edit:</strong> {"Yes" if obj.can_edit() else "No"}</p>')

            # Model-specific info
            html.append('<h4 style="color: #0066cc;">📝 Request Info</h4>')
            html.append(f'<p><strong>Approval Required:</strong> {"Yes" if obj.approval_required else "No"}</p>')
            html.append(f'<p><strong>Urgency:</strong> {obj.get_urgency_level_display()}</p>')
            html.append(f'<p><strong>Request Type:</strong> {obj.get_request_type_display()}</p>')

            # Workflow info from nomenclatures
            try:
                workflow_info = obj.get_workflow_info()
                if workflow_info:
                    html.append('<h4 style="color: #0066cc;">🔄 Available Transitions</h4>')
                    if workflow_info.available_transitions:
                        html.append('<ul>')
                        for trans in workflow_info.available_transitions:
                            html.append(f'<li><strong>{trans["to_status"]}</strong>: {trans["label"]}</li>')
                        html.append('</ul>')
                    else:
                        html.append('<p style="color: #6c757d;">No transitions available</p>')
            except:
                pass

            # Legacy approval info
            if obj.approved_by:
                html.append('<h4 style="color: #0066cc;">👤 Legacy Approval</h4>')
                html.append(f'<p><strong>Approved By:</strong> {obj.approved_by.get_full_name()}</p>')
                html.append(f'<p><strong>Approved At:</strong> {obj.approved_at}</p>')

            # Test buttons
            html.append('<h4 style="color: #0066cc;">🧪 Testing Actions</h4>')
            html.append(
                f'<a href="{reverse("admin:purchases_purchaserequest_test_workflow", args=[obj.pk])}" target="_blank" style="background: #28a745; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none;">Test Workflow</a>')

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
            actions = obj.get_available_actions(user=getattr(self, 'current_user', None))

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
        """Approval history from ApprovalLog + legacy fields"""
        if not obj.pk:
            return 'Save document first'

        html = ['<div style="font-family: monospace; font-size: 11px; max-height: 200px; overflow-y: auto;">']

        try:
            # Get nomenclatures history
            history = obj.get_approval_history()

            # Add legacy approval info
            legacy_entries = []
            if obj.approved_by and obj.approved_at:
                legacy_entries.append({
                    'action': 'APPROVED (Legacy)',
                    'actor': obj.approved_by.get_full_name(),
                    'timestamp': obj.approved_at.strftime('%Y-%m-%d %H:%M'),
                    'from_status': 'submitted',
                    'to_status': 'approved'
                })

            if obj.rejection_reason:
                legacy_entries.append({
                    'action': 'REJECTED (Legacy)',
                    'actor': 'System',
                    'timestamp': obj.updated_at.strftime('%Y-%m-%d %H:%M'),
                    'comments': obj.rejection_reason
                })

            all_entries = list(history) + legacy_entries

            if not all_entries:
                html.append('<span style="color: #6c757d;">No approval history</span>')
            else:
                for entry in all_entries[:10]:  # Last 10 entries
                    timestamp = entry.get('timestamp', 'Unknown')
                    actor = entry.get('actor', 'Unknown')
                    action = entry.get('action', 'Unknown')
                    from_status = entry.get('from_status', '')
                    to_status = entry.get('to_status', '')
                    comments = entry.get('comments', '')

                    html.append(f'''
                        <div style="padding: 4px; border-bottom: 1px solid #dee2e6;">
                            <strong>{action.upper()}</strong> {from_status} → {to_status}<br>
                            <small>By: {actor} | {timestamp}</small>
                            {f'<div style="font-style: italic;">{comments}</div>' if comments else ''}
                        </div>
                    ''')

        except Exception as e:
            html.append(f'<span style="color: #dc3545;">Error: {e}</span>')

        html.append('</div>')
        return format_html(''.join(html))

    approval_history_display.short_description = _('Approval History')

    # =====================
    # CUSTOM URLs & VIEWS - SIMPLIFIED
    # =====================

    def get_urls(self):
        """Add custom URLs for workflow testing - FIXED"""
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
            # 🔥 FIX: Add debug URL inside get_urls method
            path(
                '<int:object_id>/debug-workflow/',
                self.admin_site.admin_view(self.debug_workflow_action),
                name='purchases_purchaserequest_debug_workflow'
            ),
        ]
        return custom_urls + urls

    def workflow_action_view(self, request, object_id):
        """
        🔥 FIXED: Handle workflow action execution properly
        """
        obj = self.get_object(request, object_id)
        if not obj:
            messages.error(request, "Document not found")
            return redirect('admin:purchases_purchaserequest_changelist')

        # 🔥 FIX: Handle both GET and POST properly
        if request.method == 'POST':
            # POST request from form submission
            action = request.POST.get('action')
            status = request.POST.get('status')
            comments = request.POST.get('comments', '')
        else:
            # GET request from URL parameters (buttons)
            action = request.GET.get('action')
            status = request.GET.get('status')
            comments = ''

        # 🔥 FIX: Execute if we have action and status (regardless of method)
        if action and status:
            try:
                print(f"🧪 DEBUG: Executing {action} to {status} for {obj.document_number}")

                # Call the model's transition method
                result = obj.transition_to(status, request.user, comments)

                print(f"🧪 DEBUG: Result type: {type(result)}")
                print(f"🧪 DEBUG: Result: {result}")

                # 🔥 FIX: Handle different result types
                if hasattr(result, 'ok'):
                    # Result object from DocumentService
                    if result.ok:
                        messages.success(request, f'✅ Successfully transitioned to {status}')
                        print(f"🧪 DEBUG: Transition successful!")
                    else:
                        messages.error(request, f'❌ Transition failed: {result.msg}')
                        print(f"🧪 DEBUG: Transition failed: {result.msg}")
                elif result is True:
                    # Boolean success
                    messages.success(request, f'✅ Successfully transitioned to {status}')
                else:
                    # Unknown result
                    messages.warning(request, f'⚠️ Transition completed with unknown result: {result}')

                # 🔥 FIX: Force refresh to see changes
                obj.refresh_from_db()
                print(f"🧪 DEBUG: New status after refresh: {obj.status}")

            except Exception as e:
                print(f"🧪 DEBUG: Exception during transition: {e}")
                messages.error(request, f'❌ Error: {str(e)}')

        else:
            # 🔥 FIX: Better error message for debugging
            messages.error(request, f'❌ Missing parameters: action={action}, status={status}')
            print(f"🧪 DEBUG: Missing params - action: {action}, status: {status}")

        return redirect('admin:purchases_purchaserequest_change', object_id)

    def test_workflow_view(self, request, object_id):
        """Simple workflow testing interface"""
        obj = self.get_object(request, object_id)
        if not obj:
            return redirect('admin:purchases_purchaserequest_changelist')

        context = {
            'title': f'Workflow Testing - {obj.document_number}',
            'object': obj,
            'available_actions': obj.get_available_actions(request.user),
            'can_edit': obj.can_edit(request.user),
            'workflow_info': obj.get_workflow_info(),
        }

        return TemplateResponse(request, 'admin/purchases/test_workflow.html', context)

    def debug_workflow_action(self, request, object_id):
        """Debug workflow action - shows what's happening"""
        obj = self.get_object(request, object_id)
        if not obj:
            return redirect('admin:purchases_purchaserequest_changelist')

        debug_info = []
        debug_info.append(f"Method: {request.method}")
        debug_info.append(f"GET params: {dict(request.GET)}")
        debug_info.append(f"POST params: {dict(request.POST)}")
        debug_info.append(f"Current status: {obj.status}")
        debug_info.append(f"Document type: {obj.document_type}")

        try:
            actions = obj.get_available_actions(request.user)
            debug_info.append(f"Available actions: {len(actions)}")
            for action in actions:
                debug_info.append(f"  - {action}")
        except Exception as e:
            debug_info.append(f"Error getting actions: {e}")

        messages.info(request, "DEBUG INFO:\n" + "\n".join(debug_info))
        return redirect('admin:purchases_purchaserequest_change', object_id)

    # =====================
    # ADMIN ACTIONS - UPDATED
    # =====================

    actions = [
        'test_document_service',
        'test_approval_service',
        'sync_with_nomenclatures',
        'validate_workflow_config'
    ]

    def test_document_service(self, request, queryset):
        """Test DocumentService on selected objects"""
        tested = 0
        errors = []

        for obj in queryset:
            try:
                can_edit = obj.can_edit(request.user)
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
                workflow_info = obj.get_workflow_info()
                history = obj.get_approval_history()
                tested += 1
            except Exception as e:
                errors.append(f'{obj.document_number}: {str(e)}')

        if errors:
            self.message_user(request, f'Tested {tested} documents. Errors: {"; ".join(errors[:5])}',
                              level=messages.WARNING)
        else:
            self.message_user(request, f'Successfully tested ApprovalService on {tested} documents')

    test_approval_service.short_description = _('Test ApprovalService')

    def sync_with_nomenclatures(self, request, queryset):
        """Sync selected documents with nomenclatures system"""
        synced = 0

        for obj in queryset:
            try:
                # Set document type if missing
                if not obj.document_type:
                    try:
                        from nomenclatures.models import get_document_type_by_key
                        obj.document_type = get_document_type_by_key('purchase_request')
                        obj.save(update_fields=['document_type'])
                    except:
                        pass

                # Set initial status if needed
                if not obj.status:
                    obj.status = 'draft'
                    obj.save(update_fields=['status'])

                synced += 1
            except Exception as e:
                self.message_user(request, f'Error syncing {obj.document_number}: {e}', level=messages.ERROR)

        self.message_user(request, f'Synced {synced} documents with nomenclatures')

    sync_with_nomenclatures.short_description = _('Sync with nomenclatures')

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

                # Test workflow methods
                try:
                    obj.can_edit(request.user)
                    obj.get_available_actions(request.user)
                    validated += 1
                except Exception as e:
                    issues.append(f'{obj.document_number}: Workflow error - {str(e)}')

            except Exception as e:
                issues.append(f'{obj.document_number}: Error - {str(e)}')

        if issues:
            self.message_user(request, f'Validated {validated} documents. Issues: {"; ".join(issues[:5])}',
                              level=messages.WARNING)
        else:
            self.message_user(request, f'Successfully validated {validated} documents - no issues found')

    validate_workflow_config.short_description = _('Validate workflow config')

    # =====================
    # FORM CUSTOMIZATION - UPDATED
    # =====================

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

        # Store current user for workflow methods
        self.current_user = request.user

        # Log the save action
        messages.info(request, f'Document saved. Current status: {obj.status}')

    # =====================
    # LIST VIEW CUSTOMIZATION
    # =====================

    def get_queryset(self, request):
        """Optimized queryset with prefetch"""
        return super().get_queryset(request).select_related(
            'supplier', 'document_type', 'requested_by', 'converted_to_order',
            'location', 'created_by', 'approved_by', 'converted_by'
        ).prefetch_related(
            'lines__product',
            'lines__unit'
        )