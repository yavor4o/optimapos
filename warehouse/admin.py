from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Warehouse, StockMovement, StockLevel,
    WarehouseProductPrice, WarehouseProductPriceByGroup,
    WarehouseProductStepPrice, WarehousePromotionalPrice, PriceGroup
)


# === WAREHOUSE ADMIN ===

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'warehouse_type', 'manager',
        'default_markup_percentage', 'total_products', 'total_value', 'is_active'
    ]
    list_filter = ['warehouse_type', 'is_active', 'created_at']
    search_fields = ['code', 'name', 'address']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'warehouse_type', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('address', 'phone', 'email', 'manager'),
            'classes': ('collapse',)
        }),
        ('Pricing Settings', {
            'fields': ('default_markup_percentage',),
            'description': 'Default markup used when no specific price is set for products'
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def total_products(self, obj):
        count = obj.stock_levels.count()
        if count > 0:
            url = reverse('admin:warehouse_stocklevel_changelist') + f'?warehouse__id__exact={obj.id}'
            return format_html('<a href="{}">{} продукта</a>', url, count)
        return "0 продукта"

    total_products.short_description = 'Products'

    def total_value(self, obj):
        value = obj.get_total_stock_value()
        return f"{value:.2f} лв"

    total_value.short_description = 'Stock Value'


# === STOCK MOVEMENT ADMIN ===

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'document_date', 'warehouse', 'product_display',
        'batch_number', 'quantity_display', 'unit_price',  'purchase_document_link','created_by', 'created_at'
    ]
    list_filter = [
        'movement_type', 'warehouse', 'document_date', 'created_at',
        'product__product_group'
    ]
    search_fields = [
        'document', 'product__code', 'product__name', 'batch_number'
    ]
    readonly_fields = ['created_at']
    date_hierarchy = 'document_date'

    fieldsets = (
        ('Movement Information', {
            'fields': ('warehouse', 'product', 'movement_type', 'quantity', 'unit_price')
        }),
        ('Document Information', {
            'fields': ('document', 'document_date','purchase_document', 'reason')
        }),
        ('Batch Information', {
            'fields': ('batch_number', 'expiry_date'),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_by', 'created_at'),
            'classes': ('collapse',)
        })
    )

    def purchase_document_link(self, obj):
        if obj.purchase_document:
            from django.urls import reverse
            url = reverse('admin:purchases_purchasedocument_change', args=[obj.purchase_document.pk])
            return format_html(
                '<a href="{}" target="_blank">📋 {}</a>',
                url,
                obj.purchase_document.document_number
            )
        return "-"

    purchase_document_link.short_description = 'Purchase Doc'
    purchase_document_link.admin_order_field = 'purchase_document'

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:30]}"

    product_display.short_description = 'Product'

    def quantity_display(self, obj):
        direction = "📈" if obj.movement_type == 'in' else "📉"
        sign = "+" if obj.movement_type == 'in' else "-"
        color = "green" if obj.movement_type == 'in' else "red"
        return format_html(
            '{} <span style="color: {};">{}{}</span>',
            direction, color, sign, obj.quantity
        )

    quantity_display.short_description = 'Quantity'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'warehouse', 'product', 'created_by'
        )


# === STOCK LEVEL ADMIN ===

