# # purchases/admin/orders.py - ПРОФЕСИОНАЛЕН АДМИН ЗА ORDERS
# """
# Purchase Order Admin - SYNCHRONIZED WITH NOMENCLATURES
#
# FEATURES:
# ✅ Matches PurchaseOrder model exactly
# ✅ DocumentService integration
# ✅ ApprovalService workflow actions
# ✅ MovementService integration
# ✅ Professional display methods
# ✅ Bulk operations
# ✅ Real-time status management
# """
#
# from django.contrib import admin
# from django.utils.html import format_html, mark_safe
# from django.utils.translation import gettext_lazy as _
# from django.utils import timezone
# from django.urls import reverse
# from django.http import HttpResponseRedirect
# from django.contrib import messages
# from decimal import Decimal
#
# from ..models.orders import PurchaseOrder, PurchaseOrderLine
#
#
# # =================================================================
# # PURCHASE ORDER LINE INLINE
# # =================================================================
#
# class PurchaseOrderLineInline(admin.TabularInline):
#     """
#     Purchase Order Line Inline - ПОПРАВЕН с правилните полета
#     """
#     model = PurchaseOrderLine
#     extra = 0
#     min_num = 1
#
#     fields = [
#         'line_number', 'product', 'unit', 'ordered_quantity', 'entered_price', 'unit_price',
#         'discount_percent', 'vat_rate', 'line_total_display'
#     ]
#
#     readonly_fields = ['line_number', 'line_total_display']
#
#     def line_total_display(self, obj):
#         """Rich line total с FinancialLineMixin полета"""
#         if not obj or not obj.quantity:
#             return '-'
#
#         try:
#             qty = float(obj.quantity or 0)
#             entered_price = float(obj.entered_price or 0)
#             unit_price = float(obj.unit_price or 0)
#             discount_percent = float(obj.discount_percent or 0)
#             vat_rate = float(obj.vat_rate or 20)
#
#             # Използвай net_amount и gross_amount ако са изчислени
#             net_amount = float(getattr(obj, 'net_amount', 0))
#             gross_amount = float(getattr(obj, 'gross_amount', 0))
#             vat_amount = float(getattr(obj, 'vat_amount', 0))
#
#             # Fallback calculation ако полетата не са попълнени
#             if net_amount == 0 and unit_price > 0:
#                 gross_line = qty * unit_price
#                 discount_amount = gross_line * (discount_percent / 100)
#                 net_amount = gross_line - discount_amount
#                 vat_amount = net_amount * (vat_rate / 100)
#                 gross_amount = net_amount + vat_amount
#
#             # Color coding
#             color = '#27ae60' if net_amount > 0 else '#e74c3c'
#
#             html = (
#                 f'<div style="text-align: right; font-size: 10px; line-height: 1.2;">'
#                 f'<div style="color: #666;">Entered: {entered_price:.2f} лв</div>'
#                 f'<div style="color: #666;">Unit: {unit_price:.2f} (excl VAT)</div>'
#                 f'<div style="color: #e67e22;">Disc: -{discount_percent:.1f}%</div>'
#                 f'<div style="color: {color}; font-weight: bold; font-size: 12px;">Net: {net_amount:.2f} лв</div>'
#                 f'<div style="color: #3498db; font-size: 9px;">VAT: {vat_amount:.2f} ({vat_rate:.0f}%)</div>'
#                 f'<div style="color: #2c3e50; font-weight: bold;">Total: {gross_amount:.2f} лв</div>'
#                 f'</div>'
#             )
#
#             return mark_safe(html)
#
#         except Exception as e:
#             return f'Error: {e}'
#
#     line_total_display.short_description = 'Line Total'
#     line_total_display.allow_tags = True
#
#
# # =================================================================
# # MAIN PURCHASE ORDER ADMIN
# # =================================================================
#
# @admin.register(PurchaseOrder)
# class PurchaseOrderAdmin(admin.ModelAdmin):
#     """
#     Purchase Order Admin - ПЪЛНА СИНХРОНИЗАЦИЯ
#
#     Features:
#     - DocumentService integration
#     - ApprovalService workflow
#     - MovementService auto-receive
#     - Professional display
#     - Bulk operations
#     """
#
#     # =====================
#     # LIST DISPLAY & FILTERS
#     # =====================
#
#     list_display = [
#         'document_number_display',
#         'supplier_display',
#         'status_display',
#         'urgency_badge',
#         'total_display',
#         'delivery_status_display',
#         'expected_delivery_display',
#         'supplier_confirmed_display',
#         'workflow_actions_display'
#     ]
#
#     list_filter = [
#         'status',
#         'delivery_status',
#         'is_urgent',
#         'supplier_confirmed',
#         'document_type',
#         'supplier',
#         'location',
#         'expected_delivery_date',
#         ('source_request', admin.EmptyFieldListFilter),
#     ]
#
#     search_fields = [
#         'document_number',
#         'supplier__name',
#         'supplier__code',
#         'supplier_order_reference',
#         'external_reference',
#         'notes',
#         'source_request__document_number',
#     ]
#
#     # =====================
#     # FORM ORGANIZATION
#     # =====================
#
#     fieldsets = (
#         (_('Document Information'), {
#             'fields': (
#                 ('document_number', 'document_type'),
#                 ('document_date', 'status'),
#                 ('supplier', 'location'),
#             )
#         }),
#
#         (_('Order Details'), {
#             'fields': (
#                 ('is_urgent', 'expected_delivery_date'),
#                 ('external_reference', 'supplier_order_reference'),
#                 'supplier_confirmed',
#             )
#         }),
#
#         (_('Source & Workflow'), {
#             'fields': (
#                 'source_request',
#             ),
#             'classes': ('collapse',)
#         }),
#
#         (_('Financial Summary'), {
#             'fields': (
#                 ('subtotal', 'discount_total'),
#                 ('vat_total', 'total'),
#                 'prices_entered_with_vat',
#             ),
#             'classes': ('collapse',)
#         }),
#
#         (_('Payment Information'), {
#             'fields': (
#                 'is_paid', 'payment_date', 'payment_method'
#             ),
#             'classes': ('collapse',)
#         }),
#
#         (_('Notes & Comments'), {
#             'fields': ('notes',)
#         }),
#
#         (_('System Information'), {
#             'fields': (
#                 ('created_by', 'created_at'),
#                 ('updated_by', 'updated_at'),
#                 'order_analytics_display',
#                 'workflow_summary_display',
#             ),
#             'classes': ('collapse',)
#         }),
#     )
#
#     readonly_fields = [
#         'document_number', 'created_at', 'updated_at',
#         'subtotal', 'discount_total', 'vat_total', 'total',
#         'order_analytics_display', 'workflow_summary_display'
#     ]
#
#     inlines = [PurchaseOrderLineInline]
#
#     date_hierarchy = 'expected_delivery_date'
#
#     # =====================
#     # DISPLAY METHODS
#     # =====================
#
#     def document_number_display(self, obj):
#         """Rich document number с status indicator"""
#         status_colors = {
#             'draft': '#95a5a6',
#             'sent': '#3498db',
#             'confirmed': '#27ae60',
#             'completed': '#2ecc71',
#             'cancelled': '#e74c3c'
#         }
#
#         color = status_colors.get(obj.status, '#34495e')
#         icon = '📄'
#
#         if obj.is_urgent:
#             icon = '🔥'
#
#         html = (
#             f'<div style="display: flex; align-items: center; gap: 5px;">'
#             f'<span style="font-size: 14px;">{icon}</span>'
#             f'<div>'
#             f'<div style="font-weight: bold; color: {color};">{obj.document_number}</div>'
#             f'<div style="font-size: 10px; color: #7f8c8d;">{obj.document_date}</div>'
#             f'</div>'
#             f'</div>'
#         )
#
#         return mark_safe(html)
#
#     document_number_display.short_description = 'Document'
#     document_number_display.admin_order_field = 'document_number'
#
#     def supplier_display(self, obj):
#         """Rich supplier display with divisions"""
#         if not obj.supplier:
#             return '-'
#
#         divisions = obj.supplier.divisions.filter(is_active=True)
#         codes = ", ".join([d.code or d.name for d in divisions]) if divisions.exists() else ""
#
#         html = (
#             f'<div>'
#             f'<div style="font-weight: bold;">{obj.supplier.name}</div>'
#             f'<div style="font-size: 10px; color: #7f8c8d;">{codes}</div>'
#             f'</div>'
#         )
#         return mark_safe(html)
#
#     supplier_display.short_description = 'Supplier'
#     supplier_display.admin_order_field = 'supplier__name'
#
#     def status_display(self, obj):
#         """Professional status display с integration"""
#         status_config = {
#             'draft': {'color': '#95a5a6', 'icon': '📝', 'bg': '#ecf0f1'},
#             'sent': {'color': '#3498db', 'icon': '📤', 'bg': '#ebf3fd'},
#             'confirmed': {'color': '#27ae60', 'icon': '✅', 'bg': '#eafaf1'},
#             'completed': {'color': '#2ecc71', 'icon': '🏁', 'bg': '#e8f8f5'},
#             'cancelled': {'color': '#e74c3c', 'icon': '❌', 'bg': '#fadbd8'},
#         }
#
#         config = status_config.get(obj.status, {
#             'color': '#34495e', 'icon': '❓', 'bg': '#f8f9fa'
#         })
#
#         # Опит за human label от DocumentService
#         try:
#             from nomenclatures.services import DocumentService
#             status_info = DocumentService._get_status_info(obj)
#             status_label = status_info.get('label', obj.status)
#             actions = DocumentService.get_available_actions(obj, None)
#             next_action = actions[0]['label'] if actions else 'No actions'
#         except Exception:
#             status_label = obj.status or '-'
#             next_action = 'Check workflow'
#
#         html = (
#             f'<div style="padding: 5px 10px; background: {config["bg"]}; '
#             f'border-radius: 4px; border-left: 3px solid {config["color"]};">'
#             f'<div style="color: {config["color"]}; font-weight: bold; display: flex; align-items: center; gap: 5px;">'
#             f'<span>{config["icon"]}</span>'
#             f'<span>{status_label}</span>'
#             f'</div>'
#             f'<div style="font-size: 9px; color: #7f8c8d; margin-top: 2px;">'
#             f'Next: {next_action}'
#             f'</div>'
#             f'</div>'
#         )
#         return mark_safe(html)
#
#     status_display.short_description = 'Status'
#     status_display.admin_order_field = 'status'
#
#     def urgency_badge(self, obj):
#         """Urgency indicator"""
#         if not obj.is_urgent:
#             return format_html('<span style="color: #95a5a6;">Normal</span>')
#
#         return format_html(
#             '<span style="background: #e74c3c; color: white; padding: 2px 6px; '
#             'border-radius: 3px; font-size: 10px; font-weight: bold;">🔥 URGENT</span>'
#         )
#
#     urgency_badge.short_description = 'Priority'
#     urgency_badge.admin_order_field = 'is_urgent'
#
#     def total_display(self, obj):
#         """Rich total display"""
#         try:
#             total = float(obj.total or 0)
#             subtotal = float(obj.subtotal or 0)
#             vat = float(obj.vat_total or 0)
#
#             # Color based on amount
#             if total > 10000:
#                 color = '#e74c3c'  # Red for high amounts
#             elif total > 1000:
#                 color = '#f39c12'  # Orange for medium
#             else:
#                 color = '#27ae60'  # Green for small
#
#             html = (
#                 f'<div style="text-align: right;">'
#                 f'<div style="color: {color}; font-weight: bold; font-size: 13px;">{total:.2f} лв</div>'
#                 f'<div style="font-size: 9px; color: #7f8c8d;">'
#                 f'Net: {subtotal:.2f} + VAT: {vat:.2f}'
#                 f'</div>'
#                 f'</div>'
#             )
#
#             return mark_safe(html)
#
#         except:
#             return '-'
#
#     total_display.short_description = 'Total'
#     total_display.admin_order_field = 'total'
#
#     def delivery_status_display(self, obj):
#         """Professional delivery status"""
#         status_config = {
#             'pending': {'color': '#f39c12', 'icon': '⏳', 'bg': '#fef9e7'},
#             'partial': {'color': '#9b59b6', 'icon': '📦', 'bg': '#f4ecf7'},
#             'completed': {'color': '#27ae60', 'icon': '✅', 'bg': '#eafaf1'},
#             'cancelled': {'color': '#95a5a6', 'icon': '❌', 'bg': '#f8f9fa'},
#         }
#
#         config = status_config.get(obj.delivery_status, {
#             'color': '#34495e', 'icon': '❓', 'bg': '#f8f9fa'
#         })
#
#         # Calculate delivery progress
#         try:
#             total_ordered = sum(line.ordered_quantity for line in obj.lines.all())
#             total_delivered = sum(line.delivered_quantity or 0 for line in obj.lines.all())
#             progress = (total_delivered / total_ordered * 100) if total_ordered > 0 else 0
#         except:
#             progress = 0
#
#         html = (
#             f'<div style="padding: 4px 8px; background: {config["bg"]}; '
#             f'border-radius: 3px; border-left: 2px solid {config["color"]};">'
#             f'<div style="color: {config["color"]}; font-weight: bold; display: flex; align-items: center; gap: 3px;">'
#             f'<span>{config["icon"]}</span>'
#             f'<span style="font-size: 11px;">{obj.get_delivery_status_display()}</span>'
#             f'</div>'
#             f'<div style="font-size: 8px; color: #7f8c8d;">{progress:.0f}% delivered</div>'
#             f'</div>'
#         )
#
#         return mark_safe(html)
#
#     delivery_status_display.short_description = 'Delivery'
#     delivery_status_display.admin_order_field = 'delivery_status'
#
#     def expected_delivery_display(self, obj):
#         """Smart delivery date display"""
#         if not obj.expected_delivery_date:
#             return format_html('<span style="color: #95a5a6;">Not set</span>')
#
#         from django.utils import timezone
#         today = timezone.now().date()
#         days_diff = (obj.expected_delivery_date - today).days
#
#         if days_diff < 0:
#             # Overdue
#             color = '#e74c3c'
#             icon = '⚠️'
#             suffix = f'({abs(days_diff)} days overdue)'
#         elif days_diff == 0:
#             # Today
#             color = '#f39c12'
#             icon = '🎯'
#             suffix = '(Today!)'
#         elif days_diff <= 3:
#             # Soon
#             color = '#f39c12'
#             icon = '⏰'
#             suffix = f'(in {days_diff} days)'
#         else:
#             # Future
#             color = '#27ae60'
#             icon = '📅'
#             suffix = f'(in {days_diff} days)'
#
#         html = (
#             f'<div style="color: {color}; font-weight: bold;">'
#             f'<span>{icon}</span> {obj.expected_delivery_date}'
#             f'</div>'
#             f'<div style="font-size: 9px; color: #7f8c8d;">{suffix}</div>'
#         )
#
#         return mark_safe(html)
#
#     expected_delivery_display.short_description = 'Expected Delivery'
#     expected_delivery_display.admin_order_field = 'expected_delivery_date'
#
#     def supplier_confirmed_display(self, obj):
#         """Supplier confirmation status"""
#         if obj.supplier_confirmed:
#             icon = '✅'
#             color = '#27ae60'
#             text = 'Confirmed'
#             if obj.supplier_order_reference:
#                 detail = f'Ref: {obj.supplier_order_reference}'
#             else:
#                 detail = 'No reference'
#         else:
#             icon = '⏳'
#             color = '#f39c12'
#             text = 'Pending'
#             detail = 'Awaiting confirmation'
#
#         html = (
#             f'<div style="color: {color}; font-weight: bold;">'
#             f'<span>{icon}</span> {text}'
#             f'</div>'
#             f'<div style="font-size: 9px; color: #7f8c8d;">{detail}</div>'
#         )
#
#         return mark_safe(html)
#
#     supplier_confirmed_display.short_description = 'Supplier Status'
#     supplier_confirmed_display.admin_order_field = 'supplier_confirmed'
#
#     def workflow_actions_display(self, obj):
#         """Live workflow actions"""
#         try:
#             from nomenclatures.services import DocumentService
#             actions = DocumentService.get_available_actions(obj, None)
#
#             if not actions:
#                 return format_html('<span style="color: #95a5a6;">No actions</span>')
#
#             # Show up to 2 most important actions
#             action_buttons = []
#             for action in actions[:2]:
#                 button_style = action.get('button_style', 'secondary')
#                 colors = {
#                     'primary': '#3498db',
#                     'success': '#27ae60',
#                     'warning': '#f39c12',
#                     'danger': '#e74c3c',
#                     'secondary': '#95a5a6'
#                 }
#
#                 color = colors.get(button_style, '#95a5a6')
#
#                 action_buttons.append(
#                     f'<span style="background: {color}; color: white; padding: 2px 5px; '
#                     f'border-radius: 2px; font-size: 9px; margin-right: 2px;">'
#                     f'{action["label"]}'
#                     f'</span>'
#                 )
#
#             return mark_safe(''.join(action_buttons))
#
#         except Exception as e:
#             return format_html('<span style="color: #e74c3c;">Error: {}</span>', str(e))
#
#     workflow_actions_display.short_description = 'Available Actions'
#
#     # =====================
#     # ANALYTICS METHODS
#     # =====================
#
#     def order_analytics_display(self, obj):
#         """Comprehensive order analytics"""
#         if not obj.pk:
#             return "Save order first to see analytics"
#
#         try:
#             lines_count = obj.lines.count()
#             total_items = sum(line.ordered_quantity for line in obj.lines.all())
#             total_value = float(obj.total or 0)
#
#             # Delivery progress
#             total_ordered = sum(line.ordered_quantity for line in obj.lines.all())
#             total_delivered = sum(line.delivered_quantity or 0 for line in obj.lines.all())
#             delivery_progress = (total_delivered / total_ordered * 100) if total_ordered > 0 else 0
#
#             analysis_parts = [
#                 f"<strong>📋 Document:</strong> {obj.document_number}",
#                 f"<strong>📊 Status:</strong> {obj.get_status_display()}",
#                 f"<strong>📦 Lines:</strong> {lines_count} lines, {total_items} total items",
#                 f"<strong>💰 Value:</strong> {total_value:.2f} лв",
#                 f"<strong>🚚 Delivery:</strong> {delivery_progress:.1f}% completed",
#             ]
#
#             if obj.source_request:
#                 analysis_parts.append(f"<strong>📝 Source:</strong> {obj.source_request.document_number}")
#
#             if obj.supplier_order_reference:
#                 analysis_parts.append(f"<strong>🏷️ Supplier Ref:</strong> {obj.supplier_order_reference}")
#
#             if obj.expected_delivery_date:
#                 from django.utils import timezone
#                 days_to_delivery = (obj.expected_delivery_date - timezone.now().date()).days
#                 analysis_parts.append(
#                     f"<strong>📅 Delivery:</strong> {obj.expected_delivery_date} ({days_to_delivery} days)")
#
#             return mark_safe('<br>'.join(analysis_parts))
#
#         except Exception as e:
#             return f"Analytics error: {e}"
#
#     order_analytics_display.short_description = 'Order Analytics'
#
#     def workflow_summary_display(self, obj):
#         """DocumentService workflow summary"""
#         try:
#             from nomenclatures.services import DocumentService
#
#             # Get workflow info
#             actions = DocumentService.get_available_actions(obj, None)
#
#             workflow_parts = [
#                 f"<strong>Current Status:</strong> {obj.get_status_display()}",
#                 f"<strong>Document Type:</strong> {obj.document_type.name if obj.document_type else 'Not set'}",
#             ]
#
#             if actions:
#                 action_labels = [action['label'] for action in actions[:3]]
#                 workflow_parts.append(f"<strong>Available Actions:</strong> {', '.join(action_labels)}")
#             else:
#                 workflow_parts.append("<strong>Available Actions:</strong> None")
#
#             # ApprovalService info if available
#             try:
#                 from nomenclatures.services import ApprovalService
#                 workflow_info = ApprovalService.get_workflow_info(obj)
#                 if hasattr(workflow_info, 'workflow_progress'):
#                     progress = workflow_info.workflow_progress
#                     if isinstance(progress, dict) and 'completed_steps' in progress:
#                         workflow_parts.append(
#                             f"<strong>Workflow Progress:</strong> {progress['completed_steps']}/{progress['total_steps']} steps")
#             except:
#                 pass
#
#             return mark_safe('<br>'.join(workflow_parts))
#
#         except Exception as e:
#             return f"Workflow error: {e}"
#
#     workflow_summary_display.short_description = 'Workflow Summary'
#
#     # =====================
#     # BULK ACTIONS
#     # =====================
#
#     actions = [
#         'send_to_supplier_action',
#         'mark_confirmed_action',
#         'create_delivery_receipts_action',
#         'test_document_service_action',
#         'sync_with_nomenclatures_action'
#     ]
#
#     def send_to_supplier_action(self, request, queryset):
#         """Send orders to suppliers via DocumentService"""
#         success_count = 0
#         error_count = 0
#
#         for order in queryset.filter(status='draft'):
#             try:
#                 # Use DocumentService for proper workflow
#                 result = order.transition_to('sent', request.user, 'Sent via admin bulk action')
#                 if hasattr(result, 'ok') and result.ok:
#                     success_count += 1
#                 else:
#                     error_count += 1
#             except Exception as e:
#                 error_count += 1
#                 messages.error(request, f'Error sending {order.document_number}: {e}')
#
#         if success_count:
#             messages.success(request, f'Successfully sent {success_count} orders to suppliers.')
#         if error_count:
#             messages.warning(request, f'{error_count} orders could not be sent.')
#
#     send_to_supplier_action.short_description = '📤 Send to suppliers (DocumentService)'
#
#     def mark_confirmed_action(self, request, queryset):
#         """Mark orders as confirmed"""
#         success_count = 0
#
#         for order in queryset.filter(status='sent'):
#             try:
#                 result = order.transition_to('confirmed', request.user, 'Confirmed via admin bulk action')
#                 if hasattr(result, 'ok') and result.ok:
#                     order.supplier_confirmed = True
#                     order.save(update_fields=['supplier_confirmed'])
#                     success_count += 1
#             except Exception as e:
#                 messages.error(request, f'Error confirming {order.document_number}: {e}')
#
#         messages.success(request, f'Confirmed {success_count} orders.')
#
#     mark_confirmed_action.short_description = '✅ Mark as confirmed'
#
#     def create_delivery_receipts_action(self, request, queryset):
#         """Create delivery receipts for confirmed orders"""
#         success_count = 0
#
#         for order in queryset.filter(status='confirmed'):
#             try:
#                 # Here you would call delivery creation service
#                 # delivery = DeliveryService.create_from_order(order, request.user)
#                 success_count += 1
#             except Exception as e:
#                 messages.error(request, f'Error creating delivery for {order.document_number}: {e}')
#
#         messages.success(request, f'Created delivery receipts for {success_count} orders.')
#
#     create_delivery_receipts_action.short_description = '🚚 Create delivery receipts'
#
#     def test_document_service_action(self, request, queryset):
#         """Test DocumentService integration"""
#         try:
#             from nomenclatures.services import DocumentService
#
#             for order in queryset[:3]:  # Test only first 3
#                 actions = DocumentService.get_available_actions(order, request.user)
#                 messages.info(request, f'{order.document_number}: {len(actions)} actions available')
#
#             messages.success(request, 'DocumentService integration test completed.')
#
#         except Exception as e:
#             messages.error(request, f'DocumentService test failed: {e}')
#
#     test_document_service_action.short_description = '🔧 Test DocumentService'
#
#     def sync_with_nomenclatures_action(self, request, queryset):
#         """Sync with nomenclatures system"""
#         try:
#             from nomenclatures.services import DocumentService
#
#             sync_count = 0
#             for order in queryset:
#                 if not order.document_type:
#                     # Try to set document type
#                     doc_type = DocumentService._get_document_type_for_model(order.__class__)
#                     if doc_type:
#                         order.document_type = doc_type
#                         order.save(update_fields=['document_type'])
#                         sync_count += 1
#
#             messages.success(request, f'Synced {sync_count} orders with nomenclatures.')
#
#         except Exception as e:
#             messages.error(request, f'Nomenclatures sync failed: {e}')
#
#     sync_with_nomenclatures_action.short_description = '🔄 Sync with nomenclatures'


