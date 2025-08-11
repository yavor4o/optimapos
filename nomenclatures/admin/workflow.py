# nomenclatures/admin/workflow.py
from django.contrib import admin

# Try to import models
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_MODELS = True
except ImportError:
    HAS_MODELS = False

if HAS_MODELS:
    @admin.register(ApprovalRule)
    class ApprovalRuleAdmin(admin.ModelAdmin):
        list_display = ['name', 'document_type', 'is_active']
        list_filter = ['document_type', 'is_active']
        search_fields = ['name']


    @admin.register(ApprovalLog)
    class ApprovalLogAdmin(admin.ModelAdmin):
        list_display = ['action', 'is_active']
        list_filter = ['action', 'is_active']
        readonly_fields = ['action']

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False