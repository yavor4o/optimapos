# nomenclatures/admin/documents.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from ..models import DocumentType


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'type_key', 'app_name',
        'affects_inventory_display', 'requires_approval_display',
        'current_number', 'is_active'
    ]

    list_filter = [
        'app_name', 'type_key', 'affects_inventory',
        'requires_approval', 'is_fiscal', 'pos_document', 'is_active'
    ]

    search_fields = ['code', 'name', 'type_key', 'number_prefix']

    readonly_fields = ['current_number', 'last_reset_year']

    fieldsets = [
        ('Basic Information', {
            'fields': ['code', 'name', 'type_key', 'app_name', 'model_name', 'is_active', 'sort_order']
        }),
        ('Numbering System', {
            'fields': [
                'number_prefix', 'current_number', 'number_format',
                'reset_numbering_yearly', 'last_reset_year', 'auto_number'
            ]
        }),
        ('Workflow Configuration', {
            'fields': [
                'allowed_statuses', 'default_status', 'status_transitions',
                 'final_statuses'
            ],
            'description': 'Configure status workflow for this document type'
        }),
        ('Approval Settings', {
            'fields': [
                'requires_approval',

            ]
        }),
        ('Business Behavior', {
            'fields': [
                'affects_inventory', 'inventory_direction', 'inventory_timing',
                'is_fiscal', 'requires_vat_calculation', 'requires_payment',

            ]
        }),


        ('Quality & Compliance', {
            'fields': [
                'requires_batch_tracking', 'requires_expiry_dates',
                'requires_serial_numbers', 'requires_quality_check',
                'requires_certificates'
            ]
        }),

        ('POS Integration', {
            'fields': [
                'pos_document', 'prints_receipt', 'opens_cash_drawer'
            ],
            'classes': ['collapse']
        }),
        ('Automation Settings', {
            'fields': [
                'auto_confirm', 'requires_lines'
            ]
        }),
        ('Validation Rules', {
            'fields': [
                'min_total_amount', 'max_total_amount'
            ],
            'classes': ['collapse']
        })
    ]

    # Custom display methods
    def affects_inventory_display(self, obj):
        if obj.affects_inventory:
            direction = obj.get_inventory_direction_display() if obj.inventory_direction else 'Unknown'
            return format_html(
                '<span style="color: green;">✅ {}</span>',
                direction
            )
        return format_html('<span style="color: gray;">—</span>')

    affects_inventory_display.short_description = _('Inventory Impact')

    def requires_approval_display(self, obj):
        if obj.requires_approval:
            # ПРЕМАХНИ approval_limit референцията
            return format_html(
                '<span style="color: orange;">⚠️ Yes</span>'
            )
        return format_html('<span style="color: green;">✅ No</span>')

    requires_approval_display.short_description = _('Approval Required')



    # Actions
    actions = ['reset_numbering', 'activate_types', 'deactivate_types']

    def reset_numbering(self, request, queryset):
        for doc_type in queryset:
            doc_type.reset_numbering()
        self.message_user(request, f'Numbering reset for {queryset.count()} document types.')

    reset_numbering.short_description = "Reset numbering to 0"

    def activate_types(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} document types activated.')

    activate_types.short_description = "Activate selected document types"

    def deactivate_types(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} document types deactivated.')

    deactivate_types.short_description = "Deactivate selected document types"

    # Filter for better UX
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "allowed_source_types":
            kwargs["queryset"] = DocumentType.objects.filter(is_active=True).order_by('app_name', 'name')
        return super().formfield_for_manytomany(db_field, request, **kwargs)