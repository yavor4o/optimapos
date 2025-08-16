# nomenclatures/views/product.py
"""
Product Classification Views - Professional CBV Implementation

АРХИТЕКТУРА:
- Всички views наследяват от Django Generic CBVs
- Локализация на всички strings
- Permission mixins за security
- Consistent error handling
- KT UI integration
"""

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Count
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from ..models import ProductGroup, Brand, ProductType


# =================================================================
# BASE MIXINS FOR NOMENCLATURES
# =================================================================

class NomenclatureViewMixin(LoginRequiredMixin):
    """Base mixin for all nomenclature views"""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'app_name': 'nomenclatures',
            'module_name': self.get_module_name(),
            'page_title': self.get_page_title(),
            'page_description': self.get_page_description(),
            'breadcrumbs': self.get_breadcrumbs(),
        })
        return context

    def get_module_name(self):
        """Override in subclasses"""
        return _("Nomenclatures")

    def get_page_title(self):
        """Override in subclasses"""
        return _("Nomenclature Management")

    def get_page_description(self):
        """Override in subclasses"""
        return _("Manage system nomenclatures")

    def get_breadcrumbs(self):
        """Override in subclasses"""
        return [
            {'name': _("Dashboard"), 'url': '/'},
            {'name': _("Nomenclatures"), 'url': reverse('nomenclatures:product_groups')},
        ]


class NomenclatureListMixin(NomenclatureViewMixin):
    """Mixin for list views with search and filtering"""
    paginate_by = 25
    ordering = ['sort_order', 'name']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Search functionality
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(code__icontains=search_query) |
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Status filter
        status_filter = self.request.GET.get('status', '')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'status_filter': self.request.GET.get('status', ''),
            'total_count': self.get_queryset().count(),
            'active_count': self.model.objects.filter(is_active=True).count(),
            'inactive_count': self.model.objects.filter(is_active=False).count(),
        })
        return context


# =================================================================
# PRODUCT GROUP VIEWS
# =================================================================

class ProductGroupListView(NomenclatureListMixin, ListView):
    """Professional ListView for Product Groups with tree display"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_list.html'
    context_object_name = 'product_groups'

    def get_module_name(self):
        return _("Product Classifications")

    def get_page_title(self):
        return _("Product Groups")

    def get_page_description(self):
        return _("Hierarchical product group management with tree structure")

    def get_breadcrumbs(self):
        return [
            {'name': _("Dashboard"), 'url': '/'},
            {'name': _("Nomenclatures"), 'url': '#'},
            {'name': _("Product Groups"), 'url': ''},
        ]

    def get_queryset(self):
        """Get queryset with tree annotations"""
        queryset = super().get_queryset()

        # Add tree-specific annotations
        queryset = queryset.select_related('parent').prefetch_related('children')

        # For tree display, we might want to show only root nodes initially
        show_tree = self.request.GET.get('view', 'flat') == 'tree'
        if show_tree:
            queryset = queryset.filter(parent__isnull=True)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'view_mode': self.request.GET.get('view', 'flat'),
            'create_url': reverse('nomenclatures:product_groups_create'),
            'can_create': True,  # TODO: Add permission check
            'tree_data': self.get_tree_data() if self.request.GET.get('view') == 'tree' else None,
        })
        return context

    def get_tree_data(self):
        """Get hierarchical tree data for JavaScript tree component"""

        def build_tree_node(group):
            return {
                'id': group.pk,
                'text': f"{group.code} - {group.name}",
                'icon': 'ki-filled ki-abstract-14',
                'state': {'opened': True if group.level < 2 else False},
                'children': [build_tree_node(child) for child in group.get_children()],
                'li_attr': {'class': 'tree-node'},
                'a_attr': {
                    'href': reverse('nomenclatures:product_groups_detail', kwargs={'pk': group.pk}),
                    'class': 'tree-link'
                }
            }

        roots = ProductGroup.objects.filter(parent__isnull=True)
        return [build_tree_node(root) for root in roots]


class ProductGroupDetailView(NomenclatureViewMixin, DetailView):
    """Detailed view for Product Group with children display"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_detail.html'
    context_object_name = 'product_group'

    def get_page_title(self):
        return f"{_('Product Group')}: {self.object.name}"

    def get_page_description(self):
        return _("View product group details and hierarchy")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'children': self.object.get_children(),
            'ancestors': self.object.get_ancestors(),
            'edit_url': reverse('nomenclatures:product_groups_edit', kwargs={'pk': self.object.pk}),
            'delete_url': reverse('nomenclatures:product_groups_delete', kwargs={'pk': self.object.pk}),
            'can_edit': True,  # TODO: Add permission check
            'can_delete': self.object.can_delete()[0],
        })
        return context


