# purchases/services/request_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models.requests import PurchaseRequest, PurchaseRequestLine
from ..models.orders import PurchaseOrder, PurchaseOrderLine
from .notification_service import NotificationService
from .analytics_service import AnalyticsService

User = get_user_model()


class RequestService:
    """Service for Purchase Request operations"""

    # =====================
    # CREATION & EDITING
    # =====================

    @staticmethod
    def create_request(
            supplier,
            location,
            user,
            request_type='regular',
            urgency_level='normal',
            business_justification='',
            expected_usage='',
            **kwargs
    ) -> Dict:
        """Create new purchase request"""

        try:
            with transaction.atomic():
                request = PurchaseRequest.objects.create(
                    supplier=supplier,
                    location=location,
                    request_type=request_type,
                    urgency_level=urgency_level,
                    business_justification=business_justification,
                    expected_usage=expected_usage,
                    requested_by=user,
                    created_by=user,
                    document_date=timezone.now().date(),
                    **kwargs
                )

                # Log creation
                AnalyticsService.log_request_action(request, 'created', user)

                return {
                    'success': True,
                    'message': f'Request {request.document_number} created successfully',
                    'request': request
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error creating request: {str(e)}',
                'request': None
            }

    @staticmethod
    def add_line_to_request(
            request: PurchaseRequest,
            product,
            requested_quantity: Decimal,
            estimated_price: Optional[Decimal] = None,
            usage_description: str = '',
            suggested_supplier=None,
            user=None
    ) -> Dict:
        """Add line to purchase request"""

        if request.status != 'draft':
            raise ValidationError("Cannot modify non-draft requests")

        try:
            line = PurchaseRequestLine.objects.create(
                document=request,
                product=product,
                requested_quantity=requested_quantity,
                estimated_price=estimated_price,
                usage_description=usage_description,
                suggested_supplier=suggested_supplier
            )

            return {
                'success': True,
                'message': f'Line added: {product.name}',
                'line': line
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error adding line: {str(e)}',
                'line': None
            }

    # =====================
    # WORKFLOW OPERATIONS
    # =====================

    @staticmethod
    def submit_for_approval(request: PurchaseRequest, user=None) -> Dict:
        """Submit request for approval"""

        # Validation
        if request.status != 'draft':
            raise ValidationError("Can only submit draft requests")

        if not request.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        # Business rules validation
        if request.urgency_level == 'critical' and not request.business_justification:
            raise ValidationError("Critical requests must have business justification")

        try:
            with transaction.atomic():
                request.status = 'submitted'
                request.updated_by = user
                request.save()

                # Notify approvers
                NotificationService.notify_request_approvers(request)

                # Log action
                AnalyticsService.log_request_action(request, 'submitted', user)

                return {
                    'success': True,
                    'message': f'Request {request.document_number} submitted for approval',
                    'request': request
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error submitting request: {str(e)}',
                'request': request
            }

    @staticmethod
    def approve_request(request: PurchaseRequest, user, notes: str = '') -> Dict:
        """Approve purchase request"""

        # Validation
        if request.status != 'submitted':
            raise ValidationError("Can only approve submitted requests")

        if not user.has_perm('purchases.approve_requests'):
            raise PermissionDenied("User cannot approve requests")

        # Check approval limits
        estimated_total = request.get_estimated_total()
        if estimated_total and not RequestService._can_approve_amount(user, estimated_total):
            raise PermissionDenied(f"User cannot approve amounts over {user.approval_limit}")

        try:
            with transaction.atomic():
                request.status = 'approved'
                request.approved_by = user
                request.approved_at = timezone.now()
                request.updated_by = user

                if notes:
                    request.notes = (request.notes + '\n' + notes).strip()

                request.save()

                # Notify requester
                NotificationService.notify_request_approved(request)

                # Log action
                AnalyticsService.log_request_action(request, 'approved', user, {
                    'estimated_total': estimated_total,
                    'approval_notes': notes
                })

                return {
                    'success': True,
                    'message': f'Request {request.document_number} approved',
                    'request': request
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error approving request: {str(e)}',
                'request': request
            }

    @staticmethod
    def reject_request(request: PurchaseRequest, user, reason: str) -> Dict:
        """Reject purchase request"""

        if request.status != 'submitted':
            raise ValidationError("Can only reject submitted requests")

        if not user.has_perm('purchases.approve_requests'):
            raise PermissionDenied("User cannot reject requests")

        if not reason:
            raise ValidationError("Rejection reason is required")

        try:
            with transaction.atomic():
                request.status = 'rejected'
                request.rejection_reason = reason
                request.updated_by = user
                request.save()

                # Notify requester
                NotificationService.notify_request_rejected(request, reason)

                # Log action
                AnalyticsService.log_request_action(request, 'rejected', user, {
                    'rejection_reason': reason
                })

                return {
                    'success': True,
                    'message': f'Request {request.document_number} rejected',
                    'request': request
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error rejecting request: {str(e)}',
                'request': request
            }

    # =====================
    # CONVERSION TO ORDER
    # =====================

    @staticmethod
    def convert_to_order(
            request: PurchaseRequest,
            user,
            expected_delivery_date=None,
            order_notes: str = '',
            line_modifications: Optional[Dict] = None
    ) -> Dict:
        """Convert approved request to purchase order"""

        if request.status != 'approved':
            raise ValidationError("Can only convert approved requests")

        if request.converted_to_order:
            raise ValidationError("Request already converted to order")

        try:
            with transaction.atomic():
                # Create order
                order = PurchaseOrder.objects.create(
                    supplier=request.supplier,
                    location=request.location,
                    source_request=request,
                    document_date=timezone.now().date(),
                    expected_delivery_date=expected_delivery_date,
                    is_urgent=(request.urgency_level in ['high', 'critical']),
                    created_by=user,
                    notes=f"Converted from request {request.document_number}\n{order_notes}".strip()
                )

                # Convert lines
                converted_lines = []
                for req_line in request.lines.all():
                    # Apply modifications if provided
                    quantity = req_line.requested_quantity
                    unit_price = req_line.estimated_price

                    if line_modifications and req_line.id in line_modifications:
                        modifications = line_modifications[req_line.id]
                        quantity = modifications.get('quantity', quantity)
                        unit_price = modifications.get('unit_price', unit_price)

                    order_line = PurchaseOrderLine.objects.create(
                        document=order,
                        product=req_line.product,
                        quantity=quantity,
                        unit_price=unit_price or Decimal('0.00'),
                        notes=req_line.usage_description
                    )
                    converted_lines.append(order_line)

                # Update request status
                request.status = 'converted'
                request.converted_to_order = order
                request.converted_at = timezone.now()
                request.converted_by = user
                request.save()

                # Recalculate order totals
                order.recalculate_totals()

                # Notifications
                NotificationService.notify_request_converted(request, order)

                # Analytics
                AnalyticsService.log_request_action(request, 'converted', user, {
                    'order_number': order.document_number,
                    'lines_converted': len(converted_lines),
                    'order_total': order.grand_total
                })

                return {
                    'success': True,
                    'message': f'Request {request.document_number} converted to order {order.document_number}',
                    'request': request,
                    'order': order,
                    'converted_lines': converted_lines
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error converting request: {str(e)}',
                'request': request,
                'order': None
            }

    # =====================
    # BULK OPERATIONS
    # =====================

    @staticmethod
    def bulk_approve_requests(requests: List[PurchaseRequest], user, notes: str = '') -> Dict:
        """Bulk approve multiple requests"""

        approved = []
        failed = []

        for request in requests:
            try:
                result = RequestService.approve_request(request, user, notes)
                if result['success']:
                    approved.append(request)
                else:
                    failed.append({'request': request, 'error': result['message']})
            except Exception as e:
                failed.append({'request': request, 'error': str(e)})

        return {
            'approved_count': len(approved),
            'failed_count': len(failed),
            'approved_requests': approved,
            'failed_requests': failed
        }

    @staticmethod
    def bulk_convert_to_orders(requests: List[PurchaseRequest], user, **kwargs) -> Dict:
        """Bulk convert multiple requests to orders"""

        converted = []
        failed = []

        for request in requests:
            try:
                result = RequestService.convert_to_order(request, user, **kwargs)
                if result['success']:
                    converted.append({
                        'request': request,
                        'order': result['order']
                    })
                else:
                    failed.append({'request': request, 'error': result['message']})
            except Exception as e:
                failed.append({'request': request, 'error': str(e)})

        return {
            'converted_count': len(converted),
            'failed_count': len(failed),
            'converted_orders': converted,
            'failed_requests': failed
        }

    # =====================
    # ANALYTICS & REPORTING
    # =====================

    @staticmethod
    def get_request_analytics(request: PurchaseRequest) -> Dict:
        """Get analytics for specific request"""

        return {
            'basic_info': {
                'document_number': request.document_number,
                'status': request.status,
                'request_type': request.request_type,
                'urgency_level': request.urgency_level,
                'created_at': request.created_at,
                'requested_by': request.requested_by.get_full_name() if request.requested_by else None
            },
            'workflow_timing': {
                'time_to_submit': RequestService._calculate_time_to_submit(request),
                'time_to_approve': RequestService._calculate_time_to_approve(request),
                'time_to_convert': RequestService._calculate_time_to_convert(request),
                'total_processing_time': RequestService._calculate_total_processing_time(request)
            },
            'content_analysis': {
                'lines_count': request.lines.count(),
                'estimated_total': request.get_estimated_total(),
                'has_estimated_prices': request.lines.filter(estimated_price__isnull=False).count(),
                'missing_estimated_prices': request.lines.filter(estimated_price__isnull=True).count()
            },
            'approval_info': {
                'requires_approval': request.approval_required,
                'approved_by': request.approved_by.get_full_name() if request.approved_by else None,
                'approved_at': request.approved_at,
                'approval_notes': request.notes
            }
        }

    # =====================
    # HELPER METHODS
    # =====================

    @staticmethod
    def _can_approve_amount(user, amount: Decimal) -> bool:
        """Check if user can approve given amount"""
        if hasattr(user, 'approval_limit'):
            return user.approval_limit >= amount
        return True  # No limit set

    @staticmethod
    def _calculate_time_to_submit(request: PurchaseRequest) -> Optional[int]:
        """Calculate hours from creation to submission"""
        if request.status in ['submitted', 'approved', 'rejected', 'converted']:
            # Would need to track submission timestamp
            # For now, return None - implement with workflow tracking
            return None
        return None

    @staticmethod
    def _calculate_time_to_approve(request: PurchaseRequest) -> Optional[int]:
        """Calculate hours from submission to approval"""
        if request.approved_at:
            # Would need submission timestamp
            return None
        return None

    @staticmethod
    def _calculate_time_to_convert(request: PurchaseRequest) -> Optional[int]:
        """Calculate hours from approval to conversion"""
        if request.converted_at and request.approved_at:
            delta = request.converted_at - request.approved_at
            return int(delta.total_seconds() / 3600)
        return None

    @staticmethod
    def _calculate_total_processing_time(request: PurchaseRequest) -> Optional[int]:
        """Calculate total processing time"""
        if request.status == 'converted' and request.converted_at:
            delta = request.converted_at - request.created_at
            return int(delta.total_seconds() / 3600)
        return None