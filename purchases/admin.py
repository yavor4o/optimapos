from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db import models
from .models import DocumentType, PurchaseDocument, PurchaseDocumentLine
from django.utils.translation import gettext_lazy as _

# === INLINE ADMINS ===

class PurchaseDocumentLineInline(admin.TabularInline):
    model = PurchaseDocumentLine
    extra = 1
    fields = [
        'line_number', 'product', 'quantity', 'unit', 'unit_price',
        'discount_percent', 'quantity_base_display', 'unit_price_base_display',
        'final_unit_price', 'line_total',
        'old_sale_price', 'new_sale_price', 'markup_percentage',
        'batch_number', 'expiry_date'
    ]
    readonly_fields = [
        'final_unit_price', 'line_total', 'old_sale_price', 'markup_percentage',
        'quantity_base_display', 'unit_price_base_display'
    ]

    def quantity_base_display(self, obj):
        if obj.quantity_base_unit and obj.product:
            return f"{obj.quantity_base_unit} {obj.product.base_unit.code}"
        return "-"
    quantity_base_display.short_description = 'Qty (Base Unit)'

    def unit_price_base_display(self, obj):
        if obj.unit_price_base and obj.product:
            return f"{obj.unit_price_base:.4f} лв/{obj.product.base_unit.code}"
        return "-"
    unit_price_base_display.short_description = 'Price (Base Unit)'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'unit', 'product__base_unit')


# === MAIN ADMINS ===

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'type_key', 'stock_effect_display',
        'requires_batch', 'is_active',  'allow_reverse_operations'
    ]
    list_filter = ['type_key', 'stock_effect', 'requires_batch', 'is_active', 'allow_reverse_operations']
    search_fields = ['code', 'name']
    list_editable = ['requires_batch', 'is_active', 'allow_reverse_operations']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'type_key', 'is_active')
        }),
        ('Stock Management', {
            'fields': ('stock_effect', 'requires_batch','allow_reverse_operations'),
            'description': 'How this document type affects inventory'
        })
    )

    def stock_effect_display(self, obj):
        if obj.stock_effect == 1:
            base_icon = '<span style="color: green;">📈 Increases</span>'
        elif obj.stock_effect == -1:
            base_icon = '<span style="color: red;">📉 Decreases</span>'
        else:
            base_icon = '<span style="color: gray;">➖ No effect</span>'

        # Добавяме индикатор за reverse operations
        if obj.allow_reverse_operations:
            reverse_indicator = ' <span style="color: orange; font-size: 0.8em;">🔄 Reversible</span>'
            return format_html(base_icon + reverse_indicator)

        return format_html(base_icon)

    stock_effect_display.short_description = 'Stock Effect'


