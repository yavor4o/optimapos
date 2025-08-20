# # pricing/admin/packaging.py - ПРОСТ ADMIN
#
# from django.contrib import admin
# from django.utils.translation import gettext_lazy as _
#
# from ..models import PackagingPrice
#
#
# @admin.register(PackagingPrice)
# class PackagingPriceAdmin(admin.ModelAdmin):
#     list_display = [
#         'packaging_simple', 'location', 'pricing_method',
#         'price', 'is_active'
#     ]
#
#     list_filter = [
#         'is_active', 'location', 'pricing_method',
#         'packaging__product__product_group', 'packaging__product__brand',
#         'packaging__unit'
#     ]
#
#     search_fields = [
#         'packaging__product__code', 'packaging__product__name',
#         'location__code', 'packaging__unit__name'
#     ]
#
#     list_editable = ['price', 'is_active']
#
#     readonly_fields = ['created_at', 'updated_at']
#
#     fieldsets = (
#         (_('Packaging & Location'), {
#             'fields': ('location', 'packaging', 'is_active')
#         }),
#         (_('Pricing Method'), {
#             'fields': ('pricing_method',),
#         }),
#         (_('Price Settings'), {
#             'fields': ('price', 'markup_percentage', 'discount_percentage'),
#         }),
#         (_('System Information'), {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         })
#     )
#
#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related(
#             'location', 'packaging', 'packaging__product',
#             'packaging__unit', 'packaging__product__base_unit'
#         )
#
#     def packaging_simple(self, obj):
#         """Прост дисплей на опаковката"""
#         return f"{obj.packaging.product.code} - {obj.packaging.unit.code} x{obj.packaging.conversion_factor}"
#
#     packaging_simple.short_description = _('Packaging')
#
#     # Прости действия
#     actions = ['recalculate_prices']
#
#     def recalculate_prices(self, request, queryset):
#         """Преизчисляване на цени"""
#         count = 0
#         for packaging_price in queryset.exclude(pricing_method='FIXED'):
#             packaging_price.calculate_effective_price()
#             packaging_price.save(update_fields=['price'])
#             count += 1
#
#         self.message_user(request, f'Recalculated {count} packaging prices.')
#
#     recalculate_prices.short_description = _('Recalculate prices')