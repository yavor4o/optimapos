# purchases/services/reporting_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import models
from django.utils import timezone
from datetime import timedelta, date
from django.db.models import Sum, Count, Avg, Q, F

from ..models import PurchaseDocument, PurchaseDocumentLine


class ReportingService:
    """Сервис за отчети и анализи"""

    @staticmethod
    def get_dashboard_data(location=None, days_back=30) -> Dict:
        """Основни данни за dashboard"""

        today = timezone.now().date()
        period_start = today - timedelta(days=days_back)

        # Base querysets
        docs_qs = PurchaseDocument.objects.active()
        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            docs_qs = docs_qs.for_location(location)
            lines_qs = lines_qs.for_location(location)

        # Основни KPI-та
        kpis = {
            'total_documents': docs_qs.count(),
            'total_value': docs_qs.aggregate(total=Sum('grand_total'))['total'] or 0,
            'pending_deliveries': docs_qs.confirmed().count(),
            'overdue_payments': docs_qs.overdue_payment().count(),
            'quality_issues': lines_qs.quality_issues().count(),
            'expiring_products': lines_qs.expiring_soon(days=7).count()
        }

        # Тенденции за периода
        period_docs = docs_qs.in_date_range(period_start, today)
        trends = {
            'period_documents': period_docs.count(),
            'period_value': period_docs.aggregate(total=Sum('grand_total'))['total'] or 0,
            'avg_document_value': period_docs.aggregate(avg=Avg('grand_total'))['avg'] or 0,
            'top_suppliers': ReportingService.get_top_suppliers(location, period_start, today, limit=5)
        }

        # Urgent items
        urgent = {
            'deliveries_today': docs_qs.today_deliveries().count(),
            'payments_due_soon': docs_qs.due_soon(days=3).count(),
            'critical_expiry': lines_qs.expiring_soon(days=3).count()
        }

        return {
            'kpis': kpis,
            'trends': trends,
            'urgent': urgent,
            'period': {'from': period_start, 'to': today}
        }

    @staticmethod
    def get_supplier_analysis(date_from=None, date_to=None, location=None) -> List[Dict]:
        """Анализ по доставчици"""

        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            lines_qs = lines_qs.for_location(location)

        if date_from or date_to:
            lines_qs = lines_qs.in_date_range(date_from, date_to)

        return lines_qs.supplier_performance()

    @staticmethod
    def get_product_cost_analysis(date_from=None, date_to=None, location=None) -> List[Dict]:
        """Анализ на себестойности по продукти"""

        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            lines_qs = lines_qs.for_location(location)

        if date_from or date_to:
            lines_qs = lines_qs.in_date_range(date_from, date_to)

        return lines_qs.cost_analysis_by_product()

    @staticmethod
    def get_expiry_report(location=None, days_ahead=30) -> Dict:
        """Отчет за срокове на годност"""

        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            lines_qs = lines_qs.for_location(location)

        # Категории по срок на годност
        today = timezone.now().date()

        categories = {
            'expired': lines_qs.expired().count(),
            'expires_this_week': lines_qs.expiring_soon(days=7).count(),
            'expires_this_month': lines_qs.expiring_soon(days=30).count(),
            'good_expiry': lines_qs.good_expiry(min_days=30).count()
        }

        # Детайлен списък
        expiry_details = lines_qs.expiry_report()[:50]  # Top 50

        # Стойностен анализ
        value_analysis = {
            'expired_value': lines_qs.expired().aggregate(
                total=Sum('line_total')
            )['total'] or 0,
            'critical_value': lines_qs.expiring_soon(days=7).aggregate(
                total=Sum('line_total')
            )['total'] or 0
        }

        return {
            'categories': categories,
            'details': list(expiry_details),
            'value_analysis': value_analysis,
            'report_date': today
        }

    @staticmethod
    def get_payment_schedule(location=None, days_ahead=30) -> Dict:
        """График на плащания"""

        today = timezone.now().date()
        end_date = today + timedelta(days=days_ahead)

        docs_qs = PurchaseDocument.objects.pending_payment()

        if location:
            docs_qs = docs_qs.for_location(location)

        # Анотираме с due dates
        docs_with_due_dates = docs_qs.annotate(
            due_date=F('delivery_date') + models.F('supplier__payment_days')
        ).filter(
            due_date__lte=end_date
        ).order_by('due_date')

        # Групираме по статус
        overdue = []
        due_soon = []
        future = []

        for doc in docs_with_due_dates:
            doc_data = {
                'document_number': doc.document_number,
                'supplier': doc.supplier.name,
                'amount': doc.grand_total,
                'due_date': doc.due_date,
                'days_overdue': (today - doc.due_date).days if doc.due_date < today else 0,
                'days_until_due': (doc.due_date - today).days if doc.due_date >= today else 0
            }

            if doc.due_date < today:
                overdue.append(doc_data)
            elif doc.due_date <= today + timedelta(days=7):
                due_soon.append(doc_data)
            else:
                future.append(doc_data)

        # Сумарни данни
        totals = {
            'overdue_amount': sum(item['amount'] for item in overdue),
            'due_soon_amount': sum(item['amount'] for item in due_soon),
            'future_amount': sum(item['amount'] for item in future),
            'total_pending': sum(item['amount'] for item in overdue + due_soon + future)
        }

        return {
            'overdue': overdue,
            'due_soon': due_soon,
            'future': future,
            'totals': totals,
            'period': {'from': today, 'to': end_date}
        }

    @staticmethod
    def get_inventory_impact_report(date_from=None, date_to=None, location=None) -> Dict:
        """Отчет за влиянието върху наличности"""

        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            lines_qs = lines_qs.for_location(location)

        if date_from or date_to:
            lines_qs = lines_qs.in_date_range(date_from, date_to)

        # Общ анализ
        inventory_stats = lines_qs.aggregate(
            total_quantity_received=Sum('received_quantity'),
            total_value_received=Sum('line_total'),
            unique_products=Count('product', distinct=True),
            total_lines=Count('id')
        )

        # По продукти
        product_impact = lines_qs.values(
            'product__code',
            'product__name'
        ).annotate(
            quantity_added=Sum('received_quantity'),
            value_added=Sum('line_total'),
            purchase_count=Count('id'),
            avg_cost=Avg('unit_price_base'),
            latest_purchase=models.Max('document__delivery_date')
        ).order_by('-value_added')[:20]

        # По локации (ако не е филтрирано)
        location_impact = []
        if not location:
            location_impact = lines_qs.values(
                'document__location__code',
                'document__location__name'
            ).annotate(
                quantity_added=Sum('received_quantity'),
                value_added=Sum('line_total'),
                lines_count=Count('id')
            ).order_by('-value_added')

        return {
            'summary': inventory_stats,
            'by_product': list(product_impact),
            'by_location': list(location_impact),
            'period': {'from': date_from, 'to': date_to}
        }

    @staticmethod
    def get_quality_analysis(date_from=None, date_to=None, location=None) -> Dict:
        """Анализ на качеството"""

        lines_qs = PurchaseDocumentLine.objects.received_only()

        if location:
            lines_qs = lines_qs.for_location(location)

        if date_from or date_to:
            lines_qs = lines_qs.in_date_range(date_from, date_to)

        # Общ анализ
        total_lines = lines_qs.count()
        quality_stats = {
            'total_lines': total_lines,
            'approved_lines': lines_qs.quality_approved().count(),
            'rejected_lines': lines_qs.quality_issues().count(),
            'approval_rate': 0
        }

        if total_lines > 0:
            quality_stats['approval_rate'] = (quality_stats['approved_lines'] / total_lines) * 100

        # По доставчици
        supplier_quality = lines_qs.values(
            'document__supplier__name'
        ).annotate(
            total_lines=Count('id'),
            approved_lines=Count('id', filter=Q(quality_approved=True)),
            rejected_lines=Count('id', filter=Q(quality_approved=False)),
            total_value=Sum('line_total'),
            rejected_value=Sum('line_total', filter=Q(quality_approved=False))
        ).annotate(
            approval_rate=Case(
                When(total_lines=0, then=0),
                default=F('approved_lines') * 100.0 / F('total_lines'),
                output_field=models.DecimalField(max_digits=5, decimal_places=2)
            )
        ).order_by('approval_rate')

        # Проблемни продукти
        problem_products = lines_qs.quality_issues().values(
            'product__code',
            'product__name'
        ).annotate(
            issues_count=Count('id'),
            total_value=Sum('line_total')
        ).order_by('-issues_count')[:10]

        return {
            'summary': quality_stats,
            'by_supplier': list(supplier_quality),
            'problem_products': list(problem_products),
            'period': {'from': date_from, 'to': date_to}
        }

    @staticmethod
    def get_pricing_opportunities_report(location=None) -> Dict:
        """Отчет за възможности за ценообразуване"""

        lines_qs = PurchaseDocumentLine.objects.with_pricing_suggestions()

        if location:
            lines_qs = lines_qs.for_location(location)

        opportunities = lines_qs.pricing_opportunities()

        # Сумарен анализ
        total_opportunities = opportunities.count()
        potential_revenue = opportunities.aggregate(
            total_increase=Sum('price_increase')
        )['total_increase'] or 0

        # Топ възможности
        top_opportunities = opportunities.order_by('-price_increase')[:20]

        # По категории markup
        markup_analysis = {
            'high_markup': lines_qs.high_markup(threshold=50).count(),
            'medium_markup': lines_qs.filter(
                markup_percentage__gte=20,
                markup_percentage__lt=50
            ).count(),
            'low_markup': lines_qs.low_markup(threshold=20).count()
        }

        return {
            'total_opportunities': total_opportunities,
            'potential_revenue_increase': potential_revenue,
            'top_opportunities': list(top_opportunities),
            'markup_distribution': markup_analysis
        }

    @staticmethod
    def get_top_suppliers(location=None, date_from=None, date_to=None, limit=10) -> List[Dict]:
        """Топ доставчици по стойност"""

        docs_qs = PurchaseDocument.objects.received()

        if location:
            docs_qs = docs_qs.for_location(location)

        if date_from or date_to:
            docs_qs = docs_qs.in_date_range(date_from, date_to)

        return list(docs_qs.values(
            'supplier__name',
            'supplier__code'
        ).annotate(
            total_value=Sum('grand_total'),
            documents_count=Count('id'),
            avg_document_value=Avg('grand_total'),
            last_delivery=models.Max('delivery_date')
        ).order_by('-total_value')[:limit])

    @staticmethod
    def export_period_report(date_from: date, date_to: date, location=None) -> Dict:
        """Цялостен отчет за период за експорт"""

        report_data = {
            'period': {'from': date_from, 'to': date_to},
            'location': location.name if location else 'All Locations',
            'generated_at': timezone.now(),
            'dashboard': ReportingService.get_dashboard_data(location, (date_to - date_from).days),
            'suppliers': ReportingService.get_supplier_analysis(date_from, date_to, location),
            'products': ReportingService.get_product_cost_analysis(date_from, date_to, location),
            'quality': ReportingService.get_quality_analysis(date_from, date_to, location),
            'inventory_impact': ReportingService.get_inventory_impact_report(date_from, date_to, location),
            'payments': ReportingService.get_payment_schedule(location, 30)
        }

        return report_data