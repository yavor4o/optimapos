from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from mptt.admin import MPTTModelAdmin, DraggableMPTTAdmin
from ..models import ProductGroup, Brand, ProductType


@admin.register(ProductGroup)
class ProductGroupAdmin(DraggableMPTTAdmin):
    """Админ за продуктови групи с drag-and-drop подреждане"""

    list_display = [
        'tree_actions',
        'indented_title',
        'code',
        'product_count',
        'is_active',
        'sort_order',
    ]
    list_display_links = ['indented_title']
    list_filter = ['is_active', 'level']
    search_fields = ['name', 'code']
    prepopulated_fields = {'code': ('name',)}

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'parent')
        }),
        (_('Settings'), {
            'fields': ('is_active', 'sort_order'),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # ПОПРАВЕНО: Използваме правилното име на reverse relation
        return qs.annotate(
            product_count_ann=Count('product', distinct=True)
        )

    def product_count(self, obj):
        """Брой продукти в групата"""
        # Използваме анотацията ако я има
        count = getattr(obj, 'product_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">{}</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    product_count.short_description = _('Products')
    product_count.admin_order_field = 'product_count_ann'

    def indented_title(self, obj):
        """Показва името с индентация според нивото"""
        return format_html(
            '<div style="text-indent:{}px">{}</div>',
            obj.level * 20,
            obj.name,
        )

    indented_title.short_description = _('Group Name')

    class Media:
        css = {
            'all': ('admin/css/nomenclatures.css',)
        }


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'logo_preview',
        'product_count',
        'is_active',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['code', 'name']
    readonly_fields = ['created_at', 'updated_at', 'logo_preview_large']

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'is_active')
        }),
        (_('Brand Info'), {
            'fields': ('logo', 'logo_preview_large', 'website'),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            product_count_ann=Count('product', distinct=True)
        )

    def product_count(self, obj):
        """Брой продукти от тази марка"""
        count = getattr(obj, 'product_count_ann', 0)
        return count

    product_count.short_description = _('Products')
    product_count.admin_order_field = 'product_count_ann'

    def logo_preview(self, obj):
        """Малък preview на логото в списъка"""
        if obj.logo:
            return format_html(
                '<img src="{}" style="width: 30px; height: 30px; object-fit: contain;" />',
                obj.logo.url
            )
        return '-'

    logo_preview.short_description = _('Logo')

    def logo_preview_large(self, obj):
        """Голям preview на логото в детайлите"""
        if obj.logo:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.logo.url
            )
        return _('No logo uploaded')

    logo_preview_large.short_description = _('Logo Preview')

    def get_readonly_fields(self, request, obj=None):
        """Прави code readonly при редактиране"""
        readonly = list(self.readonly_fields)
        if obj:  # Editing
            readonly.append('code')
        return readonly


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'category_badge',
        'requires_expiry',
        'product_count',
        'is_active'
    ]
    list_filter = ['category', 'requires_expiry_date', 'is_active']
    search_fields = ['code', 'name']


    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'category', 'is_active')
        }),
        (_('Settings'), {
            'fields': ('requires_expiry_date',),
            'description': _('Special rules for this product type')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            product_count_ann=Count('product', distinct=True)
        )

    def product_count(self, obj):
        count = getattr(obj, 'product_count_ann', 0)
        return count

    product_count.short_description = _('Products')
    product_count.admin_order_field = 'product_count_ann'

    def category_badge(self, obj):
        """Показва категорията с цветен badge"""
        colors = {
            'FOOD': '#4CAF50',
            'NONFOOD': '#2196F3',
            'TOBACCO': '#FF9800',
            'ALCOHOL': '#F44336',
            'SERVICE': '#9C27B0',
        }
        color = colors.get(obj.category, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_category_display()
        )

    category_badge.short_description = _('Category')
    category_badge.admin_order_field = 'category'

    def requires_expiry(self, obj):
        """Показва иконка за изискване на срок на годност"""
        if obj.requires_expiry_date:
            return format_html(
                '<img src="/static/admin/img/icon-yes.svg" alt="Yes">'
            )
        return format_html(
            '<img src="/static/admin/img/icon-no.svg" alt="No">'
        )

    requires_expiry.short_description = _('Expiry Required')
    requires_expiry.admin_order_field = 'requires_expiry_date'

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields or [])
        if obj:  # Editing
            readonly.append('code')
        return readonly

    def save_model(self, request, obj, form, change):
        """Автоматично uppercase на code"""
        if obj.code:
            obj.code = obj.code.upper()
        super().save_model(request, obj, form, change)