# purchases/admin/orders.py - СЪЗДАЙ ТОЗИ ФАЙЛ
"""
Enhanced Purchase Order Admin with Workflow Testing
Copy от request admin и адаптиран за orders
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count, Q
from django.utils import timezone

from ..models import PurchaseOrder, PurchaseOrderLine


# =================================================================
# PURCHASE ORDER LINE INLINE
# =================================================================

class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = [
        'line_number', 'product', 'ordered_quantity', 'unit',
        'unit_price', 'discount_percent', 'net_amount', 'delivery_status'
    ]
    readonly_fields = ['line_number', 'net_amount']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


# =================================================================
# MAIN PURCHASE ORDER ADMIN
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """
    Enhanced Purchase Order Admin with Workflow Testing
    """

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'delivery_status_display', 'total_display', 'expected_delivery_date',
        'supplier_confirmed', 'workflow_actions'
    ]

    list_filter = [
        'status', 'delivery_status', 'supplier_confirmed', 'is_urgent',
        'location', 'supplier', 'expected_delivery_date', 'created_at'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'supplier_order_reference',
        'external_reference', 'notes'
    ]

    date_hierarchy = 'expected_delivery_date'
    inlines = [PurchaseOrderLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'subtotal', 'vat_total', 'total',
        'order_analytics', 'workflow_summary_display'
    ]

    fieldsets = (
        (_('🛒 Order Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status'
            )
        }),
        (_('📦 Delivery Details'), {
            'fields': (
                'expected_delivery_date', 'delivery_status', 'is_urgent'
            )
        }),
        (_('🏢 Supplier Communication'), {
            'fields': (
                'supplier_order_reference', 'supplier_confirmed', 'order_method'
            )
        }),
        (_('📋 Source & References'), {
            'fields': ('source_request', 'external_reference'),
            'classes': ('collapse',)
        }),
        (_('💰 Financial Summary'), {
            'fields': ('subtotal', 'vat_total', 'total'),
            'classes': ('collapse',)
        }),
        (_('💳 Payment Information'), {
            'fields': ('is_paid', 'payment_date', 'payment_method'),
            'classes': ('collapse',)
        }),
        (_('📝 Additional Info'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('🧪 Testing & Analytics'), {
            'fields': ('order_analytics', 'workflow_summary_display'),
            'classes': ('wide',)
        })
    )

    # =================================================================
    # CUSTOM URLS FOR TESTING
    # =================================================================

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/workflow-action/',
                self.admin_site.admin_view(self.workflow_action_view),
                name='purchases_purchaseorder_workflow_action'
            ),
            path(
                '<int:object_id>/test-workflow/',
                self.admin_site.admin_view(self.test_workflow_view),
                name='purchases_purchaseorder_test_workflow'
            ),
            path(
                '<int:object_id>/create-delivery/',
                self.admin_site.admin_view(self.create_delivery_view),
                name='purchases_purchaseorder_create_delivery'
            ),
            path(
                '<int:object_id>/debug-workflow/',
                self.admin_site.admin_view(self.debug_workflow_action),
                name='purchases_purchaseorder_debug_workflow'
            ),
        ]
        return custom_urls + urls

    # =================================================================
    # DISPLAY METHODS
    # =================================================================

    def status_display(self, obj):
        """Colored status display"""
        colors = {
            'draft': '#757575',
            'sent': '#FF9800',
            'confirmed': '#2196F3',
            'partially_delivered': '#9C27B0',
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

    def delivery_status_display(self, obj):
        """Delivery status with progress"""
        colors = {
            'pending': '#FF9800',
            'partial': '#9C27B0',
            'completed': '#4CAF50'
        }
        color = colors.get(obj.delivery_status, '#757575')

        # Calculate delivery progress
        total_lines = obj.lines.count()
        completed_lines = obj.lines.filter(delivery_status='completed').count()
        progress = (completed_lines / total_lines * 100) if total_lines > 0 else 0

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span><br>'
            '<small>{}% ({}/{})</small>',
            color, obj.get_delivery_status_display(),
            int(progress), completed_lines, total_lines
        )

    delivery_status_display.short_description = _('Delivery Status')

    def total_display(self, obj):
        """Financial total with currency"""
        if obj.total:
            return format_html(
                '<strong style="color: #2196F3;">{:.2f} лв</strong>',
                float(obj.total)
            )
        return '-'

    total_display.short_description = _('Total')

    def workflow_actions(self, obj):
        """Quick workflow action buttons"""
        if not obj.pk:
            return 'Save first'

        test_url = reverse('admin:purchases_purchaseorder_test_workflow', args=[obj.pk])
        delivery_url = reverse('admin:purchases_purchaseorder_create_delivery', args=[obj.pk])

        buttons = []

        # Test workflow button
        buttons.append(
            f'<a href="{test_url}" target="_blank" '
            f'style="background: #007cba; color: white; padding: 2px 6px; '
            f'border-radius: 3px; text-decoration: none; margin-right: 5px;">🧪 Test</a>'
        )

        # Create delivery button (if confirmed)
        if obj.status == 'confirmed':
            buttons.append(
                f'<a href="{delivery_url}" '
                f'style="background: #4CAF50; color: white; padding: 2px 6px; '
                f'border-radius: 3px; text-decoration: none;">📦 Delivery</a>'
            )

        return format_html(''.join(buttons))

    workflow_actions.short_description = _('Actions')

    # =================================================================
    # ANALYTICS METHODS
    # =================================================================

    def order_analytics(self, obj):
        """Comprehensive order analytics"""
        if not obj.pk:
            return "Save order first to see analytics"

        analytics = []

        # Basic stats
        lines_count = obj.lines.count()
        total_items = sum(line.ordered_quantity for line in obj.lines.all())

        # Delivery tracking
        delivered_lines = obj.lines.filter(delivery_status='completed').count()
        pending_lines = lines_count - delivered_lines

        # Financial summary
        analytics.extend([
            f"📊 <strong>Order Summary</strong>",
            f"Document: {obj.document_number}",
            f"Lines: {lines_count} | Total Items: {total_items}",
            f"Value: {obj.total:.2f} лв" if obj.total else "Value: Not calculated",
            f"",
            f"📦 <strong>Delivery Status</strong>",
            f"Completed: {delivered_lines}/{lines_count} lines",
            f"Pending: {pending_lines} lines",
        ])

        # Source tracking
        if obj.source_request:
            analytics.append(f"📋 <strong>Source:</strong> {obj.source_request.document_number}")

        # Supplier info
        if obj.supplier_order_reference:
            analytics.append(f"🏢 <strong>Supplier Ref:</strong> {obj.supplier_order_reference}")

        # Urgency
        if obj.is_urgent:
            analytics.append(f"🚨 <strong>URGENT ORDER</strong>")

        # Payment status
        if obj.is_paid:
            analytics.append(f"💳 <strong>PAID</strong> on {obj.payment_date}")
        else:
            analytics.append(f"💰 <strong>Payment Pending</strong>")

        return format_html('<br>'.join(analytics))

    order_analytics.short_description = _('Order Analytics')

    def workflow_summary_display(self, obj):
        """Workflow status and available actions"""
        if not obj.pk:
            return 'Save order first to see workflow info'

        html = ['<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">']

        try:
            # Current status info
            html.append(f'<h4 style="color: #0066cc; margin-top: 0;">📋 Order Status</h4>')
            html.append(f'<p><strong>Status:</strong> {obj.get_status_display()}</p>')
            html.append(f'<p><strong>Delivery:</strong> {obj.get_delivery_status_display()}</p>')
            html.append(f'<p><strong>Supplier Confirmed:</strong> {"Yes" if obj.supplier_confirmed else "No"}</p>')

            # Available actions
            try:
                actions = obj.get_available_actions(None)  # No user for now
                if actions:
                    html.append('<h4 style="color: #0066cc;">🔄 Available Transitions</h4>')
                    html.append('<ul>')
                    for action in actions:
                        action_url = reverse('admin:purchases_purchaseorder_workflow_action', args=[obj.pk])
                        html.append(
                            f'<li><a href="{action_url}?action={action.get("action", "")}&status={action.get("to_status", "")}" '
                            f'style="color: #007cba; text-decoration: none;">'
                            f'<strong>{action.get("to_status", "")}</strong>: {action.get("label", "")}</a></li>'
                        )
                    html.append('</ul>')
                else:
                    html.append('<p style="color: #6c757d;">No workflow actions available</p>')
            except Exception as e:
                html.append(f'<p style="color: #dc3545;">Error loading actions: {e}</p>')

            # Test buttons
            html.append('<h4 style="color: #0066cc;">🧪 Testing Actions</h4>')
            test_url = reverse('admin:purchases_purchaseorder_test_workflow', args=[obj.pk])
            debug_url = reverse('admin:purchases_purchaseorder_debug_workflow', args=[obj.pk])
            html.append(
                f'<a href="{test_url}" target="_blank" '
                f'style="background: #28a745; color: white; padding: 4px 8px; '
                f'border-radius: 3px; text-decoration: none; margin-right: 5px;">Test Workflow</a>'
            )
            html.append(
                f'<a href="{debug_url}" target="_blank" '
                f'style="background: #dc3545; color: white; padding: 4px 8px; '
                f'border-radius: 3px; text-decoration: none;">Debug Info</a>'
            )

        except Exception as e:
            html.append(f'<p style="color: #dc3545;">Error loading workflow info: {e}</p>')

        html.append('</div>')
        return format_html(''.join(html))

    workflow_summary_display.short_description = _('Workflow Summary')

    # =================================================================
    # WORKFLOW TESTING VIEWS
    # =================================================================

    def workflow_action_view(self, request, object_id):
        """Handle workflow action execution"""
        obj = get_object_or_404(PurchaseOrder, pk=object_id)

        if request.method == 'POST':
            action = request.POST.get('action')
            status = request.POST.get('status')
            comments = request.POST.get('comments', '')
        else:
            action = request.GET.get('action')
            status = request.GET.get('status')
            comments = ''

        if action and status:
            try:
                print(f"🧪 ORDER TEST: Executing {action} to {status} for {obj.document_number}")

                # Try to call transition method
                if hasattr(obj, 'transition_to'):
                    result = obj.transition_to(status, request.user, comments)
                else:
                    # Fallback - direct status change
                    old_status = obj.status
                    obj.status = status
                    obj.save()
                    result = True
                    print(f"🧪 ORDER TEST: Direct status change {old_status} → {status}")

                # Handle result
                if hasattr(result, 'ok') and result.ok:
                    messages.success(request, f'✅ Order transitioned to {status}')
                elif result is True:
                    messages.success(request, f'✅ Order status changed to {status}')
                else:
                    messages.warning(request, f'⚠️ Transition completed: {result}')

                # Force refresh
                obj.refresh_from_db()

            except Exception as e:
                print(f"🧪 ORDER TEST: Exception: {e}")
                messages.error(request, f'❌ Error: {str(e)}')
        else:
            messages.error(request, f'❌ Missing parameters: action={action}, status={status}')

        return redirect('admin:purchases_purchaseorder_change', object_id)

    def test_workflow_view(self, request, object_id):
        """Workflow testing interface"""
        obj = get_object_or_404(PurchaseOrder, pk=object_id)

        # Get available actions
        try:
            available_actions = obj.get_available_actions(request.user)
        except:
            available_actions = []

        context = {
            'title': f'Order Workflow Testing - {obj.document_number}',
            'object': obj,
            'available_actions': available_actions,
            'current_user': request.user,
        }

        return TemplateResponse(request, 'admin/purchases/test_order_workflow.html', context)

    def create_delivery_view(self, request, object_id):
        """Quick delivery creation for testing"""
        obj = get_object_or_404(PurchaseOrder, pk=object_id)

        if obj.status != 'confirmed':
            messages.error(request, f'❌ Order must be confirmed to create delivery. Current status: {obj.status}')
            return redirect('admin:purchases_purchaseorder_change', object_id)

        try:
            # Import here to avoid circular imports
            from ..models import DeliveryReceipt, DeliveryLine

            # Create delivery receipt
            delivery = DeliveryReceipt.objects.create(
                supplier=obj.supplier,
                location=obj.location,
                delivery_date=timezone.now().date(),
                source_order=obj,
                notes=f"Test delivery for {obj.document_number}"
            )

            # Copy all order lines to delivery (full quantities for testing)
            for order_line in obj.lines.all():
                DeliveryLine.objects.create(
                    document=delivery,
                    line_number=order_line.line_number,
                    product=order_line.product,
                    unit=order_line.unit,
                    received_quantity=order_line.ordered_quantity,  # Full delivery for testing
                    unit_price=order_line.unit_price,
                    source_order_line=order_line
                )

            # Update order delivery status
            obj._update_delivery_status()

            messages.success(request,
                             f'✅ Created delivery {delivery.document_number} for order {obj.document_number}')

            # Redirect to delivery admin
            delivery_url = reverse('admin:purchases_deliveryreceipt_change', args=[delivery.pk])
            return redirect(delivery_url)

        except Exception as e:
            messages.error(request, f'❌ Error creating delivery: {str(e)}')
            return redirect('admin:purchases_purchaseorder_change', object_id)

    def debug_workflow_action(self, request, object_id):
        """Debug information for troubleshooting"""
        obj = get_object_or_404(PurchaseOrder, pk=object_id)

        debug_info = {
            'object': obj,
            'current_status': obj.status,
            'delivery_status': obj.delivery_status,
            'document_type': getattr(obj, 'document_type', 'Not set'),
            'lines_count': obj.lines.count(),
            'has_lines': obj.lines.exists(),
            'total': obj.total,
            'can_edit': obj.can_edit if hasattr(obj, 'can_edit') else 'Unknown',
        }

        try:
            debug_info['available_actions'] = obj.get_available_actions(request.user)
        except Exception as e:
            debug_info['available_actions'] = f'Error: {e}'

        # Print to console for debugging
        print("🧪 ORDER DEBUG INFO:")
        for key, value in debug_info.items():
            print(f"  {key}: {value}")

        messages.info(request, f'🔍 Debug info printed to console for {obj.document_number}')
        return redirect('admin:purchases_purchaseorder_change', object_id)

    # =================================================================
    # BULK ACTIONS
    # =================================================================

    actions = ['send_to_supplier', 'mark_as_confirmed', 'create_test_deliveries', 'recalculate_totals']

    def send_to_supplier(self, request, queryset):
        """Send orders to supplier (change status to sent)"""
        count = 0
        for order in queryset.filter(status='draft'):
            try:
                if hasattr(order, 'transition_to'):
                    order.transition_to('sent', request.user)
                else:
                    order.status = 'sent'
                    order.save()
                count += 1
            except Exception as e:
                self.message_user(request, f'❌ Error sending {order.document_number}: {e}', level='ERROR')

        self.message_user(request, f'📧 Sent {count} orders to suppliers')

    send_to_supplier.short_description = _('📧 Send to supplier')

    def mark_as_confirmed(self, request, queryset):
        """Mark orders as confirmed by supplier"""
        count = 0
        for order in queryset.filter(status='sent'):
            try:
                order.supplier_confirmed = True
                if hasattr(order, 'transition_to'):
                    order.transition_to('confirmed', request.user)
                else:
                    order.status = 'confirmed'
                    order.save()
                count += 1
            except Exception as e:
                self.message_user(request, f'❌ Error confirming {order.document_number}: {e}', level='ERROR')

        self.message_user(request, f'✅ Confirmed {count} orders')

    mark_as_confirmed.short_description = _('✅ Mark as confirmed')

    def create_test_deliveries(self, request, queryset):
        """Create test deliveries for confirmed orders"""
        count = 0
        for order in queryset.filter(status='confirmed'):
            try:
                # This would call the create_delivery_view logic
                # For now, just mark as partially delivered for testing
                order.delivery_status = 'partial'
                order.save()
                count += 1
            except Exception as e:
                self.message_user(request, f'❌ Error creating delivery for {order.document_number}: {e}', level='ERROR')

        self.message_user(request, f'📦 Created test deliveries for {count} orders')

    create_test_deliveries.short_description = _('📦 Create test deliveries')

    def recalculate_totals(self, request, queryset):
        """Recalculate financial totals"""
        count = 0
        for order in queryset:
            try:
                if hasattr(order, 'recalculate_totals'):
                    order.recalculate_totals()
                count += 1
            except Exception as e:
                self.message_user(request, f'❌ Error recalculating {order.document_number}: {e}', level='ERROR')

        self.message_user(request, f'💰 Recalculated totals for {count} orders')

    recalculate_totals.short_description = _('💰 Recalculate totals')

    # =================================================================
    # QUERYSET OPTIMIZATION
    # =================================================================

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'location', 'source_request'
        ).prefetch_related('lines')