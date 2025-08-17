import json

from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string
from ..forms.product import ProductGroupForm, BrandForm
from ..models import ProductGroup, Brand


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
    context_object_name = 'object_list'

    def get_page_title(self):
        return _("Product Groups")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Handle view mode
        view_mode = self.request.GET.get('view')
        if not view_mode:
            view_mode = self.request.COOKIES.get('product_groups_view', 'flat')

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
        # ВИНАГИ използваме MPTT подредбата за да имаме правилните нива
        # Това ще ни даде правилен level независимо от view mode
        queryset = ProductGroup.objects.annotate(
            products_count=Count('product')
        ).select_related('parent').order_by('tree_id', 'lft')

        return queryset


# Добави тези импорти в началото на nomenclatures/views/products.py
import json
from django.views import View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


# Добави този клас след другите views в nomenclatures/views/products.py

@method_decorator(csrf_exempt, name='dispatch')  # За тестване, после ще добавим CSRF
class ProductGroupMoveView(View):
    """Handle drag and drop reordering of product groups"""

    def post(self, request, pk):
        try:
            # Get the group being moved
            group = ProductGroup.objects.get(pk=pk)

            # Parse request data
            data = json.loads(request.body)
            new_parent_id = data.get('parent_id')
            position = data.get('position', 0)

            # Update parent if changed
            if new_parent_id:
                try:
                    new_parent = ProductGroup.objects.get(pk=new_parent_id)
                    group.parent = new_parent
                except ProductGroup.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Parent group not found'
                    })
            else:
                group.parent = None

            # Update sort order
            group.sort_order = position
            group.save()

            # Rebuild the MPTT tree structure
            ProductGroup.objects.rebuild()

            return JsonResponse({
                'success': True,
                'message': 'Group moved successfully'
            })

        except ProductGroup.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Group not found'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

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


class BrandListView(NomenclatureListMixin, ListView):
    model = Brand
    template_name = 'frontend/nomenclatures/product/brands_list.html'
    context_object_name = 'brands'
    paginate_by = 25
    ordering = ['name']

    def get_page_title(self):
        return _("Brands")

    def get_queryset(self):
        queryset = super().get_queryset()
        # Анотираме с брой продукти
        queryset = queryset.annotate(
            products_count=Count('product', distinct=True)
        )

        # Филтрираме по статус ако е подаден
        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        # Търсене
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_count': Brand.objects.count(),
            'active_count': Brand.objects.filter(is_active=True).count(),
            'inactive_count': Brand.objects.filter(is_active=False).count(),
            'can_create': True,
            'create_url': reverse_lazy('nomenclatures:brands_create'),
            'search_query': self.request.GET.get('search', ''),
            'status_filter': self.request.GET.get('status', ''),
        })
        return context


class BrandCreateView(NomenclatureViewMixin, CreateView):
    model = Brand
    form_class = BrandForm
    template_name = 'frontend/nomenclatures/product/brands_form.html'
    success_url = reverse_lazy('nomenclatures:brands')

    def get_page_title(self):
        return _("Create Brand")


class BrandUpdateView(NomenclatureViewMixin, UpdateView):
    model = Brand
    form_class = BrandForm
    template_name = 'frontend/nomenclatures/product/brands_form.html'
    success_url = reverse_lazy('nomenclatures:brands')

    def get_page_title(self):
        return _("Edit Brand")


class BrandDetailView(NomenclatureViewMixin, DetailView):
    model = Brand

    def get(self, request, *args, **kwargs):
        """AJAX detail view за modal"""
        self.object = self.get_object()

        # Анотираме с брой продукти
        products_count = self.object.product_set.count() if hasattr(self.object, 'product_set') else 0

        data = {
            'success': True,
            'brand': {
                'id': self.object.pk,
                'code': self.object.code,
                'name': self.object.name,
                'website': self.object.website or '',
                'is_active': self.object.is_active,
                'logo_url': self.object.logo.url if self.object.logo else None,
                'products_count': products_count,
                'created_at': self.object.created_at.strftime('%d.%m.%Y %H:%M'),
                'updated_at': self.object.updated_at.strftime('%d.%m.%Y %H:%M'),
            }
        }
        return JsonResponse(data)


class BrandDeleteView(NomenclatureViewMixin, DeleteView):
    model = Brand
    template_name = 'frontend/nomenclatures/brand/brands_confirm_delete.html'
    success_url = reverse_lazy('nomenclatures:brands')

    def get_page_title(self):
        return _("Delete Brand")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Проверяваме дали има свързани продукти
        context['has_products'] = self.object.product_set.exists() if hasattr(self.object, 'product_set') else False
        context['products_count'] = self.object.product_set.count() if hasattr(self.object, 'product_set') else 0
        return context