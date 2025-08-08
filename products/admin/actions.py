# products/admin/actions.py - REUSABLE ADMIN ACTIONS

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse
from django.db.models import Q
import csv
from decimal import Decimal

from ..models import ProductLifecycleChoices, Product
from ..services import ProductLifecycleService, ProductValidationService


# === LIFECYCLE ACTIONS ===

def make_products_active(modeladmin, request, queryset):
    """Admin action to make products active"""
    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset),
        ProductLifecycleChoices.ACTIVE,
        request.user
    )

    success_count = results['summary']['successful_count']
    failed_count = results['summary']['failed_count']

    if success_count:
        messages.success(request, f'✅ Made {success_count} products active.')
    if failed_count:
        messages.warning(request, f'⚠️ {failed_count} products could not be made active.')
        for failed in results['failed'][:5]:  # Show first 5 failures
            messages.error(request, f"❌ {failed['product'].code}: {failed['reason']}")


make_products_active.short_description = _('✅ Make selected products ACTIVE')


def make_products_phase_out(modeladmin, request, queryset):
    """Admin action to phase out products"""
    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset),
        ProductLifecycleChoices.PHASE_OUT,
        request.user
    )

    success_count = results['summary']['successful_count']
    failed_count = results['summary']['failed_count']

    if success_count:
        messages.info(request, f'⬇️ Set {success_count} products to phase out.')
    if failed_count:
        messages.warning(request, f'⚠️ {failed_count} products could not be phased out.')


make_products_phase_out.short_description = _('⬇️ Mark selected products as PHASE OUT')


def make_products_discontinued(modeladmin, request, queryset):
    """Admin action to discontinue products"""
    # Check for products with stock
    products_with_stock = []
    for product in queryset:
        if product.total_stock > 0:
            products_with_stock.append(product)

    if products_with_stock:
        messages.error(
            request,
            f'❌ Cannot discontinue {len(products_with_stock)} products with remaining stock. '
            f'Clear stock first.'
        )
        for product in products_with_stock[:5]:  # Show first 5
            messages.warning(request, f"⚠️ {product.code}: {product.total_stock:.0f} units in stock")
        return

    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset),
        ProductLifecycleChoices.DISCONTINUED,
        request.user
    )

    success_count = results['summary']['successful_count']
    if success_count:
        messages.success(request, f'⛔ Discontinued {success_count} products.')


make_products_discontinued.short_description = _('⛔ Mark selected products as DISCONTINUED')


# === BLOCKING ACTIONS ===

def block_product_sales(modeladmin, request, queryset):
    """Admin action to block sales"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.block_sales(product, request.user, reason="Admin bulk action")
        if result['success']:
            count += 1

    messages.success(request, f'🚫 Blocked sales for {count} products.')


block_product_sales.short_description = _('🚫💰 Block sales for selected products')


def unblock_product_sales(modeladmin, request, queryset):
    """Admin action to unblock sales"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.unblock_sales(product, request.user)
        if result['success']:
            count += 1

    messages.success(request, f'✅ Unblocked sales for {count} products.')


unblock_product_sales.short_description = _('✅💰 Unblock sales for selected products')


def block_product_purchases(modeladmin, request, queryset):
    """Admin action to block purchases"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.block_purchases(product, request.user, reason="Admin bulk action")
        if result['success']:
            count += 1

    messages.success(request, f'🚫 Blocked purchases for {count} products.')


block_product_purchases.short_description = _('🚫📦 Block purchases for selected products')


def unblock_product_purchases(modeladmin, request, queryset):
    """Admin action to unblock purchases"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.unblock_purchases(product, request.user)
        if result['success']:
            count += 1

    messages.success(request, f'✅ Unblocked purchases for {count} products.')


unblock_product_purchases.short_description = _('✅📦 Unblock purchases for selected products')


# === EXPORT ACTIONS ===

