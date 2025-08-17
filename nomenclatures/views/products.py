# nomenclatures/views/products.py - Updated with AJAX Modal Support
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string

from ..forms.product import ProductGroupForm
from ..models import ProductGroup


class NomenclatureViewMixin(LoginRequiredMixin):
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
    paginate_by = 25
    ordering = ['sort_order', 'name']


class ProductGroupListView(NomenclatureListMixin, ListView):
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


class ProductGroupCreateView(NomenclatureViewMixin, CreateView):
    model = ProductGroup
    form_class = ProductGroupForm
    template_name = 'frontend/nomenclatures/product/product_groups_form.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return _("Create Product Group")


class ProductGroupUpdateView(NomenclatureViewMixin, UpdateView):
    model = ProductGroup
    form_class = ProductGroupForm
    template_name = 'frontend/nomenclatures/product/product_groups_form.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return _("Edit Product Group")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object:
            form.fields['parent'].queryset = ProductGroup.objects.exclude(pk=self.object.pk)
        return form


class ProductGroupDetailView(NomenclatureViewMixin, DetailView):
    """
    AJAX-Ready Detail View for Product Groups
    - Returns JSON with HTML for AJAX requests (modal)
    - Returns normal page for direct access (fallback)
    """
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_detail.html'

    def get_page_title(self):
        return _("Product Group Details")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check if this is an AJAX request for modal
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return self.ajax_response()

        # Normal page request (fallback)
        return super().get(request, *args, **kwargs)

    def ajax_response(self):
        """Return JSON response with modal HTML for AJAX requests"""
        try:
            context = self.get_context_data(object=self.object)

            # Render the modal template
            modal_html = render_to_string(
                'frontend/nomenclatures/product/product_groups_detail_modal.html',
                context,
                request=self.request
            )

            return JsonResponse({
                'success': True,
                'html': modal_html,
                'title': f'{self.object.name} - {_("Product Group Details")}'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'message': _('Error loading product group details')
            }, status=500)


class ProductGroupDeleteView(NomenclatureViewMixin, DeleteView):
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return _("Delete Product Group")