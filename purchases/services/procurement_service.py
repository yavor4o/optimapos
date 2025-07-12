# purchases/services/procurement_service.py

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class ProcurementService:
    """Основна бизнес логика за procurement процеси"""

    @staticmethod
    @transaction.atomic
    def create_purchase_document(
            supplier,
            location,
            document_type_code: str,
            document_date=None,
            delivery_date=None,
            created_by=None,
            lines_data: List[Dict] = None,
            **kwargs
    ) -> PurchaseDocument:
        """
        Създава нов purchase document с редове

        Args:
            supplier: Supplier instance
            location: InventoryLocation instance
            document_type_code: Код на DocumentType (INV, DEL, etc.)
            lines_data: List от dict-ове с данни за редове
                [
                    {
                        'product': product_instance,
                        'quantity': Decimal('10.000'),
                        'unit': unit_instance,
                        'unit_price': Decimal('25.50'),
                        'discount_percent': Decimal('5.00'),
                        'batch_number': 'BATCH001',
                        'expiry_date': date(2025, 12, 31)
                    },
                    ...
                ]

        Returns:
            PurchaseDocument instance
        """

        # Валидации
        if not supplier.is_active:
            raise ValidationError("Supplier is not active")

        if not location.is_active:
            raise ValidationError("Location is not active")

        # Вземаме document type
        try:
            document_type = DocumentType.objects.get(code=document_type_code, is_active=True)
        except DocumentType.DoesNotExist:
            raise ValidationError(f"Document type '{document_type_code}' not found")

        # Default dates
        if not document_date:
            document_date = timezone.now().date()

        if not delivery_date:
            delivery_date = document_date

        # Създаваме документа
        document = PurchaseDocument.objects.create(
            supplier=supplier,
            location=location,
            document_type=document_type,
            document_date=document_date,
            delivery_date=delivery_date,
            created_by=created_by,
            **kwargs
        )

        # Добавяме редове ако има
        if lines_data:
            for i, line_data in enumerate(lines_data, 1):
                ProcurementService.add_line_to_document(
                    document=document,
                    line_number=i,
                    **line_data
                )

        return document

    @staticmethod
    def add_line_to_document(
            document: PurchaseDocument,
            product,
            quantity: Decimal,
            unit,
            unit_price: Decimal,
            line_number: int = None,
            discount_percent: Decimal = Decimal('0.00'),
            batch_number: str = '',
            expiry_date=None,
            **kwargs
    ) -> PurchaseDocumentLine:
        """Добавя ред към purchase document"""

        # Валидации
        if not document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        if not product.is_active:
            raise ValidationError(f"Product {product.code} is not active")

        # Auto line number ако не е подаден
        if line_number is None:
            max_line = document.lines.aggregate(
                max_line=models.Max('line_number')
            )['max_line'] or 0
            line_number = max_line + 1

        # Валидация на unit
        valid_units = [product.base_unit]
        if hasattr(product, 'packagings'):
            valid_units.extend([p.unit for p in product.packagings.all()])

        if unit not in valid_units:
            raise ValidationError(f"Unit {unit.code} is not valid for product {product.code}")

        # Създаваме реда
        line = PurchaseDocumentLine.objects.create(
            document=document,
            line_number=line_number,
            product=product,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            discount_percent=discount_percent,
            batch_number=batch_number,
            expiry_date=expiry_date,
            **kwargs
        )

        return line

    @staticmethod
    @transaction.atomic
    def confirm_document(document: PurchaseDocument, user=None) -> bool:
        """Потвърждава purchase document"""

        if document.status != document.DRAFT:
            raise ValidationError("Can only confirm draft documents")

        # Валидации преди потвърждаване
        validation_errors = ProcurementService.validate_document_for_confirmation(document)
        if validation_errors:
            raise ValidationError(validation_errors)

        # Потвърждаваме документа
        document.confirm(user=user)

        # Логваме действието
        from ..models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=document,
            action=PurchaseAuditLog.CONFIRM,
            user=user,
            notes="Document confirmed"
        )

        return True

    @staticmethod
    @transaction.atomic
    def receive_document(document: PurchaseDocument, user=None) -> bool:
        """Получава purchase document и създава stock movements"""

        if document.status != document.CONFIRMED:
            raise ValidationError("Can only receive confirmed documents")

        # Получаваме документа
        document.receive(user=user)

        # Логваме действието
        from ..models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=document,
            action=PurchaseAuditLog.RECEIVE,
            user=user,
            notes=f"Document received, {document.lines.count()} movements created"
        )

        return True

    @staticmethod
    @transaction.atomic
    def bulk_receive_documents(document_ids: List[int], user=None) -> Dict:
        """Bulk receive на множество документи"""

        documents = PurchaseDocument.objects.filter(
            id__in=document_ids,
            status=PurchaseDocument.CONFIRMED
        )

        success_count = 0
        errors = []

        for doc in documents:
            try:
                ProcurementService.receive_document(doc, user=user)
                success_count += 1
            except Exception as e:
                errors.append(f"{doc.document_number}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(document_ids),
            'errors': errors
        }

    @staticmethod
    def validate_document_for_confirmation(document: PurchaseDocument) -> List[str]:
        """Валидира документ преди потвърждаване"""
        errors = []

        # Проверяваме дали има редове
        if not document.lines.exists():
            errors.append("Document has no lines")

        # Валидираме всеки ред
        for line in document.lines.all():
            # Проверяваме дали продуктът е активен
            if not line.product.is_active:
                errors.append(f"Line {line.line_number}: Product {line.product.code} is not active")

            # Проверяваме batch ако е задължителен
            if document.document_type.requires_batch and not line.batch_number:
                errors.append(f"Line {line.line_number}: Batch number is required")

            # Проверяваме expiry date ако е задължителна
            if document.document_type.requires_expiry and not line.expiry_date:
                errors.append(f"Line {line.line_number}: Expiry date is required")

            # Проверяваме дали expiry date не е в миналото
            if line.expiry_date and line.expiry_date <= timezone.now().date():
                errors.append(f"Line {line.line_number}: Expiry date cannot be in the past")

        return errors

    @staticmethod
    def duplicate_document(
            original_document: PurchaseDocument,
            new_date=None,
            user=None,
            copy_lines=True
    ) -> PurchaseDocument:
        """Дуплицира purchase document"""

        new_doc = original_document.duplicate(
            new_date=new_date,
            user=user
        )

        # Логваме действието
        from ..models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=new_doc,
            action=PurchaseAuditLog.CREATE,
            user=user,
            notes=f"Duplicated from {original_document.document_number}"
        )

        return new_doc

    @staticmethod
    def get_supplier_performance(supplier, date_from=None, date_to=None) -> Dict:
        """Анализира производителността на доставчик"""

        queryset = PurchaseDocument.objects.for_supplier(supplier)

        if date_from or date_to:
            queryset = queryset.in_date_range(date_from, date_to)

        # Основна статистика
        stats = queryset.with_totals().summary_stats()

        # Delivery performance
        received_docs = queryset.received()
        on_time_count = 0
        late_count = 0

        for doc in received_docs:
            delivery_diff = (doc.delivery_date - doc.document_date).days
            if delivery_diff <= 1:  # Same day or next day
                on_time_count += 1
            else:
                late_count += 1

        # Quality statistics
        total_lines = PurchaseDocumentLine.objects.for_supplier(supplier).count()
        quality_issues = PurchaseDocumentLine.objects.for_supplier(supplier).quality_issues().count()

        return {
            'supplier': supplier.name,
            'period': {
                'from': date_from,
                'to': date_to
            },
            'totals': stats,
            'delivery_performance': {
                'on_time': on_time_count,
                'late': late_count,
                'on_time_percentage': (on_time_count / (on_time_count + late_count) * 100) if (
                                                                                                          on_time_count + late_count) > 0 else 0
            },
            'quality': {
                'total_lines': total_lines,
                'quality_issues': quality_issues,
                'quality_rate': ((total_lines - quality_issues) / total_lines * 100) if total_lines > 0 else 0
            }
        }

    @staticmethod
    def get_pending_deliveries(location=None, days_ahead=7) -> List[Dict]:
        """Връща предстоящи доставки"""

        today = timezone.now().date()
        end_date = today + timedelta(days=days_ahead)

        queryset = PurchaseDocument.objects.confirmed().filter(
            delivery_date__range=[today, end_date]
        ).order_by('delivery_date')

        if location:
            queryset = queryset.for_location(location)

        deliveries = []
        for doc in queryset.select_related('supplier', 'location'):
            deliveries.append({
                'document_number': doc.document_number,
                'supplier': doc.supplier.name,
                'location': doc.location.name,
                'delivery_date': doc.delivery_date,
                'grand_total': doc.grand_total,
                'lines_count': doc.lines.count(),
                'days_until_delivery': (doc.delivery_date - today).days,
                'is_urgent': doc.delivery_date == today
            })

        return deliveries

    @staticmethod
    def get_cost_analysis(product=None, location=None, date_from=None, date_to=None) -> Dict:
        """Анализ на себестойностите"""

        queryset = PurchaseDocumentLine.objects.received_only()

        if product:
            queryset = queryset.for_product(product)

        if location:
            queryset = queryset.for_location(location)

        if date_from or date_to:
            queryset = queryset.in_date_range(date_from, date_to)

        # Основна статистика
        total_lines = queryset.count()

        if total_lines == 0:
            return {
                'message': 'No data available for the specified criteria',
                'total_lines': 0
            }

        # Агрегирани данни
        cost_stats = queryset.aggregate(
            avg_cost=models.Avg('unit_price_base'),
            min_cost=models.Min('unit_price_base'),
            max_cost=models.Max('unit_price_base'),
            total_quantity=models.Sum('received_quantity'),
            total_value=models.Sum('line_total'),
            avg_discount=models.Avg('discount_percent')
        )

        # Trend анализ - последните 10 покупки
        recent_purchases = queryset.order_by('-document__delivery_date')[:10]
        trend_data = []

        for line in recent_purchases:
            trend_data.append({
                'date': line.document.delivery_date,
                'cost': line.unit_price_base,
                'quantity': line.received_quantity,
                'supplier': line.document.supplier.name,
                'discount': line.discount_percent
            })

        # Cost variance
        cost_variance = cost_stats['max_cost'] - cost_stats['min_cost'] if cost_stats['max_cost'] and cost_stats[
            'min_cost'] else 0

        return {
            'total_lines': total_lines,
            'cost_statistics': cost_stats,
            'trend_data': trend_data,
            'cost_variance': cost_variance,
            'variance_percentage': (cost_variance / cost_stats['avg_cost'] * 100) if cost_stats['avg_cost'] > 0 else 0
        }

    @staticmethod
    def apply_bulk_price_suggestions(line_ids: List[int], user=None) -> Dict:
        """Прилага price suggestions за множество редове"""

        lines = PurchaseDocumentLine.objects.filter(
            id__in=line_ids,
            new_sale_price__isnull=False
        )

        success_count = 0
        errors = []

        for line in lines:
            try:
                line.apply_suggested_price()
                success_count += 1

                # Логваме промяната
                from ..models import PurchaseAuditLog
                PurchaseAuditLog.log_action(
                    document=line.document,
                    action=PurchaseAuditLog.PRICE_UPDATE,
                    user=user,
                    field_name=f"line_{line.line_number}_price",
                    old_value=str(line.old_sale_price),
                    new_value=str(line.new_sale_price),
                    notes=f"Applied suggested price for {line.product.code}"
                )

            except Exception as e:
                errors.append(f"Line {line.line_number}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(line_ids),
            'errors': errors
        }