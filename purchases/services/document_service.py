# purchases/services/document_service.py - ENHANCED VERSION

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class DocumentService:
    """Enhanced сервис за работа с документи и техните workflow-и"""

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
        """Създава нов purchase document с редове"""

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
                discount_percent=line_data.get('discount_percent', Decimal('0')),
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
            )
            line.full_clean()
            line.save()
            created_lines.append(line)

        # Recalculate totals
        document.recalculate_totals()
        document.save()
        return created_lines

    # =====================
    # AUTO INVOICE CREATION (НОВО!)
    # =====================

    @staticmethod
    @transaction.atomic
    def create_invoice_from_grn(grn_document: PurchaseDocument) -> Optional[PurchaseDocument]:
        """Създава INV документ автоматично от GRN документ"""

        if grn_document.document_type.code != 'GRN':
            return None

        if not grn_document.supplier_document_number:
            return None

        # Проверяваме дали вече съществува INV с този номер
        existing_invoice = PurchaseDocument.objects.filter(
            document_type__code='INV',
            supplier_document_number=grn_document.supplier_document_number,
            supplier=grn_document.supplier
        ).first()

        if existing_invoice:
            return existing_invoice  # Не създаваме дублиран

        # Копираме данните от GRN-а за INV
        lines_data = []
        for line in grn_document.lines.all():
            lines_data.append({
                'product': line.product,
                'quantity': line.received_quantity or line.quantity,
                'unit': line.unit,
                'unit_price': line.unit_price,
                'discount_percent': line.discount_percent,
            })

        # Създаваме INV документ
        invoice = DocumentService.create_purchase_document(
            supplier=grn_document.supplier,
            location=grn_document.location,
            document_type_code='INV',
            document_date=grn_document.document_date,
            delivery_date=grn_document.delivery_date,
            supplier_document_number=grn_document.supplier_document_number,
            external_reference=f"GRN: {grn_document.document_number}",
            notes=f"Auto-created from {grn_document.document_number}",
            is_paid=grn_document.is_paid,
            created_by=grn_document.created_by,
            lines_data=lines_data
        )

        return invoice

    # =====================
    # STOCK MOVEMENTS (ПРЕМЕСТЕНО ОТ МОДЕЛА!)
    # =====================

    @staticmethod
    @transaction.atomic
    def create_stock_movements(document: PurchaseDocument) -> Dict:
        """Създава stock movements за всички редове - ПРЕМЕСТЕНО ОТ МОДЕЛА"""

        result = {
            'success': True,
            'movements_created': 0,
            'errors': []
        }

        try:
            from inventory.services import MovementService

            for line in document.lines.all():
                try:
                    MovementService.create_incoming_movement(
                        location=document.location,
                        product=line.product,
                        quantity=line.quantity_base_unit,
                        cost_price=line.unit_price_base,
                        source_document_type='PURCHASE',
                        source_document_number=document.document_number,
                        movement_date=document.delivery_date,
                        batch_number=line.batch_number,
                        expiry_date=line.expiry_date,
                        reason=f"Purchase from {document.supplier.name}",
                        created_by=document.created_by
                    )
                    result['movements_created'] += 1

                except Exception as e:
                    result['errors'].append(f"Line {line.line_number}: {str(e)}")

        except Exception as e:
            result['success'] = False
            result['errors'].append(f"Movement service error: {str(e)}")

        return result

    # =====================
    # DUPLICATE FUNCTIONALITY (ПРЕМЕСТЕНО ОТ МОДЕЛА!)
    # =====================

    @staticmethod
    @transaction.atomic
    def duplicate_document(document: PurchaseDocument, new_date=None, user=None) -> PurchaseDocument:
        """Създава копие на документ - ПРЕМЕСТЕНО ОТ МОДЕЛА"""

        # Копираме данните за новия документ
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

        # Създаваме новия документ
        new_doc = DocumentService.create_purchase_document(
            supplier=document.supplier,
            location=document.location,
            document_type_code=document.document_type.code,
            document_date=new_date or timezone.now().date(),
            delivery_date=new_date or timezone.now().date(),
            created_by=user or document.created_by,
            notes=f"Copy of {document.document_number}\n{document.notes}",
            supplier_document_number=document.supplier_document_number,
            external_reference=document.external_reference,
            lines_data=lines_data
        )

        return new_doc

    # =====================
    # WORKFLOW OPERATIONS
    # =====================

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

                # Създаваме stock movements ако е нужно
                if kwargs.get('create_stock_movements', False):
                    movements_result = DocumentService.create_stock_movements(document)
                    if not movements_result['success']:
                        result[
                            'message'] = f"Received but stock movements failed: {'; '.join(movements_result['errors'])}"
                    else:
                        result[
                            'message'] = f"Document received and {movements_result['movements_created']} stock movements created"
                else:
                    result['message'] = 'Document received successfully'

                result['success'] = True

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
    def validate_document_for_confirmation(document: PurchaseDocument) -> List[str]:
        """Валидира документ преди потвърждаване"""
        errors = []

        # Проверяваме дали има редове
        if not document.lines.exists():
            errors.append("Document has no lines")

        # Валидираме всеки ред
        for line in document.lines.all():
            if not line.product.is_active:
                errors.append(f"Line {line.line_number}: Product {line.product.code} is not active")

            # Проверяваме batch ако е задължителен
            if document.document_type.requires_batch and not line.batch_number:
                errors.append(f"Line {line.line_number}: Batch number is required")

            # Проверяваме expiry date ако е задължителна
            if document.document_type.requires_expiry and not line.expiry_date:
                errors.append(f"Line {line.line_number}: Expiry date is required")

        return errors

    # =====================
    # UTILITY METHODS
    # =====================

    @staticmethod
    def recalculate_document_totals(document: PurchaseDocument) -> None:
        """Explicit recalculation на document totals"""
        document.recalculate_totals()
        document.save(update_fields=[
            'subtotal', 'discount_amount', 'vat_amount', 'grand_total', 'updated_at'
        ])

    @staticmethod
    def get_document_summary(document: PurchaseDocument) -> Dict:
        """Връща обобщена информация за документ"""
        lines = document.lines.all()

        summary = {
            'document_number': document.document_number,
            'status': document.status,
            'supplier': document.supplier.name,
            'location': document.location.name,
            'lines_count': lines.count(),
            'subtotal': document.subtotal,
            'discount_amount': document.discount_amount,
            'total_amount': document.total_amount,
            'grand_total': document.grand_total,
            'related_invoice': document.get_related_invoice(),
        }

        return summary