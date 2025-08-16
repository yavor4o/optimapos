# nomenclatures/views/financial.py
"""
Financial Nomenclature Views - PLACEHOLDER IMPLEMENTATION

TODO: Implement full CBV classes when financial models are finalized
"""

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from .product import NomenclatureViewMixin, NomenclatureListMixin
# TODO: Import actual models when ready
# from ..models import Currency, TaxGroup, PriceGroup

class TemporaryMixin:
    """Temporary mixin to prevent import errors"""
    model = None
    template_name = 'frontend/nomenclatures/placeholder.html'

# =================================================================
# CURRENCY VIEWS (PLACEHOLDER)
# =================================================================

class CurrencyListView(TemporaryMixin, NomenclatureListMixin, ListView):
    """Currency listing view - PLACEHOLDER"""
    def get_page_title(self):
        return _("Currencies")

class CurrencyDetailView(TemporaryMixin, NomenclatureViewMixin, DetailView):
    """Currency detail view - PLACEHOLDER"""
    pass

class CurrencyCreateView(TemporaryMixin, NomenclatureViewMixin, CreateView):
    """Currency create view - PLACEHOLDER"""
    pass

class CurrencyUpdateView(TemporaryMixin, NomenclatureViewMixin, UpdateView):
    """Currency update view - PLACEHOLDER"""
    pass

class CurrencyDeleteView(TemporaryMixin, NomenclatureViewMixin, DeleteView):
    """Currency delete view - PLACEHOLDER"""
    success_url = reverse_lazy('nomenclatures:currencies')

# =================================================================
# TAX GROUP VIEWS (PLACEHOLDER)
# =================================================================

class TaxGroupListView(TemporaryMixin, NomenclatureListMixin, ListView):
    """Tax Group listing view - PLACEHOLDER"""
    def get_page_title(self):
        return _("Tax Groups")

class TaxGroupDetailView(TemporaryMixin, NomenclatureViewMixin, DetailView):
    """Tax Group detail view - PLACEHOLDER"""
    pass

class TaxGroupCreateView(TemporaryMixin, NomenclatureViewMixin, CreateView):
    """Tax Group create view - PLACEHOLDER"""
    pass

class TaxGroupUpdateView(TemporaryMixin, NomenclatureViewMixin, UpdateView):
    """Tax Group update view - PLACEHOLDER"""
    pass

class TaxGroupDeleteView(TemporaryMixin, NomenclatureViewMixin, DeleteView):
    """Tax Group delete view - PLACEHOLDER"""
    success_url = reverse_lazy('nomenclatures:tax_groups')

# =================================================================
# PRICE GROUP VIEWS (PLACEHOLDER)
# =================================================================

class PriceGroupListView(TemporaryMixin, NomenclatureListMixin, ListView):
    """Price Group listing view - PLACEHOLDER"""
    def get_page_title(self):
        return _("Price Groups")

class PriceGroupDetailView(TemporaryMixin, NomenclatureViewMixin, DetailView):
    """Price Group detail view - PLACEHOLDER"""
    pass

class PriceGroupCreateView(TemporaryMixin, NomenclatureViewMixin, CreateView):
    """Price Group create view - PLACEHOLDER"""
    pass

class PriceGroupUpdateView(TemporaryMixin, NomenclatureViewMixin, UpdateView):
    """Price Group update view - PLACEHOLDER"""
    pass

class PriceGroupDeleteView(TemporaryMixin, NomenclatureViewMixin, DeleteView):
    """Price Group delete view - PLACEHOLDER"""
    success_url = reverse_lazy('nomenclatures:price_groups')