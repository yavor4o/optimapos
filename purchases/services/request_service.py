from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import PurchaseRequest, PurchaseRequestLine, DocumentType


class RequestService:
    """Service for Purchase Request operations"""

    @staticmethod
    @transaction.atomic
    def create_request(
            supplier,
            location,
            requested_by,
            lines_data: List[Dict],
            delivery_date=None,
            urgency_level='normal',
            business_justification='',
            **kwargs
    ) -> PurchaseRequest:
        """Create new purchase request with lines"""

        # Default delivery date
        if not delivery_date:
            delivery_date = timezone.now().date() + timezone.timedelta(days=7)

        # Create request
        request = PurchaseRequest.objects.create(
            supplier=supplier,
            location=location,
            delivery_date=delivery_date,
            requested_by=requested_by,
            urgency_level=urgency_level,
            business_justification=business_justification,
            **kwargs
        )

        # Add lines
        RequestService.add_lines_to_request(request, lines_data)

        return request

    @staticmethod
    @transaction.atomic
    def add_lines_to_request(request: PurchaseRequest, lines_data: List[Dict]) -> List[PurchaseRequestLine]:
        """Add lines to purchase request"""

        if not request.can_be_edited():
            raise ValidationError("Cannot modify request in current state")

        lines = []
        for i, line_data in enumerate(lines_data, 1):
            line = PurchaseRequestLine.objects.create(
                document=request,
                line_number=i,
                product=line_data['product'],
                quantity=line_data['quantity'],
                unit=line_data['unit'],
                unit_price=line_data.get('unit_price', Decimal('0.0000')),
                requested_quantity=line_data['quantity'],
                estimated_price=line_data.get('estimated_price'),
                line_justification=line_data.get('justification', ''),
                **line_data.get('extra_fields', {})
            )
            lines.append(line)

        # Recalculate totals
        request.recalculate_totals()

        return lines

    @staticmethod
    @transaction.atomic
    def submit_for_approval(request: PurchaseRequest, user=None) -> Dict:
        """Submit request for approval"""

        try:
            request.submit_for_approval(user)
            return {
                'success': True,
                'message': f'Request {request.document_number} submitted for approval',
                'request': request
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'request': request
            }

    @staticmethod
    @transaction.atomic
    def approve_request(request: PurchaseRequest, user, notes='') -> Dict:
        """Approve purchase request"""

        try:
            request.approve(user, notes)
            return {
                'success': True,
                'message': f'Request {request.document_number} approved',
                'request': request
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'request': request
            }

    @staticmethod
    @transaction.atomic
    def reject_request(request: PurchaseRequest, user, reason) -> Dict:
        """Reject purchase request"""

        try:
            request.reject(user, reason)
            return {
                'success': True,
                'message': f'Request {request.document_number} rejected',
                'request': request
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'request': request
            }

    @staticmethod
    @transaction.atomic
    def convert_to_order(request: PurchaseRequest, user=None, **order_kwargs) -> Dict:
        """Convert approved request to purchase order"""

        try:
            order = request.convert_to_order(user)

            # Apply any additional order modifications
            if order_kwargs:
                for key, value in order_kwargs.items():
                    if hasattr(order, key):
                        setattr(order, key, value)
                order.save()

            return {
                'success': True,
                'message': f'Request {request.document_number} converted to order {order.document_number}',
                'request': request,
                'order': order
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'request': request
            }

    @staticmethod
    def get_pending_approvals(user=None) -> List[PurchaseRequest]:
        """Get requests pending approval"""
        queryset = PurchaseRequest.objects.pending_approval()

        if user:
            # Filter by user permissions (implement based on your approval hierarchy)
            queryset = queryset.filter(requested_by=user)  # Placeholder

        return list(queryset)

    @staticmethod
    def get_request_analytics(date_from=None, date_to=None) -> Dict:
        """Get request analytics and statistics"""

        queryset = PurchaseRequest.objects.all()

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return {
            'total_requests': queryset.count(),
            'pending_approval': queryset.filter(status='submitted').count(),
            'approved': queryset.filter(status='approved').count(),
            'converted': queryset.filter(status='converted').count(),
            'urgent_requests': queryset.filter(urgency_level='urgent').count(),
        }
