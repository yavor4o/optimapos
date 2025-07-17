# purchases/services/delivery_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from purchases.models.deliveries import DeliveryReceipt, DeliveryLine
from purchases.models.orders import PurchaseOrder


class DeliveryService:
    """Service for Delivery Receipt operations"""

    @staticmethod
    @transaction.atomic
    def create_delivery(
            supplier,
            location,
            received_by,
            creation_type='direct',
            lines_data: Optional[List[Dict]] = None,
            source_orders: Optional[List[PurchaseOrder]] = None,
            **kwargs
    ) -> DeliveryReceipt:
        """Create new delivery receipt"""

        # Create delivery
        delivery = DeliveryReceipt.objects.create(
            supplier=supplier,
            location=location,
            received_by=received_by,
            creation_type=creation_type,
            delivery_date=timezone.now().date(),
            **kwargs
        )

        # Add source orders if provided
        if source_orders:
            delivery.add_source_orders(source_orders)
            if creation_type == 'from_orders':
                delivery.copy_lines_from_orders()

        # Add manual lines if provided
        if lines_data:
            DeliveryService.add_lines_to_delivery(delivery, lines_data)

        return delivery

    @staticmethod
    @transaction.atomic
    def create_from_orders(
            orders: List[PurchaseOrder],
            received_by,
            delivery_data: Optional[Dict] = None,
            additional_lines: Optional[List[Dict]] = None
    ) -> DeliveryReceipt:
        """Create delivery from one or more orders"""

        if not orders:
            raise ValidationError("At least one order is required")

        # Validate all orders can be used for delivery
        for order in orders:
            if not order.can_be_used_for_delivery():
                raise ValidationError(f"Order {order.document_number} cannot be used for delivery")

        # Use first order's supplier and location as defaults
        first_order = orders[0]
        delivery_data = delivery_data or {}

        delivery_data.setdefaults({
            'supplier': first_order.supplier,
            'location': first_order.location,
            'expected_delivery_date': first_order.expected_delivery_date,
        })

        # Determine creation type
        creation_type = 'mixed' if additional_lines else 'from_orders'

        # Create delivery
        delivery = DeliveryService.create_delivery(
            creation_type=creation_type,
            received_by=received_by,
            source_orders=orders,
            **delivery_data
        )

        # Add additional lines if provided
        if additional_lines:
            DeliveryService.add_lines_to_delivery(delivery, additional_lines)

        return delivery

    @staticmethod
    @transaction.atomic
    def create_direct_delivery(
            supplier,
            location,
            received_by,
            lines_data: List[Dict],
            **kwargs
    ) -> DeliveryReceipt:
        """Create direct delivery (no orders)"""

        return DeliveryService.create_delivery(
            supplier=supplier,
            location=location,
            received_by=received_by,
            creation_type='direct',
            lines_data=lines_data,
            **kwargs
        )

    @staticmethod
    @transaction.atomic
    def add_lines_to_delivery(delivery: DeliveryReceipt, lines_data: List[Dict]) -> List[DeliveryLine]:
        """Add lines to delivery receipt"""

        if not delivery.can_be_edited():
            raise ValidationError("Cannot modify delivery in current state")

        lines = []
        existing_lines_count = delivery.lines.count()

        for i, line_data in enumerate(lines_data, existing_lines_count + 1):
            line = DeliveryLine.objects.create(
                document=delivery,
                line_number=i,
                product=line_data['product'],
                received_quantity=line_data['received_quantity'],
                unit=line_data['unit'],
                unit_price=line_data['unit_price'],
                source_order_line=line_data.get('source_order_line'),
                ordered_quantity=line_data.get('ordered_quantity'),
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
                quality_approved=line_data.get('quality_approved', True),
                **line_data.get('extra_fields', {})
            )
            lines.append(line)

        # Recalculate totals
        delivery.recalculate_totals()

        return lines

    @staticmethod
    @transaction.atomic
    def receive_delivery(delivery: DeliveryReceipt, user, quality_check=True) -> Dict:
        """Receive and process delivery"""

        try:
            delivery.receive_delivery(user, quality_check)
            return {
                'success': True,
                'message': f'Delivery {delivery.document_number} received successfully',
                'delivery': delivery
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'delivery': delivery
            }

    @staticmethod
    def get_delivery_options(supplier) -> Dict:
        """Get delivery creation options for supplier"""

        available_orders = PurchaseOrder.objects.ready_for_delivery_creation().filter(
            supplier=supplier
        )

        return {
            'supplier': supplier,
            'available_orders': list(available_orders),
            'can_create_direct': True,  # TODO: Check from core settings
            'can_create_mixed': True,
        }

    @staticmethod
    def get_delivery_analytics(date_from=None, date_to=None) -> Dict:
        """Get delivery analytics and statistics"""

        queryset = DeliveryReceipt.objects.all()

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return {
            'total_deliveries': queryset.count(),
            'received_deliveries': queryset.filter(status='received').count(),
            'direct_deliveries': queryset.filter(creation_type='direct').count(),
            'from_orders': queryset.filter(creation_type='from_orders').count(),
            'with_quality_issues': queryset.filter(has_quality_issues=True).count(),
            'with_variances': queryset.filter(has_variances=True).count(),
        }
