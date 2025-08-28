# nomenclatures/services/document_line_service.py

from decimal import Decimal

from django.db import transaction

from core.utils.result import Result
import logging

logger = logging.getLogger(__name__)


class DocumentLineService:
    """
    Централизиран сервис за управление на document lines

    Работи с всички типове редове: PurchaseRequestLine, PurchaseOrderLine, DeliveryLine
    """

    @staticmethod
    @transaction.atomic
    def add_line(document, product, quantity: Decimal, **kwargs) -> Result:
        """
        Добавя нов ред към документ

        Args:
            document: Document instance (PurchaseRequest, PurchaseOrder, etc.)
            product: Product instance
            quantity: Decimal количество
            **kwargs: Допълнителни полета специфични за типа ред

        Returns:
            Result with created line
        """
        try:
            # Валидация на входните данни
            if not document or not product:
                return Result.error('INVALID_INPUT', 'Document and product are required')

            if not quantity or quantity <= 0:
                return Result.error('INVALID_QUANTITY', 'Quantity must be greater than zero')

            # Намери line model class
            line_class = DocumentLineService._get_line_class(document)
            if not line_class:
                return Result.error('UNSUPPORTED_DOCUMENT',
                                    f'No line class found for {document.__class__.__name__}')

            # Генерирай следващия line_number
            next_line_number = DocumentLineService._get_next_line_number(document)

            # Подготви данните за създаване
            line_data = {
                'document': document,
                'product': product,
                'line_number': next_line_number,
                **kwargs
            }

            # Добави количеството според типа ред
            quantity_field = DocumentLineService._get_quantity_field(line_class)
            line_data[quantity_field] = quantity

            # Създай реда
            line = line_class.objects.create(**line_data)

            # Trigger recalculations ако е нужно
            DocumentLineService._post_line_creation(document, line)

            return Result.success(
                data={'line': line, 'line_number': next_line_number},
                msg=f'Line {next_line_number} added successfully'
            )

        except Exception as e:
            return Result.error('LINE_CREATION_FAILED', f'Failed to add line: {str(e)}')

    @staticmethod
    @transaction.atomic
    def remove_line(document, line_number: int) -> Result:
        """Премахва ред от документ"""
        try:
            line_class = DocumentLineService._get_line_class(document)
            if not line_class:
                return Result.error('UNSUPPORTED_DOCUMENT',
                                    f'No line class found for {document.__class__.__name__}')

            line = line_class.objects.filter(
                document=document,
                line_number=line_number
            ).first()

            if not line:
                return Result.error('LINE_NOT_FOUND',
                                    f'Line {line_number} not found in document {document.document_number}')

            # Check permissions
            if not DocumentLineService._can_modify_line(document, line):
                return Result.error('LINE_MODIFICATION_DENIED',
                                    'Cannot modify lines in current document status')

            line.delete()

            # Reorder remaining lines
            DocumentLineService._reorder_lines(document)

            # Trigger recalculations
            DocumentLineService._post_line_modification(document)

            return Result.success(msg=f'Line {line_number} removed successfully')

        except Exception as e:
            return Result.error('LINE_REMOVAL_FAILED', f'Failed to remove line: {str(e)}')

    @staticmethod
    def validate_lines(document) -> Result:
        """Валидира всички редове на документ"""
        try:
            line_class = DocumentLineService._get_line_class(document)
            if not line_class:
                return Result.success(msg='Document has no lines to validate')

            lines = line_class.objects.filter(document=document)
            errors = []

            if not lines.exists():
                errors.append('Document has no lines')

            for line in lines:
                # Валидация на количество
                quantity_field = DocumentLineService._get_quantity_field(line_class)
                quantity = getattr(line, quantity_field, None)

                if not quantity or quantity <= 0:
                    errors.append(f'Line {line.line_number}: Invalid quantity {quantity}')

                # Валидация на продукт
                if not line.product:
                    errors.append(f'Line {line.line_number}: Product is required')
                elif hasattr(line.product, 'lifecycle_status'):
                    if line.product.lifecycle_status != 'ACTIVE':
                        errors.append(f'Line {line.line_number}: Product is not active')
                elif hasattr(line.product, 'is_active'):
                    if not line.product.is_active:
                        errors.append(f'Line {line.line_number}: Product is not active')

            if errors:
                return Result.error('LINE_VALIDATION_FAILED',
                                    f'Validation errors: {"; ".join(errors)}')

            return Result.success(
                data={'lines_count': lines.count()},
                msg=f'All {lines.count()} lines are valid'
            )

        except Exception as e:
            return Result.error('LINE_VALIDATION_ERROR', f'Validation failed: {str(e)}')

    # =====================
    # PRIVATE HELPERS
    # =====================

    @staticmethod
    def _get_line_class(document):
        """Намира Line class за даден document"""
        document_class_name = document.__class__.__name__

        mapping = {
            'PurchaseRequest': 'PurchaseRequestLine',
            'PurchaseOrder': 'PurchaseOrderLine',
            'DeliveryReceipt': 'DeliveryLine'
        }

        line_class_name = mapping.get(document_class_name)
        if not line_class_name:
            return None

        # Import dynamically
        try:
            if 'Request' in document_class_name:
                from purchases.models import PurchaseRequestLine
                return PurchaseRequestLine
            elif 'Order' in document_class_name:
                from purchases.models import PurchaseOrderLine
                return PurchaseOrderLine
            elif 'Delivery' in document_class_name or 'Receipt' in document_class_name:
                from purchases.models import DeliveryLine
                return DeliveryLine
        except ImportError:
            return None

        return None

    @staticmethod
    def _get_quantity_field(line_class):
        """Намира quantity field за Line class"""
        if hasattr(line_class, 'requested_quantity'):
            return 'requested_quantity'
        elif hasattr(line_class, 'ordered_quantity'):
            return 'ordered_quantity'
        elif hasattr(line_class, 'received_quantity'):
            return 'received_quantity'
        else:
            return 'quantity'  # fallback

    @staticmethod
    def _get_next_line_number(document) -> int:
        """Генерира следващия line_number"""
        line_class = DocumentLineService._get_line_class(document)
        if not line_class:
            return 1

        last_line = line_class.objects.filter(document=document).order_by('-line_number').first()
        return (last_line.line_number + 1) if last_line else 1

    @staticmethod
    def _can_modify_line(document, line) -> bool:
        """Проверява дали може да се модифицира ред"""
        # Използва DocumentService за проверка на permissions
        try:
            from nomenclatures.services import DocumentService
            result = DocumentService.can_edit_document(document, None)  # TODO: добави user
            return result.data.get('can_edit', False) if result.ok else False
        except:
            return document.status in ['draft', 'pending']

    @staticmethod
    @transaction.atomic
    def _reorder_lines(document):
        """Преподрежда line_number след изтриване"""
        line_class = DocumentLineService._get_line_class(document)
        if not line_class:
            return

        lines = line_class.objects.filter(document=document).order_by('line_number')
        for i, line in enumerate(lines, 1):
            if line.line_number != i:
                line.line_number = i
                line.save(update_fields=['line_number'])

    @staticmethod
    def _post_line_creation(document, line):
        """Post-processing след създаване на ред"""
        # Trigger document recalculations ако има financial data
        if hasattr(document, 'recalculate_lines'):
            try:
                document.recalculate_lines()
            except Exception as e:
                logger.warning(f"Failed to recalculate document after line creation: {e}")

    @staticmethod
    def _post_line_modification(document):
        """Post-processing след модификация на редове"""
        # Същото като _post_line_creation но без line parameter
        if hasattr(document, 'recalculate_lines'):
            try:
                document.recalculate_lines()
            except Exception as e:
                logger.warning(f"Failed to recalculate document after line modification: {e}")


# =====================
# CONVENIENCE METHODS ЗА ВСЕКИ DOCUMENT TYPE
# =====================

class PurchaseRequestLineService:
    """Convenience wrapper за PurchaseRequest lines"""

    @staticmethod
    def add_line(request, product, quantity: Decimal, estimated_price: Decimal = None) -> Result:
        return DocumentLineService.add_line(
            request, product, quantity,
            estimated_price=estimated_price
        )


class PurchaseOrderLineService:
    """Convenience wrapper за PurchaseOrder lines"""

    @staticmethod
    def add_line(order, product, quantity: Decimal, unit_price: Decimal,
                 source_request_line=None) -> Result:
        return DocumentLineService.add_line(
            order, product, quantity,
            unit_price=unit_price,
            source_request_line=source_request_line
        )


class DeliveryLineService:
    """Convenience wrapper за Delivery lines"""

    @staticmethod
    def add_line(delivery, product, quantity: Decimal, unit_price: Decimal,
                 source_order_line=None, batch_number: str = None) -> Result:
        return DocumentLineService.add_line(
            delivery, product, quantity,
            unit_price=unit_price,
            source_order_line=source_order_line,
            batch_number=batch_number
        )