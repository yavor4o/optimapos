# purchases/admin.py - FIXED COMPLETE ADMIN
import logging

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# ✅ IMPORT САМО СЪЩЕСТВУВАЩИ МОДЕЛИ
from purchases.models.requests import PurchaseRequestLine, PurchaseRequest

logger = logging.getLogger(__name__)

# =================================================================
# INLINE ADMINS - FIXED WITH NEW FIELDS
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1

    fields = [
        'product', 'requested_quantity', 'unit',
        'entered_price',  # ✅ ONLY entered_price now
        'price_suggestion_info',
        ('unit_price', 'vat_rate'),
        ('net_amount', 'gross_amount'),
    ]

    readonly_fields = [
        'price_suggestion_info',
        'unit_price', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount'
    ]

    def price_suggestion_info(self, obj):
        """Show price suggestion and processing info"""
        if not obj or not obj.pk:
            return format_html('<em>Save to see price info</em>')

        info_parts = []

        # Show current price
        if obj.entered_price and obj.entered_price > 0:
            info_parts.append(
                f'<span style="color: blue;">💰 Price: {obj.entered_price}</span>'
            )
        else:
            info_parts.append(
                '<span style="color: orange;">⚠️ No price entered</span>'
            )

        # Show VAT processing result
        if obj.unit_price and obj.unit_price > 0:
            if obj.entered_price and obj.entered_price != obj.unit_price:
                # VAT was processed (prices were extracted)
                info_parts.append(
                    f'<small>→ Processed: {obj.unit_price} (VAT: {obj.vat_rate}%)</small>'
                )
            else:
                # No VAT processing needed
                info_parts.append(
                    f'<small>→ Direct: {obj.unit_price} (VAT: {obj.vat_rate}%)</small>'
                )

        # Show auto-suggestion if available
        if obj.product and (not obj.entered_price or obj.entered_price == 0):
            try:
                suggested = obj.product.get_estimated_purchase_price(obj.unit)
                if suggested and suggested > 0:
                    info_parts.append(
                        f'<span style="color: green;">💡 Suggested: {suggested}</span>'
                    )
            except:
                pass

        return format_html('<br>'.join(info_parts))

    price_suggestion_info.short_description = 'Price Info'

    def save_formset(self, request, form, formset, change):
        """Enhanced save with auto-suggestion"""
        instances = formset.save(commit=False)

        for instance in instances:
            # Auto-suggest price if none entered
            if (not instance.entered_price or instance.entered_price == 0) and instance.product:
                try:
                    suggested = instance.product.get_estimated_purchase_price(instance.unit)
                    if suggested and suggested > 0:
                        instance.entered_price = suggested
                        messages.info(
                            request,
                            f'Auto-suggested price {suggested} for {instance.product.code}'
                        )
                except Exception as e:
                    logger.warning(f"Auto-suggestion failed for {instance.product.code}: {e}")

            instance.save()

        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()

        # Recalculate document totals
        if form.instance.pk and hasattr(form.instance, 'recalculate_totals'):
            form.instance.recalculate_totals()


