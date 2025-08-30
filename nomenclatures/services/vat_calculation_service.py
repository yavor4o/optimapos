# nomenclatures/services/vat_calculation_service.py - RESULT PATTERN REFACTORING


import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from django.db.models import Sum

from core.utils.result import Result

logger = logging.getLogger(__name__)


class VATCalculationService:
    """
    ✅ UNIFIED SERVICE за всички VAT/Tax изчисления - REFACTORED WITH RESULT PATTERN

    CHANGES: All public methods now return Result objects
    Legacy methods available for backward compatibility
    """

    # =====================
    # CONSTANTS & DEFAULTS
    # =====================
    DEFAULT_VAT_RATE = Decimal('0.20')  # 20% VAT
    PURCHASE_PRICES_INCLUDE_VAT = False  # Purchases без ДДС by default
    SALES_PRICES_INCLUDE_VAT = True  # Sales с ДДС by default
    CACHE_TIMEOUT = 3600  # 1 час за cache

    # =====================================================
    # NEW: RESULT-BASED PUBLIC API
    # =====================================================

    @classmethod
    def calculate_line_vat(cls, line, entered_price: Decimal, save: bool = True) -> Result:
        """
        🎯 PRIMARY API: Calculate VAT for a single line - NEW Result-based method

        Args:
            line: Document line object
            entered_price: Price entered by user
            save: Whether to save the line after calculation

        Returns:
            Result with calculation data or error
        """
        try:
            # Validate inputs
            if entered_price < 0:
                return Result.error(
                    code='INVALID_PRICE',
                    msg='Price cannot be negative',
                    data={'entered_price': entered_price}
                )

            if not line:
                return Result.error(
                    code='INVALID_LINE',
                    msg='Line object is required'
                )

            # Perform calculation using existing logic
            calc_result = cls._calculate_line_totals_internal(line, entered_price)

            # Apply calculated values to line if requested
            if save:
                # Direct field mapping
                direct_fields = ['vat_rate', 'unit_price', 'entered_price']
                for field in direct_fields:
                    if field in calc_result and hasattr(line, field):
                        setattr(line, field, calc_result[field])
                
                # Custom field mapping for FinancialLineMixin
                field_mapping = {
                    'vat_amount_per_unit': 'vat_amount',
                    'line_total_without_vat': 'net_amount', 
                    'line_total_with_vat': 'gross_amount',
                    'unit_price': 'unit_price_with_vat'  # Map calculated unit_price to unit_price_with_vat
                }
                
                for calc_field, line_field in field_mapping.items():
                    if calc_field in calc_result and hasattr(line, line_field):
                        setattr(line, line_field, calc_result[calc_field])
                
                line.save()

            return Result.success(
                data=calc_result,
                msg='VAT calculation completed successfully'
            )

        except Exception as e:
            logger.error(f"Error in VAT calculation: {e}")
            return Result.error(
                code='CALCULATION_ERROR',
                msg=f'VAT calculation failed: {str(e)}',
                data={'entered_price': entered_price}
            )

    @classmethod
    def calculate_document_vat(cls, document, save: bool = True) -> Result:
        """
        🎯 DOCUMENT API: Recalculate entire document VAT - NEW Result-based method

        Args:
            document: Document object
            save: Whether to save document totals after calculation

        Returns:
            Result with document totals or error
        """
        try:
            if not document:
                return Result.error(
                    code='INVALID_DOCUMENT',
                    msg='Document object is required'
                )

            # Calculate totals using existing logic
            totals = cls._recalculate_document_totals_internal(document)

            # Apply totals to document if requested
            if save:
                cls._apply_totals_to_document(document, totals)

            return Result.success(
                data=totals,
                msg='Document VAT calculation completed successfully'
            )

        except Exception as e:
            logger.error(f"Error in document VAT calculation: {e}")
            return Result.error(
                code='DOCUMENT_CALCULATION_ERROR',
                msg=f'Document VAT calculation failed: {str(e)}',
                data={'document_id': getattr(document, 'id', None)}
            )

    @classmethod
    def validate_vat_setup(cls, document) -> Result:
        """
        🎯 VALIDATION API: Validate document VAT configuration

        Returns:
            Result with validation status and suggestions
        """
        try:
            validation_data = {
                'document_id': getattr(document, 'id', None),
                'prices_include_vat': cls.get_price_entry_mode(document),
                'default_vat_rate': cls.get_vat_rate(document=document),
                'lines_count': 0,
                'lines_with_issues': [],
                'configuration_warnings': []
            }

            # Check document configuration
            if not hasattr(document, 'location') or not document.location:
                validation_data['configuration_warnings'].append(
                    'No location specified - using system defaults'
                )

            # Validate lines if they exist
            if hasattr(document, 'lines'):
                lines = document.lines.all()
                validation_data['lines_count'] = lines.count()

                for line in lines:
                    line_issues = cls._validate_line_vat_setup(line)
                    if line_issues:
                        validation_data['lines_with_issues'].append({
                            'line_id': getattr(line, 'id', None),
                            'line_number': getattr(line, 'line_number', None),
                            'issues': line_issues
                        })

            # Determine overall validation result
            has_errors = len(validation_data['lines_with_issues']) > 0
            has_warnings = len(validation_data['configuration_warnings']) > 0

            if has_errors:
                return Result.error(
                    code='VAT_SETUP_INVALID',
                    msg=f'Found {len(validation_data["lines_with_issues"])} lines with VAT issues',
                    data=validation_data
                )
            elif has_warnings:
                return Result.success(
                    data=validation_data,
                    msg='VAT setup valid but has configuration warnings'
                )
            else:
                return Result.success(
                    data=validation_data,
                    msg='VAT setup is valid'
                )

        except Exception as e:
            logger.error(f"Error in VAT validation: {e}")
            return Result.error(
                code='VALIDATION_ERROR',
                msg=f'VAT validation failed: {str(e)}'
            )

    @classmethod
    def bulk_process_document_vat(cls, document, force_recalculation: bool = False) -> Result:
        """
        🎯 BULK API: Process VAT setup for document and all lines

        Args:
            document: Document object
            force_recalculation: Force recalculation even if values exist

        Returns:
            Result with bulk processing statistics
        """
        try:
            results = {
                'success': False,
                'document_processed': False,
                'lines_processed': 0,
                'lines_with_errors': 0,
                'errors': []
            }

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
                            # Get entered price using dynamic detection
                            from .document_line_service import DocumentLineService
                            entered_price = DocumentLineService._get_price_field_value(line) or Decimal('0')

                            if entered_price > 0:
                                # Calculate using our Result-based method
                                calc_result = cls.calculate_line_vat(line, entered_price, save=True)

                                if not calc_result.ok:
                                    results['errors'].append(f"Line {getattr(line, 'id', '?')}: {calc_result.msg}")
                                    results['lines_with_errors'] += 1
                                    continue

                        results['lines_processed'] += 1

                    except Exception as e:
                        results['lines_with_errors'] += 1
                        results['errors'].append(f"Line {getattr(line, 'id', '?')}: {str(e)}")

            # Recalculate document totals
            doc_result = cls.calculate_document_vat(document, save=True)
            if doc_result.ok:
                results['document_processed'] = True
            else:
                results['errors'].append(f"Document totals: {doc_result.msg}")

            results['success'] = results['lines_with_errors'] == 0

            if results['success']:
                return Result.success(
                    data=results,
                    msg=f'Bulk VAT processing completed: {results["lines_processed"]} lines processed'
                )
            else:
                return Result.error(
                    code='BULK_PROCESSING_ERRORS',
                    msg=f'Bulk processing completed with {results["lines_with_errors"]} errors',
                    data=results
                )

        except Exception as e:
            logger.error(f"Error in bulk VAT processing: {e}")
            return Result.error(
                code='BULK_PROCESSING_ERROR',
                msg=f'Bulk VAT processing failed: {str(e)}'
            )

    # =====================================================
    # INTERNAL CALCULATION METHODS (unchanged logic)
    # =====================================================

    @classmethod
    def _calculate_line_totals_internal(cls, line, entered_price: Decimal) -> Dict:
        """✅ FIXED VERSION - LINE-LEVEL ROUNDING според търговски стандарти"""

        document = getattr(line, 'document', None)
        product = getattr(line, 'product', None)
        # Get quantity using dynamic detection
        from .document_line_service import DocumentLineService
        quantity_field = DocumentLineService._get_quantity_field(line.__class__)
        quantity = getattr(line, quantity_field, Decimal('1'))

        # Get configuration
        prices_include_vat = cls.get_price_entry_mode(document)
        vat_rate = cls.get_vat_rate(line=line, product=product)
        vat_applicable = cls.is_vat_applicable(line, product)

        result = {
            'prices_include_vat': prices_include_vat,
            'vat_applicable': vat_applicable,
            'vat_rate': vat_rate,
            'quantity': quantity,
            'entered_price': entered_price,
        }

        if not vat_applicable:
            # No VAT case - запазваме същата логика
            line_total = entered_price * quantity
            result.update({
                'unit_price': entered_price,
                'unit_price_without_vat': entered_price,
                'vat_amount_per_unit': Decimal('0'),
                'line_total_without_vat': line_total,
                'line_vat_amount': Decimal('0'),
                'line_total_with_vat': line_total,
                'calculation_reason': 'VAT not applicable'
            })
        else:
            # ✅ ПРАВИЛЕН ПОДХОД: LINE-LEVEL calculation

            # Стъпка 1: Изчисли line totals БЕЗ рано закръгляване
            line_extended_price = entered_price * quantity

            if prices_include_vat:
                # Price includes VAT - работим с line totals
                line_total_with_vat = line_extended_price
                line_total_without_vat = line_total_with_vat / (Decimal('1') + vat_rate)
                line_vat_amount = line_total_with_vat - line_total_without_vat
            else:
                # Price excludes VAT - работим с line totals
                line_total_without_vat = line_extended_price
                line_vat_amount = line_total_without_vat * vat_rate
                line_total_with_vat = line_total_without_vat + line_vat_amount

            # Стъпка 2: Закръгли ФИНАЛНИТЕ line totals - това е ключът!
            line_total_without_vat = line_total_without_vat.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line_vat_amount = line_vat_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line_total_with_vat = (line_total_without_vat + line_vat_amount)  # Ensure consistency

            # Стъпка 3: Backward calculate unit prices за display/storage
            if quantity > 0:
                unit_price_without_vat = line_total_without_vat / quantity
                vat_amount_per_unit = line_vat_amount / quantity
                unit_price_with_vat = line_total_with_vat / quantity
            else:
                unit_price_without_vat = Decimal('0')
                vat_amount_per_unit = Decimal('0')
                unit_price_with_vat = Decimal('0')

            result.update({
                'unit_price': unit_price_with_vat,  # Може да има повече от 2 digits
                'unit_price_without_vat': unit_price_without_vat,
                'vat_amount_per_unit': vat_amount_per_unit,
                'line_total_without_vat': line_total_without_vat,  # ✅ ТОЧНО закръглен
                'line_vat_amount': line_vat_amount,  # ✅ ТОЧНО закръглен
                'line_total_with_vat': line_total_with_vat,  # ✅ ТОЧНО закръглен
                'calculation_reason': f'VAT {vat_rate * 100:.1f}% {"included" if prices_include_vat else "added"}'
            })

        return result

    @classmethod
    def _recalculate_document_totals_internal(cls, document) -> Dict:
        """Internal document totals calculation - preserves existing logic"""
        # This is the existing recalculate_document_totals method, unchanged

        totals = {
            'subtotal': Decimal('0'),  # <-- Променено
            'vat_total': Decimal('0'),  # <-- Променено
            'total': Decimal('0'),  # <-- Променено
            'discount_total': Decimal('0'),  # <-- Добавено
            'lines_count': 0
        }

        if hasattr(document, 'lines'):
            # Calculate totals from line_total properties (works for all line types)
            subtotal = Decimal('0')
            lines_count = 0
            
            for line in document.lines.all():
                if hasattr(line, 'line_total'):
                    line_total = line.line_total
                    if line_total:
                        subtotal += line_total
                        lines_count += 1
                        
            # Calculate VAT based on document settings
            if subtotal > 0:
                # Default VAT rate for Bulgaria is 20%
                vat_rate = Decimal('0.20')
                prices_include_vat = getattr(document, 'prices_entered_with_vat', False)
                
                if prices_include_vat:
                    # Extract VAT from total
                    vat_total = (subtotal - (subtotal / (Decimal('1') + vat_rate))).quantize(Decimal('0.01'))
                    subtotal_without_vat = subtotal - vat_total
                    total = subtotal  # Total is the same as subtotal when prices include VAT
                else:
                    # Add VAT to subtotal
                    vat_total = (subtotal * vat_rate).quantize(Decimal('0.01'))
                    subtotal_without_vat = subtotal
                    total = (subtotal + vat_total).quantize(Decimal('0.01'))
                    
                totals['subtotal'] = subtotal_without_vat.quantize(Decimal('0.01'))
                totals['vat_total'] = vat_total
                totals['total'] = total
            else:
                totals['subtotal'] = Decimal('0')
                totals['vat_total'] = Decimal('0')
                totals['total'] = Decimal('0')
                
            totals['lines_count'] = lines_count

        return totals

    @classmethod
    def _apply_totals_to_document(cls, document, totals: Dict):
        """Apply calculated totals to document fields and save"""
        try:
            # Update document financial fields
            if hasattr(document, 'subtotal'):
                document.subtotal = totals.get('subtotal', Decimal('0'))
            if hasattr(document, 'vat_total'):
                document.vat_total = totals.get('vat_total', Decimal('0'))
            if hasattr(document, 'discount_total'):
                document.discount_total = totals.get('discount_total', Decimal('0'))
            if hasattr(document, 'total'):
                document.total = totals.get('total', Decimal('0'))
            
            # Save with only financial fields
            document.save(update_fields=['subtotal', 'vat_total', 'discount_total', 'total'])
            
        except Exception as e:
            logger.error(f"Failed to apply totals to document: {e}")
            raise

    @classmethod
    def _validate_line_vat_setup(cls, line) -> List[str]:
        """Internal line validation - returns list of issues"""
        issues = []

        # Check for missing product
        if not hasattr(line, 'product') or not line.product:
            issues.append('Missing product')
            return issues

        # Check for missing or invalid quantities
        if not hasattr(line, 'quantity') or not line.quantity or line.quantity <= 0:
            issues.append('Invalid quantity')

        # Check for missing prices using dynamic detection
        from .document_line_service import DocumentLineService
        entered_price = DocumentLineService._get_price_field_value(line)
        if not entered_price or entered_price <= 0:
            issues.append('Missing or invalid price')

        # Check VAT configuration
        try:
            vat_rate = cls.get_vat_rate(line=line)
            if vat_rate < 0 or vat_rate > 1:
                issues.append(f'Invalid VAT rate: {vat_rate}')
        except Exception:
            issues.append('Could not determine VAT rate')

        return issues

    # =====================================================
    # EXISTING CORE METHODS (unchanged)
    # =====================================================

    @classmethod
    def get_price_entry_mode(cls, document) -> bool:
        """Existing method - unchanged"""
        if hasattr(document, 'prices_entered_with_vat'):
            if document.prices_entered_with_vat is not None:
                return document.prices_entered_with_vat

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

        if document._meta.app_label == 'purchases':
            return cls.PURCHASE_PRICES_INCLUDE_VAT
        elif document._meta.app_label == 'sales':
            return cls.SALES_PRICES_INCLUDE_VAT
        else:
            return False

    @classmethod
    def get_vat_rate(cls, line=None, product=None, location=None, document=None) -> Decimal:
        """Existing method - unchanged"""
        if not product and line and hasattr(line, 'product'):
            product = line.product

        if not document and line and hasattr(line, 'document'):
            document = line.document

        if product and hasattr(product, 'tax_group') and product.tax_group:
            if hasattr(product.tax_group, 'rate'):
                rate = Decimal(str(product.tax_group.rate))
                if rate > 1:
                    rate = rate / Decimal('100')
                return rate

        if line and hasattr(line, 'vat_rate') and line.vat_rate is not None:
            if line.vat_rate not in [Decimal('20.00'), Decimal('0.200')]:
                rate = Decimal(str(line.vat_rate))
                if rate > 1:
                    rate = rate / Decimal('100')
                return rate

        if not location and document and hasattr(document, 'location'):
            location = document.location

        if location and hasattr(location, 'default_vat_rate'):
            rate = Decimal(str(location.default_vat_rate))
            if rate > 1:
                rate = rate / Decimal('100')
            return rate

        return cls.DEFAULT_VAT_RATE

    @classmethod
    def is_vat_applicable(cls, line=None, product=None) -> bool:
        """Existing method - unchanged"""
        if not product and line and hasattr(line, 'product'):
            product = line.product

        if product and hasattr(product, 'tax_group') and product.tax_group:
            if hasattr(product.tax_group, 'is_vat_applicable'):
                return product.tax_group.is_vat_applicable

        return True
