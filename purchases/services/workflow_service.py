# purchases/services/workflow_service.py - FIXED WITH REAL METHOD SIGNATURES

from typing import Dict, Any, Optional, List
from django.db import transaction
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging

from core.utils.result import Result
from nomenclatures.services import DocumentService, ApprovalService
from products.services import ProductValidationService
from inventory.services import InventoryService
from pricing.services import PricingService
from purchases.models import PurchaseRequest, PurchaseRequestLine

User = get_user_model()
logger = logging.getLogger(__name__)


class PurchaseWorkflowService:
    """
    Purchase-specific workflow orchestration service
    FIXED: Uses actual service method signatures from codebase
    """

    @staticmethod
    @transaction.atomic
    def create_purchase_request(
            location,
            user: User,
            supplier=None,
            required_by_date=None,
            priority: str = 'normal',
            notes: str = '',
            lines_data: list = None
    ) -> Result:
        """
        Създава нова purchase request с правилна service integration

        Args:
            location: InventoryLocation
            user: User който създава заявката
            supplier: Supplier (опционално)
            required_by_date: Дата за доставка
            priority: low/normal/high/urgent
            notes: Бележки
            lines_data: List of dicts с данни за редовете
                [{'product': Product, 'requested_quantity': Decimal, 'unit': Unit, 'estimated_price': Decimal, 'notes': str}]

        Returns:
            Result със създадената заявка или грешка
        """
        try:
            logger.info(f"Starting purchase request creation for location {location.code} by user {user.username}")

            # ============================================================================
            # PHASE 1: INPUT VALIDATION
            # ============================================================================

            validation_result = PurchaseWorkflowService._validate_input_data(
                location, user, supplier, priority, lines_data
            )
            if not validation_result.ok:
                return validation_result

            # ============================================================================
            # PHASE 2: BUSINESS VALIDATION USING REAL SERVICES
            # ============================================================================

            # Validate location is active
            if not getattr(location, 'is_active', True):
                return Result.error(
                    code='INACTIVE_LOCATION',
                    msg=f'Location {location.code} is not active'
                )

            # Validate supplier if provided
            if supplier and not getattr(supplier, 'is_active', True):
                return Result.error(
                    code='INACTIVE_SUPPLIER',
                    msg=f'Supplier {supplier.code} is not active'
                )

            # Validate and enhance lines using REAL service methods
            enhanced_lines_data = []
            total_estimated_value = Decimal('0')

            for index, line_data in enumerate(lines_data, start=1):
                line_result = PurchaseWorkflowService._validate_and_enhance_line(
                    line_data, index, location, supplier
                )
                if not line_result.ok:
                    return line_result

                enhanced_line = line_result.data
                enhanced_lines_data.append(enhanced_line)

                # Calculate estimated total
                if enhanced_line.get('estimated_price') and enhanced_line.get('requested_quantity'):
                    total_estimated_value += enhanced_line['estimated_price'] * enhanced_line['requested_quantity']

            logger.info(f"Validated {len(enhanced_lines_data)} lines, total estimated value: {total_estimated_value}")

            # ============================================================================
            # PHASE 3: DOCUMENT CREATION VIA DOCUMENTSERVICE
            # ============================================================================

            # Prepare document data with explicit type annotation
            request_data: Dict[str, Any] = {
                'location': location,
                'priority': priority,
                'notes': notes,
                'created_by': user,
                'updated_by': user,
            }

            # Add supplier if provided (GenericFK)
            if supplier:
                from django.contrib.contenttypes.models import ContentType
                partner_content_type = ContentType.objects.get_for_model(supplier)
                request_data['partner_content_type'] = partner_content_type
                request_data['partner_object_id'] = supplier.pk

            if required_by_date:
                request_data['required_by_date'] = required_by_date

            # Create document via DocumentService - USING REAL METHOD SIGNATURE
            create_result = DocumentService.create_document(
                model_class=PurchaseRequest,
                data=request_data,
                user=user,
                location=location
            )

            if not create_result.ok:
                logger.error(f"Failed to create purchase request: {create_result.msg}")
                return create_result

            purchase_request = create_result.data['document']
            logger.info(f"Created purchase request {purchase_request.document_number}")

            # ============================================================================
            # PHASE 4: LINE CREATION WITH REAL SERVICE INTEGRATION
            # ============================================================================

            created_lines = []
            lines_total = Decimal('0')

            for index, line_data in enumerate(enhanced_lines_data, start=1):
                line = PurchaseRequestLine.objects.create(
                    document=purchase_request,
                    line_number=index,
                    product=line_data['product'],
                    requested_quantity=line_data['requested_quantity'],
                    unit=line_data['unit'],
                    estimated_price=line_data.get('estimated_price'),
                    description=line_data.get('notes', '')
                )
                created_lines.append(line)

                if line.estimated_price and line.requested_quantity:
                    lines_total += line.estimated_price * line.requested_quantity

                logger.debug(f"Created line {line.line_number}: {line.product.code} x {line.requested_quantity}")

            # ============================================================================
            # PHASE 5: FINANCIAL CALCULATIONS VIA DOCUMENTSERVICE
            # ============================================================================

            # Try to recalculate document totals using DocumentService
            if hasattr(purchase_request, 'subtotal'):
                try:
                    recalc_result = DocumentService.recalculate_document_lines(
                        purchase_request, user=user, recalc_vat=True, update_pricing=False
                    )
                    if recalc_result.ok:
                        logger.info(f"Recalculated document totals: {getattr(purchase_request, 'total', 'N/A')}")
                except Exception as e:
                    logger.warning(f"Could not recalculate document totals: {e}")

            # ============================================================================
            # PHASE 6: APPROVAL WORKFLOW INITIATION - USING REAL APPROVALSERVICE
            # ============================================================================

            try:
                # Check if approval is needed using ApprovalService
                approval_result = ApprovalService.get_available_transitions(purchase_request, user)
                if approval_result.ok:
                    transitions = approval_result.data.get('transitions', [])
                    if transitions:
                        logger.info(f"Available approval transitions: {len(transitions)} options")

                        # Try to find submission transition
                        submission_transitions = [t for t in transitions if 'submit' in t['to_status'].lower()]
                        if submission_transitions:
                            logger.info(f"Submission transition available: {submission_transitions[0]['to_status']}")

            except Exception as e:
                logger.warning(f"Could not check approval workflow: {e}")

            # ============================================================================
            # PHASE 7: SUCCESS RESPONSE WITH COMPREHENSIVE DATA
            # ============================================================================

            success_data = {
                'document': purchase_request,
                'document_number': purchase_request.document_number,
                'document_id': purchase_request.pk,
                'status': purchase_request.status,
                'lines_count': len(created_lines),
                'total_estimated_value': total_estimated_value,
                'location_code': location.code,
                'supplier_code': supplier.code if supplier else None,
                'priority': priority,
                'requires_approval': hasattr(purchase_request, 'document_type') and getattr(
                    purchase_request.document_type, 'requires_approval', False),
                'created_at': purchase_request.created_at,
                'lines_summary': [
                    {
                        'line_number': line.line_number,
                        'product_code': line.product.code,
                        'quantity': line.requested_quantity,
                        'estimated_price': line.estimated_price,
                    }
                    for line in created_lines
                ]
            }

            logger.info(
                f"✅ Successfully created purchase request {purchase_request.document_number} "
                f"with {len(created_lines)} lines, estimated value: {total_estimated_value}"
            )

            return Result.success(
                data=success_data,
                msg=f'Purchase request {purchase_request.document_number} created successfully'
            )

        except Exception as e:
            logger.error(f"❌ Error creating purchase request: {e}", exc_info=True)
            return Result.error(
                code='CREATE_REQUEST_ERROR',
                msg=f'Failed to create purchase request: {str(e)}'
            )

    # ============================================================================
    # PRIVATE HELPER METHODS - USING REAL SERVICE SIGNATURES
    # ============================================================================

    @staticmethod
    def _validate_input_data(location, user, supplier, priority, lines_data) -> Result:
        """Validates basic input data before processing"""
        errors = []

        if not location:
            errors.append("Location is required")
        if not user:
            errors.append("User is required")
        if not lines_data or len(lines_data) == 0:
            errors.append("At least one line item is required")

        # Priority validation
        valid_priorities = ['low', 'normal', 'high', 'urgent']
        if priority not in valid_priorities:
            errors.append(f"Invalid priority '{priority}'. Must be one of: {valid_priorities}")

        # Lines data validation
        if lines_data:
            for index, line in enumerate(lines_data, start=1):
                if not isinstance(line, dict):
                    errors.append(f"Line {index}: must be a dictionary")
                    continue

                if not line.get('product'):
                    errors.append(f"Line {index}: product is required")

                if not line.get('requested_quantity'):
                    errors.append(f"Line {index}: requested_quantity is required")
                else:
                    try:
                        qty = Decimal(str(line['requested_quantity']))
                        if qty <= 0:
                            errors.append(f"Line {index}: quantity must be positive")
                    except (ValueError, TypeError):
                        errors.append(f"Line {index}: invalid quantity format")

        if errors:
            return Result.error(
                code='VALIDATION_ERROR',
                msg=f"Input validation failed: {len(errors)} errors",
                data={'errors': errors}
            )

        return Result.success(data={}, msg="Input validation passed")

    @staticmethod
    def _validate_and_enhance_line(line_data, line_index, location, supplier) -> Result:
        """Validates and enhances a single line using REAL service methods"""
        try:
            product = line_data['product']
            requested_quantity = Decimal(str(line_data['requested_quantity']))

            # ============================================================================
            # PRODUCT VALIDATION via ProductValidationService - REAL METHOD
            # ============================================================================

            # Use REAL ProductValidationService.validate_purchase method
            purchase_validation = ProductValidationService.validate_purchase(
                product=product,
                quantity=requested_quantity,
                supplier=supplier
            )

            if not purchase_validation.ok:
                return Result.error(
                    code='PRODUCT_VALIDATION_FAILED',
                    msg=f"Line {line_index}: {purchase_validation.msg}",
                    data=purchase_validation.data
                )

            # ============================================================================
            # UNIT DETERMINATION
            # ============================================================================

            unit = line_data.get('unit')
            if not unit:
                # Use product base unit
                unit = getattr(product, 'base_unit', None)
                if not unit:
                    # Fallback to first active unit
                    from nomenclatures.models import UnitOfMeasure
                    unit = UnitOfMeasure.objects.filter(is_active=True).first()
                    if not unit:
                        return Result.error(
                            code='NO_UNIT_AVAILABLE',
                            msg=f'Line {line_index}: No unit of measure available for product {product.code}'
                        )

            # ============================================================================
            # PRICING via PricingService - REAL METHOD SIGNATURE
            # ============================================================================

            estimated_price = line_data.get('estimated_price')
            pricing_source = 'user_provided'

            if not estimated_price:
                # Try PricingService.get_product_pricing - REAL METHOD
                try:
                    pricing_result = PricingService.get_product_pricing(
                        location=location,
                        product=product,
                        customer=supplier,  # supplier as customer for purchase pricing
                        quantity=requested_quantity,
                        date=None
                    )
                    if pricing_result.ok:
                        estimated_price = pricing_result.data.get('cost_price') or pricing_result.data.get(
                            'final_price')
                        pricing_source = 'pricing_service'
                        logger.debug(f"Got price from PricingService: {estimated_price}")
                except Exception as e:
                    logger.warning(f"Could not get price from PricingService: {e}")

                # Fallback to InventoryService.get_cost_for_location - REAL METHOD
                if not estimated_price:
                    try:
                        cost_result = InventoryService.get_cost_for_location(location, product)
                        if cost_result.ok:
                            estimated_price = cost_result.data.get('cost_price')
                            pricing_source = 'inventory_cost'
                            logger.debug(f"Got price from inventory cost: {estimated_price}")
                    except Exception as e:
                        logger.warning(f"Could not get inventory cost: {e}")

                # Final fallback to product properties
                if not estimated_price:
                    for attr in ['cost_price', 'last_purchase_cost', 'standard_cost']:
                        if hasattr(product, attr):
                            value = getattr(product, attr)
                            if value and value > 0:
                                estimated_price = value
                                pricing_source = f'product_{attr}'
                                break

            # ============================================================================
            # ENHANCED LINE DATA COMPILATION
            # ============================================================================

            enhanced_line = {
                'product': product,
                'requested_quantity': requested_quantity,
                'unit': unit,
                'estimated_price': estimated_price,
                'notes': line_data.get('notes', ''),
                'pricing_source': pricing_source,
                'validation_data': purchase_validation.data,
                'line_index': line_index
            }

            logger.debug(f"Enhanced line {line_index}: {product.code} x {requested_quantity} @ {estimated_price}")

            return Result.success(
                data=enhanced_line,
                msg=f"Line {line_index} validated and enhanced successfully"
            )

        except Exception as e:
            logger.error(f"Error validating line {line_index}: {e}")
            return Result.error(
                code='LINE_VALIDATION_ERROR',
                msg=f'Line {line_index} validation failed: {str(e)}'
            )