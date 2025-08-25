# partners/services/supplier_service.py - REFACTORED WITH RESULT PATTERN

from django.db.models import Sum, Count, Avg
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from core.utils.result import Result


class SupplierService:
    """
    Сервис за работа с доставчици

    REFACTORED: All methods now return Result objects for consistency
    Legacy methods available for backward compatibility
    """

    # =====================================================
    # NEW: RESULT-BASED METHODS
    # =====================================================

    @staticmethod
    def get_dashboard_data(supplier_id: int) -> Result:
        """
        Връща пълни данни за supplier dashboard - NEW Result-based method
        """
        from ..models import Supplier

        try:
            supplier = Supplier.objects.select_related().prefetch_related(
                'divisions', 'day_schedules'
            ).get(id=supplier_id)
        except Supplier.DoesNotExist:
            return Result.error(
                code='SUPPLIER_NOT_FOUND',
                msg=f'Supplier with ID {supplier_id} not found',
                data={'supplier_id': supplier_id}
            )

        # Основни данни
        basic_info = {
            'id': supplier.id,
            'name': supplier.name,
            'code': getattr(supplier, 'code', ''),  # От новия IPartner protocol
            'contact_person': supplier.contact_person,
            'phone': supplier.phone,
            'email': supplier.email,
            'is_active': supplier.is_active,
            'delivery_blocked': supplier.delivery_blocked,
            'can_deliver': supplier.can_deliver(),
        }

        # Дивизии
        divisions_result = SupplierService.get_divisions_data(supplier)
        divisions = divisions_result.data if divisions_result.ok else []

        # График
        schedule_result = SupplierService.get_schedule_data(supplier)
        schedule = schedule_result.data if schedule_result.ok else {}

        # Финансово резюме
        financial_result = SupplierService.get_financial_data(supplier)
        financial = financial_result.data if financial_result.ok else {}

        # История на доставки
        deliveries_result = SupplierService.get_delivery_data(supplier, limit=10)
        deliveries = deliveries_result.data if deliveries_result.ok else []

        # Статистики
        statistics_result = SupplierService.get_statistics_data(supplier)
        statistics = statistics_result.data if statistics_result.ok else {}

        dashboard_data = {
            'basic_info': basic_info,
            'divisions': divisions,
            'schedule': schedule,
            'financial': financial,
            'deliveries': deliveries,
            'statistics': statistics,
            'supplier_id': supplier_id,
            'generated_at': timezone.now().isoformat()
        }

        return Result.success(
            data=dashboard_data,
            msg=f"Dashboard data for {supplier.name} retrieved successfully"
        )

    @staticmethod
    def get_divisions_data(supplier) -> Result:
        """Връща активните дивизии на доставчика - NEW Result-based method"""
        try:
            divisions = []
            for division in supplier.divisions.filter(is_active=True):
                divisions.append({
                    'id': division.id,
                    'name': division.name,
                    'code': division.code,
                    'contact_person': division.contact_person,
                    'phone': division.phone,
                    'email': division.email,
                    'payment_days': division.get_effective_payment_days(),
                })

            return Result.success(
                data=divisions,
                msg=f"Found {len(divisions)} active divisions"
            )

        except Exception as e:
            return Result.error(
                code='DIVISIONS_ERROR',
                msg=f"Error retrieving divisions: {str(e)}",
                data={'supplier_id': supplier.id}
            )

    @staticmethod
    def get_schedule_data(supplier) -> Result:
        """Връща графика на доставчика - NEW Result-based method"""
        try:
            schedules = supplier.day_schedules.all()

            order_days = []
            delivery_days = []

            for schedule in schedules:
                day_info = {
                    'day': schedule.day,
                    'day_display': schedule.get_day_display(),
                    'order_deadline': getattr(schedule, 'order_deadline_time', None),
                    'delivery_from': getattr(schedule, 'delivery_time_from', None),
                    'delivery_to': getattr(schedule, 'delivery_time_to', None),
                }

                if schedule.expects_order:
                    order_days.append(day_info)
                if schedule.makes_delivery:
                    delivery_days.append(day_info)

            schedule_data = {
                'order_days': order_days,
                'delivery_days': delivery_days,
                'order_days_count': len(order_days),
                'delivery_days_count': len(delivery_days),
            }

            return Result.success(
                data=schedule_data,
                msg=f"Schedule: {len(order_days)} order days, {len(delivery_days)} delivery days"
            )

        except Exception as e:
            return Result.error(
                code='SCHEDULE_ERROR',
                msg=f"Error retrieving schedule: {str(e)}",
                data={'supplier_id': supplier.id}
            )

    @staticmethod
    def get_financial_data(supplier) -> Result:
        """Връща финансово резюме за доставчика - NEW Result-based method"""
        try:
            # Опитваме се да импортираме purchases models
            from purchases.models import PurchaseOrder

            # Общо стойност на поръчки
            total_orders = PurchaseOrder.objects.filter(
                supplier=supplier
            ).aggregate(
                total_amount=Sum('total'),
                count=Count('id')
            )

            # Неплатени фактури (ако има is_paid поле)
            unpaid_orders = PurchaseOrder.objects.filter(
                supplier=supplier,
                # is_paid=False  # ако има това поле
            ).aggregate(
                unpaid_amount=Sum('total'),
                unpaid_count=Count('id')
            )

            # Кредитен лимит
            used_credit = unpaid_orders.get('unpaid_amount') or Decimal('0')
            available_credit = max(Decimal('0'), supplier.credit_limit - used_credit)

            financial_data = {
                'credit_limit': supplier.credit_limit,
                'used_credit': used_credit,
                'available_credit': available_credit,
                'payment_days': supplier.payment_days,
                'total_orders_amount': total_orders.get('total_amount') or Decimal('0'),
                'total_orders_count': total_orders.get('count') or 0,
                'unpaid_amount': unpaid_orders.get('unpaid_amount') or Decimal('0'),
                'unpaid_count': unpaid_orders.get('unpaid_count') or 0,
            }

            return Result.success(
                data=financial_data,
                msg=f"Financial data: {financial_data['total_orders_count']} orders, {financial_data['unpaid_count']} unpaid"
            )

        except ImportError:
            # Purchases app не е налично
            fallback_data = {
                'credit_limit': supplier.credit_limit,
                'payment_days': supplier.payment_days,
                'message': 'Purchase data not available - purchases app not installed'
            }
            return Result.success(
                data=fallback_data,
                msg='Limited financial data (purchases app not available)'
            )
        except Exception as e:
            return Result.error(
                code='FINANCIAL_ERROR',
                msg=f"Error retrieving financial data: {str(e)}",
                data={'supplier_id': supplier.id}
            )

    @staticmethod
    def get_delivery_data(supplier, date_from=None, date_to=None, limit=None) -> Result:
        """Връща история на доставките - NEW Result-based method"""
        try:
            from purchases.models import PurchaseOrder

            # Филтриране по дати
            queryset = PurchaseOrder.objects.filter(supplier=supplier)

            if date_from:
                queryset = queryset.filter(document_date__gte=date_from)
            if date_to:
                queryset = queryset.filter(document_date__lte=date_to)

            queryset = queryset.select_related('location').order_by('-document_date')

            if limit:
                queryset = queryset[:limit]

            deliveries = []
            for order in queryset:
                deliveries.append({
                    'id': order.id,
                    'document_number': order.document_number,
                    'document_date': order.document_date,
                    'location': order.location.name if order.location else 'Unknown',
                    'status': order.status,
                    'total': getattr(order, 'total', Decimal('0')),
                    'created_at': order.created_at,
                })

            return Result.success(
                data=deliveries,
                msg=f"Found {len(deliveries)} delivery records"
            )

        except ImportError:
            return Result.success(
                data=[],
                msg='Delivery history not available (purchases app not installed)'
            )
        except Exception as e:
            return Result.error(
                code='DELIVERY_ERROR',
                msg=f"Error retrieving delivery data: {str(e)}",
                data={'supplier_id': supplier.id}
            )

    @staticmethod
    def get_statistics_data(supplier) -> Result:
        """Връща статистики за доставчика - NEW Result-based method"""
        try:
            from purchases.models import PurchaseOrder

            # Статистики за последните 12 месеца
            twelve_months_ago = timezone.now().date() - timedelta(days=365)

            stats = PurchaseOrder.objects.filter(
                supplier=supplier,
                document_date__gte=twelve_months_ago
            ).aggregate(
                total_orders=Count('id'),
                total_amount=Sum('total'),
                avg_order_value=Avg('total')
            )

            statistics_data = {
                'period': '12 months',
                'total_orders': stats.get('total_orders', 0),
                'total_amount': stats.get('total_amount') or Decimal('0'),
                'avg_order_value': stats.get('avg_order_value') or Decimal('0'),
                'active_divisions': supplier.divisions.filter(is_active=True).count(),
                'total_divisions': supplier.divisions.count(),
                'period_start': twelve_months_ago,
                'period_end': timezone.now().date(),
            }

            return Result.success(
                data=statistics_data,
                msg=f"Statistics: {statistics_data['total_orders']} orders in last 12 months"
            )

        except ImportError:
            fallback_data = {
                'message': 'Statistics not available - purchases app not installed',
                'active_divisions': supplier.divisions.filter(is_active=True).count(),
                'total_divisions': supplier.divisions.count(),
            }
            return Result.success(
                data=fallback_data,
                msg='Limited statistics (purchases app not available)'
            )
        except Exception as e:
            return Result.error(
                code='STATISTICS_ERROR',
                msg=f"Error retrieving statistics: {str(e)}",
                data={'supplier_id': supplier.id}
            )

    @staticmethod
    def validate_supplier_operation(supplier, amount: Decimal) -> Result:
        """Проверява дали може да се направи поръчка - NEW Result-based method"""
        if not supplier.is_active:
            return Result.error(
                code='SUPPLIER_INACTIVE',
                msg="Supplier is not active",
                data={'supplier_id': supplier.id, 'name': supplier.name}
            )

        if supplier.delivery_blocked:
            return Result.error(
                code='DELIVERY_BLOCKED',
                msg="Delivery is blocked for this supplier",
                data={'supplier_id': supplier.id, 'name': supplier.name}
            )

        # Проверка на кредитен лимит
        if supplier.credit_limit > 0:
            financial_result = SupplierService.get_financial_data(supplier)
            if financial_result.ok:
                available_credit = financial_result.data.get('available_credit', 0)
                if available_credit < amount:
                    return Result.error(
                        code='CREDIT_LIMIT_EXCEEDED',
                        msg=f"Credit limit exceeded. Available: {available_credit}",
                        data={
                            'credit_limit': supplier.credit_limit,
                            'available_credit': available_credit,
                            'requested_amount': amount
                        }
                    )

        return Result.success(
            data={'amount': amount, 'supplier_id': supplier.id},
            msg="Order can be placed"
        )

    # =====================================================
    # UTILITY METHODS
    # =====================================================

    @staticmethod
    def get_today_delivery_suppliers():
        """Връща доставчици които правят доставки днес"""
        from ..models import Supplier

        today = timezone.now().strftime('%a').lower()[:3]  # mon, tue, etc.

        return Supplier.objects.filter(
            day_schedules__day=today,
            day_schedules__makes_delivery=True,
            is_active=True,
            delivery_blocked=False
        ).distinct().select_related().prefetch_related('divisions')