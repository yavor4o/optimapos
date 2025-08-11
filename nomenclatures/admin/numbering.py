# nomenclatures/admin/numbering.py - ПРОФЕСИОНАЛЕН АДМИН ЗА НОМЕРАЦИЯ

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Count, Max
from django.core.exceptions import ValidationError

# Try to import numbering models
try:
    from ..models.numbering import (
        NumberingConfiguration,
        LocationNumberingAssignment,
        UserNumberingPreference
    )

    HAS_NUMBERING = True
except ImportError:
    HAS_NUMBERING = False

if HAS_NUMBERING:

    # =================================================================
    # INLINE ADMINS
    # =================================================================

    class LocationNumberingAssignmentInline(admin.TabularInline):
        model = LocationNumberingAssignment
        extra = 1
        fields = [
            'location', 'is_active', 'assigned_at', 'assigned_by'
        ]
        readonly_fields = ['assigned_at', 'assigned_by']

        def save_model(self, request, obj, form, change):
            if not obj.assigned_by:
                obj.assigned_by = request.user
            super().save_model(request, obj, form, change)


    # =================================================================
    # MAIN NUMBERING CONFIGURATION ADMIN
    # =================================================================

    @admin.register(NumberingConfiguration)
    class NumberingConfigurationAdmin(admin.ModelAdmin):
        """
        Админ за конфигурация на номерация на документи

        Позволява настройка на:
        - Префикс и формат на номерата
        - Текущ номер и reset правила
        - Location assignments
        """

        list_display = [
            'name_display', 'document_type', 'numbering_pattern',
            'current_number_display', 'locations_count', 'is_default_display',
            'is_active'
        ]

        list_filter = [
            'document_type__app_name', 'document_type', 'numbering_type',
            'is_default', 'is_active'
        ]

        search_fields = [
            'name', 'code', 'prefix', 'document_type__name'
        ]

        readonly_fields = [
            'preview_next_numbers', 'usage_statistics', 'created_at', 'updated_at'
        ]

        fieldsets = (
            (_('Basic Information'), {
                'fields': (
                    'name', 'code', 'document_type', 'description'
                )
            }),
            (_('Numbering Format'), {
                'fields': (
                    'numbering_type', 'prefix', 'suffix', 'separator',
                    'number_length', 'preview_next_numbers'
                )
            }),
            (_('Current State'), {
                'fields': (
                    'current_number', 'last_reset_date'
                )
            }),
            (_('Settings'), {
                'fields': (
                    'is_default', 'is_active', 'sort_order'
                )
            }),
            (_('Statistics'), {
                'fields': ('usage_statistics',),
                'classes': ('collapse',)
            }),
            (_('System Info'), {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            }),
        )

        inlines = [LocationNumberingAssignmentInline]

        def name_display(self, obj):
            """Показва името с визуален индикатор"""
            icon = "🔢"
            if obj.numbering_type == 'fiscal':
                icon = "🧾"
            elif obj.is_default:
                icon = "⭐"

            return format_html(
                '{} <strong>{}</strong>',
                icon, obj.name
            )

        name_display.short_description = _('Name')

        def numbering_pattern(self, obj):
            """Показва pattern на номерирането"""
            pattern_parts = []

            if obj.prefix:
                pattern_parts.append(f'<span style="color: #2196F3;">{obj.prefix}</span>')

            if obj.separator and obj.prefix:
                pattern_parts.append(f'<span style="color: #757575;">{obj.separator}</span>')

            # Показва формата на числото
            number_placeholder = '#' * (obj.number_length or 4)
            pattern_parts.append(f'<span style="color: #4CAF50;">{number_placeholder}</span>')

            if obj.suffix:
                if obj.separator:
                    pattern_parts.append(f'<span style="color: #757575;">{obj.separator}</span>')
                pattern_parts.append(f'<span style="color: #FF9800;">{obj.suffix}</span>')

            pattern = ''.join(pattern_parts)

            return format_html(
                '<code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">{}</code>',
                pattern
            )

        numbering_pattern.short_description = _('Pattern')

        def current_number_display(self, obj):
            """Показва текущия номер и следващия"""
            try:
                next_preview = obj.get_next_number_preview()
                return format_html(
                    '<div>'
                    '<strong>Current:</strong> {}<br>'
                    '<strong>Next:</strong> <span style="color: #4CAF50;">{}</span>'
                    '</div>',
                    obj.current_number,
                    next_preview
                )
            except:
                return format_html(
                    '<strong>{}</strong><br><small style="color: #F44336;">Error</small>',
                    obj.current_number
                )

        current_number_display.short_description = _('Current/Next')

        def locations_count(self, obj):
            """Брой locations използващи тази конфигурация"""
            count = obj.location_assignments.filter(is_active=True).count()
            if count > 0:
                return format_html(
                    '<span style="background: #4CAF50; color: white; padding: 2px 6px; '
                    'border-radius: 3px; font-size: 11px;">{}</span>',
                    count
                )
            return format_html(
                '<span style="color: #757575;">0</span>'
            )

        locations_count.short_description = _('Locations')

        def is_default_display(self, obj):
            """Показва дали е default конфигурация"""
            if obj.is_default:
                return format_html(
                    '<span style="background: #FF9800; color: white; padding: 2px 6px; '
                    'border-radius: 3px; font-size: 10px;">DEFAULT</span>'
                )
            return '-'

        is_default_display.short_description = _('Default')

        def preview_next_numbers(self, obj):
            """Показва preview на следващите 5 номера"""
            if not obj.pk:
                return "Save first to see preview"

            try:
                previews = []
                temp_number = obj.current_number

                for i in range(1, 6):
                    temp_number += 1
                    preview = obj._format_number(temp_number)
                    previews.append(preview)

                preview_html = '<br>'.join([
                    f'<code style="background: #f0f8ff; padding: 2px 4px; margin: 1px;">{p}</code>'
                    for p in previews
                ])

                return format_html(
                    '<div style="font-family: monospace;">'
                    '<strong>Next 5 numbers:</strong><br>{}'
                    '</div>',
                    preview_html
                )
            except Exception as e:
                return f"Preview error: {e}"

        preview_next_numbers.short_description = _('Preview Next Numbers')

        def usage_statistics(self, obj):
            """Статистики за използването"""
            if not obj.pk:
                return "Save first to see statistics"

            try:
                # Брой locations
                locations_count = obj.location_assignments.filter(is_active=True).count()

                # Брой users с preferences
                users_count = obj.user_preferences.filter(user__is_active=True).count()

                # Тип номерация
                numbering_info = {
                    'fiscal': '🧾 Fiscal (10 digits)',
                    'internal': '📝 Internal (flexible)',
                    'custom': '⚙️ Custom format'
                }.get(obj.numbering_type, obj.numbering_type)

                stats_html = f"""
                <div style="font-size: 12px;">
                    <strong>Type:</strong> {numbering_info}<br>
                    <strong>Active Locations:</strong> {locations_count}<br>
                    <strong>User Preferences:</strong> {users_count}<br>
                    <strong>Numbers Used:</strong> {obj.current_number}<br>
                </div>
                """

                return format_html(stats_html)

            except Exception as e:
                return f"Statistics error: {e}"

        usage_statistics.short_description = _('Usage Statistics')

        def save_model(self, request, obj, form, change):
            """Set created_by for new configs"""
            if not change and not obj.created_by:
                obj.created_by = request.user
            super().save_model(request, obj, form, change)

        # Actions
        actions = ['reset_counters', 'duplicate_config', 'test_number_generation']

        def reset_counters(self, request, queryset):
            """Reset номерацията на избраните конфигурации"""
            count = 0
            for config in queryset:
                try:
                    config.reset_counter()
                    count += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f'Error resetting {config.name}: {e}',
                        level='ERROR'
                    )

            self.message_user(request, f'Reset {count} numbering configurations.')

        reset_counters.short_description = _('Reset counters to 0')

        def duplicate_config(self, request, queryset):
            """Дублира избраните конфигурации"""
            count = 0
            for config in queryset:
                try:
                    # Create duplicate
                    new_config = NumberingConfiguration.objects.create(
                        name=f'{config.name} (Copy)',
                        code=f'{config.code}_copy',
                        document_type=config.document_type,
                        numbering_type=config.numbering_type,
                        prefix=config.prefix,
                        suffix=config.suffix,
                        separator=config.separator,
                        number_length=config.number_length,
                        current_number=0,  # Start from 0
                        # reset_frequency=config.reset_frequency,  # ❌ КОМЕНТИРАНО
                        is_default=False,  # Never default
                        is_active=True,
                        created_by=request.user,
                        description=f'Copy of {config.name}'
                    )
                    count += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f'Error duplicating {config.name}: {e}',
                        level='ERROR'
                    )

            self.message_user(request, f'Duplicated {count} configurations.')

        duplicate_config.short_description = _('Duplicate configurations')

        def test_number_generation(self, request, queryset):
            """Тества генерирането на номера"""
            results = []
            for config in queryset:
                try:
                    next_number = config.get_next_number_preview()
                    results.append(f'{config.name}: {next_number}')
                except Exception as e:
                    results.append(f'{config.name}: ERROR - {e}')

            message = 'Test results:<br>' + '<br>'.join(results)
            self.message_user(request, format_html(message))

        test_number_generation.short_description = _('Test number generation')


    # =================================================================
    # LOCATION NUMBERING ASSIGNMENT ADMIN
    # =================================================================

    @admin.register(LocationNumberingAssignment)
    class LocationNumberingAssignmentAdmin(admin.ModelAdmin):
        """Админ за връзки location <-> numbering configuration"""

        list_display = [
            'location', 'numbering_config', 'document_type_display',
            'assignment_status', 'assigned_at', 'assigned_by'
        ]

        list_filter = [
            'is_active', 'numbering_config__document_type',
            'location', 'assigned_at'
        ]

        search_fields = [
            'location__name', 'numbering_config__name',
            'numbering_config__document_type__name'
        ]

        readonly_fields = ['assigned_at']

        def document_type_display(self, obj):
            """Показва document type"""
            return f"{obj.numbering_config.document_type.name}"

        document_type_display.short_description = _('Document Type')

        def assignment_status(self, obj):
            """Статус на assignment"""
            if obj.is_active:
                return format_html(
                    '<span style="color: #4CAF50;">✅ Active</span>'
                )
            else:
                return format_html(
                    '<span style="color: #757575;">❌ Inactive</span>'
                )

        assignment_status.short_description = _('Status')

        def save_model(self, request, obj, form, change):
            if not obj.assigned_by:
                obj.assigned_by = request.user
            super().save_model(request, obj, form, change)


    # =================================================================
    # USER NUMBERING PREFERENCE ADMIN
    # =================================================================

    @admin.register(UserNumberingPreference)
    class UserNumberingPreferenceAdmin(admin.ModelAdmin):
        """Админ за user preferences за номерация"""

        list_display = [
            'user', 'document_type', 'preferred_config', 'created_at'
        ]

        list_filter = [
            'document_type', 'preferred_config', 'created_at'
        ]

        search_fields = [
            'user__username', 'user__first_name', 'user__last_name',
            'document_type__name', 'preferred_config__name'
        ]

        readonly_fields = ['created_at']


else:
    # Dummy classes ако няма numbering models
    print("⚠️ Numbering models not found - admin classes not registered")