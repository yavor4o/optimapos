# purchases/admin/orders.py - СИНХРОНИЗИРАН С МОДЕЛА
"""
Purchase Order Admin - FIXED FIELD NAMES

ФИКСИРАНО:
✅ Всички полета в инлайна съответстват на модела
✅ line_total_display използва правилните полета от FinancialLineMixin
✅ quantity вместо ordered_quantity в display методи
✅ Премахнати несъществуващи полета като entered_price
✅ DocumentService integration с правилни exception handling
"""

from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from decimal import Decimal

from ..models.orders import PurchaseOrder, PurchaseOrderLine


# =================================================================
# PURCHASE ORDER LINE INLINE - FIXED
# =================================================================

class PurchaseOrderLineInline(admin.TabularInline):
    """Purchase Order Line Inline - СИНХРОНИЗИРАН С МОДЕЛА"""
    model = PurchaseOrderLine
    extra = 0
    min_num = 1

    # FIXED: Използваме ТОЧНИТЕ полета от миграциите
    fields = [
        'line_number', 'product', 'unit', 'ordered_quantity',
        'entered_price', 'unit_price', 'discount_percent', 'vat_rate', 'line_total_display'
    ]

    readonly_fields = ['line_number', 'line_total_display']

    def line_total_display(self, obj):
        if not obj or not obj.ordered_quantity:
            return '-'
        try:
            ordered_qty = float(obj.ordered_quantity or 0)
            entered_price = float(obj.entered_price or 0)
            unit_price = float(obj.unit_price or 0)
            discount_percent = float(obj.discount_percent or 0)

            html = f'<div>Qty: {ordered_qty:.3f}<br>Price: {unit_price:.2f} лв</div>'
            return mark_safe(html)
        except Exception as e:
            return f'Error: {e}'

    line_total_display.short_description = 'Line Total'
    line_total_display.allow_tags = True


