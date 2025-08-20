# # pricing/admin/prices.py - ПРОСТО И РАБОТЕЩО
#
# from django.contrib import admin
# from django.utils.translation import gettext_lazy as _
#
# from ..models import ProductPrice, ProductPriceByGroup, ProductStepPrice
#
#
# @admin.register(ProductPrice)
# class ProductPriceAdmin(admin.ModelAdmin):
#     """Simple product price admin - без излишни глупости"""
#
#     list_display = [
#         'product', 'location', 'pricing_method',
#         'base_price', 'effective_price', 'is_active'
#     ]
#
#     list_filter = ['is_active', 'location', 'pricing_method']
#     search_fields = ['product__code', 'product__name', 'location__code']
#     list_editable = ['is_active']
#
#     fieldsets = (
#         (_('Basic'), {
#             'fields': ('location', 'product', 'is_active')
#         }),
#         (_('Pricing'), {
#             'fields': ('pricing_method', 'base_price', 'markup_percentage', 'effective_price',)
#         }),
#     )
#
#     readonly_fields = ['effective_price']
#
#
# @admin.register(ProductPriceByGroup)
# class ProductPriceByGroupAdmin(admin.ModelAdmin):
#     """Simple group price admin"""
#
#     list_display = [
#         'product', 'location', 'price_group',
#         'price', 'min_quantity', 'is_active'
#     ]
#
#     list_filter = ['is_active', 'location', 'price_group']
#     search_fields = ['product__code', 'product__name']
#     list_editable = ['price', 'is_active']
#
#     fieldsets = (
#         (_('Basic'), {
#             'fields': ('location', 'product', 'price_group', 'is_active')
#         }),
#         (_('Pricing'), {
#             'fields': ('price', 'min_quantity')
#         }),
#     )
#
#
# @admin.register(ProductStepPrice)
# class ProductStepPriceAdmin(admin.ModelAdmin):
#     """Simple step price admin"""
#
#     list_display = [
#         'product', 'location', 'min_quantity',
#         'price', 'description', 'is_active'
#     ]
#
#     list_filter = ['is_active', 'location']
#     search_fields = ['product__code', 'product__name']
#     list_editable = ['price', 'is_active']
#
#     fieldsets = (
#         (_('Basic'), {
#             'fields': ('location', 'product', 'is_active')
#         }),
#         (_('Step Pricing'), {
#             'fields': ('min_quantity', 'price', 'description')
#         }),
#     )