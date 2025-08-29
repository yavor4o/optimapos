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
    def add_line(document, product, quantity: Decimal, user=None, **kwargs) -> Result:
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
            
            # Добави unit ако не е подаден (използва base_unit от продукта)
            if 'unit' not in line_data and hasattr(product, 'base_unit') and product.base_unit:
                line_data['unit'] = product.base_unit

            # Map price fields според типа line
            if 'unit_price' in kwargs:
                price_field = DocumentLineService._get_price_field(line_class)
                if price_field and price_field != 'unit_price':
                    line_data[price_field] = kwargs.pop('unit_price')

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
    def remove_line(document, line_number: int, user=None) -> Result:
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
            if not DocumentLineService._can_modify_line(document, line, user):
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
        """Намира quantity field за Line class - FIXED: Check actual fields, not properties"""
        # Check for actual model fields, not properties
        field_names = [field.name for field in line_class._meta.fields]
        
        if 'requested_quantity' in field_names:
            return 'requested_quantity'
        elif 'ordered_quantity' in field_names:
            return 'ordered_quantity'
        elif 'received_quantity' in field_names:
            return 'received_quantity'
        else:
            return 'quantity'  # fallback

    @staticmethod
    def _get_price_field(line_class):
        """Намира primary price field за Line class"""
        line_class_name = line_class.__name__
        if 'Request' in line_class_name:
            return 'estimated_price'
        elif 'Order' in line_class_name:
            return 'unit_price'
        elif 'Delivery' in line_class_name:
            return 'unit_price'
        else:
            return 'unit_price'  # fallback

    @staticmethod
    def _get_next_line_number(document) -> int:
        """Генерира следващия line_number"""
        line_class = DocumentLineService._get_line_class(document)
        if not line_class:
            return 1

        last_line = line_class.objects.filter(document=document).order_by('-line_number').first()
        return (last_line.line_number + 1) if last_line else 1

    @staticmethod
    def _can_modify_line(document, line, user=None) -> bool:
        """Проверява дали може да се модифицира ред"""
        # Use convenience function with proper Result handling
        try:
            from nomenclatures.services import can_edit_document
            result = can_edit_document(document, user)
            return result.data.get('can_edit', False) if result.ok else False
        except ImportError:
            # FIXED: Use dynamic status resolution instead of hardcoded
            try:
                from ._status_resolver import can_edit_in_status
                return can_edit_in_status(document)
            except Exception:
                # Emergency fallback - more permissive
                return document.status in ['draft', 'pending', 'created', '']

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
        
        # 1. Calculate line-level VAT/financial fields first
        try:
            from .vat_calculation_service import VATCalculationService
            
            # Get entered price from line
            entered_price = (
                getattr(line, 'entered_price', None) or
                getattr(line, 'estimated_price', None) or  
                getattr(line, 'unit_price', None)
            )
            
            if entered_price and entered_price > 0:
                from decimal import Decimal
                # Ensure entered_price is Decimal
                if not isinstance(entered_price, Decimal):
                    entered_price = Decimal(str(entered_price))
                    
                line_vat_result = VATCalculationService.calculate_line_vat(
                    line=line, 
                    entered_price=entered_price, 
                    save=True
                )
                if not line_vat_result.ok:
                    logger.warning(f"Line VAT calculation failed: {line_vat_result.msg}")
                    
        except ImportError:
            logger.info("VATCalculationService not available - skipping line VAT calculations")
        except Exception as e:
            logger.warning(f"Failed to calculate line VAT: {e}")
        
        # 2. Then recalculate document totals
        if hasattr(document, 'recalculate_lines'):
            try:
                result = document.recalculate_lines()
                if hasattr(result, 'ok') and not result.ok:
                    logger.warning(f"Failed to recalculate document after line creation: {result.msg}")
            except Exception as e:
                logger.warning(f"Failed to recalculate document after line creation: {e}")
        else:
            # Fallback - trigger save to update timestamps
            try:
                document.save(update_fields=['updated_at'])
            except Exception as e:
                logger.warning(f"Failed to update document after line creation: {e}")

    @staticmethod
    def _post_line_modification(document):
        """Post-processing след модификация на редове"""
        # Use model's recalculate_lines method (which delegates to DocumentService)
        if hasattr(document, 'recalculate_lines'):
            try:
                result = document.recalculate_lines()
                if hasattr(result, 'ok') and not result.ok:
                    logger.warning(f"Failed to recalculate document after line modification: {result.msg}")
            except Exception as e:
                logger.warning(f"Failed to recalculate document after line modification: {e}")
        else:
            # Fallback - trigger save to update timestamps
            try:
                document.save(update_fields=['updated_at'])
            except Exception as e:
                logger.warning(f"Failed to update document after line modification: {e}")


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