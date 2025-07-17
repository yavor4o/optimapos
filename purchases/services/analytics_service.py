# purchases/services/analytics_service.py - NEW ANALYTICS SERVICE

from django.db import models
from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)


class AnalyticsService:
    """Analytics and reporting service for purchase workflows"""

    @staticmethod
    def get_dashboard_data() -> Dict:
        """Get comprehensive dashboard data"""
        today = timezone.now().date()

        return {
            'requests': {
                'pending_approval': PurchaseRequest.objects.pending_approval().count(),
                'approved_today': PurchaseRequest.objects.filter(
                    approved_at__date=today
                ).count(),
                'total_this_month': PurchaseRequest.objects.filter(
                    created_at__month=today.month,
                    created_at__year=today.year
                ).count(),
            },
            'orders': {
                'confirmed': PurchaseOrder.objects.confirmed().count(),
                'ready_for_delivery': PurchaseOrder.objects.ready_for_delivery_creation().count(),
                'overdue_delivery': PurchaseOrder.objects.overdue_delivery().count(),
                'total_value': PurchaseOrder.objects.confirmed().aggregate(
                    total=models.Sum('grand_total')
                )['total'] or Decimal('0'),
            },
            'deliveries': {
                'pending_processing': DeliveryReceipt.objects.pending_processing().count(),
                'received_today': DeliveryReceipt.objects.today().count(),
                'with_quality_issues': DeliveryReceipt.objects.with_quality_issues().count(),
                'with_variances': DeliveryReceipt.objects.filter(has_variances=True).count(),
            }
        }

    @staticmethod
    def search_across_documents(query: str, filters: Dict = None) -> Dict:
        """Search across all document types"""
        results = {
            'requests': [],
            'orders': [],
            'deliveries': []
        }

        if not query and not filters:
            return results

        # Search requests
        request_qs = PurchaseRequest.objects.all()
        if query:
            request_qs = request_qs.filter(
                models.Q(document_number__icontains=query) |
                models.Q(supplier__name__icontains=query) |
                models.Q(notes__icontains=query)
            )

        # Search orders
        order_qs = PurchaseOrder.objects.all()
        if query:
            order_qs = order_qs.filter(
                models.Q(document_number__icontains=query) |
                models.Q(supplier__name__icontains=query) |
                models.Q(order_reference__icontains=query) |
                models.Q(supplier_order_reference__icontains=query)
            )

        # Search deliveries
        delivery_qs = DeliveryReceipt.objects.all()
        if query:
            delivery_qs = delivery_qs.filter(
                models.Q(document_number__icontains=query) |
                models.Q(supplier__name__icontains=query) |
                models.Q(delivery_note_number__icontains=query)
            )

        # Apply filters
        if filters:
            if filters.get('supplier'):
                request_qs = request_qs.filter(supplier=filters['supplier'])
                order_qs = order_qs.filter(supplier=filters['supplier'])
                delivery_qs = delivery_qs.filter(supplier=filters['supplier'])

            if filters.get('location'):
                request_qs = request_qs.filter(location=filters['location'])
                order_qs = order_qs.filter(location=filters['location'])
                delivery_qs = delivery_qs.filter(location=filters['location'])

            if filters.get('date_from'):
                request_qs = request_qs.filter(delivery_date__gte=filters['date_from'])
                order_qs = order_qs.filter(expected_delivery_date__gte=filters['date_from'])
                delivery_qs = delivery_qs.filter(delivery_date__gte=filters['date_from'])

            if filters.get('date_to'):
                request_qs = request_qs.filter(delivery_date__lte=filters['date_to'])
                order_qs = order_qs.filter(expected_delivery_date__lte=filters['date_to'])
                delivery_qs = delivery_qs.filter(delivery_date__lte=filters['date_to'])

        # Limit results for performance
        results['requests'] = list(request_qs.order_by('-created_at')[:20])
        results['orders'] = list(order_qs.order_by('-created_at')[:20])
        results['deliveries'] = list(delivery_qs.order_by('-created_at')[:20])

        return results

    @staticmethod
    def get_urgent_items() -> Dict:
        """Get items requiring immediate attention"""
        today = timezone.now().date()

        return {
            'overdue_approvals': PurchaseRequest.objects.filter(
                status='submitted',
                created_at__date__lt=today - timedelta(days=2)
            ).count(),
            'orders_overdue_delivery': PurchaseOrder.objects.overdue_delivery().count(),
            'deliveries_pending_processing': DeliveryReceipt.objects.overdue_processing().count(),
            'quality_issues_today': DeliveryReceipt.objects.filter(
                has_quality_issues=True,
                delivery_date=today
            ).count(),
            'expiring_products': DeliveryLine.objects.expiring_soon(days=7).count(),
        }

    @staticmethod
    def get_supplier_performance(supplier, days=90) -> Dict:
        """Analyze supplier performance across all document types"""
        cutoff_date = timezone.now().date() - timedelta(days=days)

        # Orders data
        orders = PurchaseOrder.objects.filter(
            supplier=supplier,
            created_at__date__gte=cutoff_date
        )

        # Deliveries data
        deliveries = DeliveryReceipt.objects.filter(
            supplier=supplier,
            delivery_date__gte=cutoff_date
        )

        # Calculate metrics
        total_orders = orders.count()
        total_deliveries = deliveries.count()
        total_order_value = orders.aggregate(total=models.Sum('grand_total'))['total'] or Decimal('0')

        # Quality metrics
        quality_issues = deliveries.filter(has_quality_issues=True).count()
        quality_rate = ((total_deliveries - quality_issues) / total_deliveries * 100) if total_deliveries > 0 else 100

        # Delivery performance
        on_time_deliveries = 0
        for order in orders.filter(status='completed'):
            if order.expected_delivery_date and hasattr(order, 'deliveries'):
                actual_delivery = order.deliveries.first()
                if actual_delivery and actual_delivery.delivery_date <= order.expected_delivery_date:
                    on_time_deliveries += 1

        on_time_rate = (on_time_deliveries / total_orders * 100) if total_orders > 0 else 100

        # Variance analysis
        delivery_lines = DeliveryLine.objects.filter(
            document__supplier=supplier,
            document__delivery_date__gte=cutoff_date
        )
        total_lines = delivery_lines.count()
        variance_lines = delivery_lines.exclude(variance_=0).count()
        accuracy_rate = ((total_lines - variance_lines) / total_lines * 100) if total_lines > 0 else 100

        return {
            'summary': {
                'total_orders': total_orders,
                'total_deliveries': total_deliveries,
                'total_value': total_order_value,
                'average_order_value': total_order_value / total_orders if total_orders > 0 else Decimal('0'),
            },
            'performance': {
                'quality_rate': round(quality_rate, 1),
                'on_time_rate': round(on_time_rate, 1),
                'accuracy_rate': round(accuracy_rate, 1),
                'overall_score': round((quality_rate + on_time_rate + accuracy_rate) / 3, 1),
            },
            'details': {
                'quality_issues': quality_issues,
                'on_time_deliveries': on_time_deliveries,
                'variance_lines': variance_lines,
                'last_delivery': deliveries.order_by('-delivery_date').first(),
            }
        }

    @staticmethod
    def analyze_delivery_variances(date_from=None, date_to=None, supplier=None) -> Dict:
        """Analyze variances in deliveries"""
        lines = DeliveryLine.objects.exclude(variance_quantity=0)

        if date_from:
            lines = lines.filter(document__delivery_date__gte=date_from)
        if date_to:
            lines = lines.filter(document__delivery_date__lte=date_to)
        if supplier:
            lines = lines.filter(document__supplier=supplier)

        over_received = lines.filter(variance_quantity__gt=0)
        under_received = lines.filter(variance_quantity__lt=0)

        return {
            'summary': {
                'total_variances': lines.count(),
                'over_received_count': over_received.count(),
                'under_received_count': under_received.count(),
                'total_variance_value': sum(line.variance_value for line in lines),
            },
            'over_received_lines': list(over_received.select_related(
                'document__supplier', 'product'
            ).values(
                'document__document_number',
                'document__supplier__name',
                'product__code',
                'product__name',
                'ordered_quantity',
                'received_quantity',
                'variance_quantity',
                'unit_price'
            )[:20]),
            'under_received_lines': list(under_received.select_related(
                'document__supplier', 'product'
            ).values(
                'document__document_number',
                'document__supplier__name',
                'product__code',
                'product__name',
                'ordered_quantity',
                'received_quantity',
                'variance_quantity',
                'unit_price'
            )[:20])
        }

    @staticmethod
    def get_location_summary(location, days=30) -> Dict:
        """Get summary for specific location"""
        cutoff_date = timezone.now().date() - timedelta(days=days)

        # Requests for this location
        requests = PurchaseRequest.objects.filter(location=location)
        recent_requests = requests.filter(created_at__date__gte=cutoff_date)

        # Orders for this location
        orders = PurchaseOrder.objects.filter(location=location)
        recent_orders = orders.filter(created_at__date__gte=cutoff_date)

        # Deliveries for this location
        deliveries = DeliveryReceipt.objects.filter(location=location)
        recent_deliveries = deliveries.filter(delivery_date__gte=cutoff_date)

        return {
            'totals': {
                'total_requests': requests.count(),
                'total_orders': orders.count(),
                'total_deliveries': deliveries.count(),
            },
            f'last_{days}_days': {
                'requests': recent_requests.count(),
                'orders': recent_orders.count(),
                'deliveries': recent_deliveries.count(),
                'total_value': recent_deliveries.aggregate(
                    total=models.Sum('grand_total')
                )['total'] or Decimal('0'),
            },
            'pending': {
                'pending_approval': requests.filter(status='submitted').count(),
                'pending_delivery': orders.filter(status='confirmed').count(),
                'pending_processing': deliveries.filter(status='delivered').count(),
            },
            'top_suppliers': deliveries.values('supplier__name').annotate(
                count=models.Count('id'),
                total=models.Sum('grand_total')
            ).order_by('-total')[:5]
        }

    @staticmethod
    def get_workflow_analytics(date_from=None, date_to=None) -> Dict:
        """Analyze workflow performance"""

        # Filter by date range if provided
        request_qs = PurchaseRequest.objects.all()
        order_qs = PurchaseOrder.objects.all()
        delivery_qs = DeliveryReceipt.objects.all()

        if date_from:
            request_qs = request_qs.filter(created_at__date__gte=date_from)
            order_qs = order_qs.filter(created_at__date__gte=date_from)
            delivery_qs = delivery_qs.filter(created_at__date__gte=date_from)

        if date_to:
            request_qs = request_qs.filter(created_at__date__lte=date_to)
            order_qs = order_qs.filter(created_at__date__lte=date_to)
            delivery_qs = delivery_qs.filter(created_at__date__lte=date_to)

        # Calculate conversion rates
        total_requests = request_qs.count()
        approved_requests = request_qs.filter(status='approved').count()
        converted_requests = request_qs.filter(status='converted').count()

        total_orders = order_qs.count()
        confirmed_orders = order_qs.filter(status='confirmed').count()

        # Calculate averages
        avg_approval_time = None
        if total_requests > 0:
            approved_with_times = request_qs.filter(
                status__in=['approved', 'converted'],
                approved_at__isnull=False
            )
            if approved_with_times.exists():
                total_approval_time = sum(
                    (req.approved_at.date() - req.created_at.date()).days
                    for req in approved_with_times
                )
                avg_approval_time = total_approval_time / approved_with_times.count()

        return {
            'conversion_rates': {
                'request_approval_rate': (approved_requests / total_requests * 100) if total_requests > 0 else 0,
                'request_conversion_rate': (converted_requests / total_requests * 100) if total_requests > 0 else 0,
                'order_confirmation_rate': (confirmed_orders / total_orders * 100) if total_orders > 0 else 0,
            },
            'timing': {
                'average_approval_time_days': round(avg_approval_time, 1) if avg_approval_time else None,
            },
            'volumes': {
                'total_requests': total_requests,
                'total_orders': total_orders,
                'total_deliveries': delivery_qs.count(),
                'direct_orders': order_qs.filter(source_request__isnull=True).count(),
                'direct_deliveries': delivery_qs.filter(creation_type='direct').count(),
            }
        }

    @staticmethod
    @transaction.atomic
    def bulk_operations_across_types(operation: str, document_ids: Dict, user=None) -> Dict:
        """Perform bulk operations across different document types"""
        results = {
            'success_count': 0,
            'failed_count': 0,
            'errors': []
        }

        # Process requests
        if 'requests' in document_ids:
            request_ids = document_ids['requests']
            for req_id in request_ids:
                try:
                    request = PurchaseRequest.objects.get(id=req_id)
                    if operation == 'approve':
                        if request.can_be_approved():
                            request.approve(user)
                            results['success_count'] += 1
                        else:
                            results['errors'].append(f"Request {request.document_number}: Cannot be approved")
                            results['failed_count'] += 1
                except Exception as e:
                    results['errors'].append(f"Request {req_id}: {str(e)}")
                    results['failed_count'] += 1

        # Process orders
        if 'orders' in document_ids:
            order_ids = document_ids['orders']
            for order_id in order_ids:
                try:
                    order = PurchaseOrder.objects.get(id=order_id)
                    if operation == 'confirm':
                        if order.can_be_confirmed():
                            order.confirm_by_supplier(user)
                            results['success_count'] += 1
                        else:
                            results['errors'].append(f"Order {order.document_number}: Cannot be confirmed")
                            results['failed_count'] += 1
                except Exception as e:
                    results['errors'].append(f"Order {order_id}: {str(e)}")
                    results['failed_count'] += 1

        # Process deliveries
        if 'deliveries' in document_ids:
            delivery_ids = document_ids['deliveries']
            for delivery_id in delivery_ids:
                try:
                    delivery = DeliveryReceipt.objects.get(id=delivery_id)
                    if operation == 'receive':
                        if delivery.can_be_received():
                            delivery.receive_delivery(user)
                            results['success_count'] += 1
                        else:
                            results['errors'].append(f"Delivery {delivery.document_number}: Cannot be received")
                            results['failed_count'] += 1
                except Exception as e:
                    results['errors'].append(f"Delivery {delivery_id}: {str(e)}")
                    results['failed_count'] += 1

        return results