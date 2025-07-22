# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe

from core.models.company import Company




@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    Company admin - Singleton pattern

    Only one company record allowed. Manages system-wide VAT settings.
    """

    list_display = [
        'name', 'vat_status_display', 'phone', 'email', 'created_at'
    ]

    search_fields = ['name', 'vat_number', 'phone', 'email']

    readonly_fields = [
        'created_at', 'updated_at', 'vat_validation_status', 'system_impact_info'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'registration_number', 'address')
        }),
        (_('Contact Information'), {
            'fields': ('phone', 'email'),
            'classes': ('collapse',)
        }),
        (_('VAT Settings'), {
            'fields': (
                'vat_registered', 'vat_number', 'default_vat_rate',
                'vat_registration_date', 'vat_validation_status'
            ),
            'description': _(
                '<strong>Important:</strong> VAT registration status affects entire system behavior. '
                'Changing this will trigger inventory revaluation.'
            )
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at', 'system_impact_info'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Only show the single company record"""
        return super().get_queryset(request)

    def has_add_permission(self, request):
        """Only allow adding if no company exists"""
        return not Company.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Never allow deleting the company"""
        return False

    def save_model(self, request, obj, form, change):
        """Handle VAT status changes"""

        # Check if VAT status is changing
        vat_status_changed = False
        if change:
            try:
                original = Company.objects.get(pk=obj.pk)
                vat_status_changed = original.vat_registered != obj.vat_registered
            except Company.DoesNotExist:
                pass

        # Save the model
        super().save_model(request, obj, form, change)

        # Handle VAT status change consequences
        if vat_status_changed:
            if obj.vat_registered:
                self.message_user(
                    request,
                    format_html(
                        '<strong>VAT Registration Activated!</strong><br>'
                        'System will revalue inventory costs excluding VAT. '
                        '<a href="/admin/inventory/inventoryitem/">Check inventory</a> for changes.'
                    ),
                    level='WARNING'
                )
                # TODO: Trigger revaluation (will be implemented in ФАЗА 4)
                # obj.trigger_vat_status_change_revaluation()
            else:
                self.message_user(
                    request,
                    format_html(
                        '<strong>VAT Registration Deactivated!</strong><br>'
                        'System will now include VAT in all cost calculations.'
                    ),
                    level='WARNING'
                )

    # =====================
    # DISPLAY METHODS
    # =====================

    def vat_status_display(self, obj):
        """Display VAT status with visual indicator"""
        if obj.vat_registered:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ VAT Registered</span><br>'
                '<small>{}</small>',
                obj.vat_number or 'No VAT number'
            )
        else:
            return format_html(
                '<span style="color: orange; font-weight: bold;">✗ Not VAT Registered</span>'
            )

    vat_status_display.short_description = _('VAT Status')

    def vat_validation_status(self, obj):
        """Show VAT number validation status"""
        if not obj.vat_registered:
            return mark_safe('<span style="color: gray;">N/A (not VAT registered)</span>')

        if not obj.vat_number:
            return mark_safe('<span style="color: red;">❌ VAT number missing</span>')

        if obj.validate_vat_number():
            return mark_safe('<span style="color: green;">✅ Valid format</span>')
        else:
            return mark_safe('<span style="color: orange;">⚠️ Invalid format</span>')

    vat_validation_status.short_description = _('VAT Number Validation')

    def system_impact_info(self, obj):
        """Show how this company's settings affect the system"""
        if not obj.pk:
            return "Save company first to see system impact"

        # Get some basic statistics (will be enhanced in later phases)
        impact_info = [
            f"<strong>VAT Status:</strong> {obj.get_vat_status_display()}",
            f"<strong>Default VAT Rate:</strong> {obj.default_vat_rate}%",
        ]

        if obj.vat_registered:
            impact_info.extend([
                "<strong>Purchase Documents:</strong> Prices recorded excluding VAT",
                "<strong>Sales Documents:</strong> VAT calculated and shown separately",
                "<strong>Inventory Costs:</strong> Stored excluding VAT",
                "<strong>Cost Calculations:</strong> Based on net amounts"
            ])
        else:
            impact_info.extend([
                "<strong>Purchase Documents:</strong> Prices recorded including VAT",
                "<strong>Sales Documents:</strong> No VAT calculations",
                "<strong>Inventory Costs:</strong> Stored including VAT",
                "<strong>Cost Calculations:</strong> Based on gross amounts"
            ])

        return mark_safe('<br>'.join(impact_info))

    system_impact_info.short_description = _('System Impact')

    # =====================
    # CUSTOM ACTIONS
    # =====================

    def get_actions(self, request):
        """Remove default delete action"""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions