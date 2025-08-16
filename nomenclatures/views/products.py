# nomenclatures/views/product.py - MINIMAL VERSION
"""
Product Classification Views - MINIMAL IMPLEMENTATION FOR TESTING
"""

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from ..models import ProductGroup, Brand, ProductType


# =================================================================
# BASE MIXINS - MINIMAL
# =================================================================

class NomenclatureViewMixin(LoginRequiredMixin):
    """Base mixin for all nomenclature views"""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': self.get_page_title(),
            'page_description': self.get_page_description(),
        })
        return context

    def get_page_title(self):
        return _("Nomenclature Management")

    def get_page_description(self):
        return _("Manage system nomenclatures")


class NomenclatureListMixin(NomenclatureViewMixin):
    """Mixin for list views"""
    paginate_by = 25
    ordering = ['sort_order', 'name']


# =================================================================
# PRODUCT GROUP VIEWS - MINIMAL
# =================================================================

class ProductGroupListView(NomenclatureListMixin, ListView):
    """Minimal ProductGroup ListView"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_list.html'
    context_object_name = 'product_groups'

    def get_page_title(self):
        return _("Product Groups")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_count': ProductGroup.objects.count(),
            'active_count': ProductGroup.objects.filter(is_active=True).count(),
            'inactive_count': ProductGroup.objects.filter(is_active=False).count(),
            'can_create': True,
            'create_url': reverse_lazy('nomenclatures:product_groups_create'),
            'view_mode': 'flat',
        })
        return context


class ProductGroupDetailView(NomenclatureViewMixin, DetailView):
    """Minimal ProductGroup DetailView"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/placeholder.html'


class ProductGroupCreateView(NomenclatureViewMixin, CreateView):
    """Minimal ProductGroup CreateView"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/placeholder.html'
    fields = ['code', 'name', 'parent', 'description', 'sort_order', 'is_active']
    success_url = reverse_lazy('nomenclatures:product_groups')


class ProductGroupUpdateView(NomenclatureViewMixin, UpdateView):
    """Minimal ProductGroup UpdateView"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/placeholder.html'
    fields = ['code', 'name', 'parent', 'description', 'sort_order', 'is_active']
    success_url = reverse_lazy('nomenclatures:product_groups')


class ProductGroupDeleteView(NomenclatureViewMixin, DeleteView):
    """Minimal ProductGroup DeleteView"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/placeholder.html'
    success_url = reverse_lazy('nomenclatures:product_groups')


# =================================================================
# PLACEHOLDER VIEWS FOR BRANDS & PRODUCT TYPES
# =================================================================

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


# Brand Views - All Placeholders
BrandListView = type('BrandListView', (PlaceholderView,), {})
BrandDetailView = type('BrandDetailView', (PlaceholderView,), {})
BrandCreateView = type('BrandCreateView', (PlaceholderView,), {})
BrandUpdateView = type('BrandUpdateView', (PlaceholderView,), {})
BrandDeleteView = type('BrandDeleteView', (PlaceholderView,), {})

# Product Type Views - All Placeholders
ProductTypeListView = type('ProductTypeListView', (PlaceholderView,), {})
ProductTypeDetailView = type('ProductTypeDetailView', (PlaceholderView,), {})
ProductTypeCreateView = type('ProductTypeCreateView', (PlaceholderView,), {})
ProductTypeUpdateView = type('ProductTypeUpdateView', (PlaceholderView,), {})
ProductTypeDeleteView = type('ProductTypeDeleteView', (PlaceholderView,), {})