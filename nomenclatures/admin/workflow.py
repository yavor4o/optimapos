# nomenclatures/admin/workflow.py
from django.contrib import admin

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
        list_display = ['action', 'actor', 'timestamp']  # ← ПОПРАВЕНО
        list_filter = ['action', 'timestamp']  # ← ПОПРАВЕНО
        readonly_fields = ['action', 'actor', 'timestamp', 'from_status', 'to_status']  # ← ПОПРАВЕНО

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False