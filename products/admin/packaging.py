# products/admin/packaging.py - ОТДЕЛЕН ФАЙЛ ЗА PACKAGING ADMINS

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from ..models import ProductPackaging, ProductBarcode


@admin.register(ProductPackaging)
class ProductPackagingAdmin(admin.ModelAdmin):
    """Standalone admin for product packaging"""

    list_display = [
        'product_display', 'unit', 'conversion_factor', 'base_equivalent',
        'is_default_sale_unit', 'is_default_purchase_unit',
        'product_sellable', 'is_active'
    ]

    list_filter = [
        'is_default_sale_unit', 'is_default_purchase_unit', 'is_active',
        'unit', 'product__lifecycle_status', 'product__brand'
    ]

    search_fields = [
        'product__code', 'product__name', 'unit__name', 'unit__code'
    ]

    list_editable = [
        'conversion_factor', 'is_default_sale_unit',
        'is_default_purchase_unit', 'is_active'
    ]

    def product_display(self, obj):
        """Product with lifecycle badge"""
        badge_class = obj.product.lifecycle_badge_class
        return format_html(
            '{} <span class="badge {}">{}</span>',
            obj.product.code,
            badge_class,
            obj.product.get_lifecycle_status_display()
        )

    product_display.short_description = _('Product')

    def base_equivalent(self, obj):
        """Show base unit equivalent"""
        return format_html(
            '= {} {}',
            obj.conversion_factor,
            obj.product.base_unit.code
        )

    base_equivalent.short_description = _('Base Equivalent')

    def product_sellable(self, obj):
        """Show if product is sellable"""
        if obj.product.is_sellable:
            return format_html('<span style="color: green;">✅ Sellable</span>')
        else:
            return format_html('<span style="color: red;">❌ Not Sellable</span>')

    product_sellable.short_description = _('Sellable')


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    """Standalone admin for product barcodes"""

    list_display = [
        'barcode', 'product_display', 'barcode_type', 'packaging_info',
        'is_primary', 'product_sellable', 'is_active'
    ]

    list_filter = [
        'barcode_type', 'is_primary', 'is_active',
        'product__lifecycle_status', 'product__unit_type'
    ]

    search_fields = [
        'barcode', 'product__code', 'product__name'
    ]

    list_editable = ['is_primary', 'is_active']

    def product_display(self, obj):
        """Product with lifecycle info"""
        badge_class = obj.product.lifecycle_badge_class
        return format_html(
            '{} <span class="badge {}">{}</span>',
            obj.product.code,
            badge_class,
            obj.product.get_lifecycle_status_display()
        )

    product_display.short_description = _('Product')

    def packaging_info(self, obj):
        """Packaging information"""
        if obj.packaging:
            return format_html(
                '{} ({})',
                obj.packaging.unit.name,
                obj.packaging.conversion_factor
            )
        return format_html('<em>Base unit</em>')

    packaging_info.short_description = _('Packaging')

    def product_sellable(self, obj):
        """Product sellable status"""
        if obj.product.is_sellable:
            return format_html('<span style="color: green;">✅</span>')
        else:
            return format_html('<span style="color: red;">❌</span>')

    product_sellable.short_description = _('Sellable')