class ProductGroupCreateView(NomenclatureViewMixin, SuccessMessageMixin, CreateView):
    """Create view for Product Groups"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_form.html'
    fields = ['code', 'name', 'parent', 'description', 'sort_order', 'is_active']
    success_message = _("Product group '%(name)s' was created successfully.")

    def get_page_title(self):
        return _("Create Product Group")

    def get_page_description(self):
        return _("Add new product group to the hierarchy")

    def get_success_url(self):
        return reverse('nomenclatures:product_groups_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form_title': _("Create New Product Group"),
            'submit_text': _("Create Product Group"),
            'cancel_url': reverse('nomenclatures:product_groups'),
        })
        return context


class ProductGroupUpdateView(NomenclatureViewMixin, SuccessMessageMixin, UpdateView):
    """Update view for Product Groups"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_form.html'
    fields = ['code', 'name', 'parent', 'description', 'sort_order', 'is_active']
    success_message = _("Product group '%(name)s' was updated successfully.")

    def get_page_title(self):
        return f"{_('Edit Product Group')}: {self.object.name}"

    def get_page_description(self):
        return _("Update product group information")

    def get_success_url(self):
        return reverse('nomenclatures:product_groups_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form_title': f"{_('Edit')}: {self.object.name}",
            'submit_text': _("Update Product Group"),
            'cancel_url': reverse('nomenclatures:product_groups_detail', kwargs={'pk': self.object.pk}),
        })
        return context


class ProductGroupDeleteView(NomenclatureViewMixin, DeleteView):
    """Delete view for Product Groups with validation"""
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return f"{_('Delete Product Group')}: {self.object.name}"

    def get_page_description(self):
        return _("Confirm deletion of product group")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check if can delete
        can_delete, reason = self.object.can_delete()
        if not can_delete:
            messages.error(request, reason)
            return self.get(request, *args, **kwargs)

        # Perform deletion
        success_message = _("Product group '%(name)s' was deleted successfully.") % {'name': self.object.name}
        messages.success(request, success_message)

        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get deletion warnings
        can_delete, reason = self.object.can_delete()
        context.update({
            'can_delete': can_delete,
            'deletion_reason': reason,
            'children_count': self.object.get_children().count(),
            'cancel_url': reverse('nomenclatures:product_groups_detail', kwargs={'pk': self.object.pk}),
        })
        return context


# =================================================================
# BRAND VIEWS (Future Implementation)
# =================================================================

class BrandListView(NomenclatureListMixin, ListView):
    """Brand listing view - PLACEHOLDER"""
    model = Brand
    template_name = 'nomenclatures/product/brands_list.html'
    context_object_name = 'brands'

    def get_page_title(self):
        return _("Brands")


class BrandDetailView(NomenclatureViewMixin, DetailView):
    """Brand detail view - PLACEHOLDER"""
    model = Brand
    template_name = 'nomenclatures/product/brands_detail.html'


class BrandCreateView(NomenclatureViewMixin, CreateView):
    """Brand create view - PLACEHOLDER"""
    model = Brand
    template_name = 'nomenclatures/product/brands_form.html'
    fields = ['code', 'name', 'logo', 'website', 'description', 'is_active']


class BrandUpdateView(NomenclatureViewMixin, UpdateView):
    """Brand update view - PLACEHOLDER"""
    model = Brand
    template_name = 'nomenclatures/product/brands_form.html'
    fields = ['code', 'name', 'logo', 'website', 'description', 'is_active']


class BrandDeleteView(NomenclatureViewMixin, DeleteView):
    """Brand delete view - PLACEHOLDER"""
    model = Brand
    template_name = 'nomenclatures/product/brands_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:brands')


# =================================================================
# PRODUCT TYPE VIEWS (Future Implementation)
# =================================================================

class ProductTypeListView(NomenclatureListMixin, ListView):
    """Product Type listing view - PLACEHOLDER"""
    model = ProductType
    template_name = 'nomenclatures/product/product_types_list.html'
    context_object_name = 'product_types'


class ProductTypeDetailView(NomenclatureViewMixin, DetailView):
    """Product Type detail view - PLACEHOLDER"""
    model = ProductType
    template_name = 'nomenclatures/product/product_types_detail.html'


class ProductTypeCreateView(NomenclatureViewMixin, CreateView):
    """Product Type create view - PLACEHOLDER"""
    model = ProductType
    template_name = 'nomenclatures/product/product_types_form.html'
    fields = ['code', 'name', 'category', 'requires_expiry_date', 'description', 'is_active']


class ProductTypeUpdateView(NomenclatureViewMixin, UpdateView):
    """Product Type update view - PLACEHOLDER"""
    model = ProductType
    template_name = 'nomenclatures/product/product_types_form.html'
    fields = ['code', 'name', 'category', 'requires_expiry_date', 'description', 'is_active']


class ProductTypeDeleteView(NomenclatureViewMixin, DeleteView):
    """Product Type delete view - PLACEHOLDER"""
    model = ProductType
    template_name = 'nomenclatures/product/product_types_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:product_types')