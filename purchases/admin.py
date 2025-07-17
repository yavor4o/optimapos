# purchases/admin.py - ФИКСИРАН КОД

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone

# IMPORTS
from nomenclatures.services.approval_service import ApprovalService
from nomenclatures.admin.dynamic_actions import DynamicApprovalMixin

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
        'estimated_price', 'usage_description'
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
        'discount_percent', 'line_total'
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
        'batch_number', 'expiry_date'
    ]
    readonly_fields = ['line_number']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return 1


# =================================================================
# PURCHASE REQUEST ADMIN - ФИКСИРАН
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(DynamicApprovalMixin, admin.ModelAdmin):
    """
    Purchase Request Admin - ДИНАМИЧЕН

    Използва само ApprovalService и DocumentType конфигурацията.
    НИКАКВИ хардкодирани статуси!
    """

    list_display = [
        'document_number', 'requested_by', 'supplier', 'status_display',
        'urgency_display', 'lines_count', 'estimated_total', 'workflow_status_display'
    ]

    list_filter = [
        'status', 'urgency_level', 'request_type', 'supplier',
        'location', 'created_at', 'approved_at'
    ]

    search_fields = [
        'document_number', 'requested_by__username', 'requested_by__first_name',
        'requested_by__last_name', 'supplier__name', 'business_justification'
    ]

    date_hierarchy = 'created_at'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at', 'approved_at',
        'converted_at', 'request_analytics', 'workflow_status_display'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'requested_by', 'supplier', 'location',
                'status', 'urgency_level', 'request_type'
            )
        }),
        (_('Justification'), {
            'fields': (
                'business_justification', 'expected_usage'
            )
        }),
        (_('Approval Information'), {
            'fields': (
                'approved_by', 'approved_at', 'rejection_reason',
                'converted_to_order', 'converted_at', 'converted_by'
            ),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('request_analytics', 'workflow_status_display'),
            'classes': ('collapse',)
        }),
    )

    # =====================
    # ДИНАМИЧНИ ACTIONS - БЕЗ ХАРДКОДИНГ
    # =====================

    def get_actions(self, request):
        """
        ДИНАМИЧНО генериране на actions на база ApprovalService

        РЕШЕНИЕ 1: Просто присвояване на методите
        """
        actions = super().get_actions(request)

        # Просто присвояваме методите - Django ще се погрижи за параметрите
        actions['submit_for_approval'] = self.submit_for_approval_action
        actions['smart_workflow'] = self.smart_workflow_action
        actions['convert_final_approved'] = self.convert_final_approved_action

        return actions

    def submit_for_approval_action(self, request, queryset):
        """
        ПРОСТ ACTION: draft → submitted БЕЗ ApprovalService
        """
        updated = 0

        for document in queryset.filter(status='draft'):
            if not document.lines.exists():
                messages.warning(
                    request,
                    f'{document.document_number} has no lines - cannot submit'
                )
                continue

            document.status = 'submitted'
            document.save()
            updated += 1

        if updated:
            messages.success(
                request,
                f'Successfully submitted {updated} request(s) for approval'
            )

    submit_for_approval_action.short_description = _('Submit for approval')

    def smart_workflow_action(self, request, queryset):
        """
        УМЕН ACTION: Използва ApprovalService за всички преходи
        """
        user = request.user
        processed = 0

        for document in queryset:
            # За draft документи - прост submit
            if document.status == 'draft':
                if not document.lines.exists():
                    messages.warning(
                        request,
                        f'{document.document_number} has no lines - cannot submit'
                    )
                    continue

                document.status = 'submitted'
                document.save()
                processed += 1
                messages.info(
                    request,
                    f'{document.document_number}: submitted for approval'
                )
                continue

            # За всички останали - ApprovalService
            transitions = ApprovalService.get_available_transitions(document, user)

            if not transitions:
                messages.warning(
                    request,
                    f'{document.document_number}: No available transitions'
                )
                continue

            # Изпълняваме първия наличен преход
            first_transition = transitions[0]
            result = ApprovalService.execute_transition(
                document=document,
                to_status=first_transition['to_status'],
                user=user,
                comments=f"Smart workflow action: {first_transition['name']}"
            )

            if result['success']:
                processed += 1
                messages.success(
                    request,
                    f'{document.document_number}: {result["message"]}'
                )
            else:
                messages.error(
                    request,
                    f'{document.document_number}: {result["message"]}'
                )

        if processed:
            messages.info(
                request,
                f'Processed {processed} document(s) successfully'
            )

    smart_workflow_action.short_description = _('Smart workflow transition')

    def convert_final_approved_action(self, request, queryset):
        """
        ДИНАМИЧНО ОТКРИВАНЕ на final approved статус за conversion
        """
        success_count = 0
        failed_count = 0

        for document in queryset:
            try:
                # Проверяваме дали документът е в final approval статус
                if self._is_ready_for_conversion(document):

                    from .services.order_service import OrderService

                    result = OrderService.create_from_request(
                        request=document,
                        user=request.user,
                        order_notes=f"Converted via admin by {request.user.get_full_name() or request.user.username}"
                    )

                    if result['success']:
                        success_count += 1
                        order = result['order']
                        approval_info = " (needs approval)" if result.get(
                            'order_requires_approval') else " (auto-confirmed)"
                        messages.info(
                            request,
                            f"{document.document_number} → Order {order.document_number}{approval_info}"
                        )
                    else:
                        messages.error(request, f"Failed to convert {document.document_number}: {result['message']}")
                        failed_count += 1
                else:
                    messages.warning(
                        request,
                        f"{document.document_number}: Not ready for conversion (status: {document.status})"
                    )
                    failed_count += 1

            except Exception as e:
                messages.error(request, f"Error converting {document.document_number}: {str(e)}")
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully converted {success_count} requests to orders.')
        if failed_count:
            messages.warning(request, f'{failed_count} requests could not be converted.')

    convert_final_approved_action.short_description = _('Convert to orders (final approved)')

    def _is_ready_for_conversion(self, document):
        """
        ДИНАМИЧНО ОТКРИВАНЕ дали документът е готов за конверсия

        Логика: Документът е готов ако няма повече approval transitions
        (т.е. е достигнал final approval състояние)
        """
        if not document.document_type:
            return False

        # Вземаме next статуси от DocumentType
        next_statuses = document.get_next_statuses()

        if not next_statuses:
            # Няма повече статуси - може да е final
            return True

        # Проверяваме дали има 'converted' като възможен следващ статус
        if 'converted' in next_statuses:
            return True

        # Проверяваме дали всички останали статуси са негативни (rejected, cancelled)
        negative_statuses = {'rejected', 'cancelled', 'closed'}
        remaining_positive_statuses = [s for s in next_statuses if s not in negative_statuses]

        # Ако няма повече положителни статуси (само негативни), готов е за конверсия
        return len(remaining_positive_statuses) == 0

    # =====================
    # DISPLAY METHODS - ДИНАМИЧНИ
    # =====================

    def status_display(self, obj):
        """Динамично показване на статус без хардкодирани цветове"""
        # Базови цветове по тип статус
        status_lower = obj.status.lower()

        if 'draft' in status_lower:
            color = 'gray'
        elif 'submit' in status_lower or 'pending' in status_lower:
            color = 'orange'
        elif 'approv' in status_lower:
            color = 'green'
        elif 'reject' in status_lower or 'cancel' in status_lower:
            color = 'red'
        elif 'convert' in status_lower or 'completed' in status_lower:
            color = 'blue'
        else:
            color = 'black'

        # Показваме статуса както е дефиниран
        display_name = obj.status.replace('_', ' ').title()

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, display_name
        )

    status_display.short_description = _('Status')

    def workflow_status_display(self, obj):
        """Динамично показване на workflow статус"""
        try:
            available_transitions = ApprovalService.get_available_transitions(obj, None)

            # Проверяваме дали е в final статус
            if obj.document_type and obj.status in obj.document_type.final_statuses:
                return format_html('<span style="color: green;">✅ Final</span>')
            elif available_transitions:
                return format_html(
                    '<span style="color: orange;">⏳ {} actions</span>',
                    len(available_transitions)
                )
            else:
                return format_html('<span style="color: gray;">⏸️ No actions</span>')
        except:
            return '-'

    workflow_status_display.short_description = _('Workflow')

    # =====================
    # ДРУГИТЕ DISPLAY МЕТОДИ ОСТАВАТ СЪЩИТЕ
    # =====================

    def urgency_display(self, obj):
        """Urgency с икони"""
        urgency_icons = {
            'low': '🟢',
            'normal': '🔵',
            'high': '🟠',
            'critical': '🔴'
        }
        icon = urgency_icons.get(obj.urgency_level, '⚪')

        urgency_names = {
            'low': 'Low',
            'normal': 'Normal',
            'high': 'High',
            'critical': 'Critical'
        }
        urgency_name = urgency_names.get(obj.urgency_level, obj.urgency_level.title())

        return format_html('{} {}', icon, urgency_name)

    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        """Брой редове"""
        count = obj.lines.count()
        if count == 0:
            return format_html('<span style="color: red;">0</span>')
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def estimated_total(self, obj):
        """Приблизителна обща сума"""
        try:
            total = obj.get_estimated_total()
            if total > 0:
                return format_html('<strong>{:.2f} лв</strong>', float(total))
            else:
                return format_html('<span style="color: gray;">-</span>')
        except:
            return '-'

    estimated_total.short_description = _('Estimated Total')

    def request_analytics(self, obj):
        """Request analytics summary"""
        if not obj.pk:
            return "Save request first to see analytics"

        lines_count = obj.lines.count()
        total_items = sum(line.requested_quantity or 0 for line in obj.lines.all())
        estimated_total = obj.get_estimated_total()

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.status.replace('_', ' ').title()}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total Items:</strong> {total_items}",
            f"<strong>Estimated Total:</strong> {estimated_total:.2f} лв",
            f"<strong>Urgency:</strong> {obj.urgency_level.title()}",
        ]

        if obj.requested_by:
            analysis_parts.append(
                f"<strong>Requested By:</strong> {obj.requested_by.get_full_name() or obj.requested_by.username}")

        if obj.approved_by:
            analysis_parts.append(
                f"<strong>Approved By:</strong> {obj.approved_by.get_full_name() or obj.approved_by.username}")

        if obj.converted_to_order:
            analysis_parts.append(f"<strong>Order:</strong> {obj.converted_to_order.document_number}")

        # Показваме и workflow информация
        if obj.document_type:
            next_statuses = obj.get_next_statuses()
            if next_statuses:
                analysis_parts.append(f"<strong>Next Statuses:</strong> {', '.join(next_statuses)}")

        return mark_safe('<br>'.join(analysis_parts))

    request_analytics.short_description = _('Analytics')

