# nomenclatures/views/documents.py
"""
Document Type Views - PLACEHOLDER IMPLEMENTATION

TODO: Implement full CBV classes when document models are finalized
"""

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from nomenclatures.views.products import NomenclatureListMixin, NomenclatureViewMixin


class TemporaryMixin:
    """Temporary mixin to prevent import errors"""
    model = None
    template_name = 'frontend/nomenclatures/placeholder.html'

# =================================================================
# DOCUMENT TYPE VIEWS (PLACEHOLDER)
# =================================================================

class DocumentTypeListView(TemporaryMixin, NomenclatureListMixin, ListView):
    """Document Type listing view - PLACEHOLDER"""
    def get_page_title(self):
        return _("Document Types")

class DocumentTypeDetailView(TemporaryMixin, NomenclatureViewMixin, DetailView):
    """Document Type detail view - PLACEHOLDER"""
    pass

class DocumentTypeCreateView(TemporaryMixin, NomenclatureViewMixin, CreateView):
    """Document Type create view - PLACEHOLDER"""
    pass

class DocumentTypeUpdateView(TemporaryMixin, NomenclatureViewMixin, UpdateView):
    """Document Type update view - PLACEHOLDER"""
    pass

class DocumentTypeDeleteView(TemporaryMixin, NomenclatureViewMixin, DeleteView):
    """Document Type delete view - PLACEHOLDER"""
    success_url = reverse_lazy('nomenclatures:document_types')