# nomenclatures/views/workflow.py - MINIMAL VERSION
"""
Workflow Settings Views - MINIMAL PLACEHOLDER
"""

from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _


class WorkflowSettingsView(TemplateView):
    """Workflow Settings management view - PLACEHOLDER"""
    template_name = 'frontend/nomenclatures/placeholder.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': _("Workflow Settings"),
            'placeholder_message': _("Workflow Settings interface will be implemented here"),
        })
        return context