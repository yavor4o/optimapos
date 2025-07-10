from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class SupplierService:
    """
    Сервис за работа с доставчици
    Централизира бизнес логиката за доставки, салдо, плащания
    """

    @staticmethod
    def get_supplier_dashboard(supplier_id: int) -> Dict:
        """
        Връща пълни данни за supplier dashboard/modal
        """
        from ..models import Supplier

        try:
            supplier = Supplier.objects.select_related().prefetch_related(
                'divisions', 'day_schedules'
            ).get(id=supplier_id)
        except Supplier.DoesNotExist:
            return {'error': 'Supplier not found'}

        # Основни данни
        basic_info = {
            'id': supplier.id,
            'name': supplier.name,
            'contact_person': supplier.contact_person,
            'phone': supplier.phone,
            'email': supplier.email,
            'is_active': supplier.is_active,
            'delivery_blocked': supplier.delivery_blocked,
            'can_deliver': supplier.can_deliver(),
        }

        # Дивизии
        divisions = SupplierService.get_supplier_divisions(supplier)

        # График
        schedule = SupplierService.get_supplier_schedule(supplier)

        # Финансово резюме
        financial = SupplierService.get_financial_summary(supplier)

        # История на доставки
        deliveries = SupplierService.get_delivery_history(supplier, limit=10)

        # Статистики
        statistics = SupplierService.get_supplier_statistics(supplier)

        return {
            'basic_info': basic_info,
            'divisions': divisions,
            'schedule': schedule,
            'financial': financial,
            'deliveries': deliveries,
            'statistics': statistics,
        }

    @staticmethod
    def get_supplier_divisions(supplier) -> List[Dict]:
        """Връща активните дивизии на доставчика"""
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
        return divisions

    @staticmethod
    def get_supplier_schedule(supplier) -> Dict:
        """Връща графика на доставчика"""
        schedules = supplier.day_schedules.all()

        order_days = []
        delivery_days = []

        for schedule in schedules:
            day_info = {
                'day': schedule.day,
                'day_display': schedule.get_day_display(),
                'order_deadline': schedule.order_deadline_time,
                'delivery_from': schedule.delivery_time_from,
                'delivery_to': schedule.delivery_time_to,
            }

            if schedule.expects_order:
                order_days.append(day_info)
            if schedule.makes_delivery:
                delivery_days.append(day_info)

        return {
            'order_days': order_days,
            'delivery_days': delivery_days,
            'order_days_count': len(order_days),
            'delivery_days_count': len(delivery_days),
        }

    @staticmethod
    def get_financial_summary(supplier) -> Dict:
        """Връща финансово резюме за доставчика"""
        try:
            # Опитваме се да импортираме purchases models
            from purchases.models import PurchaseDocument

            # Общо стойност на поръчки
            total_orders = PurchaseDocument.objects.filter(
                supplier=supplier
            ).aggregate(
                total_amount=Sum('grand_total'),
                count=Count('id')
            )

            # Неплатени фактури
            unpaid_orders = PurchaseDocument.objects.filter(
                supplier=supplier,
                is_paid=False
            ).aggregate(
                unpaid_amount=Sum('grand_total'),
                count=Count('id')
            )

            # Просрочени плащания
            overdue_date = timezone.now().date() - timedelta(days=supplier.payment_days)
            overdue_orders = PurchaseDocument.objects.filter(
                supplier=supplier,
                is_paid=False,
                delivery_date__lt=overdue_date
            ).aggregate(
                overdue_amount=Sum('grand_total'),
                count=Count('id')
            )

            # Последни 30 дни
            last_30_days = timezone.now().date() - timedelta(days=30)
            recent_orders = PurchaseDocument.objects.filter(
                supplier=supplier,
                document_date__gte=last_30_days
            ).aggregate(
                recent_amount=Sum('grand_total'),
                count=Count('id')
            )

            return {
                'credit_limit': supplier.credit_limit,
                'payment_days': supplier.payment_days,
                'total_orders': {
                    'amount': total_orders['total_amount'] or Decimal('0'),
                    'count': total_orders['count'] or 0
                },
                'unpaid': {
                    'amount': unpaid_orders['unpaid_amount'] or Decimal('0'),
                    'count': unpaid_orders['count'] or 0
                },
                'overdue': {
                    'amount': overdue_orders['overdue_amount'] or Decimal('0'),
                    'count': overdue_orders['count'] or 0
                },
                'last_30_days': {
                    'amount': recent_orders['recent_amount'] or Decimal('0'),
                    'count': recent_orders['count'] or 0
                },
                'available_credit': supplier.credit_limit - (unpaid_orders['unpaid_amount'] or Decimal('0'))
            }

        except ImportError:
            # Purchases app не е налично
            return {
                'credit_limit': supplier.credit_limit,
                'payment_days': supplier.payment_days,
                'message': 'Purchase data not available - purchases app not installed'
            }

    @staticmethod
    def get_delivery_history(supplier, date_from=None, date_to=None, limit=None) -> List[Dict]:
        """Връща история на доставките"""
        try:
            from purchases.models import PurchaseDocument

            # Филтриране по дати
            queryset = PurchaseDocument.objects.filter(supplier=supplier)

            if date_from:
                queryset = queryset.filter(document_date__gte=date_from)
            if date_to:
                queryset = queryset.filter(document_date__lte=date_to)

            queryset = queryset.select_related('warehouse', 'document_type').order_by('-document_date')

            if limit:
                queryset = queryset[:limit]

            deliveries = []
            for doc in queryset:
                deliveries.append({
                    'id': doc.id,
                    'document_number': doc.document_number,
                    'document_date': doc.document_date,
                    'delivery_date': doc.delivery_date,
                    'warehouse': doc.warehouse.name,
                    'status': doc.status,
                    'status_display': doc.get_status_display(),
                    'grand_total': doc.grand_total,
                    'is_paid': doc.is_paid,
                    'document_type': doc.document_type.name,
                })

            return deliveries

        except ImportError:
            return []

    @staticmethod
    def get_supplier_statistics(supplier) -> Dict:
        """Връща статистики за доставчика"""
        try:
            from purchases.models import PurchaseDocument

            # Статистики за последните 12 месеца
            twelve_months_ago = timezone.now().date() - timedelta(days=365)

            monthly_stats = PurchaseDocument.objects.filter(
                supplier=supplier,
                document_date__gte=twelve_months_ago
            ).extra(
                select={'month': "strftime('%%Y-%%m', document_date)"}
            ).values('month').annotate(
                total_amount=Sum('grand_total'),
                order_count=Count('id')
            ).order_by('month')

            # Средно време за плащане
            paid_orders = PurchaseDocument.objects.filter(
                supplier=supplier,
                is_paid=True,
                document_date__gte=twelve_months_ago
            )

            avg_payment_delay = 0
            if paid_orders.exists():
                # Тук трябва да имаме payment_date field в PurchaseDocument
                # За сега използваме приблизителни данни
                avg_payment_delay = supplier.payment_days

            # Най-често поръчвани продукти
            try:
                from purchases.models import PurchaseDocumentLine

                top_products = PurchaseDocumentLine.objects.filter(
                    document__supplier=supplier,
                    document__document_date__gte=twelve_months_ago
                ).values(
                    'product__code', 'product__name'
                ).annotate(
                    total_quantity=Sum('quantity_base_unit'),
                    total_amount=Sum('line_total'),
                    order_count=Count('document', distinct=True)
                ).order_by('-total_amount')[:10]

                top_products_list = list(top_products)
            except ImportError:
                top_products_list = []

            return {
                'monthly_stats': list(monthly_stats),
                'avg_payment_delay': avg_payment_delay,
                'top_products': top_products_list,
                'active_divisions': supplier.divisions.filter(is_active=True).count(),
                'total_divisions': supplier.divisions.count(),
            }

        except ImportError:
            return {
                'message': 'Statistics not available - purchases app not installed',
                'active_divisions': supplier.divisions.filter(is_active=True).count(),
                'total_divisions': supplier.divisions.count(),
            }

    @staticmethod
    def get_overdue_payments(supplier) -> List[Dict]:
        """Връща просрочени плащания"""
        try:
            from purchases.models import PurchaseDocument

            overdue_date = timezone.now().date() - timedelta(days=supplier.payment_days)

            overdue_docs = PurchaseDocument.objects.filter(
                supplier=supplier,
                is_paid=False,
                delivery_date__lt=overdue_date
            ).select_related('warehouse').order_by('delivery_date')

            overdue_list = []
            for doc in overdue_docs:
                days_overdue = (timezone.now().date() - doc.delivery_date).days - supplier.payment_days

                overdue_list.append({
                    'document_number': doc.document_number,
                    'delivery_date': doc.delivery_date,
                    'amount': doc.grand_total,
                    'days_overdue': days_overdue,
                    'warehouse': doc.warehouse.name,
                })

            return overdue_list

        except ImportError:
            return []

    @staticmethod
    def can_place_order(supplier, amount: Decimal) -> Tuple[bool, str]:
        """Проверява дали може да се направи поръчка"""
        if not supplier.is_active:
            return False, "Supplier is not active"

        if supplier.delivery_blocked:
            return False, "Delivery is blocked for this supplier"

        # Проверка на кредитен лимит
        if supplier.credit_limit > 0:
            financial = SupplierService.get_financial_summary(supplier)
            if financial.get('available_credit', 0) < amount:
                return False, f"Credit limit exceeded. Available: {financial.get('available_credit', 0)}"

        return True, "OK"

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