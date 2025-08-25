# purchases/services/workflow_service.py


from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
import logging
from core.utils.result import Result
from django.utils import timezone

from inventory.services import MovementService
from nomenclatures.models import DocumentType
from nomenclatures.services import VATCalculationService, DocumentService
from nomenclatures.services.document import DocumentCreator
from partners.services import SupplierService
from purchases.models import PurchaseOrder, PurchaseOrderLine, DeliveryReceipt, DeliveryLine

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class WorkflowResult(Result):
    """Enhanced Result for workflow operations"""
    pass


class PurchaseWorkflowService:


    # =====================
    # REQUEST → ORDER CONVERSION
    # =====================

    @classmethod
    @transaction.atomic
    def convert_request_to_order(cls, request, user=None, **order_overrides) -> Result:

        try:
            # Validation
            if request.status != 'approved':
                return Result.error(
                    'REQUEST_NOT_APPROVED',
                    f'Request {request.document_number} is not approved (status: {request.status})',
                    {'request_status': request.status}
                )

            if not request.lines.exists():
                return Result.error(
                    'REQUEST_NO_LINES',
                    f'Request {request.document_number} has no lines to convert',
                    {'lines_count': 0}
                )

            if request.converted_to_order:
                return Result.error(
                    'REQUEST_ALREADY_CONVERTED',
                    f'Request {request.document_number} already converted to order {request.converted_to_order.document_number}',
                    {'existing_order': request.converted_to_order.document_number}
                )

            if request.partner:

                supplier_validation = SupplierService.validate_supplier_operation(
                    request.partner,
                    request.total or Decimal('0')
                )

                if not supplier_validation.ok:
                    return supplier_validation


            # Prepare order data
            order_data = {
                'partner': request.partner,
                'location': request.location,
                'document_type': cls._get_order_document_type(request.document_type),
                'expected_delivery_date': timezone.now().date() + timedelta(days=7),
                'external_reference': request.external_reference,
                'notes': f"Created from request {request.document_number}\n{request.notes}".strip(),
                'source_request': request,
                'created_by': user or request.updated_by,
                'updated_by': user or request.updated_by,
            }

            # Apply overrides
            order_data.update(order_overrides)


            create_result = DocumentService.create_document(
                model_class=PurchaseOrder,
                data=order_data,
                user=user,
                location=request.location
            )

            if not create_result.ok:
                return Result.error(
                    'ORDER_CREATION_FAILED',
                    f'Failed to create order: {create_result.msg}'
                )

            order = create_result.data['document']

            # Copy lines with enhanced logic
            lines_created = 0
            for req_line in request.lines.select_related('product').all():
                order_line = PurchaseOrderLine.objects.create(
                    document=order,
                    line_number=req_line.line_number,
                    product=req_line.product,
                    unit=req_line.unit,
                    ordered_quantity=req_line.requested_quantity,
                    unit_price=req_line.estimated_price or Decimal('0.0000'),
                    source_request_line=req_line,
                    notes=req_line.notes,
                )
                lines_created += 1


            request.converted_to_order = order
            request.converted_at = timezone.now()
            request.converted_by = user
            request.save(update_fields=[
                'converted_to_order', 'converted_at', 'converted_by'
            ])

            # Recalculate order totals using service
            try:

                calc_result = VATCalculationService.calculate_document_vat(order)
                if not calc_result.ok:
                    logger.warning(f"VAT calculation warning: {calc_result.msg}")
            except ImportError:
                order.recalculate_totals()  # Fallback

            return Result.success(
                {
                    'order': order,
                    'lines_count': lines_created,
                    'request_status': request.status,  # Остава 'approved'
                    'order_total': float(order.total),
                    'conversion_tracked': True,
                    'converted_at': request.converted_at.isoformat()
                },
                f'Successfully converted request {request.document_number} to order {order.document_number}'
            )

        except Exception as e:
            logger.error(f"Request conversion failed: {str(e)}")
            return Result.error(
                'CONVERSION_ERROR',
                f'Failed to convert request: {str(e)}',
                {'exception': str(e)}
            )

    # =====================
    # ORDER WORKFLOW OPERATIONS
    # =====================

    @classmethod
    @transaction.atomic
    def send_order_to_supplier(cls, order, user=None, send_email=False) -> Result:
        """
        Send order to supplier with validation.

        ИЗВЛЕЧЕНО ОТ: PurchaseOrder.send_to_supplier()
        ПОДОБРЕНИЯ:
        - Enhanced validation
        - Optional email integration
        - Service integration
        """
        try:
            # Validation
            if order.status != 'draft':
                return Result.error(
                    'ORDER_NOT_DRAFT',
                    f'Order {order.document_number} is not in draft status (current: {order.status})',
                    {'current_status': order.status}
                )

            if not order.lines.exists():
                return Result.error(
                    'ORDER_NO_LINES',
                    f'Order {order.document_number} has no lines to send',
                    {'lines_count': 0}
                )

            if order.partner:
                from partners.services import SupplierService

                supplier_validation = SupplierService.validate_supplier_operation(
                    order.partner,
                    order.total or Decimal('0')
                )

                if not supplier_validation.ok:
                    return supplier_validation

            # Use DocumentService for status transition
            try:

                transition_result = DocumentService.transition_document(
                    order, 'sent', user, 'Order sent to supplier'
                )
                if not transition_result.ok:
                    return transition_result
            except ImportError:
                # Fallback - direct status change
                order.status = 'sent'
                order.save(update_fields=['status'])

            # Update sent tracking
            order.sent_by = user
            order.sent_to_supplier_at = timezone.now()
            order.save(update_fields=['sent_by', 'sent_to_supplier_at'])

            # Optional email sending
            email_sent = False
            if send_email:
                try:
                    # TODO: Implement EmailService integration
                    # email_result = EmailService.send_order_to_supplier(order)
                    # email_sent = email_result.ok
                    pass
                except Exception as e:
                    logger.warning(f"Email sending failed: {str(e)}")

            return Result.success(
                {
                    'order': order,
                    'sent_by': user.username if user else None,
                    'sent_at': order.sent_to_supplier_at.isoformat(),
                    'email_sent': email_sent,
                    'status': order.status
                },
                f'Order {order.document_number} sent to supplier successfully'
            )

        except Exception as e:
            logger.error(f"Send order failed: {str(e)}")
            return Result.error(
                'SEND_ORDER_ERROR',
                f'Failed to send order: {str(e)}',
                {'exception': str(e)}
            )

    @classmethod
    @transaction.atomic
    def confirm_purchase_order(cls, order, user=None, supplier_reference='',
                               auto_receive=None) -> Result:
        """
        Confirm order from supplier with optional auto-receive.

        ИЗВЛЕЧЕНО ОТ: PurchaseOrder.confirm_order()
        ПОДОБРЕНИЯ:
        - Enhanced validation
        - Configurable auto-receive
        - Movement service integration
        - Better error handling
        """
        try:
            # Validation
            if order.status != 'sent':
                return Result.error(
                    'ORDER_NOT_SENT',
                    f'Order {order.document_number} is not sent (current: {order.status})',
                    {'current_status': order.status}
                )

            # Use DocumentService for transition
            try:

                transition_result = DocumentService.transition_document(
                    order, 'confirmed', user, 'Order confirmed by supplier'
                )
                if not transition_result.ok:
                    return transition_result
            except ImportError:
                order.status = 'confirmed'
                order.save(update_fields=['status'])

            # Update supplier confirmation
            order.supplier_confirmed = True
            order.supplier_confirmed_date = timezone.now().date()
            if supplier_reference:
                order.supplier_order_reference = supplier_reference
            order.save(update_fields=[
                'supplier_confirmed', 'supplier_confirmed_date', 'supplier_order_reference'
            ])

            # Auto-receive logic
            movements_created = 0
            auto_receive_triggered = False

            # Determine if auto-receive should happen
            should_auto_receive = (
                    auto_receive is True or  # Explicitly requested
                    (auto_receive is None and getattr(order.document_type, 'auto_receive', False))
            )

            if should_auto_receive:
                try:

                    movement_result = MovementService.process_document_movements(order)

                    if movement_result.ok:
                        auto_receive_triggered = True
                        movements_created = movement_result.data.get('movements_count', 0)
                        logger.info(f"Auto-created {movements_created} movements for {order.document_number}")
                    else:
                        logger.warning(f"Auto-receive failed: {movement_result.msg}")

                except ImportError:
                    logger.warning("MovementService not available for auto-receive")
                except Exception as e:
                    logger.error(f"Auto-receive error: {str(e)}")
                    # Don't fail the confirmation for movement errors

            return Result.success(
                {
                    'order': order,
                    'confirmed_by': user.username if user else None,
                    'supplier_reference': supplier_reference,
                    'auto_receive_triggered': auto_receive_triggered,
                    'movements_created': movements_created,
                    'status': order.status
                },
                f'Order {order.document_number} confirmed successfully'
            )

        except Exception as e:
            logger.error(f"Order confirmation failed: {str(e)}")
            return Result.error(
                'CONFIRMATION_ERROR',
                f'Failed to confirm order: {str(e)}',
                {'exception': str(e)}
            )

    # =====================
    # DELIVERY CREATION
    # =====================



    @classmethod
    @transaction.atomic
    def create_delivery_from_order(cls, order, delivery_data=None, user=None) -> Result:
        """
        Create delivery receipt from purchase order using correct DocumentCreator signature.
        """
        try:

            # ===================================================================
            # СТЪПКА 0: ENSURE WE HAVE A VALID USER
            # ===================================================================
            if user is None:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.filter(is_active=True).first()
                    if user is None:
                        return Result.error(
                            'NO_USER_AVAILABLE',
                            'No active user found for delivery creation'
                        )
                    logger.warning(f"No user provided, using fallback user: {user.username}")
                except Exception as e:
                    return Result.error(
                        'USER_RESOLUTION_ERROR',
                        f'Failed to resolve user: {str(e)}'
                    )

            # Validate order
            if order.status not in ['confirmed', 'sent']:
                return Result.error(
                    'INVALID_ORDER_STATUS',
                    f'Cannot create delivery from order with status: {order.status}'
                )

            if order.partner:
                from partners.services import SupplierService

                supplier_validation = SupplierService.validate_supplier_operation(
                    order.partner,
                    order.total or Decimal('0')
                )

                if not supplier_validation.ok:
                    return supplier_validation

            # ===================================================================
            # СТЪПКА 1: СЪЗДАЙ DELIVERY INSTANCE (БЕЗ SAVE)
            # ===================================================================
            delivery_data_final = {
                'partner': order.partner,
                'location': order.location,
                'delivery_date': timezone.now().date(),  # ИЗПОЛЗВАЙ DATE ОБЕКТ, НЕ STRING
                'source_order': order,
                'external_reference': getattr(order, 'external_reference', ''),
                'notes': f"Created from order {order.document_number}",
                'received_by': user,
                'subtotal': Decimal('0.00'),
                'vat_total': Decimal('0.00'),
                'discount_total': Decimal('0.00'),
                'total': Decimal('0.00'),
                'prices_entered_with_vat': getattr(order, 'prices_entered_with_vat', None),
            }

            if delivery_data:
                delivery_data_final.update(delivery_data)


            delivery = DeliveryReceipt(**delivery_data_final)
            delivery.created_by = user
            delivery.updated_by = user

            # ===================================================================
            # ВАЖНО: СЕТНИ DOCUMENT_TYPE ПРЕДИ DocumentCreator
            # ===================================================================
            try:

                doc_type = DocumentType.objects.filter(
                    type_key=delivery.get_document_type_key()
                ).first()
                if doc_type:
                    delivery.document_type = doc_type
                    logger.debug(f"Set document_type: {doc_type}")
                else:
                    logger.warning(f"DocumentType not found for key: {delivery.get_document_type_key()}")
            except Exception as e:
                logger.warning(f"Could not set document_type: {e}")

            # ===================================================================
            # СТЪПКА 2: ИЗПОЛЗВАЙ DocumentCreator ПРАВИЛНО
            # ===================================================================
            try:
                # DocumentCreator трябва да handle всичко - document_type, numbering, etc.
                DocumentCreator.create_document(delivery, user)
            except Exception as e:
                logger.error(f"DocumentCreator failed: {e}")
                # Fallback: basic save
                delivery.save()
                return Result.error(
                    'DOCUMENT_CREATION_ERROR',
                    f'Document creation failed: {str(e)}'
                )

            # ===================================================================
            # СТЪПКА 3: КОПИРАЙ LINES И ИЗЧИСЛИ ФИНАНСОВИ ДАННИ
            # ===================================================================
            lines_created = 0
            for order_line in order.lines.all():
                # Създай line
                delivery_line = DeliveryLine.objects.create(
                    document=delivery,
                    line_number=order_line.line_number,
                    product=order_line.product,
                    quantity=getattr(order_line, 'ordered_quantity',
                                     getattr(order_line, 'quantity', Decimal('1.00'))),
                    unit=getattr(order_line, 'unit', ''),
                    unit_price=getattr(order_line, 'unit_price', Decimal('0.00')),
                    source_order_line=order_line,
                    quality_approved=False,
                    quality_issue_type='',
                    batch_number='',
                    expiry_date=None,
                    notes=getattr(order_line, 'notes', ''),
                )

                # ИЗЧИСЛИ ФИНАНСОВИ ДАННИ ЗА ТОЗИ RED
                try:
                    vat_result = VATCalculationService.calculate_line_vat(
                        delivery_line,
                        entered_price=delivery_line.unit_price,
                        save=False
                    )
                    if vat_result.ok and vat_result.data:
                        # ПРАВИЛЕН MAPPING от VATCalculationService към DeliveryLine полета
                        data = vat_result.data
                        delivery_line.subtotal = data.get('line_total_without_vat', Decimal('0.00'))
                        delivery_line.vat_total = data.get('line_vat_amount', Decimal('0.00'))
                        delivery_line.total = data.get('line_total_with_vat', Decimal('0.00'))
                        delivery_line.discount_total = Decimal('0.00')  # За сега няма discount
                        delivery_line.save(update_fields=['net_amount', 'vat_amount', 'gross_amount', 'discount_amount'])
                        logger.debug(f"Line {delivery_line.line_number}: calculated totals={delivery_line.total}")
                    else:
                        logger.warning(
                            f"Line VAT calculation failed for line {delivery_line.line_number}: {vat_result.msg}")
                except Exception as e:
                    logger.warning(f"Line VAT calculation error for line {delivery_line.line_number}: {e}")

                lines_created += 1

            # ===================================================================
            # СТЪПКА 4: ИЗЧИСЛИ TOTALS
            # ===================================================================
            try:
                totals_result = VATCalculationService.calculate_document_vat(delivery)
                if not totals_result.ok:
                    logger.warning(f"VAT service failed: {totals_result.msg}")
                    return Result.error(
                        'VAT_CALCULATION_ERROR',
                        f'VAT calculation failed: {totals_result.msg}'
                    )
            except Exception as e:
                logger.error(f"Totals calculation failed: {e}")
                return Result.error(
                    'TOTALS_CALCULATION_ERROR',
                    f'Failed to calculate totals: {str(e)}'
                )

            return Result.success(
                {
                    'delivery': delivery,
                    'lines_created': lines_created,
                    'order_status': order.status,
                    'delivery_status': delivery.status,
                    'document_number': delivery.document_number,
                    'totals': {
                        'subtotal': float(delivery.subtotal or 0),
                        'vat_total': float(delivery.vat_total or 0),
                        'total': float(delivery.total or 0)
                    }
                },
                f'Successfully created delivery {delivery.document_number} from order {order.document_number}'
            )

        except Exception as e:
            logger.error(f"Delivery creation failed: {str(e)}")
            return Result.error(
                'DELIVERY_CREATION_ERROR',
                f'Failed to create delivery: {str(e)}'
            )


    # ===================================================================
    # SAFE FIELD ACCESS HELPER
    # ===================================================================

    def safe_get_vat_field(document):
        """
        Helper to safely get VAT field regardless of naming convention
        """
        # Try different possible field names
        vat_field_names = [
            'prices_entered_with_vat',
            'prices_include_vat',
            'price_includes_vat',
            'vat_included'
        ]

        for field_name in vat_field_names:
            if hasattr(document, field_name):
                return getattr(document, field_name)

        # Fallback: check location settings
        if hasattr(document, 'location') and document.location:
            if hasattr(document.location, 'purchase_prices_include_vat'):
                return document.location.purchase_prices_include_vat

        # Ultimate fallback
        return False  # Assume prices exclude VAT for B2B purchases

    # =====================
    # BULK OPERATIONS
    # =====================

    @classmethod
    @transaction.atomic
    def bulk_convert_requests(cls, request_queryset, user=None) -> Result:
        """
        Bulk convert multiple approved requests to orders.

        Returns:
            Result with data={'success_count': int, 'failed_requests': list, 'orders': list}
        """
        try:
            results = []
            orders_created = []
            failed_requests = []

            for request in request_queryset:
                result = cls.convert_request_to_order(request, user)
                results.append(result)

                if result.ok:
                    orders_created.append(result.data['order'])
                else:
                    failed_requests.append({
                        'request': request.document_number,
                        'error': result.code,
                        'message': result.msg
                    })

            success_count = len(orders_created)

            return Result.success(
                {
                    'success_count': success_count,
                    'failed_count': len(failed_requests),
                    'failed_requests': failed_requests,
                    'orders': [order.document_number for order in orders_created]
                },
                f'Bulk conversion completed: {success_count} successes, {len(failed_requests)} failures'
            )

        except Exception as e:
            logger.error(f"Bulk conversion failed: {str(e)}")
            return Result.error(
                'BULK_CONVERSION_ERROR',
                f'Bulk conversion failed: {str(e)}',
                {'exception': str(e)}
            )

    @classmethod
    @transaction.atomic
    def bulk_confirm_orders(cls, order_queryset, user=None, auto_receive=False) -> Result:
        """
        Bulk confirm multiple sent orders.

        Returns:
            Result with confirmation statistics
        """
        try:
            results = []
            confirmed_orders = []
            failed_orders = []
            total_movements = 0

            for order in order_queryset:
                result = cls.confirm_purchase_order(order, user, auto_receive=auto_receive)
                results.append(result)

                if result.ok:
                    confirmed_orders.append(order)
                    total_movements += result.data.get('movements_created', 0)
                else:
                    failed_orders.append({
                        'order': order.document_number,
                        'error': result.code,
                        'message': result.msg
                    })

            success_count = len(confirmed_orders)

            return Result.success(
                {
                    'success_count': success_count,
                    'failed_count': len(failed_orders),
                    'failed_orders': failed_orders,
                    'total_movements_created': total_movements,
                    'confirmed_orders': [order.document_number for order in confirmed_orders]
                },
                f'Bulk confirmation completed: {success_count} successes, {len(failed_orders)} failures'
            )

        except Exception as e:
            logger.error(f"Bulk confirmation failed: {str(e)}")
            return Result.error(
                'BULK_CONFIRMATION_ERROR',
                f'Bulk confirmation failed: {str(e)}',
                {'exception': str(e)}
            )

    # =====================
    # WORKFLOW ANALYSIS
    # =====================

    @classmethod
    def get_workflow_analysis(cls, queryset=None) -> Result:
        """
        Анализ на workflow състоянието.

        Returns:
            Result with workflow statistics and bottlenecks
        """
        try:
            from purchases.models import PurchaseRequest, PurchaseOrder
            from django.db.models import Count, Q

            if queryset is None:
                requests = PurchaseRequest.objects.all()
                orders = PurchaseOrder.objects.all()
            else:
                # Assume mixed queryset - separate by model
                requests = queryset.filter(
                    _meta__model_name='purchaserequest'
                ) if hasattr(queryset, 'filter') else PurchaseRequest.objects.none()

                orders = queryset.filter(
                    _meta__model_name='purchaseorder'
                ) if hasattr(queryset, 'filter') else PurchaseOrder.objects.none()

            # Request analysis
            request_stats = requests.aggregate(
                total=Count('id'),
                draft=Count('id', filter=Q(status='draft')),
                submitted=Count('id', filter=Q(status='submitted')),
                approved=Count('id', filter=Q(status='approved')),
                converted=Count('id', filter=Q(status='converted')),
                rejected=Count('id', filter=Q(status='rejected')),
            )

            # Order analysis
            order_stats = orders.aggregate(
                total=Count('id'),
                draft=Count('id', filter=Q(status='draft')),
                sent=Count('id', filter=Q(status='sent')),
                confirmed=Count('id', filter=Q(status='confirmed')),
                completed=Count('id', filter=Q(status='completed')),
                cancelled=Count('id', filter=Q(status='cancelled')),
            )

            # Bottleneck detection
            bottlenecks = []

            if request_stats['submitted'] > 10:
                bottlenecks.append({
                    'type': 'approval_bottleneck',
                    'count': request_stats['submitted'],
                    'message': 'High number of requests pending approval'
                })

            if order_stats['sent'] > 5:
                bottlenecks.append({
                    'type': 'supplier_confirmation_bottleneck',
                    'count': order_stats['sent'],
                    'message': 'Many orders waiting for supplier confirmation'
                })

            conversion_rate = (
                    request_stats['converted'] / max(request_stats['total'], 1) * 100
            )

            return Result.success(
                {
                    'request_stats': request_stats,
                    'order_stats': order_stats,
                    'conversion_rate': round(conversion_rate, 2),
                    'bottlenecks': bottlenecks,
                    'recommendations': cls._get_workflow_recommendations(request_stats, order_stats)
                },
                'Workflow analysis completed successfully'
            )

        except Exception as e:
            logger.error(f"Workflow analysis failed: {str(e)}")
            return Result.error(
                'WORKFLOW_ANALYSIS_ERROR',
                f'Workflow analysis failed: {str(e)}',
                {'exception': str(e)}
            )

    @staticmethod
    def _get_order_document_type(request_document_type):
        """
        Convert request document type to order document type using convention

        Convention:
        - purchase_request → purchase_order
        - sales_request → sales_order
        - etc.
        """


        if request_document_type.app_name == 'purchases':
            if request_document_type.type_key == 'purchase_request':
                # Търси purchase_order в същия app
                order_type = DocumentType.objects.filter(
                    app_name='purchases',
                    type_key='purchase_order',
                    is_active=True
                ).first()

                if order_type:
                    return order_type

        # Fallback към същия type ако няма convention mapping
        logger.warning(f"No convention mapping found for {request_document_type.type_key}, using same type")
        return request_document_type

    @staticmethod
    def _get_workflow_recommendations(request_stats, order_stats):
        """Generate workflow improvement recommendations"""
        recommendations = []

        total_requests = request_stats['total']
        if total_requests > 0:
            approval_rate = request_stats['approved'] / total_requests
            if approval_rate < 0.7:
                recommendations.append({
                    'type': 'improve_approval_rate',
                    'message': f'Low approval rate ({approval_rate:.1%}). Review request quality.'
                })

            pending_ratio = request_stats['submitted'] / total_requests
            if pending_ratio > 0.3:
                recommendations.append({
                    'type': 'reduce_approval_time',
                    'message': f'High pending ratio ({pending_ratio:.1%}). Consider approval automation.'
                })

        total_orders = order_stats['total']
        if total_orders > 0:
            completion_rate = order_stats['completed'] / total_orders
            if completion_rate < 0.8:
                recommendations.append({
                    'type': 'improve_order_completion',
                    'message': f'Low completion rate ({completion_rate:.1%}). Review supplier performance.'
                })

        return recommendations

    # =====================
    # PURCHASE-SPECIFIC DOCUMENT OPERATIONS - ОТ DocumentProcessingService
    # =====================



    @classmethod
    @transaction.atomic
    def process_quality_control(cls, delivery, quality_decisions=None, user=None) -> Result:
        """
        Process quality control decisions for delivery.

        FEATURES:
        - Approve/reject individual lines
        - Create inventory movements only for approved quantities
        - Track quality metrics
        - Update supplier performance

        Args:
            delivery: DeliveryReceipt instance
            quality_decisions: Dict[line_id, {'approved': bool, 'issue_type': str}]
            user: User making quality decisions

        Returns:
            Result with quality processing summary
        """
        try:
            if not quality_decisions:
                quality_decisions = {}

            lines_processed = 0
            approved_quantity = Decimal('0')
            rejected_quantity = Decimal('0')
            movements_created = 0

            for delivery_line in delivery.lines.select_related('product').all():
                line_decision = quality_decisions.get(str(delivery_line.id), {})

                # Default: approve unless explicitly rejected
                is_approved = line_decision.get('approved', True)
                issue_type = line_decision.get('issue_type', '')

                old_approval = delivery_line.quality_approved
                delivery_line.quality_approved = is_approved

                if not is_approved and issue_type:
                    delivery_line.quality_issue_type = issue_type

                delivery_line.quality_checked_by = user
                delivery_line.quality_checked_at = timezone.now()
                delivery_line.save()

                # Track quantities
                if is_approved:
                    approved_quantity += delivery_line.quantity
                else:
                    rejected_quantity += delivery_line.quantity

                # Create inventory movement only for approved items
                if is_approved and old_approval != is_approved:
                    try:
                        from inventory.services.movement_service import MovementService

                        movement_result = MovementService.create_incoming_stock(
                            location=delivery.location,
                            product=delivery_line.product,
                            quantity=delivery_line.quantity,
                            cost_price=delivery_line.unit_price,
                            document=delivery,
                            document_line=delivery_line,
                            user=user
                        )

                        if movement_result.ok:
                            movements_created += 1

                    except ImportError:
                        logger.warning("MovementService not available for quality processing")

                lines_processed += 1

            # Update delivery-level quality status
            total_quantity = approved_quantity + rejected_quantity
            approval_rate = (
                float(approved_quantity / total_quantity * 100)
                if total_quantity > 0 else 0
            )

            if approval_rate == 100:
                delivery.quality_status = 'approved'
            elif approval_rate == 0:
                delivery.quality_status = 'rejected'
            else:
                delivery.quality_status = 'partial'

            delivery.quality_checked_by = user
            delivery.quality_checked_at = timezone.now()
            delivery.save(update_fields=[
                'quality_status', 'quality_checked_by', 'quality_checked_at'
            ])



            return Result.success(
                {
                    'lines_processed': lines_processed,
                    'approved_quantity': float(approved_quantity),
                    'rejected_quantity': float(rejected_quantity),
                    'approval_rate': round(float(approval_rate), 2),
                    'movements_created': movements_created,
                    'delivery_quality_status': delivery.quality_status
                },
                f'Processed quality control for delivery {delivery.document_number}'
            )

        except Exception as e:
            logger.error(f"Quality control processing failed: {str(e)}")
            return Result.error(
                'QUALITY_CONTROL_ERROR',
                f'Failed to process quality control: {str(e)}',
                {'exception': str(e)}
            )