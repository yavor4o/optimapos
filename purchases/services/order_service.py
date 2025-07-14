from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

from purchases.models.orders import PurchaseOrder, PurchaseOrderLine
from purchases.models.requests import PurchaseRequest


class OrderService:
    """Service for Purchase Order operations"""

    @staticmethod
    @transaction.atomic
    def create_order(
            supplier,
            location,
            lines_data: List[Dict],
            delivery_date=None,
            source_request: Optional[PurchaseRequest] = None,
            is_urgent=False,
            order_method='',
            **kwargs
    ) -> PurchaseOrder:
        """Create new purchase order"""

        # Default delivery date
        if not delivery_date:
            delivery_date = timezone.now().date() + timezone.timedelta(days=3)

        # Create order
        order = PurchaseOrder.objects.create(
            supplier=supplier,
            location=location,
            delivery_date=delivery_date,
            expected_delivery_date=delivery_date,
            source_request=source_request,
            is_urgent=is_urgent,
            order_method=order_method,
            **kwargs
        )

        # Add lines
        OrderService.add_lines_to_order(order, lines_data)

        return order

    @staticmethod
    @transaction.atomic
    def create_from_request(request: PurchaseRequest, user=None, **order_kwargs) -> PurchaseOrder:
        """Create order from approved request - Alternative to request.convert_to_order()"""

        if not request.can_be_converted():
            raise ValidationError("Request cannot be converted to order")

        # Use the request's convert method
        return request.convert_to_order(user)

    @staticmethod
    @transaction.atomic
    def add_lines_to_order(order: PurchaseOrder, lines_data: List[Dict]) -> List[PurchaseOrderLine]:
        """Add lines to purchase order"""

        if not order.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        lines = []
        for i, line_data in enumerate(lines_data, 1):
            line = PurchaseOrderLine.objects.create(
                document=order,
                line_number=i,
                product=line_data['product'],
                quantity=line_data['quantity'],
                ordered_quantity=line_data['quantity'],
                unit=line_data['unit'],
                unit_price=line_data['unit_price'],
                discount_percent=line_data.get('discount_percent', Decimal('0.00')),
                source_request_line=line_data.get('source_request_line'),
                supplier_product_code=line_data.get('supplier_product_code', ''),
                **line_data.get('extra_fields', {})
            )
            lines.append(line)

        # Recalculate totals
        order.recalculate_totals()

        return lines

    @staticmethod
    @transaction.atomic
    def send_to_supplier(order: PurchaseOrder, user=None, **kwargs) -> Dict:
        """Send order to supplier"""

        try:
            order.send_to_supplier(user)
            return {
                'success': True,
                'message': f'Order {order.document_number} sent to supplier',
                'order': order
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'order': order
            }

    @staticmethod
    @transaction.atomic
    def confirm_by_supplier(order: PurchaseOrder, user=None, supplier_reference='', **kwargs) -> Dict:
        """Confirm order by supplier"""

        try:
            order.confirm_by_supplier(user, supplier_reference)
            return {
                'success': True,
                'message': f'Order {order.document_number} confirmed by supplier',
                'order': order
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'order': order
            }

    @staticmethod
    def get_orders_ready_for_delivery(supplier=None) -> List[PurchaseOrder]:
        """Get orders ready for delivery creation"""
        return list(PurchaseOrder.objects.ready_for_delivery_creation().filter(
            supplier=supplier if supplier else models.Q()
        ))

    @staticmethod
    def get_order_analytics(date_from=None, date_to=None) -> Dict:
        """Get order analytics and statistics"""

        queryset = PurchaseOrder.objects.all()

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return {
            'total_orders': queryset.count(),
            'confirmed_orders': queryset.filter(status='confirmed').count(),
            'sent_orders': queryset.filter(status='sent').count(),
            'direct_orders': queryset.filter(source_request__isnull=True).count(),
            'from_requests': queryset.filter(source_request__isnull=False).count(),
            'urgent_orders': queryset.filter(is_urgent=True).count(),
        }
