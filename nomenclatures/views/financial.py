# nomenclatures/views/financial.py - MINIMAL VERSION
"""
Financial Nomenclature Views - MINIMAL PLACEHOLDER
"""

from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _


class PlaceholderView(TemplateView):
    """Generic placeholder view"""
    template_name = 'frontend/nomenclatures/placeholder.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': _("Coming Soon"),
            'placeholder_message': _("This feature is under development."),
        })
        return context


# All Financial Views as Placeholders
CurrencyListView = type('CurrencyListView', (PlaceholderView,), {})
CurrencyDetailView = type('CurrencyDetailView', (PlaceholderView,), {})
CurrencyCreateView = type('CurrencyCreateView', (PlaceholderView,), {})
CurrencyUpdateView = type('CurrencyUpdateView', (PlaceholderView,), {})
CurrencyDeleteView = type('CurrencyDeleteView', (PlaceholderView,), {})

TaxGroupListView = type('TaxGroupListView', (PlaceholderView,), {})
TaxGroupDetailView = type('TaxGroupDetailView', (PlaceholderView,), {})
TaxGroupCreateView = type('TaxGroupCreateView', (PlaceholderView,), {})
TaxGroupUpdateView = type('TaxGroupUpdateView', (PlaceholderView,), {})
TaxGroupDeleteView = type('TaxGroupDeleteView', (PlaceholderView,), {})

PriceGroupListView = type('PriceGroupListView', (PlaceholderView,), {})
PriceGroupDetailView = type('PriceGroupDetailView', (PlaceholderView,), {})
PriceGroupCreateView = type('PriceGroupCreateView', (PlaceholderView,), {})
PriceGroupUpdateView = type('PriceGroupUpdateView', (PlaceholderView,), {})
PriceGroupDeleteView = type('PriceGroupDeleteView', (PlaceholderView,), {})