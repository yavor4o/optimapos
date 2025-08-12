# purchases/services/vat_integration_service.py
"""
VAT Integration Service

Handles cross-service VAT operations and document workflows
"""
import logging
from typing import Dict, List, Optional, Union
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from purchases.models import  PurchaseOrder, DeliveryReceipt
from purchases.models.requests import PurchaseRequest

ogger = logging.getLogger(__name__)  # ✅ ADDED for error logging

class VATIntegrationService:
    """
    Service for VAT-aware document workflow operations
    """

    @staticmethod
    def process_document_vat_setup(
            document: Union[PurchaseRequest, PurchaseOrder, DeliveryReceipt],
            force_recalculation: bool = False
    ) -> Dict:
        """
        Set up VAT processing for a document and all its lines

        Args:
            document: Document instance
            force_recalculation: Force recalculation even if already processed

        Returns:
            Dict with processing results
        """
        results = {
            'success': False,
            'document_processed': False,
            'lines_processed': 0,
            'lines_with_errors': 0,
            'errors': [],
            'vat_context': {}
        }

        try:
            # Get VAT context
            vat_context = document.get_vat_context_info()
            results['vat_context'] = vat_context

            # Process lines
            if hasattr(document, 'lines'):
                for line in document.lines.all():
                    try:
                        # Check if line needs processing
                        needs_processing = (
                                force_recalculation or
                                not hasattr(line, 'unit_price') or
                                not getattr(line, 'unit_price') or
                                not hasattr(line, 'vat_amount')
                        )

                        if needs_processing:
                            # Trigger VAT processing by saving
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

    @staticmethod
    def convert_request_to_order_with_vat(
            request: PurchaseRequest,
            user,
            price_adjustments: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Convert request to order with VAT-aware price processing

        Args:
            request: PurchaseRequest instance
            user: User performing conversion
            price_adjustments: List of price adjustments {'line_id': int, 'new_price': Decimal}
        """
       
        results = {
            'success': False,
            'order': None,
            'conversion_summary': {},
            'errors': []
        }

        try:
            with transaction.atomic():
                # Step 1: Prepare request for conversion
                preparation = RequestService.prepare_request_for_order_conversion(request)

                if not preparation['ready_for_conversion']:
                    results['errors'].extend(preparation['issues'])
                    return results

                # Step 2: Create order using OrderService
                order_creation = OrderService.create_from_request(request, user)

                if not order_creation['success']:
                    results['errors'].append(order_creation['message'])
                    return results

                order = order_creation['order']

                # Step 3: Apply price adjustments if provided
                if price_adjustments:
                    adjustment_results = OrderService.process_order_price_changes(
                        order, price_adjustments
                    )

                    if not adjustment_results['success']:
                        results['errors'].extend(adjustment_results['errors'])
                        return results

                # Step 4: Final VAT processing
                vat_setup = VATIntegrationService.process_document_vat_setup(
                    order, force_recalculation=True
                )

                if not vat_setup['success']:
                    results['errors'].extend(vat_setup['errors'])
                    return results

                # Step 5: Create conversion summary
                request_totals = RequestService.calculate_request_totals(request)
                order_totals = OrderService.calculate_order_totals(order)

                conversion_summary = {
                    'source_request': request.document_number,
                    'target_order': order.document_number,
                    'lines_converted': order.lines.count(),
                    'request_estimated_total': request_totals['estimated_total'],
                    'request_vat_total': request_totals['vat_aware_totals']['total'],
                    'order_total': order_totals['total'],
                    'price_variance': order_totals['total'] - request_totals['estimated_total'],
                    'vat_applicable': order.is_vat_applicable(),
                    'conversion_timestamp': timezone.now()
                }

                results.update({
                    'success': True,
                    'order': order,
                    'conversion_summary': conversion_summary
                })

        except Exception as e:
            results['errors'].append(f"Conversion transaction error: {str(e)}")

        return results

    @staticmethod
    def bulk_vat_recalculation(
            document_type: str,
            document_ids: Optional[List[int]] = None,
            filters: Optional[Dict] = None
    ) -> Dict:
        """
        Perform bulk VAT recalculation on multiple documents

        Args:
            document_type: 'request', 'order', or 'delivery'
            document_ids: Specific document IDs to process
            filters: Django filter parameters
        """
        from .request_service import RequestService
        from .order_service import OrderService
        from .delivery_service import DeliveryService

        results = {
            'success': False,
            'documents_processed': 0,
            'documents_with_errors': 0,
            'total_documents': 0,
            'errors': [],
            'processing_summary': {}
        }

        # Get document model and service
        model_map = {
            'request': (PurchaseRequest, RequestService),
            'order': (PurchaseOrder, OrderService),
            'delivery': (DeliveryReceipt, DeliveryService)
        }

        if document_type not in model_map:
            results['errors'].append(f"Invalid document type: {document_type}")
            return results

        model_class, service_class = model_map[document_type]

        try:
            # Build queryset
            queryset = model_class.objects.all()

            if document_ids:
                queryset = queryset.filter(pk__in=document_ids)

            if filters:
                queryset = queryset.filter(**filters)

            results['total_documents'] = queryset.count()

            # Process each document
            for document in queryset:
                try:
                    # Force VAT recalculation
                    if document_type == 'request':
                        recalc_result = RequestService.process_request_prices_for_vat(document)
                    elif document_type == 'order':
                        recalc_result = OrderService.recalculate_order_totals(document)
                    else:  # delivery
                        recalc_result = DeliveryService.recalculate_delivery_totals(document)

                    if recalc_result.get('success', False):
                        results['documents_processed'] += 1
                    else:
                        results['documents_with_errors'] += 1
                        results['errors'].extend(recalc_result.get('errors', []))

                except Exception as e:
                    results['documents_with_errors'] += 1
                    results['errors'].append(f"Document {document.pk}: {str(e)}")

            results['success'] = results['documents_with_errors'] == 0

            results['processing_summary'] = {
                'success_rate': (
                    results['documents_processed'] / results['total_documents'] * 100
                    if results['total_documents'] > 0 else 0
                ),
                'error_rate': (
                    results['documents_with_errors'] / results['total_documents'] * 100
                    if results['total_documents'] > 0 else 0
                )
            }

        except Exception as e:
            results['errors'].append(f"Bulk processing error: {str(e)}")

        return results

    @staticmethod
    def validate_vat_consistency_across_workflow(
            request: PurchaseRequest,
            order: Optional[PurchaseOrder] = None,
            delivery: Optional[DeliveryReceipt] = None
    ) -> Dict:
        """
        Validate VAT consistency across related documents in workflow

        Args:
            request: Source request
            order: Related order (optional)
            delivery: Related delivery (optional)
        """
        validation_results = {
            'consistent': True,
            'issues': [],
            'warnings': [],
            'document_comparison': {}
        }

        # Get VAT contexts
        contexts = {
            'request': request.get_vat_context_info()
        }

        if order:
            contexts['order'] = order.get_vat_context_info()

        if delivery:
            contexts['delivery'] = delivery.get_vat_context_info()

        validation_results['document_comparison'] = contexts

        # Check consistency across documents
        base_context = contexts['request']

        for doc_type, context in contexts.items():
            if doc_type == 'request':
                continue

            # Check company VAT consistency
            if context['company_vat_registered'] != base_context['company_vat_registered']:
                validation_results['issues'].append(
                    f"Company VAT status inconsistent between request and {doc_type}"
                )
                validation_results['consistent'] = False

            # Check supplier VAT consistency
            if context['supplier_vat_registered'] != base_context['supplier_vat_registered']:
                validation_results['warnings'].append(
                    f"Supplier VAT status differs between request and {doc_type}"
                )

            # Check price entry mode consistency
            if context['prices_entered_with_vat'] != base_context['prices_entered_with_vat']:
                validation_results['warnings'].append(
                    f"Price entry mode differs between request and {doc_type}"
                )

        return validation_results

    @staticmethod
    def get_workflow_vat_summary(
            request: PurchaseRequest,
            order: Optional[PurchaseOrder] = None,
            delivery: Optional[DeliveryReceipt] = None
    ) -> Dict:
        """
        Get comprehensive VAT summary across entire workflow
        """
        from .request_service import RequestService
        from .order_service import OrderService
        from .delivery_service import DeliveryService

        summary = {
            'workflow_info': {
                'request_number': request.document_number,
                'order_number': order.document_number if order else None,
                'delivery_number': delivery.document_number if delivery else None,
                'workflow_complete': bool(order and delivery)
            },
            'vat_consistency': VATIntegrationService.validate_vat_consistency_across_workflow(
                request, order, delivery
            ),
            'financial_progression': {}
        }

        # Get financial data for each stage
        request_totals = RequestService.calculate_request_totals(request)
        summary['financial_progression']['request'] = {
            'estimated_total': request_totals['estimated_total'],
            'vat_calculated_total': request_totals['vat_aware_totals']['total'],
            'stage': 'planning'
        }

        if order:
            order_totals = OrderService.calculate_order_totals(order)
            summary['financial_progression']['order'] = {
                'subtotal': order_totals['subtotal'],
                'vat_total': order_totals['vat_total'],
                'total': order_totals['total'],
                'effective_cost': order_totals['order_specific']['effective_total_cost'],
                'stage': 'committed'
            }

        if delivery:
            delivery_totals = DeliveryService.calculate_delivery_totals(delivery)
            summary['financial_progression']['delivery'] = {
                'subtotal': delivery_totals['subtotal'],
                'vat_total': delivery_totals['vat_total'],
                'total': delivery_totals['total'],
                'effective_cost': delivery_totals['delivery_specific']['effective_total_cost'],
                'inventory_impact': delivery_totals['delivery_specific']['effective_total_cost'],
                'stage': 'received'
            }

        return summary