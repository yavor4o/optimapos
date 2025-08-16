# nomenclatures/views/documents.py - MINIMAL VERSION
"""
Document Type Views - MINIMAL PLACEHOLDER
"""

from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _


class PlaceholderView(TemplateView):
    """Generic placeholder view"""
    template_name = 'frontend/nomenclatures/product/product_groups_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': _("Coming Soon"),
            'placeholder_message': _("This feature is under development."),
        })
        return context


# All Document Views as Placeholders
DocumentTypeListView = type('DocumentTypeListView', (PlaceholderView,), {})
DocumentTypeDetailView = type('DocumentTypeDetailView', (PlaceholderView,), {})
DocumentTypeCreateView = type('DocumentTypeCreateView', (PlaceholderView,), {})
DocumentTypeUpdateView = type('DocumentTypeUpdateView', (PlaceholderView,), {})
DocumentTypeDeleteView = type('DocumentTypeDeleteView', (PlaceholderView,), {})