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

        # Handle view mode
        view_mode = self.request.GET.get('view', 'flat')
        if view_mode not in ['flat', 'tree']:
            view_mode = 'flat'

        context.update({
            'total_count': ProductGroup.objects.count(),
            'active_count': ProductGroup.objects.filter(is_active=True).count(),
            'inactive_count': ProductGroup.objects.filter(is_active=False).count(),
            'can_create': True,
            'create_url': reverse_lazy('nomenclatures:product_groups_create'),
            'view_mode': view_mode,
        })
        return context

    def get_queryset(self):
        view_mode = self.request.GET.get('view', 'flat')
        if view_mode == 'tree':
            return ProductGroup.objects.all().select_related('parent')
        return super().get_queryset()


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





class ProductGroupDetailModalView(NomenclatureViewMixin, DetailView):
    model = ProductGroup

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        data = {
            "success": True,
            "title": f"{self.object.code} - {self.object.name}",
            "group": {
                "id": self.object.pk,
                "code": self.object.code,
                "name": self.object.name,
                "level": getattr(self.object, "level", 0) or 0,
                "is_active": bool(self.object.is_active),
                "parent": {
                    "id": self.object.parent.pk,
                    "name": self.object.parent.name,
                } if self.object.parent_id else None,
            },
            "children_count": (
                self.object.get_children().count()
                if hasattr(self.object, "get_children") else 0
            ),
            "descendants_count": (
                self.object.get_descendant_count()
                if hasattr(self.object, "get_descendant_count") else 0
            ),
        }
        return JsonResponse(data)


class ProductGroupDeleteView(NomenclatureViewMixin, DeleteView):
    model = ProductGroup
    template_name = 'frontend/nomenclatures/product/product_groups_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:product_groups')

    def get_page_title(self):
        return _("Delete Product Group")

