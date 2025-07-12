# purchases/services/purchase_service.py
from django.db import models
from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class PurchaseService:
    """Основен бизнес сервис за purchases"""

    @staticmethod
    def get_dashboard_data() -> Dict:
        """Данни за dashboard"""
        return PurchaseDocument.objects.get_dashboard_summary()

    @staticmethod
    def search_documents(query: str, filters: Dict = None) -> 'QuerySet':
        """Търсене на документи с филтри"""
        queryset = PurchaseDocument.objects.search(query) if query else PurchaseDocument.objects.all()

        if filters:
            if filters.get('supplier'):
                queryset = queryset.for_supplier(filters['supplier'])
            if filters.get('location'):
                queryset = queryset.for_location(filters['location'])
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])
            if filters.get('date_from'):
                queryset = queryset.filter(delivery_date__gte=filters['date_from'])
            if filters.get('date_to'):
                queryset = queryset.filter(delivery_date__lte=filters['date_to'])
            if filters.get('min_amount'):
                queryset = queryset.filter(grand_total__gte=filters['min_amount'])
            if filters.get('max_amount'):
                queryset = queryset.filter(grand_total__lte=filters['max_amount'])

        return queryset.order_by('-delivery_date')

    @staticmethod
    def get_urgent_items() -> Dict:
        """Спешни елементи за внимание"""
        return {
            'today_deliveries': PurchaseDocument.objects.today_deliveries(),
            'overdue_payments': PurchaseDocument.objects.overdue_payment(),
            'due_soon': PurchaseDocument.objects.due_soon(),
            'quality_issues': PurchaseDocument.objects.with_quality_issues(),
            'expiring_products': PurchaseDocument.objects.expiring_soon(),
            'pending_receipt': PurchaseDocument.objects.pending_receipt(),
        }

    @staticmethod
    def get_supplier_performance(supplier) -> Dict:
        """Анализ на представяне на доставчик"""
        docs = PurchaseDocument.objects.for_supplier(supplier)

        # Основни статистики
        total_docs = docs.count()
        total_amount = docs.aggregate(total=models.Sum('grand_total'))['total'] or 0
        unpaid_amount = docs.unpaid().aggregate(total=models.Sum('grand_total'))['total'] or 0
        overdue_count = docs.overdue_payment().count()

        # Качествени проблеми
        quality_issues = docs.with_quality_issues().count()
        quality_rate = ((total_docs - quality_issues) / total_docs * 100) if total_docs > 0 else 100

        # Скорошна активност
        last_30_days = docs.filter(
            delivery_date__gte=timezone.now().date() - timedelta(days=30)
        )

        return {
            'total_documents': total_docs,
            'total_amount': total_amount,
            'unpaid_amount': unpaid_amount,
            'overdue_count': overdue_count,
            'quality_rate': quality_rate,
            'last_delivery': docs.order_by('-delivery_date').first(),
            'last_30_days_count': last_30_days.count(),
            'last_30_days_amount': last_30_days.aggregate(total=models.Sum('grand_total'))['total'] or 0,
        }

    @staticmethod
    @transaction.atomic
    def bulk_confirm_documents(document_ids: List[int], user=None) -> Dict:
        """Bulk потвърждаване на документи"""
        documents = PurchaseDocument.objects.filter(
            id__in=document_ids,
            status='draft'
        )

        success_count = 0
        errors = []

        for doc in documents:
            try:
                doc.confirm(user=user)
                success_count += 1
            except Exception as e:
                errors.append(f"{doc.document_number}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(document_ids),
            'failed_count': len(errors),
            'errors': errors
        }

    @staticmethod
    @transaction.atomic
    def bulk_receive_documents(document_ids: List[int], user=None) -> Dict:
        """Bulk получаване на документи"""
        documents = PurchaseDocument.objects.filter(
            id__in=document_ids,
            status='confirmed'
        )

        success_count = 0
        errors = []

        for doc in documents:
            try:
                doc.receive(user=user)
                success_count += 1
            except Exception as e:
                errors.append(f"{doc.document_number}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(document_ids),
            'failed_count': len(errors),
            'errors': errors
        }

    @staticmethod
    @transaction.atomic
    def bulk_mark_paid(document_ids: List[int], payment_date=None, user=None) -> Dict:
        """Bulk маркиране като платени"""
        documents = PurchaseDocument.objects.filter(
            id__in=document_ids,
            is_paid=False
        )

        if not payment_date:
            payment_date = timezone.now().date()

        success_count = 0
        errors = []

        for doc in documents:
            try:
                doc.is_paid = True
                doc.payment_date = payment_date
                if user:
                    doc.updated_by = user
                doc.save(update_fields=['is_paid', 'payment_date', 'updated_by', 'updated_at'])
                success_count += 1
            except Exception as e:
                errors.append(f"{doc.document_number}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(document_ids),
            'failed_count': len(errors),
            'errors': errors
        }

    @staticmethod
    def analyze_receiving_variances(date_from=None, date_to=None) -> Dict:
        """Анализ на разлики при получаване"""
        lines = PurchaseDocumentLine.objects.with_variance()

        if date_from:
            lines = lines.filter(document__delivery_date__gte=date_from)
        if date_to:
            lines = lines.filter(document__delivery_date__lte=date_to)

        over_received = lines.over_received()
        under_received = lines.under_received()

        return {
            'total_variances': lines.count(),
            'over_received_count': over_received.count(),
            'under_received_count': under_received.count(),
            'over_received_lines': list(over_received.values(
                'document__document_number',
                'document__supplier__name',
                'product__code',
                'product__name',
                'quantity',
                'received_quantity',
                'line_total'
            )[:20]),  # Ограничаваме до 20 за performance
            'under_received_lines': list(under_received.values(
                'document__document_number',
                'document__supplier__name',
                'product__code',
                'product__name',
                'quantity',
                'received_quantity',
                'line_total'
            )[:20])
        }

    @staticmethod
    def get_location_summary(location) -> Dict:
        """Резюме за локация"""
        docs = PurchaseDocument.objects.for_location(location)

        # Последните 30 дни
        last_30_days = docs.filter(
            delivery_date__gte=timezone.now().date() - timedelta(days=30)
        )

        return {
            'total_documents': docs.count(),
            'pending_receipt': docs.pending_receipt().count(),
            'pending_payment': docs.pending_payment().count(),
            'last_30_days': {
                'count': last_30_days.count(),
                'amount': last_30_days.aggregate(total=models.Sum('grand_total'))['total'] or 0,
            },
            'top_suppliers': docs.values('supplier__name').annotate(
                count=models.Count('id'),
                total=models.Sum('grand_total')
            ).order_by('-total')[:5]
        }

    @staticmethod
    def calculate_supplier_reliability(supplier, days=90) -> Dict:
        """Изчислява надеждността на доставчик"""
        cutoff_date = timezone.now().date() - timedelta(days=days)
        docs = PurchaseDocument.objects.for_supplier(supplier).filter(
            delivery_date__gte=cutoff_date
        )

        total_docs = docs.count()
        if total_docs == 0:
            return {'reliability_score': 0, 'details': 'No recent deliveries'}

        # On-time deliveries (delivered on or before promised date)
        on_time = docs.filter(
            delivery_date__lte=models.F('document_date')
        ).count()

        # Quality issues
        quality_issues = docs.with_quality_issues().count()

        # Варианси в количествата
        total_lines = PurchaseDocumentLine.objects.filter(document__in=docs).count()
        variance_lines = PurchaseDocumentLine.objects.filter(
            document__in=docs
        ).with_variance().count()

        # Изчисляваме score (0-100)
        on_time_score = (on_time / total_docs) * 40  # 40% тегло
        quality_score = ((total_docs - quality_issues) / total_docs) * 30  # 30% тегло
        accuracy_score = ((total_lines - variance_lines) / total_lines) * 30 if total_lines > 0 else 30  # 30% тегло

        reliability_score = on_time_score + quality_score + accuracy_score

        return {
            'reliability_score': round(reliability_score, 1),
            'details': {
                'total_deliveries': total_docs,
                'on_time_deliveries': on_time,
                'on_time_rate': round((on_time / total_docs) * 100, 1),
                'quality_issues': quality_issues,
                'quality_rate': round(((total_docs - quality_issues) / total_docs) * 100, 1),
                'variance_lines': variance_lines,
                'accuracy_rate': round(((total_lines - variance_lines) / total_lines) * 100,
                                       1) if total_lines > 0 else 100,
            }
        }