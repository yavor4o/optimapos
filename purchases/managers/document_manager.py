# purchases/managers/document_manager.py

from django.db import models
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q, F
from decimal import Decimal
from datetime import timedelta, date
from typing import Optional


class PurchaseDocumentQuerySet(models.QuerySet):
    """Специализиран QuerySet за PurchaseDocument с мощни филтри"""

    def active(self):
        """Връща активни документи (не cancelled)"""
        return self.exclude(status='cancelled')

    def draft(self):
        """Връща draft документи"""
        return self.filter(status='draft')

    def confirmed(self):
        """Връща потвърдени документи"""
        return self.filter(status='confirmed')

    def received(self):
        """Връща получени документи"""
        return self.filter(status='received')

    def paid(self):
        """Връща платени документи"""
        return self.filter(is_paid=True)

    def unpaid(self):
        """Връща неплатени документи"""
        return self.filter(is_paid=False)

    def pending_receipt(self):
        """Документи които чакат получаване"""
        return self.filter(status='confirmed')

    def pending_payment(self):
        """Документи които чакат плащане"""
        return self.filter(status__in=['received', 'closed'], is_paid=False)

    def overdue_payment(self, days_threshold: int = 0):
        """Документи с просрочени плащания"""
        today = timezone.now().date()

        return self.filter(
            is_paid=False,
            status__in=['received', 'closed']
        ).annotate(
            due_date=F('delivery_date') + timedelta(days=F('supplier__payment_days'))
        ).filter(
            due_date__lt=today - timedelta(days=days_threshold)
        )

    def due_soon(self, days_ahead: int = 7):
        """Документи с плащания които падат скоро"""
        today = timezone.now().date()
        future_date = today + timedelta(days=days_ahead)

        return self.filter(
            is_paid=False,
            status__in=['received', 'closed']
        ).annotate(
            due_date=F('delivery_date') + timedelta(days=F('supplier__payment_days'))
        ).filter(
            due_date__lte=future_date,
            due_date__gte=today
        )

    def for_supplier(self, supplier):
        """Документи за определен supplier"""
        return self.filter(supplier=supplier)

    def for_location(self, location):
        """Документи за определена локация"""
        return self.filter(location=location)

    def in_date_range(self, date_from: Optional[date] = None, date_to: Optional[date] = None):
        """Документи в определен период"""
        queryset = self
        if date_from:
            queryset = queryset.filter(document_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(document_date__lte=date_to)
        return queryset

    def in_delivery_range(self, date_from: Optional[date] = None, date_to: Optional[date] = None):
        """Документи с доставки в определен период"""
        queryset = self
        if date_from:
            queryset = queryset.filter(delivery_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(delivery_date__lte=date_to)
        return queryset

    def with_totals(self):
        """Анотира с изчислени суми"""
        return self.annotate(
            lines_count=Count('lines'),
            total_quantity=Sum('lines__quantity'),
            total_items=Count('lines__product', distinct=True),
            calculated_subtotal=Sum('lines__line_total'),
            avg_line_value=Avg('lines__line_total')
        )

    def with_supplier_info(self):
        """Добавя supplier информация"""
        return self.select_related('supplier').annotate(
            supplier_payment_days=F('supplier__payment_days'),
            supplier_credit_limit=F('supplier__credit_limit')
        )

    def by_document_type(self, document_type_code: str):
        """Филтрира по тип документ"""
        return self.filter(document_type__code=document_type_code)

    def invoices(self):
        """Само фактури"""
        return self.filter(document_type__type_key='invoice')

    def deliveries(self):
        """Само доставки"""
        return self.filter(document_type__type_key='stock_in')

    def large_orders(self, threshold: Decimal = Decimal('1000.00')):
        """Документи над определена стойност"""
        return self.filter(grand_total__gte=threshold)

    def today_deliveries(self):
        """Доставки за днес"""
        today = timezone.now().date()
        return self.filter(delivery_date=today)

    def this_week_deliveries(self):
        """Доставки за тази седмица"""
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return self.filter(delivery_date__range=[week_start, week_end])

    def this_month(self):
        """Документи за този месец"""
        today = timezone.now().date()
        return self.filter(
            document_date__year=today.year,
            document_date__month=today.month
        )

    def with_discounts(self):
        """Документи с отстъпки"""
        return self.filter(lines__discount_percent__gt=0).distinct()

    def with_quality_issues(self):
        """Документи с проблеми в качеството"""
        return self.filter(lines__quality_approved=False).distinct()

    def expiring_soon(self, days: int = 30):
        """Документи с продукти които изтичат скоро"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            lines__expiry_date__lte=cutoff_date,
            lines__expiry_date__isnull=False
        ).distinct()

    def search(self, query: str):
        """Търси в документи по различни критерии"""
        return self.filter(
            Q(document_number__icontains=query) |
            Q(supplier_document_number__icontains=query) |
            Q(external_reference__icontains=query) |
            Q(supplier__name__icontains=query) |
            Q(supplier__code__icontains=query) |
            Q(notes__icontains=query)
        )

    def performance_analysis(self):
        """Анотира с performance данни"""
        today = timezone.now().date()

        return self.annotate(
            # Дни до доставка
            days_to_delivery=F('delivery_date') - F('document_date'),

            # Дни до падеж на плащане
            payment_due_date=F('delivery_date') + timedelta(days=F('supplier__payment_days')),
            days_to_payment=F('payment_due_date') - today,

            # Status flags
            is_urgent_delivery=models.Case(
                models.When(delivery_date=today, then=True),
                default=False,
                output_field=models.BooleanField()
            ),

            is_late_delivery=models.Case(
                models.When(
                    delivery_date__lt=today,
                    status__in=['draft', 'confirmed'],
                    then=True
                ),
                default=False,
                output_field=models.BooleanField()
            ),

            is_overdue_payment=models.Case(
                models.When(
                    payment_due_date__lt=today,
                    is_paid=False,
                    then=True
                ),
                default=False,
                output_field=models.BooleanField()
            )
        )

    def summary_stats(self):
        """Връща summary статистики"""
        return self.aggregate(
            total_count=Count('id'),
            total_value=Sum('grand_total'),
            avg_value=Avg('grand_total'),
            total_lines=Sum('lines_count'),
            unique_suppliers=Count('supplier', distinct=True),
            unique_products=Count('lines__product', distinct=True),

            # По статуси
            draft_count=Count('id', filter=Q(status='draft')),
            confirmed_count=Count('id', filter=Q(status='confirmed')),
            received_count=Count('id', filter=Q(status='received')),
            paid_count=Count('id', filter=Q(is_paid=True)),

            # Финансови
            unpaid_value=Sum('grand_total', filter=Q(is_paid=False)),
            paid_value=Sum('grand_total', filter=Q(is_paid=True)),
        )


class PurchaseDocumentManager(models.Manager):
    """Manager за PurchaseDocument с готови методи"""

    def get_queryset(self):
        return PurchaseDocumentQuerySet(self.model, using=self._db)

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