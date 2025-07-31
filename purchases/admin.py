# purchases/admin.py - FIXED COMPLETE ADMIN
import logging

from django.contrib import admin, messages
from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe

from nomenclatures.admin.dynamic_actions import DynamicPurchaseRequestAdmin
from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)


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


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'product', 'ordered_quantity', 'unit',
        'entered_price', 'unit_price', 'discount_percent', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount'
    ]
    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = [
        'product', 'received_quantity', 'unit',
        'entered_price', 'unit_price', 'discount_percent', 'vat_rate',
        'net_amount', 'vat_amount', 'gross_amount',
        'batch_number', 'expiry_date', 'quality_approved'
    ]
    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


# =================================================================
# PURCHASE REQUEST ADMIN - FIXED
# =================================================================

# REPLACE PurchaseRequestAdmin - CORRECT VERSION

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(DynamicPurchaseRequestAdmin):
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
        'document_number', 'supplier__name', 'requested_by__username',
        'business_justification', 'notes'
    ]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'converted_to_order', 'converted_at', 'converted_by',
        'auto_approve_preview_display',  # NEW
        'approval_history_display',  # NEW

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
                'rejection_reason', 'auto_approve_preview_display'  # NEW
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
                'created_at', 'updated_at',  # NEW

            ),
            'classes': ('collapse',)
        }),
    ]

    inlines = [PurchaseRequestLineInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.requested_by = request.user
            obj.created_by = request.user
        obj.updated_by = request.user
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
        return float(obj.total)

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
        if obj.status == 'approved' and obj.was_auto_approved:
            rule_name = obj.auto_approval_rule_used.name if obj.auto_approval_rule_used else "Unknown"
            return format_html(
                '<span style="background-color: #4CAF50; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">🤖 AUTO: {}</span>',
                rule_name
            )
        elif obj.status == 'draft':
            preview = obj.is_auto_approvable()
            if preview['can_auto_approve']:
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
            return '-'

    auto_approve_indicator.short_description = _('Auto Approval')

    def auto_approve_preview_display(self, obj):
        """Detailed auto-approve preview for the admin form"""
        if not obj.pk:
            return "Save request first to see auto-approve preview"

        preview_text = obj.get_auto_approve_preview()

        # Format for HTML display
        formatted_preview = preview_text.replace('\n', '<br>')

        return format_html(
            '<div style="font-family: monospace; font-size: 12px; '
            'background-color: #f5f5f5; padding: 10px; border-radius: 4px;">{}</div>',
            formatted_preview
        )

    auto_approve_preview_display.short_description = _('Auto-Approve Preview')

    def approval_history_display(self, obj):
        """Shows approval history including auto-approvals"""
        if not obj.pk:
            return "Save request first to see approval history"

        from nomenclatures.models.approvals import ApprovalLog
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj.__class__)
        logs = ApprovalLog.objects.filter(
            content_type=content_type,
            object_id=obj.pk
        ).order_by('-created_at')

        if not logs.exists():
            return "No approval history"

        history_lines = []
        for log in logs[:5]:  # Show last 5 entries
            action_icon = {
                'approved': '✅',
                'auto_approved': '🤖',
                'rejected': '❌',
                'submitted': '📤'
            }.get(log.action, '📝')

            user_name = log.user.get_full_name() if log.user else 'System'
            timestamp = log.created_at.strftime('%Y-%m-%d %H:%M')

            rule_info = f" ({log.rule.name})" if log.rule else ""

            history_lines.append(
                f"{action_icon} {log.action.title()}{rule_info} by {user_name} at {timestamp}"
            )

        return format_html(
            '<div style="font-family: monospace; font-size: 11px;">{}</div>',
            '<br>'.join(history_lines)
        )

    approval_history_display.short_description = _('Approval History')

    # =====================
    # ENHANCED ACTIONS
    # =====================

    actions = [
        'submit_requests_with_auto_approve',  # NEW
        'preview_auto_approve_status',  # NEW
        'approve_requests',
        'convert_to_orders'
    ]

    def submit_requests_with_auto_approve(self, request, queryset):
        """NEW: Submit requests with auto-approve check"""
        submitted_count = 0
        auto_approved_count = 0
        error_count = 0

        for req in queryset.filter(status='draft'):
            try:
                result = req.submit_for_approval(request.user)
                if result['success']:
                    submitted_count += 1
                    if result['auto_approved']:
                        auto_approved_count += 1
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f'Error submitting {req.document_number}: {e}',
                    level='ERROR'
                )

        # Summary message
        messages = []
        if submitted_count > 0:
            messages.append(f'Submitted {submitted_count} requests')
        if auto_approved_count > 0:
            messages.append(f'Auto-approved {auto_approved_count} requests')
        if error_count > 0:
            messages.append(f'{error_count} errors occurred')

        self.message_user(request, ' | '.join(messages))

    submit_requests_with_auto_approve.short_description = _('Submit with auto-approve check')

    def preview_auto_approve_status(self, request, queryset):
        """NEW: Preview auto-approve status for selected requests"""
        preview_lines = []

        for req in queryset:
            preview = req.is_auto_approvable()
            status = "✅ AUTO" if preview['can_auto_approve'] else "👤 MANUAL"
            preview_lines.append(f"{req.document_number}: {status} - {preview['reason']}")

        # Show preview in message
        preview_text = '\n'.join(preview_lines[:10])  # Limit to 10 items
        if len(preview_lines) > 10:
            preview_text += f'\n... and {len(preview_lines) - 10} more'

        self.message_user(
            request,
            f'Auto-approve preview:\n{preview_text}',
            level='INFO'
        )

    preview_auto_approve_status.short_description = _('Preview auto-approve status')




