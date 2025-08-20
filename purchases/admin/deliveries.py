# ===================================================================
# ПОПРАВКА НА STRING FORMATTING: purchases/admin/deliveries.py
# ===================================================================

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import DeliveryReceipt, DeliveryLine


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = (
        'line_number',
        'product',
        'quantity',  # ✅ FIXED: беше 'received_quantity'
        'unit',
        'unit_price',
        'get_expected_quantity',
        'get_variance_quantity',
        'get_source_info',  # ✅ DEBUG INFO
        'batch_number',
        'expiry_date',
        'quality_approved',
        'quality_issue_type'
    )

    readonly_fields = (
        'get_expected_quantity',
        'get_variance_quantity',
        'get_source_info'  # ✅ DEBUG INFO
    )

    @admin.display(description='Expected')
    def get_expected_quantity(self, obj):
        """Expected quantity from source order line - FIXED FORMATTING"""
        if not obj:
            return "No obj"

        if not obj.pk:
            return "Not saved"

        try:
            if obj.source_order_line:
                expected = obj.source_order_line.ordered_quantity
                return "{:.3f}".format(expected)  # ✅ FIXED: старо formatting
            else:
                return "No source"
        except Exception as e:
            return "Error: {}".format(str(e)[:20])  # ✅ FIXED

    @admin.display(description='Variance')
    def get_variance_quantity(self, obj):
        """Variance calculation - FIXED FORMATTING"""
        if not obj or not obj.pk:
            return "Not saved"

        try:
            if not obj.source_order_line:
                return "No source"

            if not obj.quantity:
                return "No quantity"

            expected = obj.source_order_line.ordered_quantity or 0
            received = obj.quantity or 0
            variance = received - expected

            # Color coding - FIXED FORMATTING
            if variance > 0:
                return format_html(
                    '<span style="color: green; font-weight: bold;">+{}</span>',
                    "{:.3f}".format(variance)  # ✅ FIXED
                )
            elif variance < 0:
                return format_html(
                    '<span style="color: red; font-weight: bold;">{}</span>',
                    "{:.3f}".format(variance)  # ✅ FIXED
                )
            else:
                return format_html(
                    '<span style="color: black;">0.000</span>'
                )

        except Exception as e:
            return "Error: {}".format(str(e)[:20])  # ✅ FIXED

    @admin.display(description='Source Info')
    def get_source_info(self, obj):
        """Debug info за source order line връзката - FIXED FORMATTING"""
        if not obj or not obj.pk:
            return "Not saved"

        try:
            if obj.source_order_line:
                return format_html(
                    '<small>Order: {}<br>Line: {}<br>Qty: {}</small>',
                    obj.source_order_line.document.document_number[:15],
                    obj.source_order_line.line_number,
                    "{:.3f}".format(obj.source_order_line.ordered_quantity)  # ✅ FIXED
                )
            else:
                return format_html('<small style="color: red;">No source link</small>')
        except Exception as e:
            return format_html('<small style="color: red;">Error: {}</small>', str(e)[:30])


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = (
        'document_number', 'supplier', 'delivery_date', 'status',
        'get_source_order_info', 'total'
    )
    list_filter = ('status', 'quality_status', 'supplier', 'location', 'delivery_date')
    search_fields = ('document_number', 'supplier__name', 'supplier_delivery_reference')
    readonly_fields = (
        'document_number', 'status', 'created_by', 'created_at',
        'updated_by', 'updated_at', 'source_order', 'quality_checked_by', 'quality_checked_at'
    )

    inlines = [DeliveryLineInline]
    actions = [
        'process_quality_control_action',
        'create_movements_action',
        'debug_source_links_action'
    ]

    @admin.display(description='Source Order')
    def get_source_order_info(self, obj):
        """Show source order info - FIXED FORMATTING"""
        if obj.source_order:
            return format_html(
                '<a href="/admin/purchases/purchaseorder/{}/change/" target="_blank">{}</a>',
                obj.source_order.pk,
                obj.source_order.document_number
            )
        return format_html('<span style="color: red;">No source</span>')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        if instances and hasattr(instances[0].document, 'recalculate_totals'):
            document = instances[0].document
            document.recalculate_totals()
        super().save_formset(request, form, formset, change)

    # --- ADMIN ACTIONS ---
    @admin.action(description='🔍 Debug Source Links')
    def debug_source_links_action(self, request, queryset):
        """Debug action за проверка на source links"""
        for delivery in queryset:
            lines_info = []
            for line in delivery.lines.all():
                source_info = "No source"
                if line.source_order_line:
                    source_info = "Order: {}, Line: {}".format(
                        line.source_order_line.document.document_number,
                        line.source_order_line.line_number
                    )

                lines_info.append("Line {}: {}".format(line.line_number, source_info))

            message = "📋 {}:\n{}".format(delivery.document_number, "\n".join(lines_info))
            self.message_user(request, message, messages.INFO)

    @admin.action(description='✅ Process Quality Control (Approve All)')
    def process_quality_control_action(self, request, queryset):
        for delivery in queryset:
            try:
                lines_updated = 0
                for line in delivery.lines.all():
                    if line.quality_approved is None:
                        line.quality_approved = True
                        line.quality_checked_by = request.user
                        line.quality_checked_at = timezone.now()
                        line.save()
                        lines_updated += 1

                delivery.quality_status = 'approved'
                delivery.quality_checked_by = request.user
                delivery.quality_checked_at = timezone.now()
                delivery.save()

                self.message_user(
                    request,
                    "✅ Approved {} lines in {}".format(lines_updated, delivery.document_number),
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    "❌ Error processing {}: {}".format(delivery.document_number, e),
                    messages.ERROR
                )

    @admin.action(description='📦 Create Inventory Movements')
    def create_movements_action(self, request, queryset):
        for delivery in queryset:
            try:
                self.message_user(
                    request,
                    "📦 Would create movements for {}".format(delivery.document_number),
                    messages.INFO
                )
            except Exception as e:
                self.message_user(
                    request,
                    "❌ Error: {}".format(e),
                    messages.ERROR
                )


