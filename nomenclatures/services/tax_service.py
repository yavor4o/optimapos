from decimal import Decimal
from typing import Dict, List, Optional
from ..models import TaxGroup


class TaxService:
    """Сервиз за работа с данъци"""

    @staticmethod
    def calculate_tax_breakdown(
            amount: Decimal,
            tax_group: TaxGroup,
            prices_include_tax: bool = True
    ) -> Dict[str, Decimal]:
        """
        Разбивка на сумата по данъци

        Returns:
            {
                'amount_without_tax': Decimal,
                'tax_amount': Decimal,
                'amount_with_tax': Decimal,
                'tax_rate': Decimal
            }
        """
        tax_rate = tax_group.rate

        if prices_include_tax:
            # Цената включва данък
            amount_with_tax = amount
            amount_without_tax = amount / (1 + tax_rate / 100)
            tax_amount = amount_with_tax - amount_without_tax
        else:
            # Цената е без данък
            amount_without_tax = amount
            tax_amount = amount * tax_rate / 100
            amount_with_tax = amount_without_tax + tax_amount

        return {
            'amount_without_tax': round(amount_without_tax, 2),
            'tax_amount': round(tax_amount, 2),
            'amount_with_tax': round(amount_with_tax, 2),
            'tax_rate': tax_rate
        }

    @staticmethod
    def calculate_multiple_items_tax(
            items: List[Dict],
            prices_include_tax: bool = True
    ) -> Dict[str, Decimal]:
        """
        Изчислява данъци за множество артикули

        Args:
            items: [{'amount': Decimal, 'quantity': int, 'tax_group': TaxGroup}, ...]

        Returns:
            {
                'total_without_tax': Decimal,
                'total_tax': Decimal,
                'total_with_tax': Decimal,
                'tax_breakdown': {
                    'ДДС 20%': {'base': Decimal, 'tax': Decimal},
                    'ДДС 9%': {'base': Decimal, 'tax': Decimal},
                }
            }
        """
        total_without_tax = Decimal('0')
        total_tax = Decimal('0')
        tax_breakdown = {}

        for item in items:
            amount = item['amount'] * item.get('quantity', 1)
            tax_group = item['tax_group']

            result = TaxService.calculate_tax_breakdown(
                amount,
                tax_group,
                prices_include_tax
            )

            total_without_tax += result['amount_without_tax']
            total_tax += result['tax_amount']

            # Групираме по данъчна група
            tax_key = str(tax_group)
            if tax_key not in tax_breakdown:
                tax_breakdown[tax_key] = {
                    'base': Decimal('0'),
                    'tax': Decimal('0'),
                    'rate': tax_group.rate
                }

            tax_breakdown[tax_key]['base'] += result['amount_without_tax']
            tax_breakdown[tax_key]['tax'] += result['tax_amount']

        return {
            'total_without_tax': round(total_without_tax, 2),
            'total_tax': round(total_tax, 2),
            'total_with_tax': round(total_without_tax + total_tax, 2),
            'tax_breakdown': tax_breakdown
        }

    @staticmethod
    def get_default_tax_group() -> Optional[TaxGroup]:
        """Връща данъчната група по подразбиране"""
        return TaxGroup.objects.filter(is_default=True, is_active=True).first()

    @staticmethod
    def validate_fiscal_data(data: Dict) -> tuple[bool, List[str]]:
        """
        Валидира фискални данни преди издаване на документ

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Проверка за данъчни групи
        if not data.get('items'):
            errors.append('Няма артикули в документа')

        for idx, item in enumerate(data.get('items', [])):
            if not item.get('tax_group'):
                errors.append(f'Липсва данъчна група за артикул {idx + 1}')

            if item.get('amount', 0) < 0 and not data.get('is_credit_note'):
                errors.append(f'Отрицателна сума за артикул {idx + 1}')

        # Проверка на общите суми
        if data.get('total_amount', 0) < 0 and not data.get('is_credit_note'):
            errors.append('Общата сума не може да е отрицателна')

        return len(errors) == 0, errors