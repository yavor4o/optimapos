# purchases/admin/lines.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.db import models

from ..models import PurchaseDocumentLine
from ..services import LineService


@admin.register(PurchaseDocumentLine)
class PurchaseDocumentLineAdmin(admin.ModelAdmin):
    """Admin за PurchaseDocumentLine"""

    list_display = [
        'document_link', 'line_number', 'product_link', 'quantity_display',
        'unit_price_display', 'line_total_display', 'variance_badge',
        'quality_badge', 'expiry_status'
    ]

    list_filter = [
        'document__status', 'document__supplier', 'document__location',
        'quality_approved', 'unit', 'document__delivery_date'
    ]

    search_fields = [
        'document__document_number', 'product__code', 'product__name',
        'batch_number'
    ]

    date_hierarchy = 'document__delivery_date'

    ordering = ['-document__delivery_date', 'document', 'line_number']

    fieldsets = (
        (_('Document & Product'), {
            'fields': ('document', 'line_number', 'product', 'unit')
        }),
        (_('Quantities'), {
            'fields': ('quantity', 'received_quantity', 'quantity_base_unit')
        }),
        (_('Pricing'), {
            'fields': ('unit_price', 'discount_percent', 'final_unit_price', 'line_total'),
            'classes': ('collapse',)
        }),
        (_('Pricing Analysis'), {
            'fields': ('old_sale_price', 'new_sale_price', 'markup_percentage'),
            'classes': ('collapse',)
        }),
        (_('Batch & Quality'), {
            'fields': ('batch_number', 'expiry_date', 'quality_approved', 'quality_notes')
        })
    )

    readonly_fields = [
        'quantity_base_unit', 'final_unit_price', 'line_total'
    ]

    # Custom display methods
    def document_link(self, obj):
        """Линк към документа"""
        if obj.document:
            url = f"/admin/purchases/purchasedocument/{obj.document.id}/change/"
            return format_html(
                '<a href="{}">{}</a>',
                url, obj.document.document_number
            )
        return "-"

    document_link.short_description = _('Document')
    document_link.admin_order_field = 'document__document_number'

    def product_link(self, obj):
        """Линк към продукта"""
        if obj.product:
            url = f"/admin/products/product/{obj.product.id}/change/"
            return format_html(
                '<a href="{}">{}</a><br><small>{}</small>',
                url, obj.product.code, obj.product.name[:30]
            )
        return "-"

    product_link.short_description = _('Product')
    product_link.admin_order_field = 'product__code'

    def quantity_display(self, obj):
        """Форматирано количество"""
        unit_name = obj.unit.code if obj.unit else ''

        if obj.received_quantity != obj.quantity:
            return format_html(
                'Order: <strong>{:.2f}</strong> {}<br>'
                'Received: <strong style="color: {};">{:.2f}</strong> {}',
                obj.quantity, unit_name,
                '#198754' if obj.received_quantity >= obj.quantity else '#DC3545',
                obj.received_quantity, unit_name
            )
        else:
            return f"{obj.quantity:.2f} {unit_name}"

    quantity_display.short_description = _('Quantity')

    def unit_price_display(self, obj):
        """Форматирана цена"""
        if obj.discount_percent > 0:
            return format_html(
                '<del>{:.4f}</del><br>'
                '<strong>{:.4f} лв</strong><br>'
                '<small style="color: #198754;">-{:.1f}%</small>',
                obj.unit_price, obj.final_unit_price, obj.discount_percent
            )
        else:
            return f"{obj.unit_price:.4f} лв"

    unit_price_display.short_description = _('Unit Price')

    def line_total_display(self, obj):
        """Форматирана обща сума"""
        return f"{obj.line_total:.2f} лв"

    line_total_display.short_description = _('Line Total')
    line_total_display.admin_order_field = 'line_total'

    def variance_badge(self, obj):
        """Badge за варианси"""
        if obj.received_quantity == obj.quantity:
            return format_html(
                '<span style="background-color: #198754; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">EXACT</span>'
            )
        elif obj.received_quantity > obj.quantity:
            variance = ((obj.received_quantity - obj.quantity) / obj.quantity) * 100
            return format_html(
                '<span style="background-color: #FFC107; color: black; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">+{:.1f}%</span>',
                variance
            )
        else:
            variance = ((obj.quantity - obj.received_quantity) / obj.quantity) * 100
            return format_html(
                '<span style="background-color: #DC3545; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">-{:.1f}%</span>',
                variance
            )

    variance_badge.short_description = _('Variance')

    def quality_badge(self, obj):
        """Badge за качество"""
        if obj.quality_approved:
            return format_html(
                '<span style="background-color: #198754; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">OK</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #DC3545; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">ISSUE</span>'
            )

    quality_badge.short_description = _('Quality')

    def expiry_status(self, obj):
        """Статус на срок на годност"""
        if not obj.expiry_date:
            return format_html(
                '<span style="color: #6C757D; font-size: 11px;">No Expiry</span>'
            )

        from django.utils import timezone
        today = timezone.now().date()
        days_to_expiry = (obj.expiry_date - today).days

        if days_to_expiry < 0:
            return format_html(
                '<span style="background-color: #DC3545; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">EXPIRED</span>'
            )
        elif days_to_expiry <= 7:
            return format_html(
                '<span style="background-color: #FFC107; color: black; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">{} days</span>',
                days_to_expiry
            )
        elif days_to_expiry <= 30:
            return format_html(
                '<span style="background-color: #FD7E14; color: white; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">{} days</span>',
                days_to_expiry
            )
        else:
            return format_html(
                '<span style="color: #198754; font-size: 11px;">{} days</span>',
                days_to_expiry
            )

    expiry_status.short_description = _('Expiry')

    def pricing_analysis(self, obj):
        """Pricing анализ"""
        if not obj.pk:
            return "Save first to see analysis"

        suggestions = LineService.calculate_pricing_suggestions(obj)

        parts = [
            f"<strong>Cost:</strong> {obj.unit_price:.4f} лв",
        ]

        if obj.old_sale_price:
            current_markup = ((obj.old_sale_price - obj.unit_price) / obj.unit_price) * 100
            parts.append(f"<strong>Current Price:</strong> {obj.old_sale_price:.4f} лв")
            parts.append(f"<strong>Current Markup:</strong> {current_markup:.1f}%")

        if obj.new_sale_price:
            parts.append(f"<strong>Suggested Price:</strong> {obj.new_sale_price:.4f} лв")
            parts.append(f"<strong>Suggested Markup:</strong> {obj.markup_percentage:.1f}%")

        return mark_safe('<br>'.join(parts))

    pricing_analysis.short_description = _('Pricing Analysis')

    # Actions
    actions = [
        'mark_quality_approved', 'mark_quality_issues', 'apply_suggested_pricing',
        'recalculate_line_totals', 'create_quality_reports'
    ]

    def mark_quality_approved(self, request, queryset):
        """Маркиране като качествено одобрени"""
        count = queryset.update(quality_approved=True)
        self.message_user(request, f'Marked {count} lines as quality approved')

    mark_quality_approved.short_description = _('Mark as quality approved')

    def mark_quality_issues(self, request, queryset):
        """Маркиране с качествени проблеми"""
        for line in queryset:
            LineService.create_quality_issue(
                line,
                "Quality issue marked from admin",
                severity="MEDIUM"
            )
        self.message_user(request, f'Marked {queryset.count()} lines with quality issues')

    mark_quality_issues.short_description = _('Mark quality issues')

    def apply_suggested_pricing(self, request, queryset):
        """Прилагане на предложени цени"""
        count = 0
        errors = 0

        for line in queryset.filter(new_sale_price__isnull=False):
            try:
                line.apply_suggested_price()
                count += 1
            except Exception:
                errors += 1

        self.message_user(
            request,
            f'Applied pricing for {count} lines. {errors} errors occurred.'
        )

    apply_suggested_pricing.short_description = _('Apply suggested pricing')

    def recalculate_line_totals(self, request, queryset):
        """Преизчисляване на line totals"""
        documents = set()

        for line in queryset:
            line.save()  # Triggers recalculation
            documents.add(line.document_id)

        # Recalculate document totals
        for doc_id in documents:
            try:
                from ..models import PurchaseDocument
                doc = PurchaseDocument.objects.get(id=doc_id)
                doc.recalculate_totals()
                doc.save()
            except:
                pass

        self.message_user(
            request,
            f'Recalculated {queryset.count()} lines and {len(documents)} documents'
        )

    recalculate_line_totals.short_description = _('Recalculate totals')

    def create_quality_reports(self, request, queryset):
        """Създаване на quality отчети"""
        quality_issues = queryset.filter(quality_approved=False)
        if not quality_issues.exists():
            self.message_user(request, "No quality issues found in selection")
            return

        # Тук би могъл да се генерира PDF или Excel отчет
        self.message_user(
            request,
            f'Found {quality_issues.count()} lines with quality issues. '
            'Report generation feature coming soon.'
        )

    create_quality_reports.short_description = _('Generate quality report')

    # Filters
    def get_list_filter(self, request):
        """Dynamic list filters"""
        filters = list(self.list_filter)

        # Add dynamic filters based on data
        if PurchaseDocumentLine.objects.filter(quality_approved=False).exists():
            filters.append('quality_approved')

        return filters

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'document__supplier', 'document__location',
            'product', 'unit'
        )

    # Custom change form
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)

        if obj and obj.document.status not in ['draft', 'confirmed']:
            # Lock fields for received documents
            readonly.extend([
                'quantity', 'unit_price', 'discount_percent', 'product', 'unit'
            ])

        return readonly