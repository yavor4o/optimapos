# nomenclatures/admin/numbering.py - ПРАВИЛЕН АДМИН КОД
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils.safestring import mark_safe

# Try to import models
try:
    from ..models.numbering import (
        NumberingConfiguration,
        LocationNumberingAssignment,
        UserNumberingPreference
    )

    HAS_NUMBERING_MODELS = True
except ImportError:
    HAS_NUMBERING_MODELS = False

# =================================================================
# NUMBERING CONFIGURATION ADMIN - ПРАВИЛНА ВЕРСИЯ
# =================================================================

if HAS_NUMBERING_MODELS:
    @admin.register(NumberingConfiguration)
    class NumberingConfigurationAdmin(admin.ModelAdmin):
        """Професионален админ за numbering configurations"""

        list_display = [
            'code',
            'document_type',
            'numbering_type_badge',
            'series_info',
            'number_format_display',
            'current_number_display',
            'fiscal_compliance',
            'is_default_badge',
            'is_active'
        ]

        list_filter = [
            'numbering_type',
            'document_type',
            'is_default',
            'is_active',
            'reset_yearly'
        ]

        search_fields = [
            'name',
            'prefix',
            'series_name',
            'document_type__name'
        ]

        readonly_fields = [
            'created_at',
            'updated_at',
            'next_number_preview',
            'fiscal_compliance_check',
            'usage_statistics'
        ]

        fieldsets = (
            (_('Basic Information'), {
                'fields': (
                    'code',
                    'name',
                    'document_type',
                    'numbering_type',
                    'is_active',
                    'is_default'
                )
            }),
            (_('Number Format'), {
                'fields': (
                    'prefix',
                    'digits_count',  # ✅ ПРАВИЛНО ПОЛЕ
                    'current_number',
                    'max_number'
                ),
                'description': _('Configure how numbers are formatted')
            }),
            (_('Series Configuration'), {
                'fields': (
                    'series_number',
                    'series_name'
                ),
                'description': _('Series like Microinvest: (1), (2), (23)')
            }),
            (_('Reset Behavior'), {
                'fields': (
                    'reset_yearly',
                    'last_reset_year'  # ✅ ПРАВИЛНО ПОЛЕ
                ),
                'classes': ('collapse',)
            }),
            (_('Preview & Statistics'), {
                'fields': (
                    'next_number_preview',
                    'fiscal_compliance_check',
                    'usage_statistics'
                ),
                'classes': ('collapse',)
            }),
            (_('System Information'), {
                'fields': (
                    'created_at',
                    'updated_at'
                ),
                'classes': ('collapse',)
            })
        )

        ordering = ['document_type', 'series_number', 'name']

        def numbering_type_badge(self, obj):
            """Показва вида номерация с цветно badge"""
            if obj.numbering_type == 'fiscal':
                return format_html(
                    '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                    'border-radius: 3px; font-size: 11px;">🏛️ FISCAL</span>'
                )
            else:
                return format_html(
                    '<span style="background-color: #007bff; color: white; padding: 3px 8px; '
                    'border-radius: 3px; font-size: 11px;">🏢 INTERNAL</span>'
                )

        numbering_type_badge.short_description = _('Type')
        numbering_type_badge.admin_order_field = 'numbering_type'

        def series_info(self, obj):
            """Показва информация за серията"""
            if obj.series_name:
                return format_html(
                    '<strong>({}) {}</strong>',
                    obj.series_number,
                    obj.series_name
                )
            else:
                return format_html('<strong>({})</strong>', obj.series_number)

        series_info.short_description = _('Series')
        series_info.admin_order_field = 'series_number'

        def number_format_display(self, obj):
            """Показва формата на номерата"""
            pattern_parts = []

            if obj.prefix:
                pattern_parts.append(f'<span style="color: #2196F3;">{obj.prefix}</span>')

            # Показва формата на числото с правилното поле
            number_placeholder = '#' * obj.digits_count  # ✅ ПРАВИЛНО ПОЛЕ
            pattern_parts.append(f'<span style="color: #4CAF50;">{number_placeholder}</span>')

            pattern = ''.join(pattern_parts)

            return format_html(
                '<code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">{}</code>',
                pattern
            )

        number_format_display.short_description = _('Format')

        def current_number_display(self, obj):
            """Показва текущия номер и следващия"""
            # ✅ ИЗПОЛЗВАЙ СЕРВИСА ДИРЕКТНО!
            try:
                from ..services.numbering_service import NumberingService
                next_preview = NumberingService.get_next_preview_number(
                    document_type=obj.document_type,
                    location=None,
                    user=None
                )
            except Exception:
                # Simple fallback
                next_num = obj.current_number + 1
                if obj.prefix:
                    next_preview = f"{obj.prefix}{str(next_num).zfill(obj.digits_count)}"
                else:
                    next_preview = str(next_num).zfill(obj.digits_count)

            return format_html(
                'Current: <strong>{}</strong><br/>Next: <span style="color: #28a745;">{}</span>',
                obj.current_number,
                next_preview
            )

        current_number_display.short_description = _('Current/Next')
        current_number_display.admin_order_field = 'current_number'

        def fiscal_compliance(self, obj):
            """Проверява дали конфигурацията е фискално съобразена"""
            if obj.numbering_type != 'fiscal':
                return format_html('<span style="color: #6c757d;">N/A</span>')

            # ✅ ПОПРАВЕНО: Използвай NumberingService за валидация
            try:
                from ..services.numbering_service import NumberingService
                validation = NumberingService.validate_numbering_configuration(obj)

                if validation['valid']:
                    return format_html('<span style="color: #28a745;">✅ Compliant</span>')
                else:
                    issues = validation.get('issues', [])
                    first_issue = issues[0] if issues else 'Unknown issue'
                    return format_html(
                        '<span style="color: #dc3545;" title="{}">❌ Non-compliant</span>',
                        first_issue
                    )
            except Exception:
                # Simple fallback validation
                is_compliant = (
                        obj.numbering_type == 'fiscal' and
                        not obj.prefix and  # No prefix for fiscal
                        obj.digits_count >= 10  # At least 10 digits
                )

                if is_compliant:
                    return format_html('<span style="color: #28a745;">✅ Compliant</span>')
                else:
                    return format_html('<span style="color: #dc3545;">❌ Non-compliant</span>')

        fiscal_compliance.short_description = _('Fiscal')

        def is_default_badge(self, obj):
            """Показва дали е default конфигурация"""
            if obj.is_default:
                return format_html('<span style="color: #ffc107;">⭐ Default</span>')
            return ''

        is_default_badge.short_description = _('Default')
        is_default_badge.admin_order_field = 'is_default'

        def next_number_preview(self, obj):
            """Preview на следващите 5 номера"""
            try:
                preview = obj.preview_next_numbers(5)
                preview_html = '<br/>'.join([f'• {num}' for num in preview])
                return format_html('<div style="font-family: monospace;">{}</div>', preview_html)
            except Exception as e:
                return format_html('<span style="color: red;">Error: {}</span>', str(e))

        next_number_preview.short_description = _('Next Numbers Preview')

        def fiscal_compliance_check(self, obj):
            """Детайлна проверка за фискално съответствие"""
            if obj.numbering_type != 'fiscal':
                return format_html('<span style="color: #6c757d;">Not a fiscal configuration</span>')

            checks = []

            # Проверка за префикс
            if obj.prefix:
                checks.append('❌ Has prefix (fiscal should not have prefix)')
            else:
                checks.append('✅ No prefix')

            # Проверка за цифри
            if obj.digits_count >= 10:
                checks.append('✅ At least 10 digits')
            else:
                checks.append(f'❌ Only {obj.digits_count} digits (minimum 10 required)')

            # Проверка за yearly reset
            if obj.reset_yearly:
                checks.append('⚠️ Yearly reset enabled (not recommended for fiscal)')
            else:
                checks.append('✅ No yearly reset')

            return format_html('<br/>'.join(checks))

        fiscal_compliance_check.short_description = _('Fiscal Compliance Details')

        def usage_statistics(self, obj):
            """Статистики за използване"""
            stats = []

            # Location assignments
            location_count = obj.location_assignments.filter(is_active=True).count()
            if location_count > 0:
                stats.append(f'📍 {location_count} location(s)')

            # User preferences
            user_count = obj.user_preferences.count()
            if user_count > 0:
                stats.append(f'👤 {user_count} user preference(s)')

            # Numbers issued
            if obj.current_number > 0:
                stats.append(f'📄 {obj.current_number} numbers issued')

            if not stats:
                return format_html('<span style="color: #6c757d;">No usage data</span>')

            return format_html('<br/>'.join(stats))

        usage_statistics.short_description = _('Usage Statistics')

        actions = ['reset_counters', 'make_default', 'duplicate_config']

        def reset_counters(self, request, queryset):
            """Reset numbering counters to 0"""
            count = 0
            for config in queryset:
                config.reset_counter(0)
                count += 1

            self.message_user(
                request,
                f'Reset counters for {count} configurations to 0.'
            )

        reset_counters.short_description = _('Reset counters to 0')

        def make_default(self, request, queryset):
            """Make selected config default for its document type"""
            count = 0
            for config in queryset:
                # Remove default from other configs of same document type
                NumberingConfiguration.objects.filter(
                    document_type=config.document_type,
                    is_default=True
                ).update(is_default=False)

                # Set this as default
                config.is_default = True
                config.save()
                count += 1

            self.message_user(
                request,
                f'Set {count} configurations as default for their document types.'
            )

        make_default.short_description = _('Set as default')

        def duplicate_config(self, request, queryset):
            """Duplicate selected configurations"""
            count = 0
            for config in queryset:
                try:
                    # Създава дубликат с правилните полета
                    new_config = NumberingConfiguration(
                        name=f"{config.name} (Copy)",
                        code=f"{config.code}_copy",
                        document_type=config.document_type,
                        numbering_type=config.numbering_type,
                        prefix=config.prefix,
                        digits_count=config.digits_count,  # ✅ ПРАВИЛНО ПОЛЕ
                        current_number=0,
                        series_number=config.series_number + 1,  # Нова серия
                        series_name=f"{config.series_name} (Copy)" if config.series_name else "",
                        reset_yearly=config.reset_yearly,
                        last_reset_year=config.last_reset_year,  # ✅ ПРАВИЛНО ПОЛЕ
                        is_default=False,
                        max_number=config.max_number,
                        is_active=True,
                        description=f'Copy of {config.name}'
                    )
                    new_config.save()
                    count += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f'Error duplicating {config.name}: {e}',
                        level='ERROR'
                    )

            self.message_user(request, f'Duplicated {count} configurations.')

        duplicate_config.short_description = _('Duplicate configurations')

        # В purchases/admin.py - PurchaseRequestAdmin

        def save_model(self, request, obj, form, change):
            """Save numbering configuration"""
            if not change:  # Нов обект
                if hasattr(obj, 'created_by'):
                    obj.created_by = request.user
            super().save_model(request, obj, form, change)


    # =================================================================
    # LOCATION NUMBERING ASSIGNMENT ADMIN
    # =================================================================

    @admin.register(LocationNumberingAssignment)
    class LocationNumberingAssignmentAdmin(admin.ModelAdmin):
        """Админ за връзки location-numbering"""

        list_display = [
            'location',
            'numbering_config',
            'document_type_display',
            'series_display',
            'is_active_badge',
            'assigned_by',
            'assigned_at'
        ]

        list_filter = [
            'is_active',
            'numbering_config__document_type',
            'numbering_config__numbering_type',
            'assigned_at'
        ]

        search_fields = [
            'location__name',
            'numbering_config__name',
            'numbering_config__document_type__name'
        ]

        readonly_fields = [
            'assigned_at'
        ]

        raw_id_fields = ['location', 'numbering_config', 'assigned_by']

        date_hierarchy = 'assigned_at'

        def document_type_display(self, obj):
            """Показва типа документ"""
            return obj.numbering_config.document_type.name

        document_type_display.short_description = _('Document Type')
        document_type_display.admin_order_field = 'numbering_config__document_type__name'

        def series_display(self, obj):
            """Показва серията"""
            config = obj.numbering_config
            if config.series_name:
                return f"({config.series_number}) {config.series_name}"
            return f"({config.series_number})"

        series_display.short_description = _('Series')

        def is_active_badge(self, obj):
            """Показва дали е активно"""
            if obj.is_active:
                return format_html('<span style="color: #28a745;">✅ Active</span>')
            else:
                return format_html('<span style="color: #dc3545;">❌ Inactive</span>')

        is_active_badge.short_description = _('Status')
        is_active_badge.admin_order_field = 'is_active'

        def save_model(self, request, obj, form, change):
            """Auto-set assigned_by to current user if not set"""
            if not change:  # Creating new
                obj.assigned_by = request.user
            super().save_model(request, obj, form, change)


    # =================================================================
    # USER NUMBERING PREFERENCE ADMIN
    # =================================================================

    @admin.register(UserNumberingPreference)
    class UserNumberingPreferenceAdmin(admin.ModelAdmin):
        """Админ за user preferences"""

        list_display = [
            'user',
            'document_type',
            'preferred_config',
            'config_series',
            'created_at'
        ]

        list_filter = [
            'document_type',
            'preferred_config__numbering_type',
            'created_at'
        ]

        search_fields = [
            'user__username',
            'user__first_name',
            'user__last_name',
            'document_type__name',
            'preferred_config__name'
        ]

        raw_id_fields = ['user', 'preferred_config']

        readonly_fields = ['created_at']

        def config_series(self, obj):
            """Показва серията на конфигурацията"""
            config = obj.preferred_config
            if config.series_name:
                return f"({config.series_number}) {config.series_name}"
            return f"({config.series_number})"

        config_series.short_description = _('Series')

else:
    # Dummy classes if models don't exist
    class NumberingConfigurationAdmin:
        pass


    class LocationNumberingAssignmentAdmin:
        pass


    class UserNumberingPreferenceAdmin:
        pass