# nomenclatures/services/vat_calculation_service.py
"""
ЕДИНЕН VAT CALCULATION SERVICE
Заменя всички разпръснати VAT изчисления в системата

Приоритет на настройки:
1. Document level: prices_entered_with_vat field
2. Location level: purchase/sales_prices_include_vat
3. System defaults: purchases=False, sales=True
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple, Any
from django.db import models
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class VATCalculationService:
    """
    Централизиран VAT calculation service
    Всички VAT изчисления минават през тук
    """

    # System defaults
    DEFAULT_VAT_RATE = Decimal('0.20')  # 20% VAT
    PURCHASE_PRICES_INCLUDE_VAT = False  # Purchases без ДДС
    SALES_PRICES_INCLUDE_VAT = True  # Sales с ДДС

    @classmethod
    def get_price_entry_mode(cls, document) -> bool:
        """
        Определя дали цените включват ДДС

        Йерархия:
        1. Document field (prices_entered_with_vat)
        2. Location settings (purchase/sales_prices_include_vat)
        3. System defaults
        """
        # 1. Document level setting (highest priority)
        if hasattr(document, 'prices_entered_with_vat'):
            if document.prices_entered_with_vat is not None:
                return document.prices_entered_with_vat

        # 2. Location settings
        if hasattr(document, 'location') and document.location:
            app_label = document._meta.app_label

            if app_label == 'purchases':
                if hasattr(document.location, 'purchase_prices_include_vat'):
                    return document.location.purchase_prices_include_vat
                return cls.PURCHASE_PRICES_INCLUDE_VAT

            elif app_label == 'sales':
                if hasattr(document.location, 'sales_prices_include_vat'):
                    return document.location.sales_prices_include_vat
                return cls.SALES_PRICES_INCLUDE_VAT

        # 3. System defaults
        if document._meta.app_label == 'purchases':
            return cls.PURCHASE_PRICES_INCLUDE_VAT
        elif document._meta.app_label == 'sales':
            return cls.SALES_PRICES_INCLUDE_VAT
        else:
            return False

    @classmethod
    def get_vat_rate(cls, line=None, product=None, location=None) -> Decimal:
        """
        Получава VAT rate за продукт/линия

        Приоритет:
        1. Line override (ако има)
        2. Product VAT rate
        3. Location default VAT rate
        4. System default
        """
        # 1. Line override
        if line and hasattr(line, 'vat_rate') and line.vat_rate is not None:
            return Decimal(str(line.vat_rate))

        # 2. Product VAT rate
        if product or (line and hasattr(line, 'product')):
            prod = product or line.product
            if prod and hasattr(prod, 'vat_rate'):
                return Decimal(str(prod.vat_rate or cls.DEFAULT_VAT_RATE))

        # 3. Location default
        if location and hasattr(location, 'default_vat_rate'):
            return Decimal(str(location.default_vat_rate))

        # 4. System default
        return cls.DEFAULT_VAT_RATE

    @classmethod
    def calculate_vat_amounts(cls,
                              entered_price: Decimal,
                              vat_rate: Decimal,
                              quantity: Decimal = Decimal('1'),
                              prices_include_vat: bool = False) -> Dict[str, Decimal]:
        """
        Главен метод за VAT изчисления

        Args:
            entered_price: Цената както е въведена
            vat_rate: VAT процент (0.20 за 20%)
            quantity: Количество
            prices_include_vat: Дали въведената цена включва ДДС

        Returns:
            Dict с всички изчислени стойности:
            - unit_price: Единична цена БЕЗ ДДС
            - unit_price_with_vat: Единична цена С ДДС
            - line_subtotal: Сума БЕЗ ДДС (unit_price * quantity)
            - vat_amount: ДДС сума
            - line_total: Сума С ДДС
        """
        # Валидация
        entered_price = Decimal(str(entered_price or 0))
        vat_rate = Decimal(str(vat_rate or 0))
        quantity = Decimal(str(quantity or 1))

        # Изчисляване на единични цени
        if prices_include_vat:
            # Entered price включва ДДС -> изчисляваме без ДДС
            unit_price_with_vat = entered_price
            unit_price = entered_price / (1 + vat_rate)
        else:
            # Entered price е без ДДС -> изчисляваме с ДДС
            unit_price = entered_price
            unit_price_with_vat = entered_price * (1 + vat_rate)

        # Изчисляване на суми
        line_subtotal = unit_price * quantity
        vat_amount = line_subtotal * vat_rate
        line_total = line_subtotal + vat_amount

        # Закръгляне до 2 знака
        return {
            'unit_price': unit_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'unit_price_with_vat': unit_price_with_vat.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'line_subtotal': line_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'vat_amount': vat_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'line_total': line_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        }

    @classmethod
    def process_document_line(cls, line, save=True) -> Dict[str, Any]:
        """
        Обработва цялата линия на документ
        Изчислява и записва всички VAT полета
        """
        # Вземи необходимите данни
        document = line.document if hasattr(line, 'document') else None
        if not document:
            logger.warning(f"Line {line.pk} has no document reference")
            return {'success': False, 'error': 'No document'}

        # Определи price entry mode
        prices_include_vat = cls.get_price_entry_mode(document)

        # Вземи VAT rate
        vat_rate = cls.get_vat_rate(line)

        # Вземи entered price и quantity
        entered_price = getattr(line, 'entered_price', None) or getattr(line, 'unit_price', Decimal('0'))
        quantity = line.get_quantity_for_calculation() if hasattr(line, 'get_quantity_for_calculation') else Decimal(
            '1')

        # Изчисли всичко
        calculations = cls.calculate_vat_amounts(
            entered_price=entered_price,
            vat_rate=vat_rate,
            quantity=quantity,
            prices_include_vat=prices_include_vat
        )

        # Update line fields
        if hasattr(line, 'unit_price'):
            line.unit_price = calculations['unit_price']
        if hasattr(line, 'unit_price_with_vat'):
            line.unit_price_with_vat = calculations['unit_price_with_vat']
        if hasattr(line, 'line_subtotal'):
            line.line_subtotal = calculations['line_subtotal']
        if hasattr(line, 'vat_amount'):
            line.vat_amount = calculations['vat_amount']
        if hasattr(line, 'line_total'):
            line.line_total = calculations['line_total']

        # Save if requested
        if save:
            line.save(update_fields=['unit_price', 'unit_price_with_vat',
                                     'line_subtotal', 'vat_amount', 'line_total'])

        return {
            'success': True,
            'calculations': calculations,
            'prices_include_vat': prices_include_vat,
            'vat_rate': vat_rate
        }

    @classmethod
    def recalculate_document_totals(cls, document) -> Dict[str, Decimal]:
        """
        Преизчислява тоталите на документ от неговите линии
        """
        # Вземи всички линии
        lines = []
        if hasattr(document, 'lines'):
            lines = document.lines.all()
        elif hasattr(document, 'get_lines'):
            lines = document.get_lines()

        # Сумирай от линиите
        subtotal = Decimal('0')
        total_vat = Decimal('0')
        total_discount = Decimal('0')

        for line in lines:
            # Преизчисли линията първо
            cls.process_document_line(line, save=False)

            # Добави към тоталите
            subtotal += getattr(line, 'line_subtotal', Decimal('0'))
            total_vat += getattr(line, 'vat_amount', Decimal('0'))

            # Discount (ако има)
            if hasattr(line, 'discount_amount'):
                total_discount += getattr(line, 'discount_amount', Decimal('0'))

        # Изчисли финален total
        total = subtotal + total_vat - total_discount

        # Update document fields
        if hasattr(document, 'subtotal'):
            document.subtotal = subtotal
        if hasattr(document, 'vat_total'):
            document.vat_total = total_vat
        if hasattr(document, 'discount_total'):
            document.discount_total = total_discount
        if hasattr(document, 'total'):
            document.total = total

        return {
            'subtotal': subtotal.quantize(Decimal('0.01')),
            'vat_total': total_vat.quantize(Decimal('0.01')),
            'discount_total': total_discount.quantize(Decimal('0.01')),
            'total': total.quantize(Decimal('0.01')),
        }

    @classmethod
    def validate_vat_consistency(cls, document) -> Tuple[bool, Optional[str]]:
        """
        Валидира че VAT изчисленията са консистентни
        """
        try:
            # Преизчисли
            calculated = cls.recalculate_document_totals(document)

            # Сравни със записаните
            tolerance = Decimal('0.01')

            if hasattr(document, 'total'):
                diff = abs(document.total - calculated['total'])
                if diff > tolerance:
                    return False, f"Total mismatch: {document.total} vs {calculated['total']}"

            if hasattr(document, 'vat_total'):
                diff = abs(document.vat_total - calculated['vat_total'])
                if diff > tolerance:
                    return False, f"VAT mismatch: {document.vat_total} vs {calculated['vat_total']}"

            return True, None

        except Exception as e:
            return False, str(e)