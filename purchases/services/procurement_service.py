# purchases/services/procurement_service.py

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta, date

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class ProcurementService:
    """Специализиран сервис за procurement процеси и workflow-и"""

    @staticmethod
    @transaction.atomic
    def create_procurement_request(
            supplier,
            location,
            requested_by,
            items_data: List[Dict],
            delivery_date=None,
            notes: str = '',
            priority: str = 'NORMAL'
    ) -> PurchaseDocument:
        """
        Създава procurement request (draft документ)

        Args:
            supplier: Supplier instance
            location: InventoryLocation instance
            requested_by: User instance
            items_data: List[{'product': Product, 'quantity': Decimal, 'estimated_price': Decimal}]
            delivery_date: Желана дата на доставка
            notes: Бележки
            priority: URGENT, HIGH, NORMAL, LOW
        """

        # Вземаме default document type за procurement
        doc_type = DocumentType.objects.filter(
            code='REQ',  # Request
            is_active=True
        ).first()

        if not doc_type:
            # Създаваме default REQ type ако няма
            doc_type = DocumentType.objects.create(
                code='REQ',
                name='Procurement Request',
                type_key='stock_in',
                stock_effect=1,
                is_active=True
            )

        # Default delivery date
        if not delivery_date:
            delivery_date = timezone.now().date() + timedelta(days=7)

        # Създаваме документа
        document = PurchaseDocument.objects.create(
            document_date=timezone.now().date(),
            delivery_date=delivery_date,
            supplier=supplier,
            location=location,
            document_type=doc_type,
            status='draft',
            notes=f"Priority: {priority}\n{notes}",
            created_by=requested_by
        )

        # Добавяме редовете
        for i, item_data in enumerate(items_data, 1):
            PurchaseDocumentLine.objects.create(
                document=document,
                line_number=i,
                product=item_data['product'],
                quantity=item_data['quantity'],
                unit=item_data.get('unit', item_data['product'].base_unit),
                unit_price=item_data.get('estimated_price', Decimal('0')),
                batch_number=item_data.get('batch_number', ''),
                expiry_date=item_data.get('expiry_date')
            )

        # Преизчисляваме суми
        document.recalculate_totals()
        document.save()

        return document

    @staticmethod
    def convert_request_to_order(request_document: PurchaseDocument, user=None) -> PurchaseDocument:
        """Конвертира procurement request в purchase order"""

        if request_document.status != 'draft':
            raise ValidationError("Can only convert draft requests to orders")

        # Вземаме ORDER document type
        order_type = DocumentType.objects.filter(
            code='ORD',
            is_active=True
        ).first()

        if not order_type:
            order_type = DocumentType.objects.create(
                code='ORD',
                name='Purchase Order',
                type_key='stock_in',
                stock_effect=1,
                auto_confirm=True,
                is_active=True
            )

        # Създаваме новия order документ
        order_document = PurchaseDocument.objects.create(
            document_date=timezone.now().date(),
            delivery_date=request_document.delivery_date,
            supplier=request_document.supplier,
            location=request_document.location,
            document_type=order_type,
            status='confirmed',  # Orders са автоматично confirmed
            notes=f"Converted from request {request_document.document_number}\n{request_document.notes}",
            created_by=user or request_document.created_by
        )

        # Копираме редовете
        for line in request_document.lines.all():
            PurchaseDocumentLine.objects.create(
                document=order_document,
                line_number=line.line_number,
                product=line.product,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                batch_number=line.batch_number,
                expiry_date=line.expiry_date
            )

        # Преизчисляваме суми
        order_document.recalculate_totals()
        order_document.save()

        # Маркираме оригиналния request като closed
        request_document.status = 'closed'
        request_document.save()

        return order_document

    @staticmethod
    @transaction.atomic
    def process_delivery_receipt(
            order_document: PurchaseDocument,
            received_items: List[Dict],
            received_by,
            delivery_note_number: str = '',
            quality_checked: bool = True
    ) -> PurchaseDocument:
        """
        Обработва получаване на доставка

        Args:
            order_document: Purchase order document
            received_items: List[{'line_id': int, 'received_qty': Decimal, 'quality_ok': bool, 'notes': str}]
            received_by: User instance
            delivery_note_number: Номер на доставната бележка
            quality_checked: Дали е направена качествена проверка
        """

        if order_document.status != 'confirmed':
            raise ValidationError("Can only receive confirmed orders")

        # Обновяваме получените количества
        total_variance = Decimal('0')
        quality_issues = 0

        for item in received_items:
            try:
                line = order_document.lines.get(id=item['line_id'])
                line.received_quantity = item['received_qty']
                line.quality_approved = item.get('quality_ok', True)

                if item.get('notes'):
                    line.quality_notes = item['notes']

                if not line.quality_approved:
                    quality_issues += 1

                # Изчисляваме variance
                variance = abs(line.received_quantity - line.quantity)
                total_variance += variance

                line.save()

            except PurchaseDocumentLine.DoesNotExist:
                raise ValidationError(f"Line with ID {item['line_id']} not found")

        # Обновяваме документа
        order_document.status = 'received'
        order_document.supplier_document_number = delivery_note_number

        # Добавяме информация за получаването в notes
        receipt_info = [
            f"Received by: {received_by.get_full_name() or received_by.username}",
            f"Delivery note: {delivery_note_number}",
            f"Quality checked: {'Yes' if quality_checked else 'No'}",
            f"Quality issues: {quality_issues}",
            f"Total variance: {total_variance}"
        ]

        order_document.notes = f"{order_document.notes}\n\nRECEIPT INFO:\n" + "\n".join(receipt_info)
        order_document.updated_by = received_by
        order_document.save()

        # Създаваме stock movements ако е нужно
        if hasattr(order_document, 'create_stock_movements'):
            order_document.create_stock_movements()

        return order_document

    @staticmethod
    def calculate_procurement_metrics(location, days_back: int = 30) -> Dict:
        """Изчислява procurement метрики за локация"""

        cutoff_date = timezone.now().date() - timedelta(days=days_back)

        # Всички документи за периода
        all_docs = PurchaseDocument.objects.filter(
            location=location,
            document_date__gte=cutoff_date
        )

        # Requests vs Orders
        requests = all_docs.filter(document_type__code='REQ')
        orders = all_docs.filter(document_type__code='ORD')

        # Изпълнение на доставки
        on_time_deliveries = orders.filter(
            status='received',
            delivery_date__lte=models.F('document_date')
        ).count()

        total_received = orders.filter(status='received').count()

        # Качествени проблеми
        quality_issues = PurchaseDocumentLine.objects.filter(
            document__in=orders,
            quality_approved=False
        ).count()

        total_lines = PurchaseDocumentLine.objects.filter(
            document__in=orders
        ).count()

        # Финансови метрики
        financial_stats = orders.aggregate(
            total_ordered=models.Sum('grand_total'),
            total_paid=models.Sum('grand_total', filter=models.Q(is_paid=True)),
            avg_order_value=models.Avg('grand_total')
        )

        return {
            'period_days': days_back,
            'requests_count': requests.count(),
            'orders_count': orders.count(),
            'conversion_rate': (orders.count() / requests.count() * 100) if requests.count() > 0 else 0,
            'on_time_delivery_rate': (on_time_deliveries / total_received * 100) if total_received > 0 else 0,
            'quality_rate': ((total_lines - quality_issues) / total_lines * 100) if total_lines > 0 else 100,
            'financial': financial_stats,
            'avg_processing_time': ProcurementService._calculate_avg_processing_time(location, cutoff_date)
        }

    @staticmethod
    def get_procurement_pipeline(location) -> Dict:
        """Връща текущия procurement pipeline за локация"""

        docs = PurchaseDocument.objects.filter(location=location)

        pipeline = {
            'draft_requests': docs.filter(status='draft', document_type__code='REQ'),
            'pending_orders': docs.filter(status='confirmed', document_type__code='ORD'),
            'in_transit': docs.filter(
                status='confirmed',
                delivery_date__lte=timezone.now().date()
            ),
            'overdue_deliveries': docs.filter(
                status='confirmed',
                delivery_date__lt=timezone.now().date()
            ),
            'pending_payment': docs.filter(
                status='received',
                is_paid=False
            )
        }

        # Изчисляваме стойности
        for key, queryset in pipeline.items():
            pipeline[f'{key}_count'] = queryset.count()
            pipeline[f'{key}_value'] = queryset.aggregate(
                total=models.Sum('grand_total')
            )['total'] or 0

        return pipeline

    @staticmethod
    @transaction.atomic
    def auto_create_reorder_requests(location, min_stock_threshold: Decimal = None) -> List[PurchaseDocument]:
        """Автоматично създава reorder requests за продукти под минимум"""

        # TODO: Интеграция с inventory системата
        # За сега връщаме празен списък
        # В бъдещето тук ще проверяваме inventory levels

        created_requests = []

        # Примерна логика (трябва интеграция с inventory):
        # low_stock_products = InventoryItem.objects.filter(
        #     location=location,
        #     current_qty__lte=models.F('reorder_level')
        # )

        # За всеки продукт под минимум:
        # - Намираме primary supplier
        # - Изчисляваме reorder quantity
        # - Създаваме request документ

        return created_requests

    @staticmethod
    def get_supplier_procurement_summary(supplier, months_back: int = 6) -> Dict:
        """Procurement резюме за конкретен доставчик"""

        cutoff_date = timezone.now().date() - timedelta(days=months_back * 30)

        docs = PurchaseDocument.objects.filter(
            supplier=supplier,
            document_date__gte=cutoff_date
        )

        # Основни статистики
        basic_stats = docs.aggregate(
            total_orders=models.Count('id'),
            total_value=models.Sum('grand_total'),
            avg_order_value=models.Avg('grand_total'),
            received_orders=models.Count('id', filter=models.Q(status='received')),
            paid_value=models.Sum('grand_total', filter=models.Q(is_paid=True))
        )

        # Lead times (от order до received)
        received_docs = docs.filter(status='received').annotate(
            lead_time=models.F('delivery_date') - models.F('document_date')
        )

        if received_docs.exists():
            avg_lead_time = received_docs.aggregate(
                avg_days=models.Avg('lead_time')
            )['avg_days']
            if avg_lead_time:
                avg_lead_time = avg_lead_time.days
        else:
            avg_lead_time = None

        # Качествени метрики
        all_lines = PurchaseDocumentLine.objects.filter(document__in=docs)
        quality_stats = all_lines.aggregate(
            total_lines=models.Count('id'),
            quality_issues=models.Count('id', filter=models.Q(quality_approved=False)),
            variance_lines=models.Count('id', filter=~models.Q(received_quantity=models.F('quantity')))
        )

        # Топ продукти от този доставчик
        top_products = all_lines.values(
            'product__code',
            'product__name'
        ).annotate(
            total_qty=models.Sum('received_quantity'),
            total_value=models.Sum('line_total'),
            orders_count=models.Count('document', distinct=True)
        ).order_by('-total_value')[:10]

        return {
            'period_months': months_back,
            'basic_stats': basic_stats,
            'avg_lead_time_days': avg_lead_time,
            'quality_stats': quality_stats,
            'top_products': list(top_products),
            'fulfillment_rate': (basic_stats['received_orders'] / basic_stats['total_orders'] * 100) if basic_stats[
                                                                                                            'total_orders'] > 0 else 0,
            'payment_rate': (basic_stats['paid_value'] / basic_stats['total_value'] * 100) if basic_stats[
                'total_value'] else 0
        }

    @staticmethod
    def _calculate_avg_processing_time(location, since_date: date) -> Optional[float]:
        """Изчислява средното време за обработка на поръчки"""

        # От request до order
        requests = PurchaseDocument.objects.filter(
            location=location,
            document_date__gte=since_date,
            document_type__code='REQ',
            status='closed'
        )

        processing_times = []

        for request in requests:
            # Намираме съответния order (по supplier, delivery_date, стойност)
            related_order = PurchaseDocument.objects.filter(
                supplier=request.supplier,
                location=request.location,
                document_type__code='ORD',
                delivery_date=request.delivery_date,
                grand_total=request.grand_total
            ).first()

            if related_order:
                processing_time = (related_order.document_date - request.document_date).days
                processing_times.append(processing_time)

        return sum(processing_times) / len(processing_times) if processing_times else None

    @staticmethod
    def generate_procurement_forecast(location, days_ahead: int = 90) -> Dict:
        """Генерира прогноза за бъдещи procurement нужди"""

        # Анализираме исторически данни
        historical_period = timezone.now().date() - timedelta(days=days_ahead * 2)

        historical_docs = PurchaseDocument.objects.filter(
            location=location,
            document_date__gte=historical_period,
            status='received'
        )

        # Анализ по продукти
        product_analysis = PurchaseDocumentLine.objects.filter(
            document__in=historical_docs
        ).values(
            'product_id',
            'product__code',
            'product__name'
        ).annotate(
            avg_monthly_qty=models.Avg('received_quantity') * 30 / days_ahead,
            total_orders=models.Count('document', distinct=True),
            avg_price=models.Avg('unit_price'),
            last_order_date=models.Max('document__delivery_date')
        ).order_by('-avg_monthly_qty')

        # Прогнозирани нужди
        forecast_items = []
        for item in product_analysis:
            days_since_last_order = (timezone.now().date() - item['last_order_date']).days
            predicted_need_date = timezone.now().date() + timedelta(
                days=max(30 - days_since_last_order, 7)
            )

            forecast_items.append({
                'product_id': item['product_id'],
                'product_code': item['product__code'],
                'product_name': item['product__name'],
                'predicted_quantity': item['avg_monthly_qty'],
                'estimated_value': item['avg_monthly_qty'] * item['avg_price'],
                'predicted_need_date': predicted_need_date,
                'confidence': min(item['total_orders'] / 5 * 100, 100)  # Based on order frequency
            })

        return {
            'forecast_period_days': days_ahead,
            'analysis_period_days': days_ahead * 2,
            'forecast_items': forecast_items[:20],  # Top 20
            'total_predicted_value': sum(item['estimated_value'] for item in forecast_items),
            'high_confidence_items': [item for item in forecast_items if item['confidence'] > 70]
        }