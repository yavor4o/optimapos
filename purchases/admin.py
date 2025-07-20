# purchases/admin.py - ФИНАЛЕН ПРОСТ АДМИН

from django.contrib import admin
from .models import PurchaseRequest, PurchaseRequestLine


# =================================================================
# INLINE ЗА РЕДОВЕТЕ
# =================================================================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = ['product', 'requested_quantity', 'unit', 'estimated_price']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0


# =================================================================
# ПРОСТ АДМИН - САМО НУЖНИТЕ ПОЛЕТА
# =================================================================

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """Прост админ - само полетата които потребителят попълва"""

    list_display = ['document_number', 'supplier', 'status', 'urgency_level', 'created_at']
    list_filter = ['status', 'urgency_level', 'supplier']

    # СКРИВАМЕ AUTO-GENERATED ПОЛЕТА
    exclude = [
        'document_type',  # Auto-detected от SmartDocumentTypeMixin
        'document_number',  # Auto-generated
        'created_at',  # Auto timestamp
        'updated_at',  # Auto timestamp
        'created_by',  # Auto от save_model
        'updated_by',  # Auto от save_model
    ]

    # ПОКАЗВАМЕ САМО ПОЛЕТАТА КОИТО ТРЯБВА ДА СЕ ПОПЪЛНЯТ
    fields = [
        'supplier',  # ЗАДЪЛЖИТЕЛНО
        'location',  # ЗАДЪЛЖИТЕЛНО
        'status',  # ЗАДЪЛЖИТЕЛНО (default: draft)
        'urgency_level',  # Избор от dropdown
        'request_type',  # Избор от dropdown
        'business_justification',  # Текст защо е нужна заявката
        'expected_usage',  # Как ще се използва
        'requested_by',  # Auto-set в save_model
    ]

    # INLINE ЗА РЕДОВЕТЕ
    inlines = [PurchaseRequestLineInline]

    def save_model(self, request, obj, form, change):
        """Set user info - SmartDocumentTypeMixin се грижи за document_type"""
        if not change:
            obj.requested_by = request.user
            obj.created_by = request.user
        obj.updated_by = request.user

        # SmartDocumentTypeMixin автоматично ще намери document_type
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        """Default стойности за нова заявка"""
        return {
            'status': 'draft',
            'urgency_level': 'normal',
            'request_type': 'regular',
            'requested_by': request.user,
        }