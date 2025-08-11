# nomenclatures/admin/documents.py
"""
Documents Nomenclatures Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe

from ..models import DocumentType


# =======================
# DOCUMENT TYPE ADMIN
# =======================

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'key',
        'name',
        'app_name',
        'model_name',
        'status_info',
        'features_summary',
        'document_count',
        'is_active'
    ]

    list_filter = [
        'app_name',
        'affects_inventory',
        'is_fiscal_document',
        'requires_approval',
        'is_active'
    ]

    search_fields = ['key', 'name', 'app_name', 'model_name']
    ordering = ['app_name', 'name']

    readonly_fields = [
        'created_at',
        'updated_at',
        'document_usage_stats'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'key', 'name', 'description',
                'app_name', 'model_name'
            )
        }),
        (_('Document Behavior'), {
            'fields': (
                'initial_status',
                'final_status',
                'requires_approval',
                'auto_approve_conditions'
            )
        }),
        (_('Financial & Inventory'), {
            'fields': (
                'affects_inventory',
                'inventory_direction',
                'is_fiscal_document',
                'allows_negative_amounts'
            )
        }),
        (_('Features'), {
            'fields': (
                'allows_attachments',
                'auto_create_movements',
                'can_be_cancelled',
                'can_be_modified'
            )
        }),
        (_('Numbering'), {
            'fields': ('numbering_prefix', 'numbering_pattern'),
            'classes': ('collapse',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Audit'), {
            'fields': (
                'created_at',
                'updated_at',
                'document_usage_stats'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Опитваме се да анотираме с броя документи
        try:
            # Това може да не работи ако няма документи от този тип
            return qs.annotate(doc_count=Count('documents', distinct=True))
        except:
            return qs

    def status_info(self, obj):
        """Показва статус информация"""
        parts = []

        if obj.initial_status:
            parts.append(f"Start: {obj.initial_status}")

        if obj.final_status:
            parts.append(f"End: {obj.final_status}")

        if obj.requires_approval:
            parts.append('<span style="color: #dc3545;">Needs Approval</span>')

        return format_html('<br>'.join(parts)) if parts else '-'

    status_info.short_description = _('Status Flow')

    def features_summary(self, obj):
        """Обобщение на функционалностите"""
        features = []

        if obj.affects_inventory:
            direction_map = {
                'in': '📥', 'out': '📤', 'both': '🔄', 'none': '-'
            }
            icon = direction_map.get(obj.inventory_direction, '-')
            features.append(f'{icon} Inventory')

        if obj.is_fiscal_document:
            features.append('💼 Fiscal')

        if obj.allows_attachments:
            features.append('📎 Files')

        if obj.auto_create_movements:
            features.append('⚡ Auto Move')

        if obj.can_be_cancelled:
            features.append('❌ Cancel')

        if obj.can_be_modified:
            features.append('✏️ Edit')

        return format_html('<br>'.join(features)) if features else '-'

    features_summary.short_description = _('Features')

    def document_count(self, obj):
        """Брой документи от този тип"""
        try:
            count = getattr(obj, 'doc_count', 0)
            if count > 0:
                return format_html(
                    '<a href="#" style="color: #007bff; font-weight: bold;">{}</a>',
                    count
                )
            return '0'
        except:
            return '-'

    document_count.short_description = _('Documents')
    document_count.admin_order_field = 'doc_count'

    def document_usage_stats(self, obj):
        """Подробна статистика за използването"""
        try:
            # Това може да се имплементира с конкретни заявки
            # според структурата на документите
            stats = [
                "Usage statistics will be implemented",
                "based on actual document models"
            ]
            return format_html('<br>'.join(stats))
        except:
            return "No usage data available"

    document_usage_stats.short_description = _('Usage Statistics')

    def save_model(self, request, obj, form, change):
        """Автоматично uppercase на key"""
        if obj.key:
            obj.key = obj.key.upper()
        super().save_model(request, obj, form, change)

    # =======================
    # CUSTOM ACTIONS
    # =======================

    actions = ['make_active', 'make_inactive', 'reset_numbering']

    @admin.action(description=_('Activate selected document types'))
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _('Successfully activated {} document types.').format(updated)
        )

    @admin.action(description=_('Deactivate selected document types'))
    def make_inactive(self, request, queryset):
        # Проверка дали могат да се деактивират
        system_types = queryset.filter(is_system=True).count()
        if system_types > 0:
            self.message_user(
                request,
                _('Cannot deactivate system document types.'),
                level='ERROR'
            )
            return

        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _('Successfully deactivated {} document types.').format(updated)
        )

    @admin.action(description=_('Reset numbering for selected types'))
    def reset_numbering(self, request, queryset):
        """Reset numbering sequence - placeholder"""
        self.message_user(
            request,
            _('Numbering reset feature will be implemented.'),
            level='WARNING'
        )