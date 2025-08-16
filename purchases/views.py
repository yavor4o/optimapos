# purchases/views.py
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
from inventory.models import InventoryMovement
from products.models import Product
from decimal import Decimal


@staff_member_required
@require_GET
def last_purchase_price_api(request):
    """
    API endpoint за получаване на последната покупна цена на продукт
    """
    product_id = request.GET.get('product_id')

    if not product_id:
        return JsonResponse({
            'success': False,
            'error': 'Product ID is required'
        })

    try:
        product = Product.objects.get(id=product_id)

        # Намери последното IN движение за този продукт
        last_movement = InventoryMovement.objects.filter(
            product=product,
            movement_type='IN',
            source_document_type__in=['DELIVERY', 'PURCHASE_REQUEST', 'PURCHASE']
        ).order_by('-created_at').first()

        if last_movement:
            return JsonResponse({
                'success': True,
                'last_price': str(last_movement.cost_price),
                'last_date': last_movement.movement_date.strftime('%Y-%m-%d'),
                'supplier': last_movement.source_document_number,
                'product_code': product.code,
                'product_name': product.name
            })
        else:
            # Fallback към InventoryItem avg_cost
            from inventory.models import InventoryItem
            inventory_item = InventoryItem.objects.filter(
                product=product,
                avg_cost__gt=0
            ).order_by('-last_purchase_date').first()

            if inventory_item and inventory_item.last_purchase_cost:
                return JsonResponse({
                    'success': True,
                    'last_price': str(inventory_item.last_purchase_cost),
                    'last_date': inventory_item.last_purchase_date.strftime(
                        '%Y-%m-%d') if inventory_item.last_purchase_date else None,
                    'supplier': 'Inventory data',
                    'product_code': product.code,
                    'product_name': product.name
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No purchase history found for this product'
                })

    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Product not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from .models import PurchaseOrder


@staff_member_required
def test_order_workflow(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)

    # Get available actions (if DocumentService works)
    available_actions = []
    try:
        from nomenclatures.services import DocumentService
        available_actions = DocumentService.get_available_actions(order, request.user)
    except:
        pass

    context = {
        'object': order,
        'available_actions': available_actions,
        'current_user': request.user,
    }

    return render(request, 'admin/purchases/test_order_workflow.html', context)


from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .models import PurchaseOrder


@staff_member_required
def test_order_workflow(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)

    # Get available actions (if DocumentService works)
    available_actions = []
    try:
        from nomenclatures.services import DocumentService
        available_actions = DocumentService.get_available_actions(order, request.user)
    except:
        pass

    context = {
        'object': order,
        'available_actions': available_actions,
        'current_user': request.user,
    }

    return render(request, 'admin/purchases/test_order_workflow.html', context)


@staff_member_required
@require_http_methods(['POST'])
def workflow_action(request, pk):
    """Handle workflow actions"""
    order = get_object_or_404(PurchaseOrder, pk=pk)

    action = request.POST.get('action')
    status = request.POST.get('status')

    # Handle different actions
    if action == 'recalculate':
        try:
            # Recalculate order totals
            if hasattr(order, 'calculate_totals'):
                order.calculate_totals()
                order.save()
                return JsonResponse({'success': True, 'message': 'Totals recalculated'})
            else:
                return JsonResponse({'success': False, 'message': 'Calculate method not available'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    # НОВO: Real workflow transitions
    elif status in ['sent', 'confirmed', 'completed', 'cancelled']:
        try:
            from nomenclatures.services import DocumentService
            # ВАЖНО: Подавай request.user!
            result = DocumentService.transition_document(order, status, request.user, f'Transition via workflow test')

            if result.ok:
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully transitioned to {status}',
                    'new_status': status
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'Transition failed: {result.msg}'
                })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    else:
        return JsonResponse({'success': False, 'message': f'Unknown action: {action}'})



from django.shortcuts import render
from django.views.generic import TemplateView
from typing import Dict, Any


class IndexView(TemplateView):
    """Main dashboard view for demo12 with hardcoded data."""

    template_name = 'frontend/index.html'

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Hardcoded dashboard data
        context.update({
            'page_title': 'Dashboard',
            'page_description': 'Central Hub for Personal Customization',
        })

        return context