# =================================================================
# PURCHASE ORDER ADMIN - FIXED
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(DynamicPurchaseRequestAdmin):
    list_display = [
        'document_number', 'supplier', 'status_display', 'is_urgent',
        'lines_count', 'total_display', 'expected_delivery_date'  # ✅ FIXED: total_display
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier_confirmed', 'supplier',
        'location', 'expected_delivery_date'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference'
    ]

    readonly_fields = [
        'document_number', 'document_type', 'status',
        'subtotal', 'discount_total', 'vat_total', 'total',  # ✅ FIXED: total
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'status', 'is_urgent', 'prices_entered_with_vat')  # ✅ ADDED VAT control
        }),
        ('Order Details', {
            'fields': (
                'document_date', 'expected_delivery_date',
                'supplier_order_reference', 'supplier_confirmed'
            )
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),  # ✅ FIXED: total
            'classes': ('collapse',)
        }),
        ('Source Information', {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        ('Payment Information', {
            'fields': ('is_paid', 'payment_date', 'payment_method'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('document_number', 'document_type', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PurchaseOrderLineInline]

    def status_display(self, obj):
        # ✅ FIXED: Safe status display
        try:
            status_value = obj.status
            status_label = obj.get_status_display() if hasattr(obj, 'get_status_display') else status_value.title()
        except:
            status_value = 'unknown'
            status_label = 'Unknown'

        colors = {
            'draft': '#757575',
            'confirmed': '#4CAF50',
            'sent': '#2196F3',
            'delivered': '#FF9800',
            'completed': '#9C27B0',
            'unknown': '#9E9E9E'
        }
        color = colors.get(status_value, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, status_label
        )

    status_display.short_description = 'Status'

    def lines_count(self, obj):
        return format_html('<strong>{}</strong>', obj.lines.count())

    lines_count.short_description = 'Lines'

    def total_display(self, obj):
        # ✅ FIXED: Use total instead of grand_total
        return  float(obj.total)

    total_display.short_description = 'Total'


# =================================================================
# DELIVERY RECEIPT ADMIN - FIXED
# =================================================================

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(DynamicPurchaseRequestAdmin):
    list_display = [
        'document_number', 'supplier', 'delivery_date', 'status_display',
        'lines_count', 'total_display', 'quality_status', 'inventory_status', 'received_by'
    ]

    list_filter = [
        'status', 'has_quality_issues', 'has_variances', 'quality_checked',
        'delivery_date', 'supplier', 'location'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'delivery_note_number'
    ]

    readonly_fields = [
        'document_number', 'document_type', 'status',  # ✅ STATUS Е READONLY!
        'subtotal', 'discount_total', 'vat_total', 'total',
        'received_at', 'processed_at',
        'created_at', 'updated_at', 'created_by', 'updated_by',
        'inventory_movements_display', 'workflow_status_display'  # НОВИ
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location', 'prices_entered_with_vat')
            # ✅ БЕЗ STATUS тук - той е readonly
        }),
        ('Document Status', {  # ✅ НОВА СЕКЦИЯ за статус
            'fields': ('status', 'workflow_status_display'),
            'description': 'Status се контролира автоматично от системата'
        }),
        ('Delivery Details', {
            'fields': (
                'delivery_date', 'delivery_note_number', 'external_reference',
                'vehicle_info', 'driver_name', 'driver_phone'
            )
        }),
        ('Quality Control', {
            'fields': (
                'quality_checked', 'has_quality_issues', 'quality_inspector',
                'quality_notes'
            )
        }),
        ('Inventory Movements', {
            'fields': ('inventory_movements_display',),
            'classes': ('collapse',)
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount_total', 'vat_total', 'total'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': (
                'document_number', 'document_type', 'received_at', 'processed_at',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [DeliveryLineInline]

    # ЧИСТИ ACTIONS
    actions = [
        'complete_delivery_workflow',
        'show_inventory_preview',
        'mark_quality_checked'
    ]

    # =====================
    # DISPLAY МЕТОДИ
    # =====================

    def status_display(self, obj):
        """Красив display на статуса"""
        colors = {
            'draft': '#757575',
            'completed': '#4CAF50',
            'cancelled': '#F44336',
        }
        color = colors.get(obj.status, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.status.title()
        )

    status_display.short_description = 'Status'

    def workflow_status_display(self, obj):
        """Показва workflow информация"""
        if not obj.document_type:
            return format_html('<span style="color: red;">❌ No DocumentType</span>')

        next_statuses = obj.get_next_statuses()
        auto_confirm = obj.document_type.auto_confirm

        html = f'<div style="font-family: monospace; font-size: 12px;">'
        html += f'<div><strong>Current:</strong> {obj.status}</div>'

        if auto_confirm:
            html += f'<div><strong>Auto-confirm:</strong> <span style="color: green;">✅ Enabled</span></div>'
        else:
            html += f'<div><strong>Auto-confirm:</strong> <span style="color: orange;">⚠️ Disabled</span></div>'

        if next_statuses:
            html += f'<div><strong>Next possible:</strong> {", ".join(next_statuses)}</div>'
        else:
            html += f'<div><strong>Next possible:</strong> <span style="color: red;">None (final status)</span></div>'

        html += '</div>'
        return format_html(html)

    workflow_status_display.short_description = 'Workflow Info'

    def lines_count(self, obj):
        return format_html('<strong>{}</strong>', obj.lines.count())

    lines_count.short_description = 'Lines'

    def total_display(self, obj):
        return f"{float(obj.total):.2f} лв"

    total_display.short_description = 'Total'

    def quality_status(self, obj):
        if obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues</span>')
        elif obj.quality_checked:
            return format_html('<span style="color: green;">✅ OK</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')

    quality_status.short_description = 'Quality'

    def inventory_status(self, obj):
        """Показва дали има създадени inventory движения"""
        from inventory.models import InventoryMovement

        count = InventoryMovement.objects.filter(
            source_document_number=obj.document_number
        ).count()

        if count > 0:
            return format_html('<span style="color: green;">🏭 {} movements</span>', count)
        else:
            return format_html('<span style="color: orange;">⚠️ No movements</span>')

    inventory_status.short_description = 'Inventory'

    def inventory_movements_display(self, obj):
        """Показва детайли за създадените inventory движения"""
        from inventory.models import InventoryMovement

        movements = InventoryMovement.objects.filter(
            source_document_number=obj.document_number
        ).order_by('-created_at')

        if not movements.exists():
            return format_html('<span style="color: orange;">Няма създадени движения</span>')

        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
        for movement in movements:
            icon = "📈" if movement.movement_type == "IN" else "📉"
            html_parts.append(
                f'<div>{icon} {movement.movement_type}: '
                f'{movement.product.code} x {movement.quantity} '
                f'({movement.created_at.strftime("%H:%M")})</div>'
            )
        html_parts.append('</div>')
        return format_html(''.join(html_parts))

    inventory_movements_display.short_description = 'Inventory Movements'

    # =====================
    # ADMIN ACTIONS
    # =====================

    @admin.action(description='🔄 Complete delivery workflow (Auto-confirm)')
    def complete_delivery_workflow(self, request, queryset):
        """
        ЕДИНСТВЕН ACTION за завършване на доставка

        Извиква само DeliveryService._check_auto_confirm()
        """
        from purchases.services.delivery_service import DeliveryService

        success_count = 0

        for delivery in queryset:
            try:
                if delivery.status != 'draft':
                    self.message_user(
                        request,
                        f'⚠️ {delivery.document_number}: Статус "{delivery.status}" - очаква се "draft"',
                        level='WARNING'
                    )
                    continue

                if not delivery.lines.exists():
                    self.message_user(
                        request,
                        f'⚠️ {delivery.document_number}: Няма редове',
                        level='WARNING'
                    )
                    continue

                # ИЗВИКВАМЕ САМО DeliveryService._check_auto_confirm
                DeliveryService._check_auto_confirm(delivery, request.user)

                # Refresh обекта от базата да видим промените
                delivery.refresh_from_db()

                success_count += 1
                self.message_user(
                    request,
                    f'✅ {delivery.document_number}: Обработен (статус: {delivery.status})'
                )

            except Exception as e:
                self.message_user(
                    request,
                    f'❌ {delivery.document_number}: {str(e)}',
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(
                request,
                f'🎯 Успешно обработени: {success_count} доставки'
            )

    @admin.action(description='📊 Preview inventory impact')
    def show_inventory_preview(self, request, queryset):
        """Preview на inventory движенията"""
        for delivery in queryset:
            if not delivery.document_type or not delivery.document_type.affects_inventory:
                self.message_user(
                    request,
                    f'ℹ️ {delivery.document_number}: Не влияе на inventory',
                    level='INFO'
                )
                continue

            preview_details = []
            for line in delivery.lines.all():
                if hasattr(line, 'received_quantity') and line.received_quantity:
                    direction = "увеличава" if line.received_quantity > 0 else "намалява"
                    preview_details.append(
                        f"{line.product.code}: {direction} {abs(line.received_quantity)}"
                    )

            if preview_details:
                self.message_user(
                    request,
                    f'🔍 {delivery.document_number} ще създаде: {", ".join(preview_details)}',
                    level='INFO'
                )

    @admin.action(description='✅ Mark quality checked')
    def mark_quality_checked(self, request, queryset):
        count = queryset.update(
            quality_checked=True,
            quality_inspector=request.user
        )
        self.message_user(request, f'✅ Quality checked {count} deliveries.')

    # =====================
    # OVERRIDE save_model за auto-confirm при добавяне на редове
    # =====================

    # В DeliveryReceiptAdmin - ЗАМЕНИ save_formset метода:

    def save_formset(self, request, form, formset, change):
        delivery = form.instance
        super().save_formset(request, form, formset, change)

        from purchases.services.delivery_service import DeliveryService

        # Само ако е immediate
        if delivery.document_type and delivery.document_type.inventory_timing == 'immediate':
            try:
                DeliveryService.process_immediate_inventory(delivery, user=request.user)
            except Exception as e:
                self.message_user(request, f"❌ Inventory processing failed: {e}", level='ERROR')

        # Auto-confirm също е ок да остане тук:
        if (
                delivery.status == 'draft' and
                delivery.document_type.auto_confirm and
                delivery.lines.exists()
        ):
            try:
                DeliveryService._check_auto_confirm(delivery, request.user)
                delivery.refresh_from_db()
                if delivery.status != 'draft':
                    self.message_user(
                        request,
                        f"✅ Auto-confirmed to: {delivery.status}",
                        level='SUCCESS'
                    )
            except Exception as e:
                self.message_user(request, f"❌ Auto-confirm failed: {e}", level='ERROR')


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


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'ordered_quantity',
        'entered_price', 'unit_price', 'discount_percent', 'gross_amount'  # ✅ FIXED
    ]

    list_filter = ['document__status', 'document__supplier']
    search_fields = ['product__code', 'product__name', 'document__document_number']

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']


@admin.register(DeliveryLine)
class DeliveryLineAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'line_number', 'product', 'received_quantity',
        'entered_price', 'unit_price', 'gross_amount', 'quality_approved', 'batch_number'  # ✅ FIXED
    ]

    list_filter = [
        'quality_approved', 'document__status', 'document__supplier'
    ]

    search_fields = [
        'product__code', 'product__name', 'batch_number',
        'document__document_number'
    ]

    readonly_fields = ['unit_price', 'vat_rate', 'net_amount', 'vat_amount', 'gross_amount']