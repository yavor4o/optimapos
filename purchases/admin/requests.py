# purchases/admin.py

from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal
import json

from purchases.models import PurchaseRequest, PurchaseRequestLine
from purchases.services.workflow_service import PurchaseWorkflowService
from partners.models import Supplier
from inventory.models import InventoryLocation
from products.models import Product
from nomenclatures.models import UnitOfMeasure


class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 0
    readonly_fields = ('line_number', 'estimated_price')
    fields = ('line_number', 'product', 'requested_quantity', 'unit', 'estimated_price', 'description')


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    """
    Хибриден Admin - стандартен преглед + custom създаване
    """

    # Стандартни админ настройки
    list_display = ('document_number', 'status', 'priority', 'get_location_display', 'get_partner_display', 'total',
                    'created_at')
    list_filter = ('status', 'priority', 'created_at',
                   'location_content_type')  # Използвай content_type вместо location
    search_fields = ('document_number', 'notes')

    # FIX: Add 'partner' and 'location' to readonly_fields since they are GenericForeignKey fields
    readonly_fields = ('document_number', 'document_type', 'status', 'created_by', 'updated_by',
                       'created_at', 'updated_at', 'subtotal', 'total', 'vat_total',
                       'partner', 'location')

    inlines = [PurchaseRequestLineInline]

    fieldsets = (
        ('Document Info', {
            'fields': ('document_number', 'document_type', 'status', 'document_date')
        }),
        ('Request Details', {
            'fields': ('location', 'partner', 'priority', 'required_by_date', 'notes')
        }),
        ('Financial', {
            'fields': ('subtotal', 'vat_total', 'total'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    # Custom URLs
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('create-with-workflow/',
                 self.admin_site.admin_view(self.create_with_workflow_view),
                 name='purchases_purchaserequest_create_workflow'),
            path('ajax/get-product-info/',
                 self.admin_site.admin_view(self.ajax_get_product_info),
                 name='purchases_purchaserequest_ajax_product'),
        ]
        return custom_urls + urls

    # Custom change_list template за добавяне на бутон
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['create_workflow_url'] = reverse(
            'admin:purchases_purchaserequest_create_workflow'
        )
        return super().changelist_view(request, extra_context=extra_context)

    def create_with_workflow_view(self, request):
        """Custom view за създаване през workflow service"""

        if request.method == 'GET':
            # Зарежда формата за създаване
            context = {
                'title': 'Create Purchase Request via Workflow',
                'locations': InventoryLocation.objects.filter(is_active=True),
                'suppliers': Supplier.objects.filter(is_active=True),
                'products': Product.objects.purchasable()[:100],  # Use purchasable() method for active products
                'units': UnitOfMeasure.objects.filter(is_active=True),
                'priorities': PurchaseRequest._meta.get_field('priority').choices,
                'opts': self.model._meta,
                'has_view_permission': self.has_view_permission(request),
            }
            return render(request, 'admin/purchases/purchaserequest/create_workflow.html', context)

        elif request.method == 'POST':
            # Обработва създаването
            try:
                # Parse данните от формата
                location_id = request.POST.get('location')
                supplier_id = request.POST.get('supplier')
                priority = request.POST.get('priority', 'normal')
                required_by_date = request.POST.get('required_by_date') or None
                notes = request.POST.get('notes', '')

                # Parse редовете (JSON от frontend)
                lines_json = request.POST.get('lines_data', '[]')
                lines_data = []

                if lines_json:
                    raw_lines = json.loads(lines_json)
                    for line in raw_lines:
                        if line.get('product_id') and line.get('quantity'):
                            try:
                                product = Product.objects.get(pk=line['product_id'])
                                unit = UnitOfMeasure.objects.get(pk=line['unit_id']) if line.get('unit_id') else None
                                estimated_price = Decimal(str(line['estimated_price'])) if line.get(
                                    'estimated_price') else None

                                lines_data.append({
                                    'product': product,
                                    'requested_quantity': Decimal(str(line['quantity'])),
                                    'unit': unit,
                                    'estimated_price': estimated_price,
                                    'notes': line.get('notes', ''),
                                })
                            except (Product.DoesNotExist, UnitOfMeasure.DoesNotExist, ValueError):
                                continue

                # Валидации
                if not location_id:
                    raise ValueError("Location is required")
                if not lines_data:
                    raise ValueError("At least one line item is required")

                location = InventoryLocation.objects.get(pk=location_id)
                supplier = Supplier.objects.get(pk=supplier_id) if supplier_id else None

                # Извикай workflow service
                result = PurchaseWorkflowService.create_purchase_request(
                    location=location,
                    user=request.user,
                    supplier=supplier,
                    required_by_date=required_by_date,
                    priority=priority,
                    notes=notes,
                    lines_data=lines_data
                )

                if result.ok:
                    messages.success(
                        request,
                        f'Purchase Request {result.data["document_number"]} created successfully!'
                    )
                    # Redirect към created document
                    return redirect('admin:purchases_purchaserequest_change',
                                    result.data['document'].pk)
                else:
                    messages.error(request, f'Error: {result.msg}')

            except Exception as e:
                messages.error(request, f'Creation failed: {str(e)}')

            # При грешка - върни обратно към формата
            return redirect('admin:purchases_purchaserequest_create_workflow')

    def ajax_get_product_info(self, request):
        """AJAX endpoint за информация за продукт"""
        product_id = request.GET.get('product_id')
        if not product_id:
            return JsonResponse({'error': 'No product ID provided'})

        try:
            product = Product.objects.get(pk=product_id)
            data = {
                'code': product.code,
                'name': product.name,
                'base_unit_id': product.base_unit.pk if product.base_unit else None,
                'base_unit_name': product.base_unit.name if product.base_unit else None,
            }

            # Try to get cost price - check various possible attributes
            cost_price = None
            for attr in ['cost_price', 'last_purchase_cost', 'avg_cost']:
                if hasattr(product, attr):
                    value = getattr(product, attr)
                    if value is not None:
                        cost_price = str(value)
                        break

            data['cost_price'] = cost_price
            return JsonResponse(data)
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'})

    # Override add_view за redirect
    def add_view(self, request, form_url='', extra_context=None):
        """Override add view да redirect към workflow creation"""
        messages.info(request, 'Use "Create with Workflow" for better experience')
        return redirect('admin:purchases_purchaserequest_create_workflow')

    # Disable mass creation
    def has_add_permission(self, request):
        """Disable standard add - force workflow creation"""
        return True  # Keep True за custom create

    def save_model(self, request, obj, form, change):
        """Standard save за updates"""
        if not change:
            # Ако някак си стигне тук при създаване - попълни audit fields
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    # Helper methods за display
    def get_location_display(self, obj):
        """Display location in list view"""
        if obj.location:
            return f"{obj.location.code} - {obj.location.name}"
        return "No location"

    get_location_display.short_description = 'Location'

    def get_partner_display(self, obj):
        """Display partner in list view"""
        if obj.partner:
            return f"{obj.partner.code} - {obj.partner.name}"
        return "No supplier"

    get_partner_display.short_description = 'Supplier'