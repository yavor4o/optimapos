# purchases/services/document_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class DocumentService:
    """Сервис за работа с документи и техните workflow-и"""

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
            document_date: Дата на документ (default: днес)
            delivery_date: Дата на доставка (default: днес)
            created_by: User instance
            lines_data: List с данни за редовете
            **kwargs: Допълнителни полета за документа

        Returns:
            PurchaseDocument instance
        """

        # Вземаме document type
        try:
            document_type = DocumentType.objects.get(code=document_type_code, is_active=True)
        except DocumentType.DoesNotExist:
            raise ValidationError(f"Document type '{document_type_code}' not found or inactive")

        # Default dates
        if not document_date:
            document_date = timezone.now().date()
        if not delivery_date:
            delivery_date = document_date

        # Създаваме документа
        document = PurchaseDocument(
            document_date=document_date,
            delivery_date=delivery_date,
            supplier=supplier,
            location=location,
            document_type=document_type,
            created_by=created_by,
            **kwargs
        )

        # Валидираме и записваме
        document.full_clean()
        document.save()

        # Добавяме редове ако има
        if lines_data:
            DocumentService.add_lines_to_document(document, lines_data)

        return document

    @staticmethod
    @transaction.atomic
    def add_lines_to_document(document: PurchaseDocument, lines_data: List[Dict]) -> List[PurchaseDocumentLine]:
        """Добавя редове към документ"""

        if not document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        created_lines = []

        for i, line_data in enumerate(lines_data, 1):
            line = PurchaseDocumentLine(
                document=document,
                line_number=line_data.get('line_number', i),
                product=line_data['product'],
                quantity=line_data['quantity'],
                unit=line_data.get('unit', line_data['product'].base_unit),
                unit_price=line_data['unit_price'],
                discount_percent=line_data.get('discount_percent', 0),
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
            )

            line.full_clean()
            line.save()
            created_lines.append(line)

        # Преизчисляваме общите суми
        document.recalculate_totals()
        document.save()

        return created_lines

    @staticmethod
    def get_document_status_info(document: PurchaseDocument) -> Dict:
        """Връща детайлна информация за статуса на документа"""

        status_info = {
            'current_status': document.status,
            'status_display': document.get_status_display(),
            'can_modify': document.can_be_modified(),
            'can_receive': document.can_be_received(),
            'can_cancel': document.can_be_cancelled(),
            'is_paid': document.is_paid,
            'payment_overdue': document.is_overdue_payment() if hasattr(document, 'is_overdue_payment') else False,
            'days_until_payment': document.get_days_until_payment() if hasattr(document,
                                                                               'get_days_until_payment') else None
        }

        # Workflow възможности
        next_actions = []

        if document.status == document.DRAFT:
            next_actions.extend(['confirm', 'cancel', 'edit'])
        elif document.status == document.CONFIRMED:
            next_actions.extend(['receive', 'cancel'])
        elif document.status == document.RECEIVED:
            if not document.is_paid:
                next_actions.append('mark_paid')

        status_info['available_actions'] = next_actions

        return status_info

    @staticmethod
    def get_document_financial_summary(document: PurchaseDocument) -> Dict:
        """Финансово резюме на документа"""

        lines = document.lines.all()

        summary = {
            'lines_count': lines.count(),
            'total_products': lines.values('product').distinct().count(),
            'subtotal': document.subtotal,
            'discount_amount': document.discount_amount,
            'vat_amount': document.vat_amount,
            'grand_total': document.grand_total,
        }

        # Анализ на редовете
        if lines.exists():
            from django.db import models
            line_analysis = lines.aggregate(
                total_quantity=models.Sum('quantity'),
                avg_unit_price=models.Avg('unit_price'),
                max_line_total=models.Max('line_total'),
                lines_with_discount=models.Count('id', filter=models.Q(discount_percent__gt=0))
            )
            summary.update(line_analysis)

        return summary

    @staticmethod
    @transaction.atomic
    def duplicate_document(document: PurchaseDocument, new_date=None, user=None) -> PurchaseDocument:
        """Създава копие на документ"""

        new_doc = DocumentService.create_purchase_document(
            supplier=document.supplier,
            location=document.location,
            document_type_code=document.document_type.code,
            document_date=new_date or timezone.now().date(),
            delivery_date=new_date or timezone.now().date(),
            created_by=user,
            notes=f"Copy of {document.document_number}\n{document.notes}",
            supplier_document_number=document.supplier_document_number,
            external_reference=document.external_reference,
        )

        # Копираме всички редове
        lines_data = []
        for line in document.lines.all():
            lines_data.append({
                'product': line.product,
                'quantity': line.quantity,
                'unit': line.unit,
                'unit_price': line.unit_price,
                'discount_percent': line.discount_percent,
                'batch_number': line.batch_number,
                'expiry_date': line.expiry_date,
            })

        if lines_data:
            DocumentService.add_lines_to_document(new_doc, lines_data)

        return new_doc

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
            if line.expiry_date and line.expiry_date < timezone.now().date():
                errors.append(f"Line {line.line_number}: Expiry date cannot be in the past")

        return errors

    @staticmethod
    @transaction.atomic
    def process_document_workflow(document: PurchaseDocument, action: str, user=None, **kwargs) -> Dict:
        """Обработва workflow действия върху документ"""

        result = {'success': False, 'message': '', 'document': document}

        try:
            if action == 'confirm':
                # Валидираме преди потвърждаване
                validation_errors = DocumentService.validate_document_for_confirmation(document)
                if validation_errors:
                    result['message'] = '; '.join(validation_errors)
                    return result

                document.confirm(user=user)
                result['success'] = True
                result['message'] = 'Document confirmed successfully'

            elif action == 'receive':
                document.receive(user=user)
                result['success'] = True
                result['message'] = 'Document received successfully'

            elif action == 'cancel':
                document.cancel(user=user)
                result['success'] = True
                result['message'] = 'Document cancelled successfully'

            elif action == 'mark_paid':
                payment_date = kwargs.get('payment_date', timezone.now().date())
                document.is_paid = True
                document.payment_date = payment_date
                if user:
                    document.updated_by = user
                document.save()
                result['success'] = True
                result['message'] = 'Document marked as paid'

            else:
                result['message'] = f"Unknown action: {action}"

        except Exception as e:
            result['message'] = str(e)

        return result

    @staticmethod
    def get_documents_requiring_attention() -> Dict:
        """Документи които изискват внимание"""

        today = timezone.now().date()

        return {
            'overdue_deliveries': PurchaseDocument.objects.filter(
                status='confirmed',
                delivery_date__lt=today
            ).count(),

            'overdue_payments': PurchaseDocument.objects.overdue_payment().count(),

            'due_today': PurchaseDocument.objects.filter(
                delivery_date=today,
                status__in=['confirmed', 'received']
            ).count(),

            'quality_issues': PurchaseDocument.objects.with_quality_issues().count(),

            'expiring_products': PurchaseDocument.objects.expiring_soon(days=7).count(),
        }

    @staticmethod
    def generate_document_number(document_type: DocumentType) -> str:
        """Генерира следващия номер за документ"""

        prefix = document_type.code
        year = timezone.now().year

        # Намираме последния номер за тази година и тип
        last_doc = PurchaseDocument.objects.filter(
            document_number__startswith=f"{prefix}{year}",
            document_type=document_type
        ).order_by('-document_number').first()

        if last_doc:
            try:
                # Извличаме номера от последния документ
                last_number = int(last_doc.document_number[-4:])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}{year}{new_number:04d}"