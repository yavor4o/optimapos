# nomenclatures/admin/documents.py
from django.contrib import admin
from ..models import DocumentType


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'app_name',
        'type_key',
        'affects_inventory',
        'requires_approval',
        'is_fiscal',
        'is_active'
    ]

    list_filter = [
        'app_name',
        'affects_inventory',
        'requires_approval',
        'is_fiscal',
        'is_active'
    ]

    search_fields = ['name', 'type_key', 'app_name']
    ordering = ['app_name', 'name']