# =================================================================
# PURCHASE REQUEST ADMIN - FIXED
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'supplier', 'status_display', 'urgency_display',
        'estimated_total_display', 'lines_count', 'auto_approve_indicator',  # NEW
        'requested_by', 'created_at'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type',
        'approval_required', 'created_at'
    ]

    search_fields = [
        'document_number', 'supplier__name',
        'business_justification', 'notes'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'converted_to_order', 'converted_at', 'converted_by',
        'auto_approve_preview_display',  # NEW
    ]

    fieldsets = [
        (_('Document Info'), {
            'fields': ('document_number', 'document_type', 'status', 'external_reference')
        }),
        (_('Request Details'), {
            'fields': (
                'supplier', 'location', 'request_type', 'urgency_level',
                'business_justification', 'expected_usage'
            )
        }),
        (_('Approval Workflow'), {
            'fields': (
                'approval_required', 'requested_by', 'approved_by', 'approved_at',
                'rejection_reason'
            )
        }),
        (_('Conversion Tracking'), {
            'fields': (
                'converted_to_order', 'converted_at', 'converted_by'
            ),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': (
                'created_at', 'updated_at',
                'auto_approve_preview_display',  # NEW
            ),
            'classes': ('collapse',)
        }),
    ]

    inlines = [PurchaseRequestLineInline]

    def save_model(self, request, obj, form, change):
        """Generate document number using DocumentService"""

        if not change and not obj.document_number:  # Нов документ без номер
            try:
                from nomenclatures.services import DocumentService

                result = DocumentService.create_document(
                    model_class=PurchaseRequest,
                    data={
                        'supplier': obj.supplier,
                        'location': obj.location,
                        'document_date': obj.document_date,
                        'requested_by': obj.requested_by or request.user,
                        'notes': obj.notes or '',
                        'external_reference': obj.external_reference or '',
                    },
                    user=request.user,
                    location=obj.location
                )

                if result['success']:
                    # Заместваме obj с новия от DocumentService
                    new_doc = result['document']
                    obj.pk = new_doc.pk
                    obj.document_number = new_doc.document_number
                    obj.status = new_doc.status
                    self.message_user(request, f'✅ Generated number: {new_doc.document_number}')
                    return  # НЕ извикваме super() защото DocumentService вече е записал
                else:
                    self.message_user(request, f'❌ Error: {result["message"]}', level='ERROR')

            except Exception as e:
                self.message_user(request, f'⚠️ DocumentService error: {e}', level='WARNING')

        # Set defaults
        if not obj.requested_by:
            obj.requested_by = request.user
        if not obj.status:
            obj.status = 'draft'

        super().save_model(request, obj, form, change)

    def urgency_display(self, obj):
        if obj.urgency_level == 'high':
            return format_html('<span style="color: #F44336;">🔥 High</span>')
        elif obj.urgency_level == 'medium':
            return format_html('<span style="color: #FF9800;">⚡ Medium</span>')
        else:
            return format_html('<span style="color: #4CAF50;">📋 Normal</span>')

    urgency_display.short_description = 'Urgency'

    def lines_count(self, obj):
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = 'Lines'

    def estimated_total_display(self, obj):
        # Legacy estimated calculation
        try:
            total = sum(
                (getattr(line, 'entered_price', 0) or 0) * (getattr(line, 'requested_quantity', 0) or 0)
                for line in obj.lines.all()
            )
            return float(total)
        except Exception:
            return '-'

    estimated_total_display.short_description = 'Estimated'

    def total_display(self, obj):
        # VAT-calculated total
        return float(obj.total) if hasattr(obj, 'total') else 0

    def status_display(self, obj):
        """Показва статуса както е записан в базата"""
        colors = {
            'draft': '#757575',
            'submitted': '#FF9800',
            'approved': '#4CAF50',
            'converted': '#2196F3',
            'rejected': '#F44336',
            'cancelled': '#9E9E9E'
        }
        color = colors.get(obj.status, '#757575')

        # Добави 🤖 ако е автоматично одобрен
        label = obj.status
        if obj.status == 'approved' and getattr(obj, 'was_auto_approved', False):
            label += ' 🤖'

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, label
        )

    status_display.short_description = _('Status')

    total_display.short_description = 'VAT Total'

    def auto_approve_indicator(self, obj):
        """Shows if request was auto-approved or can be auto-approved"""
        try:
            if obj.status == 'approved' and getattr(obj, 'was_auto_approved', False):
                rule_name = getattr(obj, 'auto_approval_rule_used.name', "Unknown")
                return format_html(
                    '<span style="background-color: #4CAF50; color: white; padding: 2px 6px; '
                    'border-radius: 3px; font-size: 10px;">🤖 AUTO: {}</span>',
                    rule_name
                )
            elif obj.status == 'draft':
                # Check if has auto-approve method
                if hasattr(obj, 'is_auto_approvable'):
                    preview = obj.is_auto_approvable()
                    if preview.get('can_auto_approve', False):
                        return format_html(
                            '<span style="background-color: #2196F3; color: white; padding: 2px 6px; '
                            'border-radius: 3px; font-size: 10px;">⚡ WILL AUTO-APPROVE</span>'
                        )
                    else:
                        return format_html(
                            '<span style="background-color: #FF9800; color: white; padding: 2px 6px; '
                            'border-radius: 3px; font-size: 10px;">👤 MANUAL APPROVAL</span>'
                        )
                else:
                    return format_html(
                        '<span style="background-color: #FF9800; color: white; padding: 2px 6px; '
                        'border-radius: 3px; font-size: 10px;">👤 MANUAL APPROVAL</span>'
                    )
            else:
                return '-'
        except Exception:
            return '-'

    auto_approve_indicator.short_description = _('Auto Approval')

    def auto_approve_preview_display(self, obj):
        """Detailed auto-approve preview for the admin form"""
        if not obj.pk:
            return "Save request first to see auto-approve preview"

        try:
            if hasattr(obj, 'get_auto_approve_preview'):
                preview_text = obj.get_auto_approve_preview()
                # Format for HTML display
                formatted_preview = preview_text.replace('\n', '<br>')
                return format_html(
                    '<div style="font-family: monospace; font-size: 12px; '
                    'background-color: #f5f5f5; padding: 10px; border-radius: 4px;">{}</div>',
                    formatted_preview
                )
            else:
                return "Auto-approve preview not available"
        except Exception as e:
            return f"Preview error: {e}"

    auto_approve_preview_display.short_description = _('Auto-Approve Preview')

    # =====================
    # ENHANCED ACTIONS
    # =====================

    actions = [
        'submit_requests_with_auto_approve',  # NEW
        'preview_auto_approve_status',  # NEW
        'approve_requests',
    ]

    def submit_requests_with_auto_approve(self, request, queryset):
        """NEW: Submit requests with auto-approve check"""
        submitted_count = 0
        auto_approved_count = 0
        error_count = 0

        for req in queryset.filter(status='draft'):
            try:
                if hasattr(req, 'submit_for_approval'):
                    result = req.submit_for_approval(request.user)
                    if isinstance(result, dict) and result.get('success'):
                        submitted_count += 1
                        if result.get('auto_approved'):
                            auto_approved_count += 1
                    else:
                        error_count += 1
                else:
                    # Fallback to simple status update
                    req.status = 'submitted'
                    req.save()
                    submitted_count += 1

            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f'Error submitting {req.document_number}: {e}',
                    level=messages.ERROR
                )

        # Summary message
        message_parts = []
        if submitted_count > 0:
            message_parts.append(f'Submitted {submitted_count} requests')
        if auto_approved_count > 0:
            message_parts.append(f'Auto-approved {auto_approved_count} requests')
        if error_count > 0:
            message_parts.append(f'{error_count} errors occurred')

        self.message_user(request, ' | '.join(message_parts))

    submit_requests_with_auto_approve.short_description = _('Submit with auto-approve check')

    def preview_auto_approve_status(self, request, queryset):
        """NEW: Preview auto-approve status for selected requests"""
        preview_lines = []

        for req in queryset:
            try:
                if hasattr(req, 'is_auto_approvable'):
                    preview = req.is_auto_approvable()
                    status = "✅ AUTO" if preview.get('can_auto_approve', False) else "👤 MANUAL"
                    reason = preview.get('reason', 'No reason provided')
                    preview_lines.append(f"{req.document_number}: {status} - {reason}")
                else:
                    preview_lines.append(f"{req.document_number}: 👤 MANUAL - Auto-approve not configured")
            except Exception as e:
                preview_lines.append(f"{req.document_number}: ❌ ERROR - {e}")

        # Show preview in message
        preview_text = '\n'.join(preview_lines[:10])  # Limit to 10 items
        if len(preview_lines) > 10:
            preview_text += f'\n... and {len(preview_lines) - 10} more'

        self.message_user(
            request,
            f'Auto-approve preview:\n{preview_text}',
            level=messages.INFO
        )

    preview_auto_approve_status.short_description = _('Preview auto-approve status')

    def approve_requests(self, request, queryset):
        """Standard approve action"""
        count = 0
        for req in queryset.filter(status='submitted'):
            try:
                if hasattr(req, 'approve'):
                    req.approve(request.user)
                else:
                    req.status = 'approved'
                    req.approved_by = request.user
                    req.save()
                count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Error approving {req.document_number}: {e}',
                    level=messages.ERROR
                )

        self.message_user(request, f'Approved {count} requests.')

    approve_requests.short_description = _('Approve requests')


# =================================================================
# LINE MODELS ADMIN - FIXED
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'entered_price', 'unit_price', 'gross_amount'  # ✅ FIXED: added entered_price
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']


# =================================================================
# SUCCESS MESSAGE
# =================================================================

print("✅ PURCHASES ADMIN LOADED SUCCESSFULLY - ONLY WORKING MODELS")