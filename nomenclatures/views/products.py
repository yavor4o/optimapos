from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

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
    # Ако URL ползва <int:id>, разкоментирай следното:
    # pk_url_kwarg = 'id'

    def get_page_title(self):
        return _("Edit Product Group")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object:
            form.fields['parent'].queryset = ProductGroup.objects.exclude(pk=self.object.pk)
        return form


class ProductGroupDetailView(NomenclatureViewMixin, DetailView):
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_detail.html'


class ProductGroupDeleteView(NomenclatureViewMixin, DeleteView):
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return _("Delete Product Group")

