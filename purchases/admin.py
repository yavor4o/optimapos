# purchases/admin.py - FIXED FOR SmartDocumentTypeMixin

from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import PurchaseRequest, PurchaseRequestLine


# =================================================================
# INLINE ЗА РЕДОВЕТЕ - CLEAN & SIMPLE
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = ['product', 'requested_quantity', 'unit', 'estimated_price']

    # line_number се генерира автоматично в save()

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0  # purchases/admin.py - FIXED FOR SmartDocumentTypeMixin


from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import PurchaseRequest, PurchaseRequestLine


# =================================================================
# CUSTOM FORM - РАБОТИ С SmartDocumentTypeMixin
# =================================================================

class PurchaseRequestForm(forms.ModelForm):
    """Custom form за PurchaseRequest - скрива document_type и status"""

    class Meta:
        model = PurchaseRequest
        fields = [
            'supplier', 'location', 'urgency_level',
            'request_type', 'business_justification', 'expected_usage',
            'requested_by'
        ]
        # document_type и status са readonly - НЕ са в form fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set defaults САМО за полета които са в form
        if not self.instance.pk:
            self.fields['urgency_level'].initial = 'normal'
            self.fields['request_type'].initial = 'regular'
            # status се слага автоматично в model.save() - НЕ тук!

    def clean(self):
        """МИНИМАЛНА form validation - БЕЗ document_type"""
        cleaned_data = super().clean()

        # САМО основна валидация
        if cleaned_data.get('urgency_level') == 'critical':
            if not cleaned_data.get('business_justification'):
                raise ValidationError({
                    'business_justification': 'Critical requests require business justification'
                })

        return cleaned_data


# =================================================================
# INLINE ЗА РЕДОВЕТЕ - CLEAN БЕЗ MONKEY PATCHING
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = ['product', 'requested_quantity', 'unit', 'estimated_price']

    # line_number се генерира автоматично в BaseDocumentLine.save()

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


# =================================================================
# ADMIN - ИЗПОЛЗВА CUSTOM FORM
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """FIXED админ с auto status и readonly полета"""

    # ИЗПОЛЗВАМЕ CUSTOM FORM
    form = PurchaseRequestForm

    list_display = ['document_number', 'supplier', 'status', 'urgency_level', 'created_at']
    list_filter = ['status', 'urgency_level', 'supplier']
    search_fields = ['document_number', 'supplier__name']

    # READONLY ПОЛЕТА - auto-generated + auto-detected
    readonly_fields = [
        'document_number', 'document_type', 'status',  # ДОБАВИ status тук
        'created_at', 'updated_at', 'created_by', 'updated_by'
    ]

    # FIELDSETS - status и document_type са readonly
    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'location')
        }),
        ('Document Info', {
            'fields': ('document_type', 'document_number', 'status'),  # readonly полета
            'classes': ('collapse',)
        }),
        ('Request Details', {
            'fields': ('urgency_level', 'request_type', 'requested_by')
        }),
        ('Justification', {
            'fields': ('business_justification', 'expected_usage'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    # INLINE ЗА РЕДОВЕТЕ
    inlines = [PurchaseRequestLineInline]

    def save_model(self, request, obj, form, change):
        """Set user info - SmartDocumentTypeMixin + BaseDocument се грижат за останалото"""
        if not change:  # Нов обект
            obj.requested_by = request.user
            obj.created_by = request.user

        obj.updated_by = request.user

        # SmartDocumentTypeMixin автоматично ще намери document_type в obj.save()
        # BaseDocument автоматично ще сложи status = document_type.default_status
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        """Default стойности за нови заявки - БЕЗ status и document_type (автоматични)"""
        return {
            'urgency_level': 'normal',
            'request_type': 'regular',
            'requested_by': request.user,
            # status и document_type се слагат автоматично в model.save()
        }