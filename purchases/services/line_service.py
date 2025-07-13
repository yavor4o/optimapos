# purchases/services/line_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import models

from ..models import PurchaseDocument, PurchaseDocumentLine


class LineService:
    """Сервис за работа с редове в документи"""

    @staticmethod
    @transaction.atomic
    def add_line_to_document(
            document: PurchaseDocument,
            product,
            quantity: Decimal,
            unit_price: Decimal,
            unit=None,
            discount_percent: Decimal = Decimal('0'),
            batch_number: str = '',
            expiry_date=None,
            line_number: Optional[int] = None,
            **kwargs
    ) -> PurchaseDocumentLine:
        """Добавя нов ред към purchase document"""

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

        # Default unit
        if unit is None:
            unit = product.base_unit

        # Валидация на unit
        valid_units = [product.base_unit]
        if hasattr(product, 'packagings'):
            valid_units.extend([p.unit for p in product.packagings.all()])

        if unit not in valid_units:
            raise ValidationError(f"Unit {unit.code} is not valid for product {product.code}")

        # Създаваме реда
        line = PurchaseDocumentLine(
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

        line.full_clean()
        line.save()

        # Recalculate document totals - import тук за да избегнем circular import
        from .document_service import DocumentService
        DocumentService.recalculate_document_totals(document)

        return line

    @staticmethod
    @transaction.atomic
    def update_line(
            line: PurchaseDocumentLine,
            quantity: Optional[Decimal] = None,
            unit_price: Optional[Decimal] = None,
            discount_percent: Optional[Decimal] = None,
            batch_number: Optional[str] = None,
            expiry_date=None,
            **kwargs
    ) -> PurchaseDocumentLine:
        """Обновява съществуващ ред"""

        if not line.document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        # Обновяваме полетата
        if quantity is not None:
            line.quantity = quantity
        if unit_price is not None:
            line.unit_price = unit_price
        if discount_percent is not None:
            line.discount_percent = discount_percent
        if batch_number is not None:
            line.batch_number = batch_number
        if expiry_date is not None:
            line.expiry_date = expiry_date

        # Обновяваме допълнителните полета
        for key, value in kwargs.items():
            if hasattr(line, key):
                setattr(line, key, value)

        line.full_clean()
        line.save()

        # Recalculate document totals
        from .document_service import DocumentService
        DocumentService.recalculate_document_totals(line.document)

        return line

    @staticmethod
    @transaction.atomic
    def delete_line(line: PurchaseDocumentLine) -> None:
        """Изтрива ред от документ"""

        if not line.document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        document = line.document
        line.delete()

        # Recalculate document totals
        from .document_service import DocumentService
        DocumentService.recalculate_document_totals(document)

    @staticmethod
    def validate_document_lines(document: PurchaseDocument) -> List[str]:
        """Валидира всички редове в документ"""
        errors = []

        if not document.lines.exists():
            errors.append("Document must have at least one line")
            return errors

        for line in document.lines.all():
            line_errors = LineService.validate_line(line)
            if line_errors:
                errors.extend([f"Line {line.line_number}: {error}" for error in line_errors])

        return errors

    @staticmethod
    def validate_line(line: PurchaseDocumentLine) -> List[str]:
        """Валидира отделен ред"""
        errors = []

        # Основни валидации
        if line.quantity <= 0:
            errors.append("Quantity must be greater than 0")

        if line.unit_price < 0:
            errors.append("Unit price cannot be negative")

        if line.discount_percent < 0 or line.discount_percent > 100:
            errors.append("Discount percent must be between 0 and 100")

        # Product валидации
        if not line.product.is_active:
            errors.append(f"Product {line.product.code} is inactive")

        # Unit валидации
        valid_units = [line.product.base_unit]
        if hasattr(line.product, 'packagings'):
            valid_units.extend([p.unit for p in line.product.packagings.all()])

        if line.unit not in valid_units:
            errors.append(f"Unit {line.unit.code} is not valid for product {line.product.code}")

        return errors

    @staticmethod
    @transaction.atomic
    def bulk_update_lines(
            lines: List[PurchaseDocumentLine],
            updates: Dict,
            validate_each: bool = True
    ) -> Dict:
        """Bulk обновяване на редове"""
        result = {
            'success': True,
            'updated_count': 0,
            'errors': []
        }

        try:
            documents_to_recalculate = set()

            for line in lines:
                try:
                    if not line.document.can_be_modified():
                        result['errors'].append(f"Line {line.line_number}: Document cannot be modified")
                        continue

                    # Прилагаме обновяванията
                    for field, value in updates.items():
                        if hasattr(line, field):
                            setattr(line, field, value)

                    if validate_each:
                        line.full_clean()

                    line.save()
                    documents_to_recalculate.add(line.document)
                    result['updated_count'] += 1

                except Exception as e:
                    result['errors'].append(f"Line {line.line_number}: {str(e)}")

            # Recalculate всички засегнати документи
            from .document_service import DocumentService
            for document in documents_to_recalculate:
                DocumentService.recalculate_document_totals(document)

        except Exception as e:
            result['success'] = False
            result['errors'].append(f"Bulk update failed: {str(e)}")

        return result

    @staticmethod
    def get_line_analytics(document: PurchaseDocument) -> Dict:
        """Връща аналитика за редовете в документ"""
        lines = document.lines.all()

        if not lines.exists():
            return {
                'total_lines': 0,
                'total_quantity': Decimal('0'),
                'total_amount': Decimal('0'),
                'avg_unit_price': Decimal('0'),
                'lines_with_discount': 0
            }

        analytics = lines.aggregate(
            total_lines=models.Count('id'),
            total_quantity=models.Sum('quantity'),
            total_amount=models.Sum('line_total'),
            avg_unit_price=models.Avg('unit_price'),
            lines_with_discount=models.Count('id', filter=models.Q(discount_percent__gt=0)),
            max_line_total=models.Max('line_total'),
            min_line_total=models.Min('line_total')
        )

        return analytics

    @staticmethod
    def bulk_update_pricing_from_document(document: PurchaseDocument) -> Dict:
        """Обновява цените на продуктите въз основа на документа"""
        result = {
            'updated_count': 0,
            'errors': []
        }

        try:
            # Това е placeholder - трябва да се имплементира според нуждите
            # Може да обновява supplier prices, cost prices, etc.

            for line in document.lines.all():
                try:
                    # Пример за обновяване на supplier price
                    # supplier_price, created = SupplierPrice.objects.get_or_create(
                    #     supplier=document.supplier,
                    #     product=line.product,
                    #     defaults={'price': line.unit_price}
                    # )
                    # if not created:
                    #     supplier_price.price = line.unit_price
                    #     supplier_price.save()

                    result['updated_count'] += 1

                except Exception as e:
                    result['errors'].append(f"Product {line.product.code}: {str(e)}")

        except Exception as e:
            result['errors'].append(f"Pricing update failed: {str(e)}")

        return result

    @staticmethod
    @transaction.atomic
    def reorder_lines(document: PurchaseDocument, line_order: List[int]) -> None:
        """Пренарежда редовете в документ"""

        if not document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        lines = list(document.lines.all())

        if len(line_order) != len(lines):
            raise ValidationError("Line order must contain all line IDs")

        # Обновяваме line_number според новия ред
        for new_position, line_id in enumerate(line_order, 1):
            try:
                line = next(l for l in lines if l.id == line_id)
                line.line_number = new_position
                line.save(update_fields=['line_number'])
            except StopIteration:
                raise ValidationError(f"Line with ID {line_id} not found")

    @staticmethod
    def get_line_by_product(document: PurchaseDocument, product) -> Optional[PurchaseDocumentLine]:
        """Намира ред по продукт"""
        try:
            return document.lines.get(product=product)
        except PurchaseDocumentLine.DoesNotExist:
            return None
        except PurchaseDocumentLine.MultipleObjectsReturned:
            # Връща първия намерен ред
            return document.lines.filter(product=product).first()

    @staticmethod
    def merge_duplicate_lines(document: PurchaseDocument) -> int:
        """Сливане на дублирани редове със същия продукт"""

        if not document.can_be_modified():
            raise ValidationError("Cannot modify document in current status")

        lines_by_product = {}
        merged_count = 0

        for line in document.lines.all():
            key = (line.product.id, line.unit.id, line.unit_price, line.discount_percent)

            if key in lines_by_product:
                # Merge в първия намерен ред
                original_line = lines_by_product[key]
                original_line.quantity += line.quantity
                original_line.save()

                # Изтриваме дублирания ред
                line.delete()
                merged_count += 1
            else:
                lines_by_product[key] = line

        # Recalculate totals
        from .document_service import DocumentService
        DocumentService.recalculate_document_totals(document)

        return merged_count