@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'warehouse', 'batch_number', 'expiry_date', 'quantity_status',
        'avg_purchase_price', 'current_sale_price', 'markup_display', 'profit_margin',
        'quantity_reserved', 'min_stock_level', 'needs_reorder_display'
    ]
    list_filter = ['warehouse', 'product__product_group', 'product__brand', 'expiry_date']
    search_fields = ['product__code', 'product__name', 'batch_number']
    list_editable = ['quantity_reserved', 'min_stock_level']
    readonly_fields = ['quantity', 'avg_purchase_price', 'last_movement_date', 'updated_at']

    fieldsets = (
        ('Product Information', {
            'fields': ('warehouse', 'product', 'batch_number', 'expiry_date')
        }),
        ('Stock Levels', {
            'fields': ('quantity', 'quantity_reserved', 'min_stock_level'),
        }),
        ('Pricing Information', {
            'fields': ('avg_purchase_price',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('last_movement_date', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def markup_display(self, obj):
        """Показва надценката %"""
        try:
            markup = obj.get_markup_percentage()
            if markup > 0:
                # Форматирай като string ПРЕДИ да подадеш на format_html
                markup_str = f"{float(markup):.1f}"
                return format_html(
                    '<span style="color: blue;">↗️ {}%</span>',
                    markup_str
                )
            return "0.0%"
        except Exception as e:
            return f"Error: {str(e)}"

    markup_display.short_description = 'Markup %'

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:40]}"

    product_display.short_description = 'Product'

    def quantity_status(self, obj):
        available = obj.quantity_available
        if available <= 0:
            color = "red"
            icon = "🔴"
        elif obj.needs_reorder:
            color = "orange"
            icon = "🟡"
        else:
            color = "green"
            icon = "🟢"

        return format_html(
            '{} <span style="color: {};">{} / {}</span>',
            icon, color, available, obj.quantity
        )

    quantity_status.short_description = 'Available / Total'

    def current_sale_price(self, obj):
        from .models import PricingService
        try:
            price = PricingService.get_sale_price(obj.warehouse, obj.product)
            return f"{price:.2f} лв"
        except:
            return "-"

    current_sale_price.short_description = 'Sale Price'

    def profit_margin(self, obj):
        try:
            margin = obj.get_margin_percentage()
            if margin > 0:
                # Форматирай като string ПРЕДИ да подадеш на format_html
                margin_str = f"{float(margin):.1f}"
                return format_html(
                    '<span style="color: green;">{}%</span>',
                    margin_str
                )
            return "0.0%"
        except Exception as e:
            return f"Error: {str(e)}"

    profit_margin.short_description = 'Profit %'

    def needs_reorder_display(self, obj):
        if obj.needs_reorder:
            return format_html('<span style="color: red;">⚠️ Reorder</span>')
        return "✅ OK"

    needs_reorder_display.short_description = 'Status'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'warehouse', 'product'
        )


# === PRICING ADMINS ===

@admin.register(WarehouseProductPrice)
class WarehouseProductPriceAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'warehouse', 'base_price', 'is_active'
    ]
    list_filter = ['warehouse', 'is_active']
    search_fields = ['product__code', 'product__name']
    list_editable = ['base_price', 'is_active']

    fieldsets = (
        ('Basic Information', {
            'fields': ('warehouse', 'product', 'is_active')
        }),
        ('Pricing Method', {
            'fields': ('base_price',),
            'description': 'Either set fixed base price OR use markup on average cost'
        })
    )

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:40]}"

    product_display.short_description = 'Product'

    def effective_price(self, obj):
        price = obj.base_price
        return f"{price:.2f} лв"

    effective_price.short_description = 'Effective Price'


@admin.register(WarehouseProductPriceByGroup)
class WarehouseProductPriceByGroupAdmin(admin.ModelAdmin):
    list_display = ['product_display', 'warehouse', 'price_group', 'price', 'is_active']
    list_filter = ['warehouse', 'price_group', 'is_active']
    search_fields = ['product__code', 'product__name']
    list_editable = ['price', 'is_active']

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:40]}"

    product_display.short_description = 'Product'


@admin.register(WarehouseProductStepPrice)
class WarehouseProductStepPriceAdmin(admin.ModelAdmin):
    list_display = ['product_display', 'warehouse', 'min_quantity', 'price', 'is_active']
    list_filter = ['warehouse', 'is_active']
    search_fields = ['product__code', 'product__name']
    list_editable = ['min_quantity', 'price', 'is_active']

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:40]}"

    product_display.short_description = 'Product'


