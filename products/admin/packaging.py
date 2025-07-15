# products/admin/packaging.py - ОТДЕЛЕН ФАЙЛ ЗА PACKAGING ADMINS

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.urls import reverse

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

    readonly_fields = ['created_at']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('product', 'unit', 'conversion_factor')
        }),
        (_('Usage Settings'), {
            'fields': ('is_default_sale_unit', 'is_default_purchase_unit')
        }),
        (_('Physical Properties'), {
            'fields': ('weight_kg',),
            'classes': ('collapse',)
        }),
        (_('Status'), {
            'fields': ('is_active', 'created_at')
        }),
    )

    def product_display(self, obj):
        """Product with lifecycle badge"""
        badge_class = obj.product.lifecycle_badge_class
        product_url = reverse('admin:products_product_change', args=[obj.product.pk])
        return format_html(
            '<a href="{}">{}</a> <span class="badge {}">{}</span>',
            product_url,
            obj.product.code,
            badge_class,
            obj.product.get_lifecycle_status_display()
        )

    product_display.short_description = _('Product')
    product_display.admin_order_field = 'product__code'

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
    product_sellable.admin_order_field = 'product__is_sellable'

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'product', 'unit', 'product__base_unit', 'product__brand'
        )

    class Media:
        css = {
            'all': ('admin/css/packaging_admin.css',)
        }


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

    readonly_fields = ['created_at', 'decoded_weight_info']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('product', 'barcode', 'barcode_type')
        }),
        (_('Packaging Link'), {
            'fields': ('packaging',),
            'description': _('Link barcode to specific packaging unit')
        }),
        (_('Settings'), {
            'fields': ('is_primary', 'is_active')
        }),
        (_('Weight Barcode Info'), {
            'fields': ('decoded_weight_info',),
            'classes': ('collapse',),
            'description': _('Auto-decoded information for weight barcodes')
        }),
        (_('Meta'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def product_display(self, obj):
        """Product with lifecycle info"""
        badge_class = obj.product.lifecycle_badge_class
        product_url = reverse('admin:products_product_change', args=[obj.product.pk])
        return format_html(
            '<a href="{}">{}</a> <span class="badge {}">{}</span>',
            product_url,
            obj.product.code,
            badge_class,
            obj.product.get_lifecycle_status_display()
        )

    product_display.short_description = _('Product')
    product_display.admin_order_field = 'product__code'

    def packaging_info(self, obj):
        """Packaging information"""
        if obj.packaging:
            return format_html(
                '{} (×{})',
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
    product_sellable.admin_order_field = 'product__is_sellable'

    def decoded_weight_info(self, obj):
        """Show decoded weight barcode info"""
        if obj.barcode_type == 'WEIGHT':
            decoded = obj.decode_weight_barcode()
            if decoded:
                return format_html(
                    '<strong>Product Code:</strong> {}<br>'
                    '<strong>Weight:</strong> {} г ({} кг)',
                    decoded['product_code'],
                    decoded['weight_grams'],
                    decoded['weight_kg']
                )
            else:
                return format_html('<span style="color: red;">Invalid weight barcode format</span>')
        return '-'

    decoded_weight_info.short_description = _('Weight Info')

    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related(
            'product', 'packaging', 'packaging__unit', 'product__base_unit'
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize ForeignKey fields"""
        if db_field.name == "packaging":
            # Filter packaging options based on selected product
            # This will be enhanced with JavaScript in the template
            kwargs["queryset"] = ProductPackaging.objects.select_related('unit')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/barcode_admin.css',)
        }
        js = ('admin/js/barcode_admin.js',)


# === CUSTOM ACTIONS ===

@admin.action(description='Activate selected packagings')
def activate_packagings(modeladmin, request, queryset):
    """Activate selected packagings"""
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f'{updated} packagings activated.')


@admin.action(description='Deactivate selected packagings')
def deactivate_packagings(modeladmin, request, queryset):
    """Deactivate selected packagings"""
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f'{updated} packagings deactivated.')


@admin.action(description='Set as default sale unit')
def set_default_sale_unit(modeladmin, request, queryset):
    """Set selected packagings as default sale units"""
    for packaging in queryset:
        # Clear other default sale units for the same product
        ProductPackaging.objects.filter(
            product=packaging.product,
            is_default_sale_unit=True
        ).update(is_default_sale_unit=False)

        # Set this one as default
        packaging.is_default_sale_unit = True
        packaging.save()

    modeladmin.message_user(request, f'{queryset.count()} default sale units set.')


# Add actions to admin classes
ProductPackagingAdmin.actions = [activate_packagings, deactivate_packagings, set_default_sale_unit]


@admin.action(description='Activate selected barcodes')
def activate_barcodes(modeladmin, request, queryset):
    """Activate selected barcodes"""
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f'{updated} barcodes activated.')


@admin.action(description='Deactivate selected barcodes')
def deactivate_barcodes(modeladmin, request, queryset):
    """Deactivate selected barcodes"""
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f'{updated} barcodes deactivated.')


ProductBarcodeAdmin.actions = [activate_barcodes, deactivate_barcodes]