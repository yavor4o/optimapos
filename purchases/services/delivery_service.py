# purchases/services/delivery_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from purchases.models.deliveries import DeliveryReceipt, DeliveryLine
from purchases.models.orders import PurchaseOrder


class DeliveryService:
    """Service for Delivery Receipt operations"""

    @staticmethod
    @transaction.atomic
    def create_delivery(
            supplier,
            location,
            received_by,
            creation_type='direct',
            lines_data: Optional[List[Dict]] = None,
            source_orders: Optional[List[PurchaseOrder]] = None,
            **kwargs
    ) -> DeliveryReceipt:
        """Create new delivery receipt"""

        # Create delivery
        delivery = DeliveryReceipt.objects.create(
            supplier=supplier,
            location=location,
            received_by=received_by,
            creation_type=creation_type,
            delivery_date=timezone.now().date(),
            **kwargs
        )

        # Add source orders if provided
        if source_orders:
            delivery.add_source_orders(source_orders)
            if creation_type == 'from_orders':
                delivery.copy_lines_from_orders()

        # Add manual lines if provided
        if lines_data:
            DeliveryService.add_lines_to_delivery(delivery, lines_data)

        return delivery

    @staticmethod
    @transaction.atomic
    def create_from_orders(
            orders: List[PurchaseOrder],
            received_by,
            delivery_data: Optional[Dict] = None,
            additional_lines: Optional[List[Dict]] = None
    ) -> DeliveryReceipt:
        """Create delivery from one or more orders"""

        if not orders:
            raise ValidationError("At least one order is required")

        # Validate all orders can be used for delivery
        for order in orders:
            if not order.can_be_used_for_delivery():
                raise ValidationError(f"Order {order.document_number} cannot be used for delivery")

        # Use first order's supplier and location as defaults
        first_order = orders[0]
        delivery_data = delivery_data or {}

        delivery_data.setdefaults({
            'supplier': first_order.supplier,
            'location': first_order.location,
            'expected_delivery_date': first_order.expected_delivery_date,
        })

        # Determine creation type
        creation_type = 'mixed' if additional_lines else 'from_orders'

        # Create delivery
        delivery = DeliveryService.create_delivery(
            creation_type=creation_type,
            received_by=received_by,
            source_orders=orders,
            **delivery_data
        )

        # Add additional lines if provided
        if additional_lines:
            DeliveryService.add_lines_to_delivery(delivery, additional_lines)

        return delivery

    @staticmethod
    @transaction.atomic
    def create_direct_delivery(
            supplier,
            location,
            received_by,
            lines_data: List[Dict],
            **kwargs
    ) -> DeliveryReceipt:
        """Create direct delivery (no orders)"""

        return DeliveryService.create_delivery(
            supplier=supplier,
            location=location,
            received_by=received_by,
            creation_type='direct',
            lines_data=lines_data,
            **kwargs
        )

    @staticmethod
    @transaction.atomic
    def add_lines_to_delivery(delivery: DeliveryReceipt, lines_data: List[Dict], user=None) -> List[DeliveryLine]:
        """
        Add lines to delivery receipt with auto-confirm support

        Args:
            delivery: DeliveryReceipt instance
            lines_data: List of line data dictionaries
            user: User who is adding the lines (needed for auto-confirm)

        Returns:
            List[DeliveryLine]: Created delivery lines
        """
        import logging
        logger = logging.getLogger(__name__)

        if delivery.is_final_status():
            raise ValidationError("Cannot modify delivery in final status")

        lines = []
        existing_lines_count = delivery.lines.count()

        # Create lines
        for i, line_data in enumerate(lines_data, existing_lines_count + 1):
            line = DeliveryLine.objects.create(
                document=delivery,
                line_number=i,
                product=line_data['product'],
                received_quantity=line_data['received_quantity'],
                unit=line_data['unit'],
                unit_price=line_data['unit_price'],
                source_order_line=line_data.get('source_order_line'),
                ordered_quantity=line_data.get('ordered_quantity'),
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
                quality_approved=line_data.get('quality_approved', True),
                **line_data.get('extra_fields', {})
            )
            lines.append(line)

        # Recalculate totals
        delivery.recalculate_totals()

        # ✅ NEW: Auto-confirm logic
        try:
            DeliveryService._check_auto_confirm(delivery, user)
        except Exception as e:
            # Log auto-confirm errors but don't fail the line creation
            logger.warning(f"Auto-confirm failed for delivery {delivery.document_number}: {e}")

        return lines

    @staticmethod
    def _check_auto_confirm(delivery: DeliveryReceipt, user):
        """
        Check and execute auto-confirm if conditions are met

        Args:
            delivery: DeliveryReceipt to check for auto-confirm
            user: User to associate with the transition
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check if auto-confirm is enabled
        if not (delivery.document_type and delivery.document_type.auto_confirm):
            logger.debug(f"Auto-confirm disabled for delivery {delivery.document_number}")
            return

        # Check if document is in default status
        if delivery.status != delivery.document_type.default_status:
            logger.debug(f"Delivery {delivery.document_number} not in default status ({delivery.status})")
            return

        # Check if delivery has lines
        if not delivery.lines.exists():
            logger.debug(f"Delivery {delivery.document_number} has no lines yet")
            return

        # Get next allowed statuses
        next_statuses = delivery.get_next_statuses()
        if not next_statuses:
            logger.warning(f"No next statuses available for delivery {delivery.document_number}")
            return

        # Execute auto-confirm transition
        from purchases.services.workflow_service import WorkflowService

        target_status = next_statuses[0]  # Take first available status

        logger.info(f"Auto-confirming delivery {delivery.document_number}: {delivery.status} → {target_status}")

        result = WorkflowService.transition_document(
            document=delivery,
            to_status=target_status,
            user=user,
            comments="Auto-confirm: lines added to delivery"
        )

        if result['success']:
            logger.info(f"✅ Successfully auto-confirmed delivery {delivery.document_number} to {target_status}")
        else:
            logger.error(f"❌ Auto-confirm failed for delivery {delivery.document_number}: {result['message']}")
            # Re-raise as warning exception so it doesn't break the line creation
            raise ValidationError(f"Auto-confirm failed: {result['message']}")

    @staticmethod
    @transaction.atomic
    def receive_delivery(delivery: DeliveryReceipt, user, quality_check=True) -> Dict:
        """Receive and process delivery"""

        try:
            delivery.receive_delivery(user, quality_check)
            return {
                'success': True,
                'message': f'Delivery {delivery.document_number} received successfully',
                'delivery': delivery
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e),
                'delivery': delivery
            }

    @staticmethod
    def get_delivery_options(supplier) -> Dict:
        """Get delivery creation options for supplier"""

        available_orders = PurchaseOrder.objects.ready_for_delivery_creation().filter(
            supplier=supplier
        )

        return {
            'supplier': supplier,
            'available_orders': list(available_orders),
            'can_create_direct': True,  # TODO: Check from core settings
            'can_create_mixed': True,
        }

    @staticmethod
    def get_delivery_analytics(date_from=None, date_to=None) -> Dict:
        """Get delivery analytics and statistics"""

        queryset = DeliveryReceipt.objects.all()

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return {
            'total_deliveries': queryset.count(),
            'received_deliveries': queryset.filter(status='received').count(),
            'direct_deliveries': queryset.filter(creation_type='direct').count(),
            'from_orders': queryset.filter(creation_type='from_orders').count(),
            'with_quality_issues': queryset.filter(has_quality_issues=True).count(),
            'with_variances': queryset.filter(has_variances=True).count(),
        }

    # ADD these methods to purchases/services/delivery_service.py

    @staticmethod
    def calculate_delivery_totals(delivery: DeliveryReceipt) -> Dict:
        """
        Calculate delivery totals using VAT-aware system

        NEW: Complete VAT integration for deliveries
        """
        from .vat_service import SmartVATService

        # Use SmartVATService for all calculations
        base_totals = SmartVATService.calculate_document_totals(delivery)

        if not hasattr(delivery, 'lines') or not delivery.lines.exists():
            return {
                **base_totals,
                'delivery_specific': {
                    'total_received_items': Decimal('0'),
                    'quality_issues_count': 0,
                    'acceptance_rate': 100.0,
                    'effective_total_cost': Decimal('0')
                }
            }

        lines = delivery.lines.all()

        # Delivery-specific calculations
        total_received_items = sum(
            getattr(line, 'get_quantity', lambda: Decimal('0'))()
            for line in lines
        )

        # Quality analysis
        quality_issues_count = sum(
            1 for line in lines
            if hasattr(line, 'has_quality_issues') and line.has_quality_issues
        )

        acceptance_rate = (
            ((lines.count() - quality_issues_count) / lines.count() * 100)
            if lines.count() > 0 else 100.0
        )

        # Calculate effective cost for inventory
        effective_total_cost = sum(
            SmartVATService.get_effective_cost(line) * getattr(line, 'get_quantity', lambda: Decimal('0'))()
            for line in lines
        )

        return {
            **base_totals,
            'delivery_specific': {
                'total_received_items': total_received_items,
                'quality_issues_count': quality_issues_count,
                'acceptance_rate': acceptance_rate,
                'effective_total_cost': effective_total_cost,
                'avg_effective_cost_per_item': (
                    effective_total_cost / total_received_items
                    if total_received_items > 0 else Decimal('0')
                )
            }
        }

    @staticmethod
    def validate_delivery_financials(delivery: DeliveryReceipt) -> Dict:
        """
        Validate delivery financial data with VAT awareness

        NEW: Complete VAT validation for deliveries
        """
        issues = []
        warnings = []

        # Basic structure validation
        if not hasattr(delivery, 'lines') or not delivery.lines.exists():
            issues.append("Delivery has no lines")
            return {
                'valid': False,
                'issues': issues,
                'warnings': warnings
            }

        # VAT configuration validation
        company = delivery.get_company()
        if not company:
            issues.append("No company configuration found")

        # Check each line for completeness
        for line in delivery.lines.all():
            line_number = getattr(line, 'line_number', 'Unknown')

            # Check required fields
            if not hasattr(line, 'received_quantity') or not getattr(line, 'received_quantity'):
                issues.append(f"Line {line_number}: Missing received quantity")

            if not hasattr(line, 'entered_price') or not getattr(line, 'entered_price'):
                warnings.append(f"Line {line_number}: Missing price information")

            # Product validation
            if not hasattr(line, 'product') or not getattr(line, 'product'):
                issues.append(f"Line {line_number}: Missing product")
            else:
                # VAT-specific validations for VAT-registered companies
                if company and company.is_vat_applicable():
                    if not hasattr(line.product, 'tax_group') or not line.product.tax_group:
                        warnings.append(f"Line {line_number}: Product missing tax group")

        # Document totals validation
        calculated_totals = DeliveryService.calculate_delivery_totals(delivery)

        tolerance = Decimal('0.01')  # 1 cent tolerance

        if hasattr(delivery, 'subtotal'):
            if abs(delivery.subtotal - calculated_totals['subtotal']) > tolerance:
                issues.append(
                    f"Subtotal mismatch: Document={delivery.subtotal}, "
                    f"Calculated={calculated_totals['subtotal']}"
                )

        if hasattr(delivery, 'total'):
            if abs(delivery.total - calculated_totals['total']) > tolerance:
                issues.append(
                    f"Total mismatch: Document={delivery.total}, "
                    f"Calculated={calculated_totals['total']}"
                )

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'calculated_totals': calculated_totals,
            'vat_context': delivery.get_vat_context_info()
        }

    @staticmethod
    def process_delivery_from_orders(
            orders: List[PurchaseOrder],
            received_by,
            delivery_data: Dict = None
    ) -> Dict:
        """
        Create delivery from orders with VAT-aware price processing

        ENHANCED: Complete VAT integration during order-to-delivery conversion
        """
        from .vat_service import SmartVATService

        results = {
            'success': False,
            'delivery': None,
            'lines_processed': 0,
            'lines_with_errors': 0,
            'errors': [],
            'vat_processing_summary': {}
        }

        if not orders:
            results['errors'].append("No orders provided")
            return results

        # Group orders by supplier and location for validation
        suppliers = set(order.supplier for order in orders if hasattr(order, 'supplier'))
        locations = set(order.location for order in orders if hasattr(order, 'location'))

        if len(suppliers) > 1:
            results['errors'].append("Cannot create delivery from orders with different suppliers")
            return results

        if len(locations) > 1:
            results['errors'].append("Cannot create delivery from orders with different locations")
            return results

        try:
            with transaction.atomic():
                # Create delivery receipt
                delivery_defaults = {
                    'supplier': list(suppliers)[0] if suppliers else None,
                    'location': list(locations)[0] if locations else None,
                    'received_by': received_by,
                    'delivery_date': timezone.now().date(),
                    'creation_type': 'from_orders',
                }

                if delivery_data:
                    delivery_defaults.update(delivery_data)

                delivery = DeliveryReceipt.objects.create(**delivery_defaults)

                # Add source orders relationship
                if hasattr(delivery, 'source_orders'):
                    delivery.source_orders.set(orders)

                # Process lines from orders
                vat_processing_stats = {
                    'total_order_lines': 0,
                    'lines_created': 0,
                    'vat_calculations_performed': 0,
                    'price_adjustments': []
                }

                for order in orders:
                    if not hasattr(order, 'lines'):
                        continue

                    for order_line in order.lines.all():
                        vat_processing_stats['total_order_lines'] += 1

                        try:
                            # Create delivery line with order data
                            delivery_line_data = {
                                'document': delivery,
                                'product': getattr(order_line, 'product', None),
                                'received_quantity': getattr(order_line, 'get_quantity', lambda: Decimal('0'))(),
                                'unit': getattr(order_line, 'unit', None),
                            }

                            # Copy pricing data
                            entered_price = getattr(order_line, 'entered_price', None)
                            if not entered_price:
                                # Fallback to unit_price if no entered_price
                                entered_price = getattr(order_line, 'unit_price', Decimal('0'))

                            delivery_line_data['entered_price'] = entered_price

                            # Create line (save method will handle VAT processing)
                            delivery_line = DeliveryLine.objects.create(**delivery_line_data)

                            vat_processing_stats['lines_created'] += 1

                            # Check if VAT calculation was performed
                            if (hasattr(delivery_line, 'vat_amount') and
                                    getattr(delivery_line, 'vat_amount', Decimal('0')) > 0):
                                vat_processing_stats['vat_calculations_performed'] += 1

                            # Track price adjustments
                            order_unit_price = getattr(order_line, 'unit_price', Decimal('0'))
                            delivery_unit_price = getattr(delivery_line, 'unit_price', Decimal('0'))

                            if abs(order_unit_price - delivery_unit_price) > Decimal('0.001'):
                                vat_processing_stats['price_adjustments'].append({
                                    'product': str(delivery_line.product) if delivery_line.product else 'N/A',
                                    'order_price': order_unit_price,
                                    'delivery_price': delivery_unit_price,
                                    'difference': delivery_unit_price - order_unit_price
                                })

                            results['lines_processed'] += 1

                        except Exception as e:
                            results['lines_with_errors'] += 1
                            results['errors'].append(
                                f"Order {order.document_number}, Line {getattr(order_line, 'line_number', 'unknown')}: {str(e)}"
                            )

                # Recalculate delivery totals
                if hasattr(delivery, 'recalculate_totals'):
                    delivery.recalculate_totals()

                results.update({
                    'success': results['lines_with_errors'] == 0,
                    'delivery': delivery,
                    'vat_processing_summary': vat_processing_stats,
                    'final_totals': DeliveryService.calculate_delivery_totals(delivery)
                })

        except Exception as e:
            results['errors'].append(f"Transaction error: {str(e)}")

        return results

    @staticmethod
    def get_delivery_cost_analysis(delivery: DeliveryReceipt) -> Dict:
        """
        Get comprehensive cost analysis for delivery

        NEW: VAT-aware cost analysis for inventory impact
        """
        from .vat_service import SmartVATService

        analysis = {
            'document_info': {
                'document_number': delivery.document_number,
                'supplier': str(delivery.supplier) if hasattr(delivery, 'supplier') else None,
                'delivery_date': getattr(delivery, 'delivery_date', None),
                'received_by': str(delivery.received_by) if hasattr(delivery, 'received_by') else None,
            },
            'vat_context': delivery.get_vat_context_info(),
            'cost_breakdown': {
                'total_purchase_value': Decimal('0'),
                'total_effective_cost': Decimal('0'),
                'vat_recoverable': Decimal('0'),
                'inventory_impact': Decimal('0')
            },
            'lines_analysis': []
        }

        if not hasattr(delivery, 'lines') or not delivery.lines.exists():
            return analysis

        company_vat_registered = delivery.get_company_vat_status()

        for line in delivery.lines.all():
            quantity = getattr(line, 'get_quantity', lambda: Decimal('0'))()
            unit_price = getattr(line, 'unit_price', Decimal('0'))
            vat_amount_per_unit = getattr(line, 'vat_amount', Decimal('0')) / quantity if quantity > 0 else Decimal('0')
            gross_amount_per_unit = getattr(line, 'gross_amount', Decimal('0')) / quantity if quantity > 0 else Decimal(
                '0')

            # Calculate effective cost per unit
            effective_cost_per_unit = SmartVATService.get_effective_cost(line)

            line_analysis = {
                'product': str(line.product) if hasattr(line, 'product') else 'N/A',
                'quantity': quantity,
                'unit_price_excl_vat': unit_price,
                'vat_amount_per_unit': vat_amount_per_unit,
                'gross_amount_per_unit': gross_amount_per_unit,
                'effective_cost_per_unit': effective_cost_per_unit,
                'total_purchase_value': gross_amount_per_unit * quantity,
                'total_effective_cost': effective_cost_per_unit * quantity,
                'vat_recoverable': vat_amount_per_unit * quantity if company_vat_registered else Decimal('0'),
                'inventory_impact': effective_cost_per_unit * quantity
            }

            analysis['lines_analysis'].append(line_analysis)

            # Aggregate totals
            analysis['cost_breakdown']['total_purchase_value'] += line_analysis['total_purchase_value']
            analysis['cost_breakdown']['total_effective_cost'] += line_analysis['total_effective_cost']
            analysis['cost_breakdown']['vat_recoverable'] += line_analysis['vat_recoverable']
            analysis['cost_breakdown']['inventory_impact'] += line_analysis['inventory_impact']

        # Add summary metrics
        analysis['summary_metrics'] = {
            'lines_count': len(analysis['lines_analysis']),
            'avg_effective_cost_per_line': (
                analysis['cost_breakdown']['total_effective_cost'] / len(analysis['lines_analysis'])
                if analysis['lines_analysis'] else Decimal('0')
            ),
            'vat_recovery_rate': (
                analysis['cost_breakdown']['vat_recoverable'] / analysis['cost_breakdown']['total_purchase_value'] * 100
                if analysis['cost_breakdown']['total_purchase_value'] > 0 else Decimal('0')
            )
        }

        return analysis

    @staticmethod
    def recalculate_delivery_totals(delivery: DeliveryReceipt) -> Dict:
        """
        Force complete recalculation of delivery totals

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
            if hasattr(delivery, 'lines'):
                for line in delivery.lines.all():
                    try:
                        # Enhanced save method handles VAT processing
                        line.save()
                        results['lines_processed'] += 1
                    except Exception as e:
                        results['lines_with_errors'] += 1
                        results['errors'].append(f"Line {line.pk}: {str(e)}")

            # Recalculate document totals
            if hasattr(delivery, 'recalculate_totals'):
                delivery.recalculate_totals()

            results.update({
                'success': results['lines_with_errors'] == 0,
                'final_totals': DeliveryService.calculate_delivery_totals(delivery)
            })

            return results

        except Exception as e:
            results['errors'].append(f"Document level error: {str(e)}")
            return results