@admin.register(WarehousePromotionalPrice)
class WarehousePromotionalPriceAdmin(admin.ModelAdmin):
    list_display = [
        'product_display', 'warehouse', 'name', 'price',
        'start_date', 'end_date', 'min_quantity', 'is_valid_display', 'is_active'
    ]
    list_filter = ['warehouse', 'is_active', 'start_date', 'end_date']
    search_fields = ['product__code', 'product__name', 'name']
    list_editable = ['price', 'is_active']
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('warehouse', 'product', 'name', 'is_active')
        }),
        ('Promotion Details', {
            'fields': ('price', 'start_date', 'end_date', 'min_quantity')
        })
    )

    def product_display(self, obj):
        return f"{obj.product.code} - {obj.product.name[:40]}"

    product_display.short_description = 'Product'

    def is_valid_display(self, obj):
        if obj.is_valid_now():
            return format_html('<span style="color: green;">✅ Active</span>')
        return format_html('<span style="color: gray;">⏸️ Inactive</span>')

    is_valid_display.short_description = 'Current Status'


# === CUSTOM ADMIN ACTIONS ===

def recalculate_stock_levels(modeladmin, request, queryset):
    """Преизчислява наличностите от движенията"""
    count = 0
    for stock_level in queryset:
        StockLevel.refresh_for_combination(
            warehouse=stock_level.warehouse,
            product=stock_level.product,
            batch_number=stock_level.batch_number
        )
        count += 1

    modeladmin.message_user(
        request,
        f"Преизчислени {count} наличности."
    )


recalculate_stock_levels.short_description = "Recalculate stock levels from movements"


def setup_default_pricing(modeladmin, request, queryset):
    """Настройва default цени за продукти без цени"""
    from .models import WarehouseProductPrice
    count = 0

    for warehouse in queryset:
        # Намери продукти без цени в този склад
        products_without_prices = []
        for stock_level in warehouse.stock_levels.all():
            if not WarehouseProductPrice.objects.filter(
                    warehouse=warehouse,
                    product=stock_level.product
            ).exists():
                products_without_prices.append(stock_level)

        # Създай default цени
        for stock_level in products_without_prices:
            if stock_level.avg_purchase_price > 0:
                default_price = stock_level.avg_purchase_price * (
                        1 + warehouse.default_markup_percentage / 100
                )
                WarehouseProductPrice.objects.create(
                    warehouse=warehouse,
                    product=stock_level.product,
                    base_price=default_price,
                )
                count += 1

    modeladmin.message_user(
        request,
        f"Настроени default цени за {count} продукта."
    )



@admin.register(PriceGroup)
class PriceGroupAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'description_short', 'discount_percentage',
        'products_count', 'customers_count', 'is_active'
    ]
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['discount_percentage', 'is_active']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Default Settings', {
            'fields': ('discount_percentage',),
            'description': 'Default discount percentage for this group'
        })
    )

    def description_short(self, obj):
        if obj.description:
            return obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return "-"

    description_short.short_description = 'Description'

    def products_count(self, obj):
        """Count products with warehouse-specific pricing for this group"""
        try:
            from warehouse.models import WarehouseProductPriceByGroup
            count = WarehouseProductPriceByGroup.objects.filter(
                price_group=obj, is_active=True
            ).values('product').distinct().count()

            if count > 0:
                return format_html(
                    '<span style="color: green;">{} products</span>',
                    count
                )
            return "0 products"
        except:
            return "N/A"

    products_count.short_description = 'Products'

    def customers_count(self, obj):
        """Count customers in this price group"""
        try:
            from partners.models import Customer
            count = Customer.objects.filter(price_group=obj, is_active=True).count()

            if count > 0:
                return format_html(
                    '<span style="color: blue;">{} customers</span>',
                    count
                )
            return "0 customers"
        except:
            return "N/A"

    customers_count.short_description = 'Customers'


setup_default_pricing.short_description = "Setup default pricing for products without prices"

# Добави actions към админите
StockLevelAdmin.actions = [recalculate_stock_levels]
WarehouseAdmin.actions = [setup_default_pricing]