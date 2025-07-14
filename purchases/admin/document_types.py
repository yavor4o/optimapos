# # purchases/admin/document_types.py
#
# from django.contrib import admin
# from django.utils.html import format_html
# from django.utils.safestring import mark_safe
# from django.utils.translation import gettext_lazy as _
#
# from ..models import DocumentType
#
#
# @admin.register(DocumentType)
# class DocumentTypeAdmin(admin.ModelAdmin):
#     """Admin за DocumentType"""
#
#     list_display = [
#         'code', 'name', 'type_key', 'stock_effect_display',
#         'workflow_settings', 'requirements', 'is_active'
#     ]
#
#     list_filter = [
#         'type_key', 'stock_effect', 'is_active',
#         'auto_confirm', 'auto_receive', 'requires_batch', 'requires_expiry'
#     ]
#
#     search_fields = ['code', 'name']
#
#     ordering = ['type_key', 'code']
#
#     fieldsets = (
#         (_('Basic Information'), {
#             'fields': ('code', 'name', 'type_key')
#         }),
#         (_('Stock Impact'), {
#             'fields': ('stock_effect', 'allow_reverse_operations'),
#             'description': 'How this document type affects inventory levels'
#         }),
#         (_('Requirements'), {
#             'fields': ('requires_batch', 'requires_expiry'),
#             'description': 'Mandatory fields for this document type'
#         }),
#         (_('Workflow Automation'), {
#             'fields': ('auto_confirm', 'auto_receive'),
#             'description': 'Automatic status transitions'
#         }),
#         (_('Status'), {
#             'fields': ('is_active',)
#         })
#     )
#
#     def stock_effect_display(self, obj):
#         """Цветен badge за stock effect"""
#         colors = {
#             1: '#28A745',  # Green for increase
#             -1: '#DC3545',  # Red for decrease
#             0: '#6C757D'  # Gray for no effect
#         }
#
#         symbols = {
#             1: '+',
#             -1: '-',
#             0: '='
#         }
#
#         color = colors.get(obj.stock_effect, '#6C757D')
#         symbol = symbols.get(obj.stock_effect, '?')
#
#         return format_html(
#             '<span style="background-color: {}; color: white; padding: 4px 8px; '
#             'border-radius: 4px; font-size: 12px; font-weight: bold;">'
#             '{} Stock</span>',
#             color, symbol
#         )
#
#     stock_effect_display.short_description = _('Stock Effect')
#
#     def workflow_settings(self, obj):
#         """Workflow настройки"""
#         settings = []
#
#         if obj.auto_confirm:
#             settings.append('<span style="color: #0D6EFD;">Auto Confirm</span>')
#         if obj.auto_receive:
#             settings.append('<span style="color: #198754;">Auto Receive</span>')
#
#         if not settings:
#             settings.append('<span style="color: #6C757D;">Manual</span>')
#
#         return mark_safe(' | '.join(settings))
#
#     workflow_settings.short_description = _('Workflow')
#
#     def requirements(self, obj):
#         """Задължителни полета"""
#         requirements = []
#
#         if obj.requires_batch:
#             requirements.append('<span style="color: #FFC107;">Batch Required</span>')
#         if obj.requires_expiry:
#             requirements.append('<span style="color: #FD7E14;">Expiry Required</span>')
#
#         if not requirements:
#             requirements.append('<span style="color: #6C757D;">No Requirements</span>')
#
#         return mark_safe(' | '.join(requirements))
#
#     requirements.short_description = _('Requirements')
#
#     def usage_statistics(self, obj):
#         """Статистика за използване"""
#         if not obj.pk:
#             return "Save first to see statistics"
#
#         from django.db import models
#         from ..models import PurchaseDocument
#
#         # Статистики за последните 30 дни
#         from datetime import timedelta
#         from django.utils import timezone
#
#         thirty_days_ago = timezone.now().date() - timedelta(days=30)
#
#         stats = PurchaseDocument.objects.filter(
#             document_type=obj,
#             created_at__date__gte=thirty_days_ago
#         ).aggregate(
#             total_docs=models.Count('id'),
#             total_amount=models.Sum('grand_total'),
#             avg_amount=models.Avg('grand_total')
#         )
#
#         parts = [
#             f"<strong>Documents (30d):</strong> {stats['total_docs'] or 0}",
#             f"<strong>Total Amount:</strong> {stats['total_amount'] or 0:.2f} лв",
#             f"<strong>Avg Amount:</strong> {stats['avg_amount'] or 0:.2f} лв",
#         ]
#
#         return mark_safe('<br>'.join(parts))
#
#     usage_statistics.short_description = _('Usage Statistics')
#
#     # Actions
#     actions = ['activate_types', 'deactivate_types', 'enable_auto_confirm']
#
#     def activate_types(self, request, queryset):
#         """Активиране на типове"""
#         count = queryset.update(is_active=True)
#         self.message_user(request, f'Activated {count} document types')
#
#     activate_types.short_description = _('Activate selected types')
#
#     def deactivate_types(self, request, queryset):
#         """Деактивиране на типове"""
#         count = queryset.update(is_active=False)
#         self.message_user(request, f'Deactivated {count} document types')
#
#     deactivate_types.short_description = _('Deactivate selected types')
#
#     def enable_auto_confirm(self, request, queryset):
#         """Включване на auto confirm"""
#         count = queryset.update(auto_confirm=True)
#         self.message_user(request, f'Enabled auto confirm for {count} types')
#
#     enable_auto_confirm.short_description = _('Enable auto confirm')