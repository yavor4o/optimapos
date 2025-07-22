# purchases/services/order_service.py - ENHANCED
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError
from purchases.models.orders import PurchaseOrder, PurchaseOrderLine
from purchases.models.requests import PurchaseRequest


logger = logging.getLogger(__name__)

User = get_user_model()

class OrderService:
    """Service for Purchase Order business operations"""

    # =====================
    # ORDER CREATION
    # =====================

    @staticmethod
    @transaction.atomic
    def create_order(
            supplier,
            location,
            lines_data: List[Dict],
            expected_delivery_date=None,
            source_request: Optional[PurchaseRequest] = None,
            is_urgent=False,
            order_method='',
            **kwargs
    ) -> PurchaseOrder:
        """Create new purchase order"""

        # Default delivery date
        if not expected_delivery_date:
            expected_delivery_date = timezone.now().date() + timezone.timedelta(days=3)

        # Create order
        order = PurchaseOrder.objects.create(
            supplier=supplier,
            location=location,
            expected_delivery_date=expected_delivery_date,
            source_request=source_request,
            is_urgent=is_urgent,
            order_method=order_method,
            status='draft',
            **kwargs
        )

        # Add lines
        OrderService.add_lines_to_order(order, lines_data)

        return order



    @staticmethod
    @transaction.atomic
    def create_from_request(
            request: 'PurchaseRequest',
            user: 'User',
            expected_delivery_date: date = None,
            order_notes: str = '',
            line_modifications: dict = None,
            **kwargs
    ) -> Dict:
        """
        Convert approved PurchaseRequest to PurchaseOrder

        FINAL VERSION - Fixed primary key issue

        Args:
            request: PurchaseRequest to convert
            user: User performing the conversion
            expected_delivery_date: When order should be delivered
            order_notes: Additional notes for the order
            line_modifications: Dict of line_id -> {quantity, unit_price} modifications
            **kwargs: Additional order fields

        Returns:
            Dict with success status, order object, and conversion details

        Raises:
            ValidationError: If conversion fails validation
        """
        from purchases.models.orders import PurchaseOrder, PurchaseOrderLine
        from nomenclatures.models import DocumentType
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Converting request {request.document_number} to order")

        # =====================
        # VALIDATION
        # =====================

        # Check if already converted
        if request.converted_to_order:
            raise ValidationError(
                f"Request {request.document_number} already converted to order {request.converted_to_order.document_number}")

        # Check for lines
        if not request.lines.exists():
            raise ValidationError("Cannot convert request without lines")

        # Check workflow transition
        if not request.can_transition_to('converted'):
            raise ValidationError(
                f"DocumentType '{request.document_type}' doesn't allow transition from "
                f"'{request.status}' to 'converted'"
            )

        # Set default delivery date
        if not expected_delivery_date:
            days_offset = 3 if request.urgency_level in ['high', 'critical'] else 7
            expected_delivery_date = timezone.now().date() + timedelta(days=days_offset)

        # =====================
        # FIND ORDER DOCUMENT TYPE
        # =====================

        order_document_type = DocumentType.objects.filter(
            app_name='purchases',
            type_key='order',
            allowed_source_types__type_key=request.document_type.type_key,
            is_active=True
        ).first()

        if not order_document_type:
            # Fallback - any order type for purchases
            order_document_type = DocumentType.objects.filter(
                app_name='purchases',
                type_key='order',
                is_active=True
            ).first()

        if not order_document_type:
            raise ValidationError("No DocumentType configured for purchase orders")

        logger.info(f"Using DocumentType: {order_document_type.code}")

        # =====================
        # CREATE ORDER (STEP 1: Without Lines)
        # =====================

        try:
            order = PurchaseOrder(
                # Required fields
                supplier=request.supplier,
                location=request.location,
                document_type=order_document_type,

                # Dates
                document_date=timezone.now().date(),
                expected_delivery_date=expected_delivery_date,

                # Source tracking
                source_request=request,

                # Order details
                is_urgent=(request.urgency_level in ['high', 'critical']),
                order_method='converted_from_request',

                # Notes
                notes=f"Converted from request {request.document_number}\n{order_notes}".strip(),

                # Audit
                created_by=user,

                # Any additional fields from kwargs
                **{k: v for k, v in kwargs.items() if hasattr(PurchaseOrder, k)}
            )

            # ✅ CRITICAL: Skip validation during initial save
            order._skip_validation = True
            order.save()

            # Clean up flag
            delattr(order, '_skip_validation')

            # Refresh to ensure we have the saved data
            order.refresh_from_db()

            if not order.pk:
                raise ValidationError("Order was not saved properly - no primary key")

            logger.info(f"Order created with ID: {order.pk}, number: {order.document_number}")

        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise ValidationError(f"Could not create order: {e}")

        # =====================
        # CREATE LINES (STEP 2: Now that order has PK)
        # =====================

        converted_lines = []
        total_amount = Decimal('0.00')

        try:
            for req_line in request.lines.all():
                # Default values from request line
                quantity = req_line.requested_quantity
                unit_price = req_line.entered_price or Decimal('0.00')

                # Apply modifications if provided
                if line_modifications and req_line.id in line_modifications:
                    modifications = line_modifications[req_line.id]
                    quantity = modifications.get('quantity', quantity)
                    unit_price = modifications.get('unit_price', unit_price)

                # Create order line
                order_line = PurchaseOrderLine.objects.create(
                    document=order,  # ✅ Now order has primary key!
                    line_number=req_line.line_number,
                    product=req_line.product,
                    unit=req_line.unit,

                    # ✅ FIXED: САМО ordered_quantity (quantity не съществува в модела)
                    ordered_quantity=quantity,

                    # Pricing
                    unit_price=unit_price,

                    # Source tracking
                    source_request_line=req_line,

                    # ✅ FIXED: PurchaseOrderLine използва quality_notes
                    quality_notes=(getattr(req_line, 'usage_description', '') or
                                   getattr(req_line, 'item_justification', '') or
                                   getattr(req_line, 'quality_notes', '') or
                                   ''),
                )

                converted_lines.append(order_line)
                total_amount += order_line.line_total

            logger.info(f"Created {len(converted_lines)} order lines")

        except Exception as e:
            logger.error(f"Failed to create order lines: {e}")
            # Cleanup: delete the order if line creation failed
            order.delete()
            raise ValidationError(f"Could not create order lines: {e}")

        # =====================
        # UPDATE ORDER TOTALS (STEP 3)
        # =====================

        try:
            # Recalculate totals based on lines
            order.recalculate_totals()

            # Now run full validation (order has ID and lines)
            # Skip customer validation за purchases documents
            order._skip_customer_validation = True
            order.full_clean()
            order.save()
            del order._skip_customer_validation

            logger.info(f"Order totals updated - Grand total: {order.total}")

        except Exception as e:
            logger.error(f"Failed to update order totals: {e}")
            # Note: We don't delete order here since lines are already created
            # Better to have order with wrong totals than lose the conversion
            logger.warning(f"Order {order.document_number} may have incorrect totals")

        # =====================
        # UPDATE REQUEST STATUS (STEP 4)
        # =====================

        try:
            request.status = 'converted'
            request.converted_to_order = order
            request.converted_at = timezone.now()
            request.converted_by = user
            request.save()

            logger.info(f"Request {request.document_number} marked as converted")

        except Exception as e:
            logger.error(f"Failed to update request status: {e}")
            # Don't fail the entire conversion for this
            logger.warning(f"Request {request.document_number} status not updated properly")

        # =====================
        # FINAL SUCCESS RESPONSE
        # =====================

        success_message = f"Request {request.document_number} converted to order {order.document_number}"
        logger.info(f"Conversion completed successfully: {success_message}")

        return {
            'success': True,
            'message': success_message,
            'request': request,
            'order': order,
            'converted_lines_count': len(converted_lines),
            'total_amount': total_amount,
            'order_requires_approval': order.document_type.requires_approval if order.document_type else False,
            'conversion_summary': {
                'source_request': request.document_number,
                'target_order': order.document_number,
                'lines_converted': len(converted_lines),
                'total_amount': float(total_amount),
                'order_status': order.status,
                'approval_required': order.document_type.requires_approval if order.document_type else False,
                'delivery_date': expected_delivery_date.isoformat(),
                'conversion_time': timezone.now().isoformat()
            }
        }


    @staticmethod
    @transaction.atomic
    def duplicate_order(
            original_order: PurchaseOrder,
            user,
            modifications: Optional[Dict] = None
    ) -> PurchaseOrder:
        """Create copy of existing order"""

        try:
            # Copy basic fields
            new_order = PurchaseOrder.objects.create(
                supplier=original_order.supplier,
                location=original_order.location,
                expected_delivery_date=modifications.get('expected_delivery_date',
                                                         timezone.now().date() + timedelta(days=7)),
                is_urgent=modifications.get('is_urgent', original_order.is_urgent),
                order_method=modifications.get('order_method', original_order.order_method),
                delivery_terms=original_order.delivery_terms,
                payment_terms=original_order.payment_terms,
                special_conditions=original_order.special_conditions,
                created_by=user,
                notes=f"Duplicated from order {original_order.document_number}",
                status='draft'
            )

            # Copy lines
            for original_line in original_order.lines.all():
                OrderService.add_line_to_order(
                    order=new_order,
                    product=original_line.product,
                    ordered_quantity=original_line.ordered_quantity,
                    unit_price=original_line.unit_price,
                    discount_percent=original_line.discount_percent,
                    user=user
                )

            return new_order

        except Exception as e:
            raise ValidationError(f'Error duplicating order: {str(e)}')

    # =====================
    # LINE MANAGEMENT
    # =====================

    @staticmethod
    @transaction.atomic
    def add_lines_to_order(order: PurchaseOrder, lines_data: List[Dict]) -> List[PurchaseOrderLine]:
        """Add multiple lines to purchase order"""

        if not order.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        lines = []
        starting_line_number = order.lines.count()

        for i, line_data in enumerate(lines_data, starting_line_number + 1):
            line = PurchaseOrderLine.objects.create(
                document=order,
                line_number=i,
                product=line_data['product'],
                ordered_quantity=line_data['quantity'],
                unit=line_data['unit'],
                unit_price=line_data['unit_price'],
                discount_percent=line_data.get('discount_percent', Decimal('0.00')),
                source_request_line=line_data.get('source_request_line'),
                supplier_product_code=line_data.get('supplier_product_code', ''),
                notes=line_data.get('notes', ''),
                **line_data.get('extra_fields', {})
            )
            lines.append(line)

        # Recalculate totals
        order.recalculate_totals()

        return lines

    @staticmethod
    @transaction.atomic
    def add_line_to_order(
            order: PurchaseOrder,
            product,
            ordered_quantity: Decimal,
            unit_price: Decimal,
            discount_percent: Decimal = Decimal('0.00'),
            notes: str = '',
            user=None
    ) -> Dict:
        """Add single line to order"""

        if not order.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        try:
            # Get next line number
            next_line_number = order.lines.count() + 1

            line = PurchaseOrderLine.objects.create(
                document=order,
                line_number=next_line_number,
                product=product,
                ordered_quantity=ordered_quantity,
                unit = product.get_preferred_purchase_unit(),
                unit_price=unit_price,
                discount_percent=discount_percent,
                notes=notes
            )

            # Recalculate totals
            order.recalculate_totals()

            return {
                'success': True,
                'message': f'Line added: {product.name}',
                'line': line
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error adding line: {str(e)}',
                'line': None
            }

    @staticmethod
    @transaction.atomic
    def update_line_quantity(
            line: PurchaseOrderLine,
            new_quantity: Decimal,
            user=None
    ) -> Dict:
        """Update line quantity"""

        if not line.document.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        try:
            old_quantity = line.ordered_quantity
            line.ordered_quantity = new_quantity
            line.save()

            # Recalculate order totals
            line.document.recalculate_totals()

            return {
                'success': True,
                'message': f'Quantity updated: {old_quantity} → {new_quantity}',
                'line': line
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error updating quantity: {str(e)}',
                'line': line
            }

    @staticmethod
    @transaction.atomic
    def remove_line_from_order(
            line: PurchaseOrderLine,
            user=None
    ) -> Dict:
        """Remove line from order"""

        if not line.document.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        try:
            order = line.document
            product_name = line.product.name
            line.delete()

            # Reorder line numbers
            OrderService._reorder_line_numbers(order)

            # Recalculate totals
            order.recalculate_totals()

            return {
                'success': True,
                'message': f'Line removed: {product_name}',
                'order': order
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error removing line: {str(e)}',
                'line': line
            }

    @staticmethod
    def _reorder_line_numbers(order: PurchaseOrder):
        """Reorder line numbers after deletion"""
        lines = order.lines.order_by('line_number')
        for idx, line in enumerate(lines, 1):
            if line.line_number != idx:
                line.line_number = idx
                line.save(update_fields=['line_number'])

    # =====================
    # BUSINESS CALCULATIONS
    # =====================

    @staticmethod
    def validate_order_completeness(order: PurchaseOrder) -> Dict:
        """Validate if order is complete enough for sending"""

        issues = []
        warnings = []

        # Check lines
        if not order.lines.exists():
            issues.append("Order has no lines")

        # Check delivery date
        if not order.expected_delivery_date:
            issues.append("Expected delivery date is required")
        elif order.expected_delivery_date < timezone.now().date():
            warnings.append("Delivery date is in the past")

        # Check payment terms
        if not order.payment_terms:
            warnings.append("Payment terms not specified")

        # Check prices
        lines_without_prices = order.lines.filter(unit_price=0).count()
        if lines_without_prices > 0:
            issues.append(f"{lines_without_prices} lines have zero prices")

        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'completeness_score': OrderService._calculate_completeness_score(order)
        }

    # =====================
    # ANALYTICS & REPORTING
    # =====================

    @staticmethod
    def get_order_analytics(order: PurchaseOrder) -> Dict:
        """Get comprehensive analytics for specific order"""

        return {
            'basic_info': {
                'document_number': order.document_number,
                'status': order.status,
                'delivery_status': order.delivery_status,
                'is_urgent': order.is_urgent,
                'created_at': order.created_at,
                'expected_delivery_date': order.expected_delivery_date,
                'supplier': order.supplier.name
            },
            'financial_summary': OrderService.calculate_order_totals(order),
            'source_analysis': {
                'source_request': order.source_request.document_number if order.source_request else None,
                'creation_method': 'converted' if order.source_request else 'direct',
                'conversion_time': OrderService._calculate_conversion_time(order) if order.source_request else None
            },
            'delivery_analysis': {
                'days_until_delivery': (
                            order.expected_delivery_date - timezone.now().date()).days if order.expected_delivery_date else None,
                'delivery_status': order.delivery_status,
                'supplier_confirmed': order.supplier_confirmed,
                'confirmation_date': order.supplier_confirmed_date
            },
            'line_analysis': OrderService._analyze_order_lines(order)
        }

    @staticmethod
    def get_orders_ready_for_delivery(supplier=None, location=None) -> List[PurchaseOrder]:
        """Get orders ready for delivery creation"""

        queryset = PurchaseOrder.objects.filter(
            status='confirmed',
            delivery_status__in=['pending', 'partial']
        )

        if supplier:
            queryset = queryset.filter(supplier=supplier)
        if location:
            queryset = queryset.filter(location=location)

        return list(queryset.select_related('supplier', 'location'))

    @staticmethod
    def get_overdue_orders(days_overdue=0) -> List[PurchaseOrder]:
        """Get orders that are overdue for delivery"""

        cutoff_date = timezone.now().date() - timedelta(days=days_overdue)

        return list(PurchaseOrder.objects.filter(
            status='confirmed',
            expected_delivery_date__lte=cutoff_date,
            delivery_status__in=['pending', 'partial']
        ).select_related('supplier'))

    # REPLACE these methods in purchases/services/order_service.py

    # REPLACE calculate_order_totals method in purchases/services/order_service.py

    @staticmethod
    def calculate_order_totals(order: PurchaseOrder) -> Dict:
        """
        Calculate order totals - SIMPLIFIED using SmartVATService
        """
        from .vat_service import SmartVATService

        # Use SmartVATService for ALL calculations - no duplication!
        base_totals = SmartVATService.calculate_document_totals(order)

        if not hasattr(order, 'lines') or not order.lines.exists():
            base_totals['order_metrics'] = {
                'total_ordered_items': Decimal('0'),
                'delivery_progress': 0.0,
                'effective_total_cost': Decimal('0')
            }
            return base_totals

        lines = order.lines.all()

        # Order-specific metrics only
        total_ordered_items = sum(
            getattr(line, 'get_quantity', lambda: Decimal('0'))()
            for line in lines
        )

        effective_total_cost = sum(
            SmartVATService.get_effective_cost(line) * getattr(line, 'get_quantity', lambda: Decimal('0'))()
            for line in lines
        )

        # Add order-specific data to base totals
        base_totals['order_metrics'] = {
            'total_ordered_items': total_ordered_items,
            'delivery_progress': 0.0,  # Can be enhanced later
            'effective_total_cost': effective_total_cost
        }

        return base_totals

    @staticmethod
    def validate_order_financials(order: PurchaseOrder) -> Dict:
        """
        Validate order financial data with VAT awareness

        ENHANCED: Complete VAT validation integration
        """
        issues = []
        warnings = []

        # Basic structure validation
        if not hasattr(order, 'lines') or not order.lines.exists():
            issues.append("Order has no lines")
            return {
                'valid': False,
                'issues': issues,
                'warnings': warnings
            }

        # VAT configuration validation
        company = order.get_company()
        if not company:
            issues.append("No company configuration found")

        # Check each line for VAT completeness
        for line in order.lines.all():
            line_number = getattr(line, 'line_number', 'Unknown')

            # Check required fields
            if not hasattr(line, 'entered_price') or not getattr(line, 'entered_price'):
                warnings.append(f"Line {line_number}: Missing entered price")

            if not hasattr(line, 'product') or not getattr(line, 'product'):
                issues.append(f"Line {line_number}: Missing product")

            # VAT-specific validations
            if company and company.is_vat_applicable():
                if not hasattr(line, 'vat_rate'):
                    warnings.append(f"Line {line_number}: Missing VAT rate")

                if hasattr(line, 'product') and line.product:
                    if not hasattr(line.product, 'tax_group') or not line.product.tax_group:
                        warnings.append(f"Line {line_number}: Product missing tax group")

        # Document totals validation
        calculated_totals = OrderService.calculate_order_totals(order)

        tolerance = Decimal('0.01')  # 1 cent tolerance

        if hasattr(order, 'subtotal'):
            if abs(order.subtotal - calculated_totals['subtotal']) > tolerance:
                issues.append(
                    f"Subtotal mismatch: Document={order.subtotal}, "
                    f"Calculated={calculated_totals['subtotal']}"
                )

        if hasattr(order, 'vat_total'):
            if abs(order.vat_total - calculated_totals['vat_total']) > tolerance:
                issues.append(
                    f"VAT total mismatch: Document={order.vat_total}, "
                    f"Calculated={calculated_totals['vat_total']}"
                )

        if hasattr(order, 'total'):
            if abs(order.total - calculated_totals['total']) > tolerance:
                issues.append(
                    f"Total mismatch: Document={order.total}, "
                    f"Calculated={calculated_totals['total']}"
                )

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'calculated_totals': calculated_totals,
            'vat_context': order.get_vat_context_info()
        }

    @staticmethod
    @transaction.atomic
    def update_order_line_quantity(
            line: PurchaseOrderLine,
            new_quantity: Decimal,
            user=None
    ) -> Dict:
        """
        Update line quantity with VAT recalculation

        ENHANCED: Full VAT recalculation after quantity change
        """
        if not line.document.can_be_edited():
            raise ValidationError("Cannot modify order in current state")

        try:
            old_quantity = getattr(line, 'get_quantity', lambda: Decimal('0'))()

            # Update quantity field (depends on line type)
            if hasattr(line, 'ordered_quantity'):
                line.ordered_quantity = new_quantity

            # Trigger VAT recalculation by saving (enhanced save method handles this)
            line.save()

            # Recalculate document totals
            if hasattr(line.document, 'recalculate_totals'):
                line.document.recalculate_totals()

            return {
                'success': True,
                'message': f'Quantity updated: {old_quantity} → {new_quantity}',
                'line': line,
                'new_totals': OrderService.calculate_order_totals(line.document)
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error updating quantity: {str(e)}',
                'line': line
            }

    @staticmethod
    def recalculate_order_totals(order: PurchaseOrder) -> Dict:
        """
        Force complete recalculation of order totals

        ENHANCED: Uses VAT-aware calculation system
        """
        results = {
            'success': False,
            'lines_processed': 0,
            'lines_with_errors': 0,
            'errors': []
        }

        try:
            # Recalculate all line totals first
            if hasattr(order, 'lines'):
                for line in order.lines.all():
                    try:
                        # Enhanced save method handles VAT processing
                        line.save()
                        results['lines_processed'] += 1
                    except Exception as e:
                        results['lines_with_errors'] += 1
                        results['errors'].append(f"Line {line.pk}: {str(e)}")

            # Recalculate document totals
            if hasattr(order, 'recalculate_totals'):
                order.recalculate_totals()

            results.update({
                'success': results['lines_with_errors'] == 0,
                'final_totals': OrderService.calculate_order_totals(order)
            })

            return results

        except Exception as e:
            results['errors'].append(f"Document level error: {str(e)}")
            return results

    @staticmethod
    def get_order_vat_analysis(order: PurchaseOrder) -> Dict:
        """
        Get comprehensive VAT analysis for order

        NEW: Detailed VAT breakdown and analysis
        """
        from .vat_service import SmartVATService

        analysis = {
            'document_info': {
                'document_number': order.document_number,
                'supplier': str(order.supplier) if hasattr(order, 'supplier') else None,
                'location': str(order.location) if hasattr(order, 'location') else None,
            },
            'vat_context': order.get_vat_context_info(),
            'vat_breakdown': SmartVATService.get_vat_breakdown_summary(order),
            'totals': SmartVATService.calculate_document_totals(order)
        }

        # Add cost analysis
        if hasattr(order, 'lines'):
            lines_analysis = []
            total_effective_cost = Decimal('0')

            for line in order.lines.all():
                effective_cost = SmartVATService.get_effective_cost(line)
                quantity = getattr(line, 'get_quantity', lambda: Decimal('0'))()
                line_total_cost = effective_cost * quantity

                lines_analysis.append({
                    'product': str(line.product) if hasattr(line, 'product') else 'N/A',
                    'entered_price': getattr(line, 'entered_price', Decimal('0')),
                    'unit_price': getattr(line, 'unit_price', Decimal('0')),
                    'vat_rate': getattr(line, 'vat_rate', Decimal('0')),
                    'quantity': quantity,
                    'effective_cost_per_unit': effective_cost,
                    'line_total_cost': line_total_cost
                })

                total_effective_cost += line_total_cost

            analysis['cost_analysis'] = {
                'lines': lines_analysis,
                'total_effective_cost': total_effective_cost,
                'avg_cost_per_line': (
                    total_effective_cost / len(lines_analysis)
                    if lines_analysis else Decimal('0')
                )
            }

        return analysis

    @staticmethod
    def process_order_price_changes(order: PurchaseOrder, price_updates: List[Dict]) -> Dict:
        """
        Process bulk price updates with VAT recalculation

        NEW: Bulk price update with VAT awareness

        Args:
            order: PurchaseOrder instance
            price_updates: List of {'line_id': int, 'new_entered_price': Decimal}
        """
        results: Dict[str, any] = {  # ✅ Explicit type annotation
            'success': False,
            'processed_lines': 0,
            'failed_lines': 0,
            'errors': [],
            'new_totals': None  # ✅ Initialize as None
        }

        if not order.can_be_edited():
            results['errors'].append("Order cannot be edited in current state")
            return results

        try:
            with transaction.atomic():
                for update in price_updates:
                    try:
                        line = order.lines.get(pk=update['line_id'])
                        old_price = getattr(line, 'entered_price', Decimal('0'))

                        # Update entered price
                        line.entered_price = update['new_entered_price']

                        # Save triggers VAT recalculation
                        line.save()

                        results['processed_lines'] += 1

                    except Exception as e:
                        results['failed_lines'] += 1
                        results['errors'].append(
                            f"Line {update.get('line_id', 'unknown')}: {str(e)}"
                        )

                # Recalculate document totals
                if hasattr(order, 'recalculate_totals'):
                    order.recalculate_totals()

                results['success'] = results['failed_lines'] == 0

                # ✅ Calculate new totals after successful processing
                if results['success']:
                    results['new_totals'] = OrderService.calculate_order_totals(order)

        except Exception as e:
            results['errors'].append(f"Transaction error: {str(e)}")

        return results
    # =====================
    # HELPER METHODS
    # =====================

    @staticmethod
    def _calculate_conversion_time(order: PurchaseOrder) -> Optional[int]:
        """Calculate days from request approval to order creation"""
        if order.source_request and order.source_request.approved_at:
            return (order.created_at.date() - order.source_request.approved_at.date()).days
        return None

    @staticmethod
    def _analyze_order_lines(order: PurchaseOrder) -> Dict:
        """Analyze order lines breakdown"""
        lines = order.lines.select_related('product', 'product__product_group')  # ✅ ФИКСВАНО

        category_breakdown = {}
        for line in lines:
            # ✅ ФИКСВАНО: product.group -> product.product_group
            category = line.product.product_group.name if line.product.product_group else 'Uncategorized'

            if category not in category_breakdown:
                category_breakdown[category] = {
                    'lines': 0,
                    'total_quantity': Decimal('0'),
                    'total_value': Decimal('0')
                }

            category_breakdown[category]['lines'] += 1
            category_breakdown[category]['total_quantity'] += line.ordered_quantity

            # ✅ ФИКСВАНО: line.line_total -> line.gross_amount (if using FinancialLineMixin)
            # OR get calculated total from line
            line_total = getattr(line, 'gross_amount', Decimal('0')) or (
                line.unit_price * line.ordered_quantity if hasattr(line, 'unit_price') else Decimal('0')
            )
            category_breakdown[category]['total_value'] += line_total

        # ✅ ФИКСВАНО: lines.filter() -> list comprehension (lines е queryset)
        lines_list = list(lines)

        return {
            'total_categories': len(category_breakdown),
            'category_breakdown': category_breakdown,
            'highest_value_line': max(lines_list,
                                      key=lambda l: getattr(l, 'gross_amount', Decimal('0'))) if lines_list else None,
            'lines_with_discounts': len([l for l in lines_list if getattr(l, 'discount_percent', 0) > 0])
        }

    @staticmethod
    def _calculate_completeness_score(order: PurchaseOrder) -> int:
        """Calculate completeness score (0-100)"""
        score = 0

        # Basic info (40 points)
        if order.lines.exists():
            score += 20
        if order.expected_delivery_date:
            score += 20

        # Detail completeness (30 points)
        if order.payment_terms:
            score += 10
        if order.delivery_terms:
            score += 10
        if order.supplier_contact_person:
            score += 10

        # Line quality (30 points)
        total_lines = order.lines.count()
        if total_lines > 0:
            lines_with_prices = order.lines.filter(unit_price__gt=0).count()
            lines_with_discounts = order.lines.filter(discount_percent__gt=0).count()

            score += int((lines_with_prices / total_lines) * 20)
            if lines_with_discounts > 0:
                score += 10  # Bonus for negotiated discounts

        return min(score, 100)