@admin.register(PurchaseDocument)
class PurchaseDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'document_number', 'document_date', 'supplier_display',
        'location_display', 'document_type', 'status_display', 'grand_total_display',
        'is_paid_display', 'created_by', 'is_paid'
    ]
    list_filter = [
        'status', 'document_type', 'location', 'is_paid',
        'document_date', 'prices_include_vat'
    ]
    search_fields = [
        'document_number', 'supplier__name', 'notes','location__name', 'location__code'
    ]

    readonly_fields = [
        'total_before_discount', 'total_discount', 'total_after_discount',
        'total_vat', 'grand_total', 'created_at', 'updated_at'
    ]
    date_hierarchy = 'document_date'

    fieldsets = (
        ('Document Information', {
            'fields': (
                'document_number', 'document_date', 'delivery_date',
                'document_type', 'status'
            )
        }),
        ('Parties', {
            'fields': ('supplier', 'warehouse')
        }),
        ('Financial Settings', {
            'fields': (
                'payment_method', 'prices_include_vat', 'is_paid'
            )
        }),
        ('Calculated Totals', {
            'fields': (
                'total_before_discount', 'total_discount', 'total_after_discount',
                'total_vat', 'grand_total'
            ),
            'classes': ('collapse',),
            'description': 'Automatically calculated from document lines'
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [PurchaseDocumentLineInline]

    def supplier_display(self, obj):
        return f"{obj.supplier.name}"

    supplier_display.short_description = 'Supplier'

    def status_display(self, obj):
        colors = {
            'draft': 'gray',
            'confirmed': 'blue',
            'received': 'green',
            'paid': 'purple',
            'closed': 'black'
        }
        icons = {
            'draft': '📝',
            'confirmed': '✅',
            'received': '📦',
            'paid': '💰',
            'closed': '🔒'
        }

        color = colors.get(obj.status, 'gray')
        icon = icons.get(obj.status, '❓')

        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_status_display()
        )

    status_display.short_description = 'Status'

    def grand_total_display(self, obj):
        total_str = f"{float(obj.grand_total):.2f}"
        return format_html(
            '<strong>{} лв</strong>',
            total_str
        )

    grand_total_display.short_description = 'Grand Total'

    def is_paid_display(self, obj):
        if obj.is_paid:
            return format_html('<span style="color: green;">✅ Paid</span>')
        return format_html('<span style="color: red;">❌ Unpaid</span>')

    is_paid_display.short_description = 'Payment Status'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'warehouse', 'document_type', 'payment_method', 'created_by'
        )

    def location_display(self, obj):
        """Показва location вместо warehouse"""
        if obj.location:
            return format_html(
                '<a href="{}">{}</a>',
                reverse('admin:inventory_inventorylocation_change', args=[obj.location.pk]),
                obj.location.name
            )
        return '-'

    location_display.short_description = _('Location')
    location_display.admin_order_field = 'location__name'


@admin.register(PurchaseDocumentLine)
class PurchaseDocumentLineAdmin(admin.ModelAdmin):
    list_display = [
        'document_display', 'line_number', 'product_display',
        'quantity', 'unit_price', 'discount_percent', 'final_unit_price',
        'line_total', 'price_analysis'
    ]
    list_filter = [
        'document__status',
        'document__location',  # ПРОМЕНЕНО от 'document__warehouse'
        'unit'
    ]
    search_fields = [
        'document__document_number', 'product__code', 'product__name',
        'product_name', 'batch_number'
    ]
    readonly_fields = [
        'discount_amount', 'final_unit_price', 'line_total', 'vat_amount',
        'old_sale_price', 'new_sale_price', 'markup_percentage'
    ]

    fieldsets = (
        ('Document Information', {
            'fields': ('document', 'line_number')
        }),
        ('Product Information', {
            'fields': ('product', 'product_name', 'unit', 'quantity')
        }),
        ('Pricing', {
            'fields': (
                'unit_price', 'discount_percent', 'discount_amount',
                'final_unit_price', 'line_total', 'vat_amount'
            )
        }),
        ('Batch Information', {
            'fields': ('batch_number', 'expiry_date'),
            'classes': ('collapse',)
        }),
        ('Price Analysis', {
            'fields': ('old_sale_price', 'new_sale_price', 'markup_percentage'),
            'classes': ('collapse',),
            'description': 'Automatically calculated pricing suggestions'
        })
    )

    def document_display(self, obj):
        return f"{obj.document.document_number}"

    document_display.short_description = 'Document'

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = 'Product'

    def price_analysis(self, obj):
        if obj.markup_percentage:
            old_price = f"{float(obj.old_sale_price or 0):.2f}"
            new_price = f"{float(obj.new_sale_price or 0):.2f}"
            markup = f"{float(obj.markup_percentage):.1f}"

            return format_html(
                'Old: {} → New: {} ({}%)',
                old_price, new_price, markup
            )
        return "-"

    price_analysis.short_description = 'Price Analysis'

    price_analysis.short_description = 'Price Analysis'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'document', 'product', 'unit'
        )


# === CUSTOM ADMIN ACTIONS ===

def mark_as_received(modeladmin, request, queryset):
    """Маркира документи като получени"""
    count = 0
    for doc in queryset:
        if doc.status == PurchaseDocument.DRAFT or doc.status == PurchaseDocument.CONFIRMED:
            doc.status = PurchaseDocument.RECEIVED
            doc.save()  # Ще създаде StockMovements автоматично
            count += 1

    modeladmin.message_user(
        request,
        f"Marked {count} documents as received. Stock movements created."
    )


mark_as_received.short_description = "Mark selected documents as received"


def mark_as_paid(modeladmin, request, queryset):
    """Маркира документи като платени"""
    count = queryset.update(is_paid=True)
    modeladmin.message_user(
        request,
        f"Marked {count} documents as paid."
    )


mark_as_paid.short_description = "Mark selected documents as paid"

# Добави actions към админа
PurchaseDocumentAdmin.actions = [mark_as_received, mark_as_paid]

# === ADMIN SITE CUSTOMIZATION ===
admin.site.site_header = "POS System Administration"