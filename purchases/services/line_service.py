# purchases/services/line_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Dict, Any
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
            from django.db import models
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

        # Преизчисляваме общите суми на документа
        document.recalculate_totals()
        document.save()

        return line

    @staticmethod
    @transaction.atomic
    def update_line(line: PurchaseDocumentLine, **update_data) -> PurchaseDocumentLine:
        """Обновява съществуващ ред"""

        if not line.document.can_be_modified():
            raise ValidationError("Cannot modify line - document is not in editable status")

        # Обновяваме полетата
        for field, value in update_data.items():
            if hasattr(line, field):
                setattr(line, field, value)

        line.full_clean()
        line.save()

        # Преизчисляваме общите суми на документа
        line.document.recalculate_totals()
        line.document.save()

        return line

    @staticmethod
    @transaction.atomic
    def delete_line(line: PurchaseDocumentLine) -> bool:
        """Изтрива ред от документ"""

        if not line.document.can_be_modified():
            raise ValidationError("Cannot delete line - document is not in editable status")

        document = line.document
        line.delete()

        # Преизчисляваме общите суми на документа
        document.recalculate_totals()
        document.save()

        return True

    @staticmethod
    def calculate_line_pricing(line: PurchaseDocumentLine) -> Dict:
        """Изчислява pricing информация за ред"""

        # Базови изчисления
        line_subtotal = line.quantity * line.unit_price
        discount_amount = line_subtotal * (line.discount_percent / 100)
        line_total_after_discount = line_subtotal - discount_amount

        # VAT изчисления (ако продуктът има tax group)
        vat_amount = Decimal('0')
        if hasattr(line.product, 'tax_group') and line.product.tax_group:
            vat_amount = line_total_after_discount * (line.product.tax_group.rate / 100)

        line_total_with_vat = line_total_after_discount + vat_amount

        # Cost per base unit
        conversion_factor = line.get_conversion_factor()
        cost_per_base_unit = line.unit_price / conversion_factor

        return {
            'line_subtotal': line_subtotal,
            'discount_amount': discount_amount,
            'line_total_after_discount': line_total_after_discount,
            'vat_amount': vat_amount,
            'line_total_with_vat': line_total_with_vat,
            'cost_per_base_unit': cost_per_base_unit,
            'total_cost_base_units': line.quantity * conversion_factor * cost_per_base_unit,
        }

    @staticmethod
    def analyze_receiving_variance(line: PurchaseDocumentLine) -> Dict:
        """Анализира разликите при получаване на ред"""

        variance_qty = line.received_quantity - line.quantity
        variance_percentage = (variance_qty / line.quantity * 100) if line.quantity > 0 else 0
        variance_amount = variance_qty * line.unit_price

        # Статус на варианса
        if variance_qty == 0:
            status = 'exact'
        elif variance_qty > 0:
            status = 'over_received'
        else:
            status = 'under_received'

        return {
            'variance_quantity': variance_qty,
            'variance_percentage': round(variance_percentage, 2),
            'variance_amount': variance_amount,
            'status': status,
            'ordered_quantity': line.quantity,
            'received_quantity': line.received_quantity,
            'is_significant': abs(variance_percentage) > 5,  # Над 5% е значителна разлика
        }

    @staticmethod
    def calculate_pricing_suggestions(line: PurchaseDocumentLine, location=None) -> Dict:
        """Изчислява предложения за продажни цени"""

        if not location:
            location = line.document.location

        suggestions = {
            'current_cost': line.unit_price,
            'suggested_prices': [],
            'markup_analysis': []
        }

        # Различни markup проценти за анализ
        markup_options = [20, 30, 40, 50, 60]

        for markup in markup_options:
            markup_decimal = Decimal(str(markup))
            suggested_price = line.unit_price * (Decimal('1') + markup_decimal / Decimal('100'))
            margin = markup_decimal / (Decimal('100') + markup_decimal) * Decimal('100')

            suggestions['suggested_prices'].append({
                'markup_percent': markup,
                'margin_percent': round(float(margin), 1),
                'suggested_price': suggested_price,
                'profit_per_unit': suggested_price - line.unit_price
            })

        # Текуща продажна цена (ако има)
        try:
            current_sale_price = None
            # TODO: Интеграция с pricing service

            if current_sale_price is not None and Decimal(str(current_sale_price)) > Decimal('0'):
                current_sale_price_decimal = Decimal(str(current_sale_price))  # Конвертираме в Decimal
                current_markup = ((current_sale_price_decimal - line.unit_price) / line.unit_price) * Decimal('100')
                suggestions['current_sale_price'] = current_sale_price_decimal
                suggestions['current_markup'] = Decimal(str(round(float(current_markup), 1)))

        except Exception:
            pass

        return suggestions

    @staticmethod
    @transaction.atomic
    def bulk_update_received_quantities(line_updates: List[Dict]) -> Dict:
        """Bulk обновяване на получени количества

        Args:
            line_updates: List of {'line_id': int, 'received_quantity': Decimal}
        """

        success_count = 0
        errors = []
        updated_documents = set()

        for update in line_updates:
            try:
                line = PurchaseDocumentLine.objects.get(id=update['line_id'])

                if not line.document.can_be_modified():
                    errors.append(f"Line {line.line_number}: Document cannot be modified")
                    continue

                line.received_quantity = update['received_quantity']
                line.save()

                updated_documents.add(line.document.id)
                success_count += 1

            except PurchaseDocumentLine.DoesNotExist:
                errors.append(f"Line with ID {update['line_id']} not found")
            except Exception as e:
                errors.append(f"Line {update.get('line_id', 'unknown')}: {str(e)}")

        # Преизчисляваме суми за всички засегнати документи
        for doc_id in updated_documents:
            try:
                document = PurchaseDocument.objects.get(id=doc_id)
                document.recalculate_totals()
                document.save()
            except Exception as e:
                errors.append(f"Error recalculating document {doc_id}: {str(e)}")

        return {
            'success_count': success_count,
            'total_attempted': len(line_updates),
            'failed_count': len(errors),
            'errors': errors,
            'updated_documents': len(updated_documents)
        }


    @staticmethod
    def get_line_quality_info(line: PurchaseDocumentLine) -> Dict[str, Any]:
        """Информация за качеството на ред"""

        quality_info = {
            'is_approved': line.quality_approved,
            'has_notes': bool(line.quality_notes),
            'quality_notes': line.quality_notes,
        }

        # Проверка на срок на годност
        if line.expiry_date:
            today = timezone.now().date()
            days_to_expiry = (line.expiry_date - today).days

            if days_to_expiry < 0:
                quality_info['expiry_status'] = 'expired'
                quality_info['expiry_alert'] = 'EXPIRED'
            elif days_to_expiry <= 7:
                quality_info['expiry_status'] = 'expires_soon'
                quality_info['expiry_alert'] = f'Expires in {days_to_expiry} days'
            elif days_to_expiry <= 30:
                quality_info['expiry_status'] = 'expires_this_month'
                quality_info['expiry_alert'] = f'Expires in {days_to_expiry} days'
            else:
                quality_info['expiry_status'] = 'good'
                quality_info['expiry_alert'] = None

            quality_info['days_to_expiry'] = days_to_expiry
        else:
            quality_info['expiry_status'] = 'no_expiry'
            quality_info['expiry_alert'] = None

        return quality_info

    @staticmethod
    @transaction.atomic
    def create_quality_issue(line: PurchaseDocumentLine, issue_description: str, severity: str = 'MEDIUM') -> bool:
        """Създава качествен проблем за ред"""

        line.quality_approved = False

        # Добавяме issue към notes
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
        issue_note = f"[{timestamp}] {severity}: {issue_description}"

        if line.quality_notes:
            line.quality_notes = f"{issue_note}\n{line.quality_notes}"
        else:
            line.quality_notes = issue_note

        line.save(update_fields=['quality_approved', 'quality_notes'])

        return True

    @staticmethod
    def get_lines_summary_for_document(document: PurchaseDocument) -> Dict:
        """Резюме на редовете за документ"""

        # Използваме manager-а вместо .all()
        lines = PurchaseDocumentLine.objects.filter(document=document)

        if not lines.exists():
            return {'total_lines': 0}

        from django.db import models

        summary = lines.aggregate(
            total_lines=models.Count('id'),
            total_quantity=models.Sum('quantity'),
            total_received=models.Sum('received_quantity'),
            avg_unit_price=models.Avg('unit_price'),
            lines_with_discount=models.Count('id', filter=models.Q(discount_percent__gt=0)),
            lines_with_quality_issues=models.Count('id', filter=models.Q(quality_approved=False)),
            lines_with_batch=models.Count('id', filter=models.Q(batch_number__isnull=False, batch_number__gt='')),
            lines_with_expiry=models.Count('id', filter=models.Q(expiry_date__isnull=False)),
        )

        # Анализ на варианси - сега ще работят custom методите
        variance_lines = lines.with_variance()
        summary['lines_with_variance'] = variance_lines.count()
        summary['over_received_lines'] = lines.over_received().count()
        summary['under_received_lines'] = lines.under_received().count()

        # Изчисляваме проценти
        total = summary['total_lines']
        if total > 0:
            summary['discount_rate'] = round((summary['lines_with_discount'] / total) * 100, 1)
            summary['quality_issue_rate'] = round((summary['lines_with_quality_issues'] / total) * 100, 1)
            summary['variance_rate'] = round((summary['lines_with_variance'] / total) * 100, 1)

        return summary

    @staticmethod
    def find_duplicate_lines(document: PurchaseDocument) -> List[Dict]:
        """Намира дублирани редове в документ (същ продукт, unit, цена)"""

        from django.db import models

        # Намираме групи с повече от 1 ред
        duplicate_groups = PurchaseDocumentLine.objects.filter(
            document=document
        ).values(
            'product_id', 'unit_id', 'unit_price'
        ).annotate(
            count=models.Count('id'),
            total_quantity=models.Sum('quantity')
        ).filter(count__gt=1)

        duplicates = []
        for group in duplicate_groups:
            # За всяка група намираме конкретните line_ids
            line_ids = list(
                PurchaseDocumentLine.objects.filter(
                    document=document,
                    product_id=group['product_id'],
                    unit_id=group['unit_id'],
                    unit_price=group['unit_price']
                ).values_list('id', flat=True)
            )

            duplicates.append({
                'product_id': group['product_id'],
                'unit_id': group['unit_id'],
                'unit_price': group['unit_price'],
                'duplicate_count': group['count'],
                'line_ids': line_ids,
                'total_quantity': group['total_quantity'],
                'suggestion': 'Consider merging these lines'
            })

        return duplicates

    @staticmethod
    @transaction.atomic
    def bulk_update_pricing_from_document(document: PurchaseDocument) -> Dict:
        """Bulk обновяване на цени от всички редове в документ"""

        results = {
            'updated_count': 0,
            'skipped_count': 0,
            'errors': []
        }

        for line in document.lines.filter(new_sale_price__isnull=False, new_sale_price__gt=0):
            try:
                line.apply_suggested_price()
                results['updated_count'] += 1
            except Exception as e:
                results['errors'].append(f"Product {line.product.code}: {str(e)}")
                results['skipped_count'] += 1

        return results