# purchases/admin.py - FIXED ADMIN CONFIGURATION

import logging
from decimal import Decimal
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count
from django.utils import timezone

from .models.requests import PurchaseRequest, PurchaseRequestLine

logger = logging.getLogger(__name__)


# =================================================================
# PURCHASE REQUEST LINE INLINE - ✅ FIXED DUPLICATE FIELDS
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1


    fields = [
        'line_number', 'product', 'requested_quantity', 'unit',
        'entered_price',  # ✅ ONLY ONE PRICE FIELD
        ('unit_price', 'vat_rate'),  # Calculated prices
        ('discount_percent', 'discount_amount'),  # Discounts
        ('net_amount', 'vat_amount', 'gross_amount'),  # Totals
        'suggested_supplier', 'priority'
    ]

    readonly_fields = [
        'line_number', 'unit_price', 'vat_rate', 'discount_amount',
        'net_amount', 'vat_amount', 'gross_amount'
    ]

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


# =================================================================
# PURCHASE REQUEST ADMIN - ✅ SAME AS BEFORE, NO CHANGES NEEDED
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Purchase Request Admin с пълни VAT изчисления"""

    list_display = [
        'document_number', 'supplier', 'location', 'status_display',
        'urgency_display', 'lines_count', 'estimated_total_display',
        'calculated_total_display', 'vat_setting_display', 'requested_by', 'created_at'
    ]

    list_filter = [
        'status', 'urgency_level', 'location', 'supplier',
        'prices_entered_with_vat', 'created_at', 'requested_by'
    ]

    search_fields = [
        'document_number', 'supplier__name', 'requested_by__username',
        'notes', 'external_reference'
    ]

    date_hierarchy = 'created_at'
    inlines = [PurchaseRequestLineInline]

    readonly_fields = [
        'document_number', 'created_at', 'updated_at',
        'complete_financial_summary'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'document_number', 'supplier', 'location', 'status',
                'urgency_level'
            )
        }),
        (_('Request Details'), {
            'fields': (
                'document_date', 'external_reference', 'requested_by',
                'approved_by', 'approved_at'
            )
        }),
        (_('VAT Settings'), {
            'fields': (
                'prices_entered_with_vat',
            ),
            'description': 'VAT calculation settings. Leave empty to use location defaults.'
        }),
        (_('Document Totals'), {
            'fields': (
                'subtotal', 'discount_total', 'vat_total', 'total'
            ),
            'classes': ('collapse',),
            'description': 'Calculated from lines. Use admin actions to recalculate.'
        }),
        (_('Complete Financial Summary'), {
            'fields': ('complete_financial_summary',),
            'classes': ('collapse',)
        }),
        (_('Notes'), {
            'fields': ('notes',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )



    # All display methods remain the same...
    def status_display(self, obj):
        colors = {
            'draft': '#6c757d',
            'pending': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'converted': '#17a2b8',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status
        )
    status_display.short_description = _('Status')

    def urgency_display(self, obj):
        icons = {
            'low': '🔵',
            'normal': '🟢',
            'high': '🟡',
            'urgent': '🔴',
        }
        icon = icons.get(obj.urgency_level, '⚫')
        return format_html(
            '{} {}',
            icon,
            obj.get_urgency_level_display() if hasattr(obj, 'get_urgency_level_display') else obj.urgency_level
        )
    urgency_display.short_description = _('Urgency')

    def lines_count(self, obj):
        return obj.lines.count()
    lines_count.short_description = _('Lines')

    def estimated_total_display(self, obj):
        """✅ FIXED: Use entered_price consistently"""
        if not obj.pk:
            return "—"

        total = sum(
            (line.entered_price or 0) * (line.requested_quantity or 0)
            for line in obj.lines.all()
        )

        return format_html(
            '<span style="color: #6c757d;">{} лв</span>',
            "{:.2f}".format(float(total))
        )
    estimated_total_display.short_description = _('Est. Total')

    def calculated_total_display(self, obj):
        if not obj.pk:
            return "—"

        lines_with_calc = obj.lines.exclude(gross_amount=0)
        if not lines_with_calc.exists():
            return format_html('<em style="color: #999;">Not calculated</em>')

        totals = lines_with_calc.aggregate(
            net_total=Sum('net_amount'),
            vat_total=Sum('vat_amount'),
            gross_total=Sum('gross_amount')
        )

        net = totals['net_total'] or 0
        vat = totals['vat_total'] or 0
        gross = totals['gross_total'] or 0

        return format_html(
            '<div><strong style="color: #28a745;">{} лв</strong></div>'
            '<small style="color: #6c757d;">Net: {} | VAT: {}</small>',
            "{:.2f}".format(float(gross)),
            "{:.2f}".format(float(net)),
            "{:.2f}".format(float(vat))
        )
    calculated_total_display.short_description = _('Calc. Total')

    def vat_setting_display(self, obj):
        if obj.prices_entered_with_vat is None:
            if hasattr(obj.location, 'purchase_prices_include_vat'):
                setting = obj.location.purchase_prices_include_vat
                source = "Location"
            else:
                setting = False
                source = "System"

            return format_html(
                '<span style="color: #6c757d;">{} ({})</span>',
                "With VAT" if setting else "Without VAT",
                source
            )
        else:
            return format_html(
                '<strong style="color: #007bff;">{} (Document)</strong>',
                "With VAT" if obj.prices_entered_with_vat else "Without VAT"
            )
    vat_setting_display.short_description = _('VAT Mode')

    def complete_financial_summary(self, obj):
        if not obj.pk:
            return "Save request first to see financial summary"

        lines = obj.lines.all()
        lines_count = lines.count()

        if not lines_count:
            return "No lines added yet"

        # ✅ FIXED: Use entered_price consistently
        estimated_total = sum(
            (line.entered_price or 0) * (line.requested_quantity or 0)
            for line in lines
        )

        calculated_lines = lines.exclude(gross_amount=0)
        calculated_count = calculated_lines.count()

        vat_mode = "Not specified (uses location/system default)"
        if obj.prices_entered_with_vat is not None:
            vat_mode = "Prices INCLUDE VAT" if obj.prices_entered_with_vat else "Prices EXCLUDE VAT"

        summary_parts = [
            "<strong>🏷️ VAT Settings</strong>",
            "• VAT Mode: {}".format(vat_mode),
            "",
            "<strong>📊 Lines Summary</strong>",
            "• Total Lines: {}".format(lines_count),
            "• Calculated Lines: {}".format(calculated_count),
            "• Estimated Total: {:.2f} лв".format(estimated_total),
        ]

        if calculated_count > 0:
            totals = calculated_lines.aggregate(
                subtotal=Sum('net_amount'),
                discount_total=Sum('discount_amount'),
                vat_total=Sum('vat_amount'),
                gross_total=Sum('gross_amount')
            )

            subtotal = totals['subtotal'] or 0
            discount_total = totals['discount_total'] or 0
            vat_total = totals['vat_total'] or 0
            gross_total = totals['gross_total'] or 0

            summary_parts.extend([
                "",
                "<strong>💰 Calculated Totals</strong>",
                "• Subtotal (before discounts): {:.2f} лв".format(subtotal + discount_total),
                "• Discount Total: {:.2f} лв".format(discount_total),
                "• Net Amount (after discounts): {:.2f} лв".format(subtotal),
                "• VAT Amount: {:.2f} лв".format(vat_total),
                "• <strong>Gross Total (with VAT): {:.2f} лв</strong>".format(gross_total),
            ])

        return format_html("<br>".join(summary_parts))
    complete_financial_summary.short_description = _('Complete Financial Summary')

    # Actions
    actions = [
        'calculate_all_lines', 'recalculate_document_totals',
        'toggle_vat_mode', 'reset_vat_calculations'
    ]

    def calculate_all_lines(self, request, queryset):
        """✅ FIXED: Use entered_price consistently"""
        total_lines = 0
        calculated_lines = 0
        errors = []

        for req in queryset:
            for line in req.lines.all():
                # ✅ FIXED: Use entered_price consistently
                # Трябва да е:
                if line.entered_price is not None and line.requested_quantity:
                    try:
                        from nomenclatures.services.vat_calculation_service import VATCalculationService

                        calc_result = VATCalculationService.calculate_line_totals(
                            line=line,
                            entered_price=line.entered_price,
                            quantity=line.requested_quantity,
                            document=line.document
                        )

                        # Apply ALL results
                        line.unit_price = calc_result['unit_price']
                        line.vat_rate = calc_result['vat_rate']
                        line.vat_amount = calc_result['vat_amount']
                        line.discount_amount = calc_result.get('discount_amount', Decimal('0'))
                        line.net_amount = calc_result['net_amount']
                        line.gross_amount = calc_result['gross_amount']
                        line.save()

                        calculated_lines += 1

                    except Exception as e:
                        errors.append("Line {}: {}".format(line.pk, str(e)))

                total_lines += 1

        if calculated_lines:
            self.message_user(
                request,
                "✅ Calculated VAT for {}/{} lines.".format(calculated_lines, total_lines),
                level='SUCCESS'
            )
        if errors:
            for error in errors[:5]:
                self.message_user(request, "❌ Error: {}".format(error), level='ERROR')

    calculate_all_lines.short_description = _('Calculate VAT for all lines')

    def recalculate_document_totals(self, request, queryset):
        count = 0
        for req in queryset:
            try:
                from nomenclatures.services.vat_calculation_service import VATCalculationService
                totals = VATCalculationService.recalculate_document_totals(req)

                if hasattr(req, 'subtotal'):
                    req.subtotal = totals['subtotal']
                if hasattr(req, 'vat_total'):
                    req.vat_total = totals['vat_total']
                if hasattr(req, 'discount_total'):
                    req.discount_total = totals['discount_total']
                if hasattr(req, 'total'):
                    req.total = totals['total']

                req.save()
                count += 1

            except Exception as e:
                self.message_user(
                    request,
                    "❌ Error recalculating {}: {}".format(req.document_number, str(e)),
                    level='ERROR'
                )

        if count:
            self.message_user(
                request,
                "✅ Recalculated totals for {} requests.".format(count),
                level='SUCCESS'
            )

    recalculate_document_totals.short_description = _('Recalculate document totals')

    def toggle_vat_mode(self, request, queryset):
        count = 0
        for req in queryset:
            if req.prices_entered_with_vat is None:
                req.prices_entered_with_vat = True
            else:
                req.prices_entered_with_vat = not req.prices_entered_with_vat
            req.save()
            count += 1

        self.message_user(
            request,
            "🔄 Toggled VAT mode for {} requests. Recalculate lines to apply changes.".format(count),
            level='SUCCESS'
        )

    toggle_vat_mode.short_description = _('Toggle VAT mode')

    def reset_vat_calculations(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "❌ Only superusers can reset calculations.", level='ERROR')
            return

        total_lines = 0
        for req in queryset:
            for line in req.lines.all():
                line.unit_price = Decimal('0.00')
                line.vat_rate = Decimal('0.20')
                line.vat_amount = Decimal('0.00')
                line.discount_amount = Decimal('0.00')
                line.net_amount = Decimal('0.00')
                line.gross_amount = Decimal('0.00')
                line.save()
                total_lines += 1

        self.message_user(
            request,
            "🔄 Reset calculations for {} lines.".format(total_lines),
            level='SUCCESS'
        )

    reset_vat_calculations.short_description = _('Reset VAT calculations (Superuser only)')


# =================================================================
# PURCHASE REQUEST LINE STANDALONE ADMIN - ✅ FIXED FIELDSETS
# =================================================================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    """✅ FIXED: Remove duplicate fields from fieldsets"""

    list_display = [
        'document', 'line_number', 'product', 'requested_quantity',
        'entered_price', 'unit_price', 'vat_amount', 'gross_amount',
        'priority_display'
    ]

    list_filter = [
        'document__status', 'priority', 'suggested_supplier',
        'vat_rate'
    ]

    search_fields = [
        'product__code', 'product__name', 'document__document_number'
    ]

    readonly_fields = [
        'unit_price', 'vat_rate', 'discount_amount',
        'net_amount', 'vat_amount', 'gross_amount'
    ]

    # ✅ FIXED: Remove duplicate fields from fieldsets
    fieldsets = (
        (_('Document & Product'), {
            'fields': ('document', 'line_number', 'product', 'unit')
        }),
        (_('Quantities & Pricing'), {
            'fields': (
                'requested_quantity', 'entered_price'  # ✅ FIXED: Only entered_price
            )
        }),
        (_('VAT Calculations'), {
            'fields': (
                'unit_price', 'vat_rate', 'discount_percent', 'discount_amount',
                'net_amount', 'vat_amount', 'gross_amount'
            ),
            'classes': ('collapse',)
        }),
        (_('Additional Info'), {
            'fields': (
                'suggested_supplier', 'priority', 'item_justification'
            ),
            'classes': ('collapse',)
        }),
    )

    def priority_display(self, obj):
        if obj.priority > 0:
            return format_html('<span style="color: #F44336;">🔥 {}</span>', obj.priority)
        return '—'
    priority_display.short_description = _('Priority')

    actions = ['calculate_vat_for_lines']

    def calculate_vat_for_lines(self, request, queryset):
        """✅ FIXED: Use entered_price consistently"""
        calculated = 0
        errors = []

        for line in queryset:
            # Трябва да е:
            if line.entered_price is not None and line.requested_quantity:
                try:
                    from nomenclatures.services.vat_calculation_service import VATCalculationService

                    calc_result = VATCalculationService.calculate_line_totals(
                        line=line,
                        entered_price=line.entered_price,  # ✅ FIXED
                        quantity=line.requested_quantity,
                        document=line.document
                    )

                    # Apply results
                    for field, value in calc_result.items():
                        if (hasattr(line, field) and
                                field not in ['calculation_reason', 'vat_applicable', 'prices_include_vat']):
                            setattr(line, field, value)

                    line.save()
                    calculated += 1

                except Exception as e:
                    errors.append("Line {}: {}".format(line.pk, str(e)))

        if calculated:
            self.message_user(request, "✅ Calculated {} lines".format(calculated))
        if errors:
            for error in errors[:3]:
                self.message_user(request, "❌ {}".format(error), level='ERROR')

    calculate_vat_for_lines.short_description = _('Calculate VAT for selected lines')