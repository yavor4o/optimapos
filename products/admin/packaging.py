# products/admin/packaging.py

from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from decimal import Decimal

from ..models import ProductPackaging, ProductBarcode, ProductPLU


@admin.register(ProductPackaging)
class ProductPackagingAdmin(admin.ModelAdmin):
    """Admin for Product Packaging"""

    list_display = [
        'product_display',
        'unit',
        'conversion_display',
        'type_badges',
        'physical_properties',
        'barcode_count',
        'is_active'
    ]

    list_filter = [
        'is_active',
        'is_default_sale_unit',
        'is_default_purchase_unit',
        'allow_sale',
        'allow_purchase',
        'unit',
        ('product__product_group', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'product__code',
        'product__name',
        'unit__code',
        'unit__name'
    ]

    list_editable = ['is_active']

    fieldsets = (
        (_('Product & Unit'), {
            'fields': ('product', 'unit', 'conversion_factor')
        }),
        (_('Usage Settings'), {
            'fields': (
                ('allow_purchase', 'allow_sale'),
                ('is_default_purchase_unit', 'is_default_sale_unit')
            )
        }),
        (_('Physical Properties'), {
            'fields': (
                'weight_kg',
                'volume_m3',
                ('length_cm', 'width_cm', 'height_cm')
            ),
            'classes': ('collapse',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        })
    )

    def product_display(self, obj):
        """Display product with link"""
        return format_html(
            '<a href="/admin/products/product/{}/change/">{} - {}</a>',
            obj.product.id,
            obj.product.code,
            obj.product.name[:30]
        )

    product_display.short_description = _('Product')
    product_display.admin_order_field = 'product__code'

    def conversion_display(self, obj):
        """Display conversion with base unit"""
        return format_html(
            '1 {} = <strong>{}</strong> {}',
            obj.unit.code,
            obj.conversion_factor,
            obj.product.base_unit.code
        )

    conversion_display.short_description = _('Conversion')

    def type_badges(self, obj):
        """Display type badges"""
        badges = []

        if obj.is_default_sale_unit:
            badges.append('<span class="badge badge-success">Default Sale</span>')
        elif obj.allow_sale:
            badges.append('<span class="badge badge-info">Can Sell</span>')

        if obj.is_default_purchase_unit:
            badges.append('<span class="badge badge-warning">Default Purchase</span>')
        elif obj.allow_purchase:
            badges.append('<span class="badge badge-secondary">Can Purchase</span>')

        return format_html(' '.join(badges)) if badges else '-'

    type_badges.short_description = _('Type')

    def physical_properties(self, obj):
        """Display physical properties summary"""
        props = []

        if obj.weight_kg:
            props.append(f'⚖️ {obj.weight_kg}kg')

        if obj.calculated_volume:
            props.append(f'📦 {obj.calculated_volume:.4f}m³')

        if obj.length_cm and obj.width_cm and obj.height_cm:
            props.append(f'📏 {obj.length_cm}×{obj.width_cm}×{obj.height_cm}cm')

        return ' | '.join(props) if props else '-'

    physical_properties.short_description = _('Physical')

    def barcode_count(self, obj):
        """Count of barcodes for this packaging"""
        count = obj.product.barcodes.filter(packaging=obj).count()
        if count > 0:
            return format_html(
                '<a href="/admin/products/productbarcode/?packaging__id__exact={}">{} barcode(s)</a>',
                obj.id,
                count
            )
        return '-'

    barcode_count.short_description = _('Barcodes')

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'product', 'unit', 'product__base_unit'
        ).annotate(
            barcode_count=Count('product__barcodes', filter=Q(product__barcodes__packaging_id=models.F('id')))
        )


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    """Admin for Product Barcodes"""

    list_display = [
        'barcode',
        'product_display',
        'barcode_type_display',
        'packaging_display',
        'is_primary',
        'quantity_display',
        'is_active'
    ]

    list_filter = [
        'barcode_type',
        'is_primary',
        'is_active',
        ('product__product_group', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'barcode',
        'product__code',
        'product__name'
    ]

    list_editable = ['is_primary', 'is_active']

    fieldsets = (
        (_('Barcode Information'), {
            'fields': ('barcode', 'barcode_type', 'product')
        }),
        (_('Packaging Link'), {
            'fields': ('packaging',),
            'description': _('Optional: Link to specific packaging')
        }),
        (_('Settings'), {
            'fields': ('is_primary', 'is_active')
        })
    )

    def product_display(self, obj):
        """Display product info"""
        return format_html(
            '<a href="/admin/products/product/{}/change/">{}</a><br><small>{}</small>',
            obj.product.id,
            obj.product.code,
            obj.product.name[:40]
        )

    product_display.short_description = _('Product')
    product_display.admin_order_field = 'product__code'

    def barcode_type_display(self, obj):
        """Display barcode type with icon"""
        icons = {
            'STANDARD': '📊',
            'WEIGHT': '⚖️',
            'INTERNAL': '🏷️'
        }
        icon = icons.get(obj.barcode_type, '❓')

        # For weight barcodes, decode if possible
        extra = ''
        if obj.barcode_type == 'WEIGHT':
            decoded = obj.decode_weight_barcode()
            if decoded:
                extra = f"<br><small>PLU: {decoded['product_code']}, Weight: {decoded['weight_kg']}kg</small>"

        return format_html(
            '{} {}{}'.format(icon, obj.get_barcode_type_display(), extra)
        )

    barcode_type_display.short_description = _('Type')

    def packaging_display(self, obj):
        """Display packaging if linked"""
        if obj.packaging:
            return format_html(
                '{} × {}',
                obj.packaging.unit.code,
                obj.packaging.conversion_factor
            )
        return '-'

    packaging_display.short_description = _('Packaging')

    def quantity_display(self, obj):
        """Display quantity this barcode represents"""
        return f"{obj.quantity_in_base_units} {obj.display_unit.code}"

    quantity_display.short_description = _('Quantity')

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'product', 'packaging', 'packaging__unit', 'product__base_unit'
        )


@admin.register(ProductPLU)
class ProductPLUAdmin(admin.ModelAdmin):
    """Admin for Product PLU codes"""

    list_display = [
        'plu_code',
        'product_display',
        'is_primary',
        'priority',
        'description',
        'weight_product_check',
        'is_active'
    ]

    list_filter = [
        'is_primary',
        'is_active',
        'priority',
        ('product__product_group', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'plu_code',
        'product__code',
        'product__name',
        'description'
    ]

    list_editable = ['is_primary', 'priority', 'is_active']

    fieldsets = (
        (_('PLU Information'), {
            'fields': ('plu_code', 'product', 'description')
        }),
        (_('Settings'), {
            'fields': ('is_primary', 'priority', 'is_active')
        })
    )

    def product_display(self, obj):
        """Display product with weight indicator"""
        weight_icon = '⚖️' if obj.product.unit_type == 'WEIGHT' else '❌'
        return format_html(
            '{} <a href="/admin/products/product/{}/change/">{}</a><br><small>{}</small>',
            weight_icon,
            obj.product.id,
            obj.product.code,
            obj.product.name[:40]
        )

    product_display.short_description = _('Product')
    product_display.admin_order_field = 'product__code'

    def weight_product_check(self, obj):
        """Check if product is weight-based"""
        if obj.product.unit_type == 'WEIGHT':
            return format_html('<span style="color: green;">✅ Weight Product</span>')
        else:
            return format_html('<span style="color: red;">❌ Not Weight Product</span>')

    weight_product_check.short_description = _('Valid')

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'product', 'product__base_unit'
        )

    def save_model(self, request, obj, form, change):
        """Validate PLU assignment"""
        from ..services import ProductValidationService

        is_valid, error_msg = ProductValidationService.validate_plu_assignment(
            obj.product, obj.plu_code
        )

        if not is_valid:
            self.message_user(request, error_msg, level='ERROR')
            return

        super().save_model(request, obj, form, change)