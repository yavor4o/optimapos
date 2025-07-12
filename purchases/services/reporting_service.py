# purchases/services/reporting_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import models
from django.utils import timezone
from datetime import timedelta, date
from calendar import monthrange

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class ReportingService:
    """Сервис за отчети и анализи"""

    @staticmethod
    def monthly_summary(year: int, month: int) -> Dict:
        """Месечно резюме на покупки"""

        # Първи и последен ден от месеца
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])

        docs = PurchaseDocument.objects.filter(
            delivery_date__range=[start_date, end_date]
        )

        # Основни статистики
        basic_stats = docs.aggregate(
            total_documents=models.Count('id'),
            total_amount=models.Sum('grand_total'),
            avg_amount=models.Avg('grand_total'),
            paid_amount=models.Sum('grand_total', filter=models.Q(is_paid=True)),
            unpaid_amount=models.Sum('grand_total', filter=models.Q(is_paid=False)),
        )

        # По статуси
        by_status = docs.values('status').annotate(
            count=models.Count('id'),
            total=models.Sum('grand_total')
        ).order_by('status')

        # По доставчици (топ 10)
        by_supplier = docs.values('supplier__name').annotate(
            count=models.Count('id'),
            total=models.Sum('grand_total'),
            avg=models.Avg('grand_total')
        ).order_by('-total')[:10]

        # По локации
        by_location = docs.values('location__name').annotate(
            count=models.Count('id'),
            total=models.Sum('grand_total')
        ).order_by('-total')

        # Топ продукти
        lines = PurchaseDocumentLine.objects.filter(document__in=docs)
        top_products = lines.values(
            'product__code',
            'product__name'
        ).annotate(
            total_qty=models.Sum('received_quantity'),
            total_amount=models.Sum('line_total'),
            avg_price=models.Avg('unit_price'),
            documents_count=models.Count('document', distinct=True)
        ).order_by('-total_amount')[:10]

        # Качествени проблеми
        quality_stats = {
            'total_lines': lines.count(),
            'quality_issues': lines.filter(quality_approved=False).count(),
            'lines_with_variance': lines.with_variance().count(),
            'over_received': lines.over_received().count(),
            'under_received': lines.under_received().count(),
        }

        return {
            'period': f"{year}-{month:02d}",
            'date_range': {'start': start_date, 'end': end_date},
            'basic_stats': basic_stats,
            'by_status': list(by_status),
            'by_supplier': list(by_supplier),
            'by_location': list(by_location),
            'top_products': list(top_products),
            'quality_stats': quality_stats,
        }

    @staticmethod
    def supplier_comparison(date_from: date, date_to: date, supplier_ids: List[int] = None) -> Dict:
        """Сравнителен анализ на доставчици"""

        docs = PurchaseDocument.objects.filter(
            delivery_date__range=[date_from, date_to]
        )

        if supplier_ids:
            docs = docs.filter(supplier_id__in=supplier_ids)

        # Основни метрики по доставчици
        supplier_stats = docs.values(
            'supplier_id',
            'supplier__name'
        ).annotate(
            total_documents=models.Count('id'),
            total_amount=models.Sum('grand_total'),
            avg_amount=models.Avg('grand_total'),
            paid_documents=models.Count('id', filter=models.Q(is_paid=True)),
            unpaid_amount=models.Sum('grand_total', filter=models.Q(is_paid=False)),

            # Качествени метрики
            quality_issues=models.Count('lines', filter=models.Q(lines__quality_approved=False)),
            variance_lines=models.Count('lines',
                                        filter=~models.Q(lines__received_quantity=models.F('lines__quantity'))),

            # Времеви метрики
            min_delivery_date=models.Min('delivery_date'),
            max_delivery_date=models.Max('delivery_date'),
        ).order_by('-total_amount')

        # Изчисляваме допълнителни метрики
        enhanced_stats = []
        for stat in supplier_stats:
            total_docs = stat['total_documents']

            # Payment rate
            payment_rate = (stat['paid_documents'] / total_docs * 100) if total_docs > 0 else 0

            # Quality rate (за supplier-а)
            supplier_lines = PurchaseDocumentLine.objects.filter(
                document__supplier_id=stat['supplier_id'],
                document__delivery_date__range=[date_from, date_to]
            )
            total_lines = supplier_lines.count()
            quality_issues = supplier_lines.filter(quality_approved=False).count()
            quality_rate = ((total_lines - quality_issues) / total_lines * 100) if total_lines > 0 else 100

            enhanced_stats.append({
                **stat,
                'payment_rate': round(payment_rate, 1),
                'quality_rate': round(quality_rate, 1),
                'avg_days_between_deliveries': ReportingService._calculate_avg_delivery_interval(
                    stat['supplier_id'], date_from, date_to
                )
            })

        return {
            'date_range': {'start': date_from, 'end': date_to},
            'suppliers_count': len(enhanced_stats),
            'supplier_stats': enhanced_stats,
            'summary': {
                'total_amount': sum(s['total_amount'] or 0 for s in enhanced_stats),
                'total_documents': sum(s['total_documents'] for s in enhanced_stats),
                'avg_quality_rate': sum(s['quality_rate'] for s in enhanced_stats) / len(
                    enhanced_stats) if enhanced_stats else 0
            }
        }

    @staticmethod
    def location_performance(date_from: date, date_to: date) -> Dict:
        """Анализ на представянето по локации"""

        docs = PurchaseDocument.objects.filter(
            delivery_date__range=[date_from, date_to]
        )

        location_stats = docs.values(
            'location_id',
            'location__name'
        ).annotate(
            total_documents=models.Count('id'),
            total_amount=models.Sum('grand_total'),
            avg_amount=models.Avg('grand_total'),
            unique_suppliers=models.Count('supplier', distinct=True),
            unique_products=models.Count('lines__product', distinct=True),
            total_lines=models.Count('lines'),

            # Status breakdown
            draft_count=models.Count('id', filter=models.Q(status='draft')),
            confirmed_count=models.Count('id', filter=models.Q(status='confirmed')),
            received_count=models.Count('id', filter=models.Q(status='received')),

        ).order_by('-total_amount')

        return {
            'date_range': {'start': date_from, 'end': date_to},
            'location_stats': list(location_stats),
            'summary': {
                'total_locations': location_stats.count(),
                'total_amount': sum(s['total_amount'] or 0 for s in location_stats),
                'avg_suppliers_per_location': sum(s['unique_suppliers'] for s in
                                                  location_stats) / location_stats.count() if location_stats.count() > 0 else 0
            }
        }

    @staticmethod
    def product_analysis(date_from: date, date_to: date, limit: int = 50) -> Dict:
        """Анализ на продукти в покупки"""

        lines = PurchaseDocumentLine.objects.filter(
            document__delivery_date__range=[date_from, date_to]
        )

        # Топ продукти по стойност
        top_by_value = lines.values(
            'product_id',
            'product__code',
            'product__name',
            'product__brand__name'
        ).annotate(
            total_quantity=models.Sum('received_quantity'),
            total_amount=models.Sum('line_total'),
            avg_price=models.Avg('unit_price'),
            min_price=models.Min('unit_price'),
            max_price=models.Max('unit_price'),
            documents_count=models.Count('document', distinct=True),
            suppliers_count=models.Count('document__supplier', distinct=True),
            last_purchase=models.Max('document__delivery_date'),
        ).order_by('-total_amount')[:limit]

        # Топ продукти по количество
        top_by_quantity = lines.values(
            'product__code',
            'product__name'
        ).annotate(
            total_quantity=models.Sum('received_quantity'),
            total_amount=models.Sum('line_total')
        ).order_by('-total_quantity')[:20]

        # Продукти с най-големи ценови варианси
        price_variance = lines.values(
            'product__code',
            'product__name'
        ).annotate(
            min_price=models.Min('unit_price'),
            max_price=models.Max('unit_price'),
            avg_price=models.Avg('unit_price'),
            std_dev=models.StdDev('unit_price'),
            purchases_count=models.Count('id')
        ).filter(
            purchases_count__gte=3  # Минимум 3 покупки за анализ
        ).order_by('-std_dev')[:20]

        # Продукти с качествени проблеми
        quality_issues = lines.filter(
            quality_approved=False
        ).values(
            'product__code',
            'product__name'
        ).annotate(
            issues_count=models.Count('id'),
            total_purchases=models.Count('id'),
            issue_rate=models.Count('id') * 100.0 / models.Count('id')
        ).order_by('-issues_count')[:20]

        return {
            'date_range': {'start': date_from, 'end': date_to},
            'top_by_value': list(top_by_value),
            'top_by_quantity': list(top_by_quantity),
            'price_variance': list(price_variance),
            'quality_issues': list(quality_issues),
            'summary': {
                'unique_products': lines.values('product').distinct().count(),
                'total_lines': lines.count(),
                'avg_line_value': lines.aggregate(avg=models.Avg('line_total'))['avg'] or 0
            }
        }

    @staticmethod
    def payment_analysis(date_from: date, date_to: date) -> Dict:
        """Анализ на плащания"""

        docs = PurchaseDocument.objects.filter(
            delivery_date__range=[date_from, date_to]
        )

        # Основни статистики за плащания
        payment_stats = docs.aggregate(
            total_amount=models.Sum('grand_total'),
            paid_amount=models.Sum('grand_total', filter=models.Q(is_paid=True)),
            unpaid_amount=models.Sum('grand_total', filter=models.Q(is_paid=False)),
            total_documents=models.Count('id'),
            paid_documents=models.Count('id', filter=models.Q(is_paid=True)),
            unpaid_documents=models.Count('id', filter=models.Q(is_paid=False)),
        )

        # Просрочени плащания
        overdue_analysis = []
        for days in [0, 7, 14, 30, 60, 90]:
            overdue_docs = docs.overdue_payment(days)
            overdue_analysis.append({
                'days_overdue': days,
                'count': overdue_docs.count(),
                'amount': overdue_docs.aggregate(total=models.Sum('grand_total'))['total'] or 0
            })

        # По доставчици
        supplier_payment_stats = docs.values(
            'supplier__name'
        ).annotate(
            total_amount=models.Sum('grand_total'),
            paid_amount=models.Sum('grand_total', filter=models.Q(is_paid=True)),
            unpaid_amount=models.Sum('grand_total', filter=models.Q(is_paid=False)),
            avg_payment_days=models.Avg('supplier__payment_days'),
        ).order_by('-unpaid_amount')

        return {
            'date_range': {'start': date_from, 'end': date_to},
            'payment_stats': payment_stats,
            'overdue_analysis': overdue_analysis,
            'supplier_payment_stats': list(supplier_payment_stats),
            'payment_rate': round((payment_stats['paid_amount'] or 0) / (payment_stats['total_amount'] or 1) * 100, 1)
        }

    @staticmethod
    def trend_analysis(months_back: int = 12) -> Dict:
        """Trend анализ за последните месеци"""

        today = timezone.now().date()
        trends = []

        for i in range(months_back):
            # Изчисляваме месеца
            target_date = today.replace(day=1) - timedelta(days=i * 30)
            year = target_date.year
            month = target_date.month

            monthly_data = ReportingService.monthly_summary(year, month)

            trends.append({
                'year': year,
                'month': month,
                'period': f"{year}-{month:02d}",
                'total_amount': monthly_data['basic_stats']['total_amount'] or 0,
                'total_documents': monthly_data['basic_stats']['total_documents'],
                'avg_amount': monthly_data['basic_stats']['avg_amount'] or 0,
                'payment_rate': round(
                    (monthly_data['basic_stats']['paid_amount'] or 0) /
                    (monthly_data['basic_stats']['total_amount'] or 1) * 100, 1
                )
            })

        # Обръщаме реда за да е хронологичен
        trends.reverse()

        return {
            'trends': trends,
            'summary': {
                'months_analyzed': len(trends),
                'total_growth': ReportingService._calculate_growth_rate(trends, 'total_amount'),
                'document_growth': ReportingService._calculate_growth_rate(trends, 'total_documents'),
                'avg_payment_rate': sum(t['payment_rate'] for t in trends) / len(trends) if trends else 0
            }
        }

    @staticmethod
    def _calculate_avg_delivery_interval(supplier_id: int, date_from: date, date_to: date) -> Optional[float]:
        """Изчислява средния интервал между доставки за доставчик"""

        delivery_dates = list(
            PurchaseDocument.objects.filter(
                supplier_id=supplier_id,
                delivery_date__range=[date_from, date_to]
            ).order_by('delivery_date').values_list('delivery_date', flat=True)
        )

        if len(delivery_dates) < 2:
            return None

        intervals = []
        for i in range(1, len(delivery_dates)):
            delta = (delivery_dates[i] - delivery_dates[i - 1]).days
            intervals.append(delta)

        return sum(intervals) / len(intervals) if intervals else None

    @staticmethod
    def _calculate_growth_rate(trends: List[Dict], field: str) -> float:
        """Изчислява growth rate между първия и последния период"""

        if len(trends) < 2:
            return 0

        first_value = trends[0][field] or 0
        last_value = trends[-1][field] or 0

        if first_value == 0:
            return 0

        return round(((last_value - first_value) / first_value) * 100, 1)