# =================================================================
# PURCHASE ORDER ADMIN - ОБНОВЕН
# =================================================================

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(DynamicApprovalMixin, admin.ModelAdmin):
    """Purchase Order Admin с ApprovalService интеграция"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'is_urgent', 'lines_count', 'grand_total_display',
        'expected_delivery_date', 'source_request_display'
    ]

    list_filter = [
        'status', 'is_urgent', 'supplier', 'location',
        'expected_delivery_date', 'order_method'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'notes',
        'source_request__document_number'
    ]

    date_hierarchy = 'expected_delivery_date'
    inlines = [PurchaseOrderLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'source_request', 'order_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'is_urgent', 'order_method'
            )
        }),
        (_('Dates'), {
            'fields': (
                'document_date', 'expected_delivery_date'
            )
        }),
        (_('Source Information'), {
            'fields': ('source_request',),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('order_analytics',),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        """Status display с цветове"""
        status_colors = {
            'draft': 'gray',
            'pending_approval': 'orange',
            'approved': 'lightgreen',
            'confirmed': 'green',
            'sent': 'blue',
            'supplier_confirmed': 'darkgreen',
            'completed': 'purple',
            'cancelled': 'red'
        }
        color = status_colors.get(obj.status, 'black')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.status.replace('_', ' ').title()
        )

    status_display.short_description = _('Status')

    def lines_count(self, obj):
        """Брой редове"""
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def grand_total_display(self, obj):
        """Обща сума"""
        try:
            total = obj.get_estimated_total()
            return format_html('<strong>{:.2f} лв</strong>', float(total))
        except:
            return '-'

    grand_total_display.short_description = _('Total')

    def source_request_display(self, obj):
        """Source request link"""
        if obj.source_request:
            return format_html(
                '<a href="/admin/purchases/purchaserequest/{}/change/">{}</a>',
                obj.source_request.pk,
                obj.source_request.document_number
            )
        return '-'

    source_request_display.short_description = _('Source Request')

    def order_analytics(self, obj):
        """Order analytics"""
        if not obj.pk:
            return "Save order first to see analytics"

        lines_count = obj.lines.count()
        total = obj.get_estimated_total()

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.status.replace('_', ' ').title()}",
            f"<strong>Lines:</strong> {lines_count}",
            f"<strong>Total:</strong> {total:.2f} лв",
        ]

        if obj.source_request:
            analysis_parts.append(f"<strong>From Request:</strong> {obj.source_request.document_number}")

        if obj.is_urgent:
            analysis_parts.append("<strong>🔥 URGENT ORDER</strong>")

        return mark_safe('<br>'.join(analysis_parts))

    order_analytics.short_description = _('Analytics')


# =================================================================
# DELIVERY ADMIN - ОБНОВЕН
# =================================================================


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(DynamicApprovalMixin, admin.ModelAdmin):
    """Delivery Receipt Admin - ФИКСИРАН"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'lines_count', 'delivery_date', 'quality_status_display',
        'variance_status_display'
    ]

    list_filter = [
        'status', 'supplier', 'location', 'delivery_date',
        'has_quality_issues', 'has_variances', 'quality_checked'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'driver_name', 'vehicle_info'
    ]

    date_hierarchy = 'delivery_date'
    inlines = [DeliveryLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'received_at', 'processed_at', 'delivery_analytics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'delivery_date', 'creation_type'
            )
        }),
        (_('Delivery Details'), {
            'fields': (
                'driver_name', 'vehicle_info', 'external_delivery_reference'
            )
        }),
        (_('Quality Control'), {
            'fields': (
                'quality_checked', 'quality_approved', 'has_quality_issues',
                'quality_notes', 'quality_inspector'
            ),
            'classes': ('collapse',)
        }),
        (_('Variances'), {
            'fields': (
                'has_variances', 'variance_notes'
            ),
            'classes': ('collapse',)
        }),
        (_('Processing'), {
            'fields': (
                'received_by', 'received_at', 'processed_by', 'processed_at'
            ),
            'classes': ('collapse',)
        }),
        (_('Analytics'), {
            'fields': ('delivery_analytics',),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        """Status с цветове"""
        status_colors = {
            'draft': 'gray',
            'delivered': 'orange',
            'received': 'blue',
            'processed': 'green',
            'completed': 'darkgreen',
            'cancelled': 'red'
        }
        color = status_colors.get(obj.status, 'black')

        status_names = {
            'draft': 'Draft',
            'delivered': 'Delivered',
            'received': 'Received',
            'processed': 'Processed',
            'completed': 'Completed',
            'cancelled': 'Cancelled'
        }
        status_name = status_names.get(obj.status, obj.status.title())

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, status_name
        )

    status_display.short_description = _('Status')

    def lines_count(self, obj):
        """Брой редове"""
        count = obj.lines.count()
        return format_html('<strong>{}</strong>', count)

    lines_count.short_description = _('Lines')

    def quality_status_display(self, obj):
        """Quality control status"""
        if not obj.quality_checked:
            return format_html('<span style="color: gray;">⏳ Not Checked</span>')
        elif obj.has_quality_issues:
            return format_html('<span style="color: red;">❌ Issues Found</span>')
        else:
            return format_html('<span style="color: green;">✅ Approved</span>')

    quality_status_display.short_description = _('Quality')

    def variance_status_display(self, obj):
        """Variance status"""
        if obj.has_variances:
            return format_html('<span style="color: orange;">⚠️ Variances</span>')
        else:
            return format_html('<span style="color: green;">✅ No Variances</span>')

    variance_status_display.short_description = _('Variances')

    def delivery_analytics(self, obj):
        """Delivery analytics"""
        if not obj.pk:
            return "Save delivery first to see analytics"

        lines_count = obj.lines.count()

        analysis_parts = [
            f"<strong>Document:</strong> {obj.document_number}",
            f"<strong>Status:</strong> {obj.status.title()}",
            f"<strong>Lines:</strong> {lines_count}",
        ]

        if obj.delivery_date:
            analysis_parts.append(f"<strong>Delivery Date:</strong> {obj.delivery_date}")

        if obj.driver_name:
            analysis_parts.append(f"<strong>Driver:</strong> {obj.driver_name}")

        if obj.has_quality_issues:
            analysis_parts.append("<strong>🚨 Quality Issues</strong>")

        if obj.has_variances:
            analysis_parts.append("<strong>⚠️ Variances Found</strong>")

        # Check if this affects inventory
        if obj.document_type and obj.document_type.affects_inventory:
            timing = obj.document_type.inventory_timing
            analysis_parts.append(f"<strong>Inventory:</strong> {timing}")

        return mark_safe('<br>'.join(analysis_parts))

    delivery_analytics.short_description = _('Analytics')

    # =====================
    # CUSTOM ACTIONS
    # =====================

    def get_actions(self, request):
        """
        ДИНАМИЧНО генериране на actions на база ApprovalService

        РЕШЕНИЕ 1: Просто присвояване на методите
        """
        actions = super().get_actions(request)

        # Просто присвояваме методите - Django ще се погрижи за параметрите
        actions['submit_for_approval'] = self.submit_for_approval_action
        actions['smart_workflow'] = self.smart_workflow_action
        actions['convert_final_approved'] = self.convert_final_approved_action

        return actions

    def mark_as_delivered_action(self, request, queryset):
        """Mark deliveries as delivered"""
        success_count = 0
        failed_count = 0

        for delivery in queryset.filter(status='draft'):
            try:
                delivery.mark_as_delivered(request.user)
                success_count += 1
            except Exception as e:
                messages.error(request, f"Failed to mark {delivery.document_number} as delivered: {str(e)}")
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully marked {success_count} deliveries as delivered.')
        if failed_count:
            messages.warning(request, f'{failed_count} deliveries could not be marked as delivered.')

    mark_as_delivered_action.short_description = _('Mark as delivered')

    def receive_deliveries_action(self, request, queryset):
        """Receive deliveries"""
        success_count = 0
        failed_count = 0

        for delivery in queryset.filter(status='delivered'):
            try:
                delivery.receive_delivery(request.user, quality_check=True)
                success_count += 1
            except Exception as e:
                messages.error(request, f"Failed to receive {delivery.document_number}: {str(e)}")
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully received {success_count} deliveries.')
        if failed_count:
            messages.warning(request, f'{failed_count} deliveries could not be received.')

    receive_deliveries_action.short_description = _('Receive deliveries')

    def complete_processing_action(self, request, queryset):
        """Complete delivery processing"""
        success_count = 0
        failed_count = 0

        for delivery in queryset.filter(status__in=['received', 'processed']):
            try:
                delivery.complete_processing(request.user)
                success_count += 1
            except Exception as e:
                messages.error(request, f"Failed to complete {delivery.document_number}: {str(e)}")
                failed_count += 1

        if success_count:
            messages.success(request, f'Successfully completed {success_count} deliveries.')
        if failed_count:
            messages.warning(request, f'{failed_count} deliveries could not be completed.')

    complete_processing_action.short_description = _('Complete processing')