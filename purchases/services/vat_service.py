# purchases/services/vat_service.py
from typing import Dict, Optional
from decimal import Decimal
from django.core.exceptions import ValidationError


class SmartVATService:
    """
    Service for smart VAT calculations and price processing
    """

    @staticmethod
    def calculate_line_vat(
            line,
            entered_price: Decimal,
            document
    ) -> Dict:
        """
        Calculate VAT for a document line with full context

        Args:
            line: Document line instance
            entered_price: Price as entered by user
            document: Parent document instance

        Returns:
            Dict: Complete VAT calculation results
        """
        from core.services.company_service import CompanyService

        result = {
            'entered_price': entered_price,
            'unit_price': entered_price,
            'vat_rate': Decimal('0.00'),
            'vat_amount': Decimal('0.00'),
            'net_amount': Decimal('0.00'),
            'gross_amount': entered_price,
            'effective_cost': entered_price,
            'calculation_reason': '',
            'vat_applicable': False
        }

        # STEP 1: Company VAT registration check
        if not CompanyService.is_vat_applicable():
            result.update({
                'calculation_reason': 'Company not VAT registered',
                'vat_applicable': False
            })
            return result

        # STEP 2: Product VAT rate
        vat_rate = SmartVATService._get_product_vat_rate(line)

        if vat_rate == 0:
            result.update({
                'vat_rate': Decimal('0.00'),
                'calculation_reason': 'Product is VAT exempt (0% rate)',
                'vat_applicable': False
            })
            return result

        # STEP 3: Price entry mode processing
        prices_include_vat = document.get_price_entry_mode()
        quantity = getattr(line, 'get_quantity', lambda: Decimal('1'))()

        if prices_include_vat:
            # Entered price includes VAT → extract it
            vat_multiplier = 1 + (vat_rate / 100)
            unit_price = entered_price / vat_multiplier
            calculation_reason = f'Extracted VAT ({vat_rate}%) from entered price'
        else:
            # Entered price excludes VAT → use directly
            unit_price = entered_price
            calculation_reason = f'Added VAT ({vat_rate}%) to entered price'

        # STEP 4: Calculate all amounts
        gross_amount_excl_vat = quantity * unit_price
        discount_amount = gross_amount_excl_vat * (getattr(line, 'discount_percent', Decimal('0')) / 100)
        net_amount = gross_amount_excl_vat - discount_amount
        vat_amount = net_amount * (vat_rate / 100)
        gross_amount = net_amount + vat_amount

        # STEP 5: Determine effective cost
        effective_cost = unit_price if CompanyService.is_vat_applicable() else (gross_amount / quantity)

        result.update({
            'unit_price': unit_price,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'net_amount': net_amount,
            'gross_amount': gross_amount,
            'effective_cost': effective_cost,
            'calculation_reason': calculation_reason,
            'vat_applicable': True,
            'prices_include_vat': prices_include_vat
        })

        return result

    @staticmethod
    def get_effective_cost(
            line,
            company_vat_status: Optional[bool] = None
    ) -> Decimal:
        """
        Get effective cost for inventory calculations

        Args:
            line: Document line instance
            company_vat_status: Override company VAT status

        Returns:
            Decimal: Effective cost amount
        """
        if company_vat_status is None:
            from core.services.company_service import CompanyService
            company_vat_status = CompanyService.is_vat_applicable()

        if company_vat_status:
            # VAT registered company → use unit price (excluding VAT)
            return getattr(line, 'unit_price', Decimal('0'))
        else:
            # Non-VAT company → use gross amount (including VAT)
            quantity = getattr(line, 'get_quantity', lambda: Decimal('1'))()
            gross_amount = getattr(line, 'gross_amount', Decimal('0'))
            return gross_amount / quantity if quantity else gross_amount

    @staticmethod
    def _get_product_vat_rate(line) -> Decimal:
        """
        Get VAT rate from product tax group

        Args:
            line: Document line instance

        Returns:
            Decimal: VAT rate percentage
        """
        if not hasattr(line, 'product') or not line.product:
            from core.services.company_service import CompanyService
            return CompanyService.get_default_vat_rate()

        if hasattr(line.product, 'tax_group') and line.product.tax_group:
            return line.product.tax_group.rate

        # Fallback to company default
        from core.services.company_service import CompanyService
        return CompanyService.get_default_vat_rate()

    @staticmethod
    def get_vat_breakdown_summary(document) -> Dict:
        """
        Get VAT breakdown summary for entire document

        Args:
            document: Document instance with lines

        Returns:
            Dict: VAT breakdown by rate
        """
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

    @staticmethod
    def calculate_document_totals(document) -> Dict:
        """
        Calculate accurate document totals using new VAT-aware fields

        Args:
            document: Document instance with lines

        Returns:
            Dict: Complete financial totals
        """
        if not hasattr(document, 'lines'):
            return {
                'subtotal': Decimal('0.00'),
                'vat_total': Decimal('0.00'),
                'total': Decimal('0.00'),
                'lines_count': 0
            }

        lines = document.lines.all()

        # Use NEW fields for accurate calculations
        subtotal = sum(getattr(line, 'net_amount', Decimal('0')) for line in lines)
        discount_total = sum(getattr(line, 'discount_amount', Decimal('0')) for line in lines)
        vat_total = sum(getattr(line, 'vat_amount', Decimal('0')) for line in lines)
        total = subtotal + vat_total

        total_items = sum(getattr(line, 'get_quantity', lambda: Decimal('0'))() for line in lines)

        return {
            'lines_count': lines.count(),
            'total_items': total_items,
            'subtotal': subtotal,  # БЕЗ ДДС
            'discount_total': discount_total,
            'vat_total': vat_total,  # Само ДДС
            'total': total,  # С ДДС
            'average_line_value': (subtotal / lines.count()) if lines.count() > 0 else Decimal('0.00'),
            'vat_breakdown': SmartVATService.get_vat_breakdown_summary(document)
        }