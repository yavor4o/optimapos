from django.db import models
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from decimal import Decimal
from datetime import timedelta, date


class PurchaseDocumentQuerySet(models.QuerySet):
    """Custom QuerySet за PurchaseDocument с бизнес логика"""

    def active(self):
        """Активни документи (не са изтрити)"""
        return self.filter(is_active=True)

    def draft(self):
        """Чернови документи"""
        return self.filter(status='draft')

    def confirmed(self):
        """Потвърдени документи"""
        return self.filter(status='confirmed')

    def received(self):
        """Получени документи"""
        return self.filter(status='received')

    def paid(self):
        """Платени документи"""
        return self.filter(payment_status='paid')

    def unpaid(self):
        """Неплатени документи"""
        return self.filter(payment_status='unpaid')

    def pending_receipt(self):
        """Чакащи получаване"""
        return self.filter(
            status='confirmed',
            delivery_date__lte=timezone.now().date()
        )

    def pending_payment(self):
        """Чакащи плащане"""
        return self.filter(
            payment_status='unpaid',
            status='received'
        )

    def overdue_payment(self, days_threshold: int = 0):
        """Просрочени плащания"""
        cutoff_date = timezone.now().date() - timedelta(days=days_threshold)
        return self.filter(
            payment_status='unpaid',
            payment_due_date__lt=cutoff_date
        )

    def due_soon(self, days_ahead: int = 7):
        """Скоро дължими плащания"""
        future_date = timezone.now().date() + timedelta(days=days_ahead)
        return self.filter(
            payment_status='unpaid',
            payment_due_date__lte=future_date,
            payment_due_date__gte=timezone.now().date()
        )

    def for_supplier(self, supplier):
        """За конкретен доставчик"""
        return self.filter(supplier=supplier)

    def for_location(self, location):
        """За конкретна локация"""
        return self.filter(delivery_location=location)

    def today_deliveries(self):
        """Доставки днес"""
        today = timezone.now().date()
        return self.filter(delivery_date=today)

    def this_week_deliveries(self):
        """Доставки тази седмица"""
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return self.filter(delivery_date__range=[week_start, week_end])

    def this_month(self):
        """Документи този месец"""
        today = timezone.now().date()
        month_start = today.replace(day=1)
        return self.filter(created_at__date__gte=month_start)

    def in_date_range(self, date_from=None, date_to=None):
        """В дадения период"""
        queryset = self
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def search(self, query: str):
        """Търсене по различни полета"""
        return self.filter(
            Q(document_number__icontains=query) |
            Q(supplier__name__icontains=query) |
            Q(supplier__company_name__icontains=query) |
            Q(notes__icontains=query)
        )

    def large_orders(self, threshold: Decimal = Decimal('1000.00')):
        """Големи поръчки"""
        return self.filter(grand_total__gte=threshold)

    def with_discounts(self):
        """С отстъпки"""
        return self.filter(discount_amount__gt=0)

    def with_quality_issues(self):
        """С качествени проблеми"""
        return self.filter(quality_rating__lt=3)

    def expiring_soon(self, days: int = 30):
        """Изтичащи скоро (ако има expiry_date поле)"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__isnull=False,
            expiry_date__lte=cutoff_date
        )

    def summary_stats(self):
        """Обобщени статистики"""
        return self.aggregate(
            total_count=Count('id'),
            total_amount=Sum('grand_total'),
            avg_amount=Avg('grand_total'),
            draft_count=Count('id', filter=Q(status='draft')),
            confirmed_count=Count('id', filter=Q(status='confirmed')),
            received_count=Count('id', filter=Q(status='received')),
            paid_count=Count('id', filter=Q(payment_status='paid')),
            unpaid_count=Count('id', filter=Q(payment_status='unpaid')),
        )


class PurchaseDocumentManager(models.Manager):
    """Manager за PurchaseDocument с готови методи"""

    def get_queryset(self):
        return PurchaseDocumentQuerySet(self.model, using=self._db)

    # Всички методи делегират към QuerySet
    def active(self):
        return self.get_queryset().active()

    def draft(self):
        return self.get_queryset().draft()

    def confirmed(self):
        return self.get_queryset().confirmed()

    def received(self):
        return self.get_queryset().received()

    def paid(self):
        return self.get_queryset().paid()

    def unpaid(self):
        return self.get_queryset().unpaid()

    def pending_receipt(self):
        return self.get_queryset().pending_receipt()

    def pending_payment(self):
        return self.get_queryset().pending_payment()

    def overdue_payment(self, days_threshold: int = 0):
        return self.get_queryset().overdue_payment(days_threshold)

    def due_soon(self, days_ahead: int = 7):
        return self.get_queryset().due_soon(days_ahead)

    def for_supplier(self, supplier):
        return self.get_queryset().for_supplier(supplier)

    def for_location(self, location):
        return self.get_queryset().for_location(location)

    def today_deliveries(self):
        return self.get_queryset().today_deliveries()

    def this_week_deliveries(self):
        return self.get_queryset().this_week_deliveries()

    def this_month(self):
        return self.get_queryset().this_month()

    def search(self, query: str):
        return self.get_queryset().search(query)

    def large_orders(self, threshold: Decimal = Decimal('1000.00')):
        return self.get_queryset().large_orders(threshold)

    def with_discounts(self):
        return self.get_queryset().with_discounts()

    def with_quality_issues(self):
        return self.get_queryset().with_quality_issues()

    def expiring_soon(self, days: int = 30):
        return self.get_queryset().expiring_soon(days)

    def get_dashboard_summary(self):
        """Данни за dashboard"""
        today = timezone.now().date()

        # Основни числа
        basic_stats = self.get_queryset().summary_stats()

        # Urgent items
        urgent_deliveries = self.today_deliveries().count()
        overdue_payments = self.overdue_payment().count()
        due_soon_payments = self.due_soon().count()

        # Recent activity
        recent_docs = self.get_queryset().in_date_range(
            date_from=today - timedelta(days=7)
        ).order_by('-created_at')[:5]

        return {
            'basic_stats': basic_stats,
            'urgent': {
                'deliveries_today': urgent_deliveries,
                'overdue_payments': overdue_payments,
                'due_soon_payments': due_soon_payments,
            },
            'recent_activity': list(recent_docs.values(
                'document_number', 'supplier__name', 'grand_total',
                'status', 'delivery_date', 'created_at'
            ))
        }