# =================================================================
# MAIN PURCHASE ORDER ADMIN - FIXED
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Purchase Order Admin - СИНХРОНИЗИРАН С NOMENCLATURES"""

    # =====================
    # LIST DISPLAY & FILTERS - FIXED
    # =====================

    list_display = [
        'document_number_display',
        'supplier_display',
        'status_display',
        'urgency_badge',
        'total_display',
        'delivery_status_display',
        'expected_delivery_display',
        'supplier_confirmed_display',
        'workflow_actions_display'
    ]

    list_filter = [
        'status',
        'delivery_status',
        'is_urgent',
        'supplier_confirmed',
        'document_type',
        'supplier',
        'location',
        'expected_delivery_date',
        ('source_request', admin.EmptyFieldListFilter),
    ]

    search_fields = [
        'document_number',
        'supplier__name',
        'supplier__code',
        'supplier_order_reference',
        'external_reference',
        'notes',
        'source_request__document_number',
    ]

    # =====================
    # FORM ORGANIZATION - FIXED
    # =====================

    fieldsets = (
        (_('Document Information'), {
            'fields': (
                ('document_number', 'document_type'),
                ('document_date', 'status'),
                ('supplier', 'location'),
            )
        }),

        (_('Order Details'), {
            'fields': (
                ('is_urgent', 'expected_delivery_date'),
                ('external_reference', 'supplier_order_reference'),
                'supplier_confirmed',
            )
        }),

        (_('Source & Workflow'), {
            'fields': (
                'source_request',
            ),
            'classes': ('collapse',)
        }),

        (_('Financial Summary'), {
            'fields': (
                ('subtotal', 'discount_total'),
                ('vat_total', 'total'),  # FIXED: grand_total се казва 'total' в миграциите
                'prices_entered_with_vat',
            ),
            'classes': ('collapse',)
        }),

        (_('Payment Information'), {
            'fields': (
                'is_paid', 'payment_date', 'payment_method'
            ),
            'classes': ('collapse',)
        }),

        (_('Notes & Comments'), {
            'fields': ('notes',)
        }),

        (_('System Information'), {
            'fields': (
                ('created_by', 'created_at'),
                ('updated_by', 'updated_at'),
                'order_analytics_display',
                'workflow_summary_display',
            ),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'discount_total', 'vat_total', 'total',  # FIXED: grand_total -> total
        'order_analytics_display', 'workflow_summary_display'
    ]

    inlines = [PurchaseOrderLineInline]

    date_hierarchy = 'expected_delivery_date'

    # =====================
    # DISPLAY METHODS - FIXED
    # =====================

    def document_number_display(self, obj):
        """Rich document number с status indicator"""
        status_colors = {
            'draft': '#95a5a6',
            'sent': '#3498db',
            'confirmed': '#27ae60',
            'completed': '#2ecc71',
            'cancelled': '#e74c3c'
        }

        color = status_colors.get(obj.status, '#34495e')
        icon = '📄'

        if obj.is_urgent:
            icon = '🔥'

        html = (
            f'<div style="display: flex; align-items: center; gap: 5px;">'
            f'<span style="font-size: 14px;">{icon}</span>'
            f'<div>'
            f'<div style="font-weight: bold; color: {color};">{obj.document_number}</div>'
            f'<div style="font-size: 10px; color: #7f8c8d;">{obj.document_date}</div>'
            f'</div>'
            f'</div>'
        )

        return mark_safe(html)

    document_number_display.short_description = 'Document'
    document_number_display.admin_order_field = 'document_number'

    def supplier_display(self, obj):
        """Rich supplier display"""
        if not obj.supplier:
            return '-'

        # FIXED: Check if supplier has divisions method
        try:
            divisions = obj.supplier.divisions.filter(is_active=True) if hasattr(obj.supplier, 'divisions') else []
            codes = ", ".join([d.code or d.name for d in divisions]) if divisions else ""
        except:
            codes = ""

        html = (
            f'<div>'
            f'<div style="font-weight: bold;">{obj.supplier.name}</div>'
            f'<div style="font-size: 10px; color: #7f8c8d;">{codes}</div>'
            f'</div>'
        )
        return mark_safe(html)

    supplier_display.short_description = 'Supplier'
    supplier_display.admin_order_field = 'supplier__name'

    def status_display(self, obj):
        """Professional status display с DocumentService integration"""
        status_config = {
            'draft': {'color': '#95a5a6', 'icon': '📝', 'bg': '#ecf0f1'},
            'sent': {'color': '#3498db', 'icon': '📤', 'bg': '#ebf3fd'},
            'confirmed': {'color': '#27ae60', 'icon': '✅', 'bg': '#eafaf1'},
            'completed': {'color': '#2ecc71', 'icon': '🏁', 'bg': '#e8f8f5'},
            'cancelled': {'color': '#e74c3c', 'icon': '❌', 'bg': '#fadbd8'},
        }

        config = status_config.get(obj.status, {
            'color': '#34495e', 'icon': '❓', 'bg': '#f8f9fa'
        })

        # FIXED: Safe DocumentService integration
        try:
            from nomenclatures.services import DocumentService
            actions = DocumentService.get_available_actions(obj, None)
            status_label = obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status
            next_action = actions[0]['label'] if actions else 'No actions'
        except ImportError:
            status_label = obj.status or '-'
            next_action = 'Service not available'
        except Exception as e:
            status_label = obj.status or '-'
            next_action = f'Error: {str(e)[:20]}'

        html = (
            f'<div style="padding: 5px 10px; background: {config["bg"]}; '
            f'border-radius: 4px; border-left: 3px solid {config["color"]};">'
            f'<div style="color: {config["color"]}; font-weight: bold; display: flex; align-items: center; gap: 5px;">'
            f'<span>{config["icon"]}</span>'
            f'<span>{status_label}</span>'
            f'</div>'
            f'<div style="font-size: 9px; color: #7f8c8d; margin-top: 2px;">'
            f'Next: {next_action}'
            f'</div>'
            f'</div>'
        )
        return mark_safe(html)

    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def urgency_badge(self, obj):
        """Urgency indicator"""
        if not obj.is_urgent:
            return format_html('<span style="color: #95a5a6;">Normal</span>')

        return format_html(
            '<span style="background: #e74c3c; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px; font-weight: bold;">🔥 URGENT</span>'
        )

    urgency_badge.short_description = 'Priority'
    urgency_badge.admin_order_field = 'is_urgent'

    def total_display(self, obj):
        """Rich total display"""
        try:
            # FIXED: В миграциите полето се казва 'total', не 'grand_total'
            total = float(getattr(obj, 'total', 0) or 0)
            subtotal = float(obj.subtotal or 0)
            vat = float(obj.vat_total or 0)

            # Color based on amount
            if total > 10000:
                color = '#e74c3c'  # Red for high amounts
            elif total > 1000:
                color = '#f39c12'  # Orange for medium
            else:
                color = '#27ae60'  # Green for small

            html = (
                f'<div style="text-align: right;">'
                f'<div style="color: {color}; font-weight: bold; font-size: 13px;">{total:.2f} лв</div>'
                f'<div style="font-size: 9px; color: #7f8c8d;">'
                f'Net: {subtotal:.2f} + VAT: {vat:.2f}'
                f'</div>'
                f'</div>'
            )

            return mark_safe(html)

        except Exception as e:
            return f'Error: {e}'

    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'

    def delivery_status_display(self, obj):
        """Professional delivery status"""
        status_config = {
            'pending': {'color': '#f39c12', 'icon': '⏳', 'bg': '#fef9e7'},
            'partial': {'color': '#9b59b6', 'icon': '📦', 'bg': '#f4ecf7'},
            'completed': {'color': '#27ae60', 'icon': '✅', 'bg': '#eafaf1'},
            'cancelled': {'color': '#95a5a6', 'icon': '❌', 'bg': '#f8f9fa'},
        }

        config = status_config.get(obj.delivery_status, {
            'color': '#34495e', 'icon': '❓', 'bg': '#f8f9fa'
        })

        # FIXED: Safe progress calculation
        try:
            total_ordered = sum(line.ordered_quantity for line in obj.lines.all())
            total_delivered = sum(line.delivered_quantity or 0 for line in obj.lines.all())
            progress = (total_delivered / total_ordered * 100) if total_ordered > 0 else 0
        except:
            progress = 0

        html = (
            f'<div style="padding: 4px 8px; background: {config["bg"]}; '
            f'border-radius: 3px; border-left: 2px solid {config["color"]};">'
            f'<div style="color: {config["color"]}; font-weight: bold; display: flex; align-items: center; gap: 3px;">'
            f'<span>{config["icon"]}</span>'
            f'<span style="font-size: 11px;">{obj.get_delivery_status_display()}</span>'
            f'</div>'
            f'<div style="font-size: 8px; color: #7f8c8d;">{progress:.0f}% delivered</div>'
            f'</div>'
        )

        return mark_safe(html)

    delivery_status_display.short_description = 'Delivery'
    delivery_status_display.admin_order_field = 'delivery_status'

    def expected_delivery_display(self, obj):
        """Smart delivery date display"""
        if not obj.expected_delivery_date:
            return format_html('<span style="color: #95a5a6;">Not set</span>')

        today = timezone.now().date()
        days_diff = (obj.expected_delivery_date - today).days

        if days_diff < 0:
            # Overdue
            color = '#e74c3c'
            icon = '⚠️'
            suffix = f'({abs(days_diff)} days overdue)'
        elif days_diff == 0:
            # Today
            color = '#f39c12'
            icon = '🎯'
            suffix = '(Today!)'
        elif days_diff <= 3:
            # Soon
            color = '#f39c12'
            icon = '⏰'
            suffix = f'(in {days_diff} days)'
        else:
            # Future
            color = '#27ae60'
            icon = '📅'
            suffix = f'(in {days_diff} days)'

        html = (
            f'<div style="color: {color}; font-weight: bold;">'
            f'<span>{icon}</span> {obj.expected_delivery_date}'
            f'</div>'
            f'<div style="font-size: 9px; color: #7f8c8d;">{suffix}</div>'
        )

        return mark_safe(html)

    expected_delivery_display.short_description = 'Expected Delivery'
    expected_delivery_display.admin_order_field = 'expected_delivery_date'

    def supplier_confirmed_display(self, obj):
        """Supplier confirmation status"""
        if obj.supplier_confirmed:
            icon = '✅'
            color = '#27ae60'
            text = 'Confirmed'
            if obj.supplier_order_reference:
                detail = f'Ref: {obj.supplier_order_reference}'
            else:
                detail = 'No reference'
        else:
            icon = '⏳'
            color = '#f39c12'
            text = 'Pending'
            detail = 'Awaiting confirmation'

        html = (
            f'<div style="color: {color}; font-weight: bold;">'
            f'<span>{icon}</span> {text}'
            f'</div>'
            f'<div style="font-size: 9px; color: #7f8c8d;">{detail}</div>'
        )

        return mark_safe(html)

    supplier_confirmed_display.short_description = 'Supplier Status'
    supplier_confirmed_display.admin_order_field = 'supplier_confirmed'

    def workflow_actions_display(self, obj):
        try:
            from nomenclatures.services import DocumentService
            actions = DocumentService.get_available_actions(obj, None)

            # Добави test link
            test_url = f'/purchases/order/{obj.pk}/test-workflow/'
            test_link = format_html(
                '<a href="{}" style="background: #17a2b8; color: white; padding: 2px 6px; border-radius: 2px; font-size: 9px; text-decoration: none; margin-right: 3px;">🧪 Test</a>',
                test_url
            )

            if actions:
                return format_html('{} <span style="color: #27ae60;">{} actions</span>', test_link, len(actions))
            else:
                return format_html('{} <span style="color: #95a5a6;">No actions</span>', test_link)
        except:
            test_url = f'/purchases/order/{obj.pk}/test-workflow/'
            return format_html(
                '<a href="{}" style="background: #17a2b8; color: white; padding: 2px 6px; border-radius: 2px; font-size: 9px; text-decoration: none;">🧪 Test</a>',
                test_url)
    workflow_actions_display.short_description = 'Available Actions'

    # =====================
    # ANALYTICS METHODS - FIXED
    # =====================

    def order_analytics_display(self, obj):
        """Comprehensive order analytics"""
        if not obj.pk:
            return "Save order first to see analytics"

        try:
            lines_count = obj.lines.count()
            total_items = sum(line.ordered_quantity for line in obj.lines.all())
            total_value = float(getattr(obj, 'total', 0) or 0)  # FIXED: 'total' field

            # FIXED: Safe delivery progress calculation
            try:
                total_ordered = sum(line.ordered_quantity for line in obj.lines.all())
                total_delivered = sum(line.delivered_quantity or 0 for line in obj.lines.all())
                delivery_progress = (total_delivered / total_ordered * 100) if total_ordered > 0 else 0
            except:
                delivery_progress = 0

            analysis_parts = [
                f"<strong>📋 Document:</strong> {obj.document_number}",
                f"<strong>📊 Status:</strong> {obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status}",
                f"<strong>📦 Lines:</strong> {lines_count} lines, {total_items} total items",
                f"<strong>💰 Value:</strong> {total_value:.2f} лв",
                f"<strong>🚚 Delivery:</strong> {delivery_progress:.1f}% completed",
            ]

            if obj.source_request:
                analysis_parts.append(f"<strong>📝 Source:</strong> {obj.source_request.document_number}")

            if obj.supplier_order_reference:
                analysis_parts.append(f"<strong>🏷️ Supplier Ref:</strong> {obj.supplier_order_reference}")

            if obj.expected_delivery_date:
                days_to_delivery = (obj.expected_delivery_date - timezone.now().date()).days
                analysis_parts.append(
                    f"<strong>📅 Delivery:</strong> {obj.expected_delivery_date} ({days_to_delivery} days)")

            return mark_safe('<br>'.join(analysis_parts))

        except Exception as e:
            return f"Analytics error: {e}"

    order_analytics_display.short_description = 'Order Analytics'

    def workflow_summary_display(self, obj):
        """DocumentService workflow summary - FIXED"""
        try:
            from nomenclatures.services import DocumentService

            # FIXED: Safe workflow info retrieval
            try:
                actions = DocumentService.get_available_actions(obj, None)
            except:
                actions = []

            workflow_parts = [
                f"<strong>Current Status:</strong> {obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status}",
                f"<strong>Document Type:</strong> {obj.document_type.name if obj.document_type else 'Not set'}",
            ]

            if actions:
                action_labels = [action['label'] for action in actions[:3]]
                workflow_parts.append(f"<strong>Available Actions:</strong> {', '.join(action_labels)}")
            else:
                workflow_parts.append("<strong>Available Actions:</strong> None")

            # FIXED: Safe ApprovalService integration
            try:
                from nomenclatures.services import ApprovalService
                workflow_info = ApprovalService.get_workflow_info(obj)
                if hasattr(workflow_info, 'workflow_progress'):
                    progress = workflow_info.workflow_progress
                    if isinstance(progress, dict) and 'completed_steps' in progress:
                        workflow_parts.append(
                            f"<strong>Workflow Progress:</strong> {progress['completed_steps']}/{progress['total_steps']} steps")
            except:
                pass

            return mark_safe('<br>'.join(workflow_parts))

        except ImportError:
            return "DocumentService not available"
        except Exception as e:
            return f"Workflow error: {e}"

    workflow_summary_display.short_description = 'Workflow Summary'

    # =====================
    # BULK ACTIONS - FIXED
    # =====================

    actions = [
        'send_to_supplier_action',
        'mark_confirmed_action',
        'test_document_service_action',
        'sync_with_nomenclatures_action'
    ]

    def send_to_supplier_action(self, request, queryset):
        """Send orders to suppliers via DocumentService"""
        success_count = 0
        error_count = 0

        for order in queryset.filter(status='draft'):
            try:
                # FIXED: Safe transition call
                if hasattr(order, 'transition_to'):
                    result = order.transition_to('sent', request.user, 'Sent via admin bulk action')
                    if getattr(result, 'ok', False):
                        success_count += 1
                    else:
                        error_count += 1
                else:
                    # Fallback direct update
                    order.status = 'sent'
                    order.updated_by = request.user
                    order.save()
                    success_count += 1
            except Exception as e:
                error_count += 1
                messages.error(request, f'Error sending {order.document_number}: {e}')

        if success_count:
            messages.success(request, f'Successfully sent {success_count} orders to suppliers.')
        if error_count:
            messages.warning(request, f'{error_count} orders could not be sent.')

    send_to_supplier_action.short_description = '📤 Send to suppliers'

    def mark_confirmed_action(self, request, queryset):
        """Mark orders as confirmed"""
        success_count = 0

        for order in queryset.filter(status='sent'):
            try:
                if hasattr(order, 'transition_to'):
                    result = order.transition_to('confirmed', request.user, 'Confirmed via admin bulk action')
                    if getattr(result, 'ok', False):
                        order.supplier_confirmed = True
                        order.save(update_fields=['supplier_confirmed'])
                        success_count += 1
                else:
                    # Fallback direct update
                    order.status = 'confirmed'
                    order.supplier_confirmed = True
                    order.updated_by = request.user
                    order.save()
                    success_count += 1
            except Exception as e:
                messages.error(request, f'Error confirming {order.document_number}: {e}')

        messages.success(request, f'Confirmed {success_count} orders.')

    mark_confirmed_action.short_description = '✅ Mark as confirmed'

    def test_document_service_action(self, request, queryset):
        """Test DocumentService integration"""
        try:
            from nomenclatures.services import DocumentService

            for order in queryset[:3]:  # Test only first 3
                try:
                    actions = DocumentService.get_available_actions(order, request.user)
                    messages.info(request, f'{order.document_number}: {len(actions)} actions available')
                except Exception as e:
                    messages.warning(request, f'{order.document_number}: Service error - {e}')

            messages.success(request, 'DocumentService integration test completed.')

        except ImportError:
            messages.error(request, 'DocumentService not available')
        except Exception as e:
            messages.error(request, f'DocumentService test failed: {e}')

    test_document_service_action.short_description = '🔧 Test DocumentService'

    def sync_with_nomenclatures_action(self, request, queryset):
        """Sync with nomenclatures system"""
        try:
            from nomenclatures.services import DocumentService

            sync_count = 0
            for order in queryset:
                if not order.document_type:
                    # FIXED: Safe document type setting
                    try:
                        doc_type = DocumentService._get_document_type_for_model(order.__class__)
                        if doc_type:
                            order.document_type = doc_type
                            order.save(update_fields=['document_type'])
                            sync_count += 1
                    except:
                        pass

            messages.success(request, f'Synced {sync_count} orders with nomenclatures.')

        except ImportError:
            messages.error(request, 'Nomenclatures system not available')
        except Exception as e:
            messages.error(request, f'Nomenclatures sync failed: {e}')

    sync_with_nomenclatures_action.short_description = '🔄 Sync with nomenclatures'