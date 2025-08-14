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