# ===================================================================
# АЛТЕРНАТИВА: По-опростена версия без debug info
# ===================================================================

class SimpleDeliveryLineInline(admin.TabularInline):
    """Опростена версия без debug информация"""
    model = DeliveryLine
    extra = 1
    fields = (
        'line_number',
        'product',
        'quantity',  # ✅ FIXED field name
        'unit',
        'unit_price',
        'get_line_total',  # Показвай line total вместо variance
        'batch_number',
        'expiry_date',
        'quality_approved',
        'quality_issue_type'
    )

    readonly_fields = ('get_line_total',)

    @admin.display(description='Line Total')
    def get_line_total(self, obj):
        """Simple line total calculation"""
        if obj and obj.quantity and obj.unit_price:
            total = obj.quantity * obj.unit_price
            return "{:.2f}".format(total)  # ✅ Safe formatting
        return "0.00"


# ===================================================================
# DJANGO VERSION COMPATIBILITY
# ===================================================================

"""
Проблемът с f-string може да е от:
1. Стара версия на Python (< 3.6)
2. Грешен синтаксис в format_html()

РЕШЕНИЕТО:
Използвай .format() вместо f-strings в admin методи:

ВМЕСТО:
    return f"{value:.3f}"

ИЗПОЛЗВАЙ:
    return "{:.3f}".format(value)

ВМЕСТО:
    return f"Error: {str(e)}"

ИЗПОЛЗВАЙ:
    return "Error: {}".format(str(e))
"""

# ===================================================================
# ТЕСТ НА ПОПРАВКАТА
# ===================================================================

"""
След тази поправка:

1. "Unknown format code 'f'" грешката трябва да изчезне
2. Expected колоната трябва да показва числа или "No source"
3. Variance колоната трябва да показва цветни разлики или "No source"

Ако все още има проблеми:
1. Използвай SimpleDeliveryLineInline вместо сложната версия
2. Провери Python версията: python --version
3. Провери Django версията: python manage.py --version
"""