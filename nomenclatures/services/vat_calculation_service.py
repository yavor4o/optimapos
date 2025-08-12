# nomenclatures/services/vat_calculation_service.py
"""
UNIFIED VAT CALCULATION SERVICE

Обединява 4-те service файла:
1. VATService (purchases/services/vat_service.py)
2. VATIntegrationService (purchases/services/vat_integration_service.py)
3. TaxService (nomenclatures/services/tax_service.py)
4. CurrencyService (nomenclatures/services/currency_service.py)

Това е единният entry point за всички VAT/Tax/Currency операции!
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, List, Tuple, Any, Union
from datetime import date
from django.db import models, transaction
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class VATCalculationService:
    """
    ✅ UNIFIED SERVICE за всички VAT/Tax/Currency изчисления

    Заменя:
    - SmartVATService
    - VATIntegrationService
    - TaxService (commented out)
    - CurrencyService (commented out)
    """

    # =====================
    # CONSTANTS & DEFAULTS
    # =====================
    DEFAULT_VAT_RATE = Decimal('0.20')  # 20% VAT
    PURCHASE_PRICES_INCLUDE_VAT = False  # Purchases без ДДС by default
    SALES_PRICES_INCLUDE_VAT = True  # Sales с ДДС by default
    CACHE_TIMEOUT = 3600  # 1 час за cache

    # =====================
    # 1. PRICE ENTRY MODE DETECTION
    # =====================
    @classmethod
    def get_price_entry_mode(cls, document) -> bool:
        """
        🎯 CORE METHOD: Определя дали цените включват ДДС

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

    # =====================
    # 2. VAT RATE DETECTION
    # =====================
    @classmethod
    def get_vat_rate(cls, line=None, product=None, location=None) -> Decimal:
        """
        🎯 CORE METHOD: Получава VAT rate за продукт/линия

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
        if not product and line and hasattr(line, 'product'):
            product = line.product

        if product and hasattr(product, 'tax_group') and product.tax_group:
            return Decimal(str(product.tax_group.rate))

        # 3. Location default
        if not location and line and hasattr(line, 'document') and hasattr(line.document, 'location'):
            location = line.document.location

        if location and hasattr(location, 'default_vat_rate'):
            return Decimal(str(location.default_vat_rate))

        # 4. System default
        return cls.DEFAULT_VAT_RATE

    # =====================
    # 3. CORE LINE CALCULATION
    # =====================
    @classmethod
    def calculate_line_totals(
            cls,
            line,
            entered_price: Decimal,
            quantity: Optional[Decimal] = None,
            document=None
    ) -> Dict:
        """
        🎯 MAIN METHOD: Пълно изчисление на линия

        Args:
            line: Document line instance
            entered_price: Price as entered by user
            quantity: Quantity (if None, get from line)
            document: Parent document (if None, get from line)

        Returns:
            Dict: Complete calculation results
        """

        # ===== PREPARATION =====
        if not document and hasattr(line, 'document'):
            document = line.document

        if not quantity:
            quantity = cls._get_line_quantity(line)

        result = {
            'entered_price': entered_price,
            'quantity': quantity,
            'unit_price': entered_price,
            'vat_rate': Decimal('0.00'),
            'vat_amount': Decimal('0.00'),
            'discount_amount': Decimal('0.00'),
            'net_amount': Decimal('0.00'),
            'gross_amount': Decimal('0.00'),
            'effective_cost': entered_price,
            'calculation_reason': '',
            'vat_applicable': False,
            'prices_include_vat': False
        }

        # ===== COMPANY VAT CHECK =====
        if not cls._is_company_vat_registered():
            result.update({
                'unit_price': entered_price,
                'net_amount': entered_price * quantity,
                'gross_amount': entered_price * quantity,
                'calculation_reason': 'Company not VAT registered',
                'vat_applicable': False
            })
            return result

        # ===== VAT RATE =====
        vat_rate = cls.get_vat_rate(line)

        if vat_rate == 0:
            result.update({
                'vat_rate': Decimal('0.00'),
                'unit_price': entered_price,
                'net_amount': entered_price * quantity,
                'gross_amount': entered_price * quantity,
                'calculation_reason': 'Product is VAT exempt (0% rate)',
                'vat_applicable': False
            })
            return result

        # ===== PRICE ENTRY MODE =====
        prices_include_vat = cls.get_price_entry_mode(document) if document else False

        # ===== VAT CALCULATION =====
        if prices_include_vat:
            # Цената включва ДДС → extract it
            vat_multiplier = Decimal('1') + (vat_rate / Decimal('100'))
            unit_price = entered_price / vat_multiplier
            calculation_reason = f'Extracted VAT ({vat_rate}%) from entered price'
        else:
            # Цената е без ДДС → add it
            unit_price = entered_price
            calculation_reason = f'Added VAT ({vat_rate}%) to entered price'

        # ===== AMOUNTS CALCULATION =====
        # Get discount if any
        discount_percent = getattr(line, 'discount_percent', Decimal('0')) or Decimal('0')

        # Base calculations
        gross_amount_before_discount = unit_price * quantity
        discount_amount = gross_amount_before_discount * (discount_percent / Decimal('100'))
        net_amount = gross_amount_before_discount - discount_amount
        vat_amount = net_amount * (vat_rate / Decimal('100'))
        gross_amount = net_amount + vat_amount

        # ===== EFFECTIVE COST =====
        effective_cost = cls._calculate_effective_cost(unit_price, gross_amount, quantity)

        # ===== FINAL RESULT =====
        result.update({
            'unit_price': cls._round_currency(unit_price),
            'vat_rate': vat_rate,
            'vat_amount': cls._round_currency(vat_amount),
            'discount_amount': cls._round_currency(discount_amount),
            'net_amount': cls._round_currency(net_amount),
            'gross_amount': cls._round_currency(gross_amount),
            'effective_cost': cls._round_currency(effective_cost),
            'calculation_reason': calculation_reason,
            'vat_applicable': True,
            'prices_include_vat': prices_include_vat
        })

        return result

    # =====================
    # 4. DOCUMENT TOTALS CALCULATION
    # =====================
    @classmethod
    def recalculate_document_totals(cls, document) -> Dict:
        """
        🎯 CORE METHOD: Преизчислява всички totals от линиите
        """
        if not hasattr(document, 'lines'):
            return cls._empty_totals()

        lines = document.lines.all()
        if not lines.exists():
            return cls._empty_totals()

        # Calculate totals from lines
        subtotal = sum(getattr(line, 'net_amount', Decimal('0')) for line in lines)
        discount_total = sum(getattr(line, 'discount_amount', Decimal('0')) for line in lines)
        vat_total = sum(getattr(line, 'vat_amount', Decimal('0')) for line in lines)
        total = subtotal + vat_total

        total_items = sum(cls._get_line_quantity(line) for line in lines)

        return {
            'lines_count': lines.count(),
            'total_items': total_items,
            'subtotal': cls._round_currency(subtotal),
            'discount_total': cls._round_currency(discount_total),
            'vat_total': cls._round_currency(vat_total),
            'total': cls._round_currency(total),
            'average_line_value': cls._round_currency(subtotal / lines.count()) if lines.count() > 0 else Decimal(
                '0.00'),
            'vat_breakdown': cls.get_vat_breakdown_summary(document)
        }

    # =====================
    # 5. VAT BREAKDOWN & REPORTING
    # =====================
    @classmethod
    def get_vat_breakdown_summary(cls, document) -> Dict:
        """VAT breakdown by rate"""
        if not hasattr(document, 'lines'):
            return {}

        breakdown = {}
        for line in document.lines.all():
            vat_rate = getattr(line, 'vat_rate', Decimal('0'))
            rate_key = f"{vat_rate}%"

            if rate_key not in breakdown:
                breakdown[rate_key] = {
                    'vat_rate': vat_rate,
                    'net_amount': Decimal('0.00'),
                    'vat_amount': Decimal('0.00'),
                    'gross_amount': Decimal('0.00'),
                    'lines_count': 0
                }

            breakdown[rate_key]['net_amount'] += getattr(line, 'net_amount', Decimal('0'))
            breakdown[rate_key]['vat_amount'] += getattr(line, 'vat_amount', Decimal('0'))
            breakdown[rate_key]['gross_amount'] += getattr(line, 'gross_amount', Decimal('0'))
            breakdown[rate_key]['lines_count'] += 1

        return breakdown

    # =====================
    # 6. VALIDATION & CONSISTENCY
    # =====================
    @classmethod
    def validate_vat_consistency(cls, document) -> Tuple[bool, str]:
        """Валидира VAT consistency на документ"""
        try:
            # Recalculate and compare
            calculated_totals = cls.recalculate_document_totals(document)

            # Compare with stored values
            tolerance = Decimal('0.01')  # 1 стотинка tolerance

            stored_total = getattr(document, 'total', Decimal('0'))
            calculated_total = calculated_totals['total']

            if abs(stored_total - calculated_total) > tolerance:
                return False, f"Total mismatch: stored={stored_total}, calculated={calculated_total}"

            return True, "VAT calculations are consistent"

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    # =====================
    # 7. CURRENCY OPERATIONS (ex-CurrencyService)
    # =====================
    @classmethod
    def get_base_currency(cls):
        """Връща базовата валута (cached)"""
        cache_key = 'base_currency'
        base_currency = cache.get(cache_key)

        if not base_currency:
            try:
                from nomenclatures.models import Currency
                base_currency = Currency.objects.get(is_base=True)
                cache.set(cache_key, base_currency, cls.CACHE_TIMEOUT)
            except:
                base_currency = None

        return base_currency

    @classmethod
    def convert_amount(
            cls,
            amount: Decimal,
            from_currency_code: str,
            to_currency_code: str,
            conversion_date: Optional[date] = None
    ) -> Decimal:
        """Currency conversion"""
        if from_currency_code == to_currency_code:
            return amount

        # Implementation would go here
        # For now, return amount (no conversion)
        logger.warning(f"Currency conversion not implemented: {from_currency_code} -> {to_currency_code}")
        return amount

    # =====================
    # 8. INTEGRATION OPERATIONS (ex-VATIntegrationService)
    # =====================
    @classmethod
    def process_document_vat_setup(
            cls,
            document,
            force_recalculation: bool = False
    ) -> Dict:
        """Process VAT setup for document and all lines"""
        results = {
            'success': False,
            'document_processed': False,
            'lines_processed': 0,
            'lines_with_errors': 0,
            'errors': []
        }

        try:
            # Process lines
            if hasattr(document, 'lines'):
                for line in document.lines.all():
                    try:
                        # Check if line needs processing
                        needs_processing = (
                                force_recalculation or
                                not getattr(line, 'unit_price', None) or
                                not getattr(line, 'vat_amount', None)
                        )

                        if needs_processing:
                            # Get entered price
                            entered_price = (
                                    getattr(line, 'entered_price', None) or
                                    getattr(line, 'estimated_price', None) or
                                    Decimal('0')
                            )

                            if entered_price > 0:
                                # Calculate using our service
                                calc_result = cls.calculate_line_totals(line, entered_price)

                                # Apply results to line
                                for field, value in calc_result.items():
                                    if hasattr(line, field) and field not in ['calculation_reason', 'vat_applicable',
                                                                              'prices_include_vat']:
                                        setattr(line, field, value)

                                line.save()

                        results['lines_processed'] += 1

                    except Exception as e:
                        results['lines_with_errors'] += 1
                        results['errors'].append(f"Line {line.pk}: {str(e)}")

            # Recalculate document totals
            if hasattr(document, 'recalculate_totals'):
                document.recalculate_totals()
                results['document_processed'] = True

            results['success'] = results['lines_with_errors'] == 0

        except Exception as e:
            results['errors'].append(f"Document processing error: {str(e)}")

        return results

    # =====================
    # 9. HELPER METHODS
    # =====================
    @classmethod
    def _get_line_quantity(cls, line) -> Decimal:
        """Get quantity from line"""
        if hasattr(line, 'requested_quantity') and line.requested_quantity:
            return line.requested_quantity
        elif hasattr(line, 'ordered_quantity') and line.ordered_quantity:
            return line.ordered_quantity
        elif hasattr(line, 'received_quantity') and line.received_quantity:
            return line.received_quantity
        elif hasattr(line, 'quantity') and line.quantity:
            return line.quantity
        else:
            return Decimal('1')

    @classmethod
    def _is_company_vat_registered(cls) -> bool:
        """Check if company is VAT registered"""
        try:
            from core.services.company_service import CompanyService
            return CompanyService.is_vat_applicable()
        except:
            return True  # Default to VAT applicable

    @classmethod
    def _calculate_effective_cost(cls, unit_price: Decimal, gross_amount: Decimal, quantity: Decimal) -> Decimal:
        """Calculate effective cost for inventory"""
        if cls._is_company_vat_registered():
            return unit_price  # VAT registered → use net price
        else:
            return gross_amount / quantity if quantity else gross_amount  # Non-VAT → use gross

    @classmethod
    def _round_currency(cls, amount: Decimal) -> Decimal:
        """Round to 2 decimal places"""
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @classmethod
    def _empty_totals(cls) -> Dict:
        """Empty totals structure"""
        return {
            'lines_count': 0,
            'total_items': Decimal('0'),
            'subtotal': Decimal('0.00'),
            'discount_total': Decimal('0.00'),
            'vat_total': Decimal('0.00'),
            'total': Decimal('0.00'),
            'average_line_value': Decimal('0.00'),
            'vat_breakdown': {}
        }

    # =====================
    # 10. PUBLIC API METHODS
    # =====================
    @classmethod
    def process_line(cls, line, entered_price: Decimal, save: bool = True) -> Dict:
        """
        🎯 PUBLIC API: Process a single line with VAT calculation

        Usage:
            result = VATCalculationService.process_line(line, Decimal('10.00'))
        """
        calc_result = cls.calculate_line_totals(line, entered_price)

        if save:
            # Apply calculated values to line
            for field, value in calc_result.items():
                if hasattr(line, field) and field not in ['calculation_reason', 'vat_applicable', 'prices_include_vat']:
                    setattr(line, field, value)
            line.save()

        return calc_result

    @classmethod
    def recalculate_document(cls, document, save: bool = True) -> Dict:
        """
        🎯 PUBLIC API: Recalculate entire document

        Usage:
            totals = VATCalculationService.recalculate_document(purchase_request)
        """
        totals = cls.recalculate_document_totals(document)

        if save and hasattr(document, 'recalculate_totals'):
            document.recalculate_totals()

        return totals