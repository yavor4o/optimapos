# # pricing/admin/groups.py
#
# from django.contrib import admin
# from django.utils.html import format_html
# from django.utils.translation import gettext_lazy as _
# from django.db.models import Count
# from django.urls import reverse
# from django.utils.safestring import mark_safe
#
# from ..models import PriceGroup
#
#
# @admin.register(PriceGroup)
# class PriceGroupAdmin(admin.ModelAdmin):
#     list_display = [
#         'code', 'name', 'default_discount_display', 'priority',
#         'customer_count', 'product_count', 'is_active'
#     ]
#
#     list_filter = ['is_active', 'priority']
#     search_fields = ['code', 'name', 'description']
#     list_editable = ['priority', 'is_active']
#
#     readonly_fields = ['created_at', 'updated_at', 'group_summary']
#
#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': ('code', 'name', 'description', 'is_active')
#         }),
#         (_('Pricing Settings'), {
#             'fields': ('default_discount_percentage', 'priority'),
#             'description': _('Default discount applied when no specific price is set')
#         }),
#         (_('Group Summary'), {
#             'fields': ('group_summary',),
#             'classes': ('collapse',),
#             'description': _('Automatically calculated group statistics')
#         }),
#         (_('System Information'), {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         })
#     )
#
#     def get_queryset(self, request):
#         return super().get_queryset(request).annotate(
#             customer_count_ann=Count('customers', distinct=True),
#             product_count_ann=Count('product_group_prices', distinct=True)
#         )
#
#     def default_discount_display(self, obj):
#         """Display default discount with visual indicator"""
#         if obj.default_discount_percentage > 0:
#             return format_html(
#                 '<span style="color: green; font-weight: bold;">{}%</span>',
#                 obj.default_discount_percentage
#             )
#         return format_html('<span style="color: gray;">0%</span>')
#
#     default_discount_display.short_description = _('Default Discount')
#     default_discount_display.admin_order_field = 'default_discount_percentage'
#
#     def customer_count(self, obj):
#         """Number of customers in this group"""
#         count = getattr(obj, 'customer_count_ann', 0)
#         if count > 0:
#             return format_html(
#                 '<span style="color: blue;">👥 {}</span>',
#                 count
#             )
#         return format_html('<span style="color: gray;">0</span>')
#
#     customer_count.short_description = _('Customers')
#     customer_count.admin_order_field = 'customer_count_ann'
#
#     def product_count(self, obj):
#         """Number of products with specific prices for this group"""
#         count = getattr(obj, 'product_count_ann', 0)
#         if count > 0:
#             return format_html(
#                 '<span style="color: green;">📦 {}</span>',
#                 count
#             )
#         return format_html('<span style="color: gray;">0</span>')
#
#     product_count.short_description = _('Products')
#     product_count.admin_order_field = 'product_count_ann'
#
#     def group_summary(self, obj):
#         """Detailed group information"""
#         if not obj.pk:
#             return "Save group first to see summary"
#
#         summary_parts = [
#             f"<strong>Code:</strong> {obj.code}",
#             f"<strong>Default Discount:</strong> {obj.default_discount_percentage}%",
#             f"<strong>Priority:</strong> {obj.priority}",
#             f"<strong>Customers:</strong> {obj.get_customer_count()}",
#             f"<strong>Products with Special Prices:</strong> {obj.get_product_count()}"
#         ]
#
#         return mark_safe('<br>'.join(summary_parts))
#
#     group_summary.short_description = _('Group Summary')
#
#     def get_readonly_fields(self, request, obj=None):
#         readonly = list(self.readonly_fields)
#         if obj:  # Editing
#             readonly.append('code')
#         return readonly
#
#     # Actions
#     actions = ['activate_groups', 'deactivate_groups', 'reset_priorities']
#
#     def activate_groups(self, request, queryset):
#         updated = queryset.update(is_active=True)
#         self.message_user(request, f'{updated} groups activated.')
#
#     activate_groups.short_description = _('Activate selected groups')
#
#     def deactivate_groups(self, request, queryset):
#         updated = queryset.update(is_active=False)
#         self.message_user(request, f'{updated} groups deactivated.')
#
#     deactivate_groups.short_description = _('Deactivate selected groups')
#
#     def reset_priorities(self, request, queryset):
#         # Reset priorities to incremental values
#         for i, group in enumerate(queryset.order_by('name')):
#             group.priority = i * 10
#             group.save(update_fields=['priority'])
#
#         self.message_user(
#             request,
#             f'Reset priorities for {queryset.count()} groups.'
#         )
#
#     reset_priorities.short_description = _('Reset priorities (0, 10, 20...)')