def export_products_csv(modeladmin, request, queryset):
    """Export selected products to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_export.csv"'

    writer = csv.writer(response)

    # Header row
    writer.writerow([
        'Code', 'Name', 'Brand', 'Group', 'Type',
        'Lifecycle Status', 'Sales Blocked', 'Purchase Blocked',
        'Total Stock', 'Weighted Avg Cost', 'Stock Value',
        'Track Batches', 'Track Serial', 'Base Unit'
    ])

    # Data rows
    for product in queryset:
        writer.writerow([
            product.code,
            product.name,
            product.brand.name if product.brand else '',
            product.product_group.name if product.product_group else '',
            product.product_type.name if product.product_type else '',
            product.get_lifecycle_status_display(),
            'Yes' if product.sales_blocked else 'No',
            'Yes' if product.purchase_blocked else 'No',
            product.total_stock,  # Uses property
            product.weighted_avg_cost,  # Uses property
            product.stock_value,  # Uses property
            'Yes' if product.track_batches else 'No',
            'Yes' if product.track_serial_numbers else 'No',
            product.base_unit.code
        ])

    return response


export_products_csv.short_description = _('📥 Export selected products to CSV')


def export_stock_report(modeladmin, request, queryset):
    """Export stock report for selected products"""
    from inventory.models import InventoryItem

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stock_report.csv"'

    writer = csv.writer(response)

    # Header row
    writer.writerow([
        'Product Code', 'Product Name', 'Location',
        'Current Stock', 'Available', 'Reserved',
        'Avg Cost', 'Stock Value', 'Last Movement'
    ])

    # Data rows
    for product in queryset:
        items = InventoryItem.objects.filter(product=product).select_related('location')

        if items:
            for item in items:
                writer.writerow([
                    product.code,
                    product.name,
                    item.location.code,
                    item.current_qty,
                    item.available_qty,
                    item.reserved_qty,
                    item.avg_cost,
                    item.current_qty * item.avg_cost,
                    item.last_movement_date
                ])
        else:
            # Product with no stock
            writer.writerow([
                product.code,
                product.name,
                'NO STOCK',
                0, 0, 0, 0, 0, ''
            ])

    return response


export_stock_report.short_description = _('📊 Export stock report for selected products')


# === VALIDATION ACTIONS ===

def validate_products(modeladmin, request, queryset):
    """Validate selected products for issues"""
    issues = []

    for product in queryset:
        # Check lifecycle inconsistencies
        if product.lifecycle_status == ProductLifecycleChoices.DISCONTINUED and product.total_stock > 0:
            issues.append(f"{product.code}: Discontinued but has {product.total_stock:.0f} units in stock")

        if product.lifecycle_status == ProductLifecycleChoices.ACTIVE and product.sales_blocked:
            issues.append(f"{product.code}: Active but sales blocked")

        if product.lifecycle_status == ProductLifecycleChoices.PHASE_OUT and not product.purchase_blocked:
            issues.append(f"{product.code}: Phase out but purchases not blocked")

        # Check tracking settings
        if product.track_serial_numbers and product.unit_type != 'PIECE':
            issues.append(f"{product.code}: Serial tracking on non-PIECE product")

        if product.track_batches and product.track_serial_numbers:
            issues.append(f"{product.code}: Both batch and serial tracking enabled")

    if issues:
        for issue in issues[:20]:  # Show first 20 issues
            messages.warning(request, f"⚠️ {issue}")

        if len(issues) > 20:
            messages.error(request, f"... and {len(issues) - 20} more issues")
    else:
        messages.success(request, f"✅ All {queryset.count()} products validated successfully!")


validate_products.short_description = _('🔍 Validate selected products')


# === BULK UPDATE ACTIONS ===

def enable_batch_tracking(modeladmin, request, queryset):
    """Enable batch tracking for selected products"""
    count = 0
    warnings = []

    for product in queryset:
        if product.track_serial_numbers:
            warnings.append(f"{product.code}: Has serial tracking, skipping")
            continue

        if not product.track_batches:
            product.track_batches = True
            product.save(update_fields=['track_batches'])
            count += 1

    if count:
        messages.success(request, f"✅ Enabled batch tracking for {count} products")

    for warning in warnings[:5]:
        messages.warning(request, f"⚠️ {warning}")


enable_batch_tracking.short_description = _('📦 Enable batch tracking')


def disable_batch_tracking(modeladmin, request, queryset):
    """Disable batch tracking for selected products"""
    products_with_batches = []

    from inventory.models import InventoryBatch

    for product in queryset:
        if product.track_batches:
            # Check if has active batches
            has_batches = InventoryBatch.objects.filter(
                product=product,
                remaining_qty__gt=0
            ).exists()

            if has_batches:
                products_with_batches.append(product.code)
            else:
                product.track_batches = False
                product.save(update_fields=['track_batches'])

    if products_with_batches:
        messages.error(
            request,
            f"❌ Cannot disable batch tracking for products with active batches: {', '.join(products_with_batches[:5])}"
        )
    else:
        messages.success(request, f"✅ Disabled batch tracking for {queryset.count()} products")


disable_batch_tracking.short_description = _('📦❌ Disable batch tracking')

# === REGISTRY OF ALL ACTIONS ===

PRODUCT_ADMIN_ACTIONS = [
    # Lifecycle
    make_products_active,
    make_products_phase_out,
    make_products_discontinued,

    # Blocking
    block_product_sales,
    unblock_product_sales,
    block_product_purchases,
    unblock_product_purchases,

    # Export
    export_products_csv,
    export_stock_report,

    # Validation
    validate_products,

    # Bulk updates
    enable_batch_tracking,
    disable_batch_tracking,
]