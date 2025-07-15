# products/admin/actions.py - REUSABLE ADMIN ACTIONS

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from ..models import ProductLifecycleChoices
from ..services import ProductLifecycleService


def make_products_active(modeladmin, request, queryset):
    """Admin action to make products active"""
    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset), ProductLifecycleChoices.ACTIVE, request.user
    )

    success_count = results['summary']['successful_count']
    failed_count = results['summary']['failed_count']

    if success_count:
        messages.success(request, f'Made {success_count} products active.')
    if failed_count:
        messages.warning(request, f'{failed_count} products could not be made active.')


make_products_active.short_description = _('Mark selected products as ACTIVE')


def make_products_phase_out(modeladmin, request, queryset):
    """Admin action to phase out products"""
    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset), ProductLifecycleChoices.PHASE_OUT, request.user
    )

    success_count = results['summary']['successful_count']
    messages.success(request, f'Set {success_count} products to phase out.')


make_products_phase_out.short_description = _('Mark selected products as PHASE OUT')


def make_products_discontinued(modeladmin, request, queryset):
    """Admin action to discontinue products"""
    results = ProductLifecycleService.bulk_change_lifecycle(
        list(queryset), ProductLifecycleChoices.DISCONTINUED, request.user
    )

    success_count = results['summary']['successful_count']
    messages.success(request, f'Discontinued {success_count} products.')


make_products_discontinued.short_description = _('Mark selected products as DISCONTINUED')


def block_product_sales(modeladmin, request, queryset):
    """Admin action to block sales"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.block_sales(product, request.user)
        if result['success']:
            count += 1

    messages.success(request, f'Blocked sales for {count} products.')


block_product_sales.short_description = _('Block sales for selected products')


def unblock_product_sales(modeladmin, request, queryset):
    """Admin action to unblock sales"""
    count = 0
    for product in queryset:
        result = ProductLifecycleService.unblock_sales(product, request.user)
        if result['success']:
            count += 1

    messages.success(request, f'Unblocked sales for {count} products.')


unblock_product_sales.short_description = _('Unblock sales for selected products')

# Registry of all actions
PRODUCT_ADMIN_ACTIONS = [
    make_products_active,
    make_products_phase_out,
    make_products_discontinued,
    block_product_sales,
    unblock_product_sales,
]