# purchases/services/purchase_service.py
"""
Purchase Services - ПЪЛЕН РЕФАКТОР КЪМ THIN WRAPPER

ПРИНЦИПИ:
✅ 100% delegation към DocumentService
✅ САМО purchase-specific логика (conversions, domain fields)
✅ 0% дублирана validation/status/numbering логика
✅ Semantic методи от DocumentService
❌ НЕ hardcode-ва нищо
❌ НЕ bypass-ва nomenclatures architecture
"""

from typing import List, Dict, Optional
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
import logging

from core.utils.result import Result, ErrorCategory
from core.utils.error_codes import PurchaseErrorCodes, ErrorCodes, get_error_message
from nomenclatures.services import DocumentService

User = get_user_model()
logger = logging.getLogger(__name__)


class PurchaseDocumentService:
    """
    THIN WRAPPER around DocumentService for Purchase domain

    RESPONSIBILITIES:
    - Purchase-specific field mapping and validation
    - Document type routing (delivery/order/request)
    - Purchase domain conversions
    - Pure delegation to DocumentService
    """

    def __init__(self, document, user: User):
        self.document = document
        self.user = user
        self._facade: Optional[DocumentService] = None

    @property
    def facade(self) -> DocumentService:
        """Lazy DocumentService facade creation"""
        if self._facade is None:
            self._facade = DocumentService(self.document, self.user)
        return self._facade

    # =================================================
    # DOCUMENT CREATION - ТОЛЬКО purchase field mapping
    # =================================================

    @transaction.atomic
    def create_document(
            self,
            doc_type: str,
            partner,
            location,
            lines: List[dict],
            **kwargs
    ) -> Result:
        """
        Create purchase document following USAGE_EXAMPLES.md workflow
        
        WORKFLOW:
        1. Create empty document instance with required fields
        2. DocumentService.create.html() - saves to DB with numbering/status
        3. Add lines to saved document 
        4. Calculate totals
        """
        try:
            logger.info(f"Creating {doc_type} document for partner {partner}")

            # 1. ✅ Purchase-specific line preparation and validation
            lines_data = self._prepare_lines_data(lines)
            
            # ✅ MANDATORY: Purchase documents must have at least one line
            if not lines_data:
                return Result.error(
                    'NO_LINES_PROVIDED', 
                    f'Purchase {doc_type} must have at least one valid product line'
                )
            
            # Additional check for invalid line data
            if lines and not lines_data:
                return Result.error('INVALID_LINES', f'No valid lines provided from {len(lines)} input lines')
            
            # 2. ✅ INTEGRATED VALIDATION: Use DocumentService validation methods
            validation_result = self._validate_creation_data(doc_type, partner, location, lines_data)
            if not validation_result.ok:
                logger.warning(f"Validation failed: {validation_result.msg}")
                return validation_result

            # 3. ✅ Create MINIMAL document instance (following USAGE_EXAMPLES.md pattern)
            doc_instance = self._create_minimal_instance(doc_type, partner, location, **kwargs)
            if not doc_instance:
                return Result.error('INSTANCE_CREATION_FAILED', f'Failed to create.html {doc_type} instance')

            # 4. ✅ DocumentService.create.html() - SAVES document to DB with numbering/status
            facade = DocumentService(doc_instance, self.user)
            
            create_result = facade.create()
            if not create_result.ok:
                logger.error(f"DocumentService.create.html() failed: {create_result.msg}")
                return create_result
            
            logger.info(f"Document saved to DB: {doc_instance.document_number} (PK={doc_instance.pk})")
            
            # 5. ✅ Add lines to SAVED document (now has PK and can have related objects)
            for line_data in lines_data:
                # DocumentService.add_line expects: product, quantity, **kwargs
                product = line_data.pop('product')
                quantity = line_data.pop('quantity')
                
                line_result = facade.add_line(product, quantity, **line_data)
                if not line_result.ok:
                    logger.error(f"Failed to add line: {line_result.msg}")
                    return line_result  # Stop on first failure
                    
                logger.debug(f"Added line: {product} x{quantity}")
            
            # 6. ✅ Calculate totals on completed document
            totals_result = facade.calculate_totals()
            if not totals_result.ok:
                logger.warning(f"Totals calculation failed: {totals_result.msg}")
                # Don't fail document creation for totals issues
            
            logger.info(f"✅ Successfully created {doc_type} {doc_instance.document_number} with {len(lines_data)} lines")
            
            return Result.success({
                'document': doc_instance,
                'status': doc_instance.status,
                'number': doc_instance.document_number
            })

        except Exception as e:
            logger.error(f"Document creation failed: {e}")
            return Result.error('CREATION_FAILED', f'Document creation failed: {str(e)}')

    def _create_minimal_instance(self, doc_type: str, partner, location, **kwargs):
        """
        Create MINIMAL document instance following USAGE_EXAMPLES.md pattern
        
        Pattern: request = PurchaseRequest(); request.supplier = supplier; request.location = warehouse
        DocumentService(request, user).create.html()  # This saves with numbering/status
        """
        try:
            if doc_type == 'delivery':
                from purchases.models import DeliveryReceipt
                # MINIMAL - only required fields
                doc_instance = DeliveryReceipt()
                doc_instance.partner = partner  # Required
                doc_instance.location = location  # Required
                doc_instance.document_date = kwargs.get('document_date', timezone.now().date())
                doc_instance.delivery_date = kwargs.get('delivery_date', kwargs.get('document_date', timezone.now().date()))
                doc_instance.received_by = kwargs.get('received_by', self.user)
                doc_instance.supplier_delivery_reference = kwargs.get('supplier_delivery_reference', '')
                doc_instance.notes = kwargs.get('comments', '')
                return doc_instance

            elif doc_type == 'order':
                from purchases.models import PurchaseOrder
                doc_instance = PurchaseOrder()
                doc_instance.partner = partner
                doc_instance.location = location
                doc_instance.document_date = kwargs.get('document_date', timezone.now().date())
                doc_instance.expected_delivery_date = kwargs.get('expected_delivery_date')
                doc_instance.supplier_order_reference = kwargs.get('supplier_order_reference', '')
                doc_instance.notes = kwargs.get('comments', '')
                return doc_instance

            elif doc_type == 'request':
                from purchases.models import PurchaseRequest
                doc_instance = PurchaseRequest()
                doc_instance.partner = partner
                doc_instance.location = location
                doc_instance.document_date = kwargs.get('document_date', timezone.now().date())
                doc_instance.requested_by = kwargs.get('requested_by', self.user)
                doc_instance.priority = kwargs.get('priority', 'normal')
                doc_instance.justification = kwargs.get('justification', '')
                doc_instance.notes = kwargs.get('comments', '')
                return doc_instance

            else:
                logger.error(f"Unknown document type: {doc_type}")
                return None

        except Exception as e:
            logger.error(f"Minimal instance creation failed for {doc_type}: {e}")
            return None

    def _create_empty_instance(self, doc_type: str, partner, location, **kwargs):
        """
        Create document instance WITHOUT saving to database

        CHANGED:
        - БЕЗ 'status': 'draft' hardcoding!
        - БЕЗ .objects.create.html() calls
        - САМО purchase-specific fields
        """
        try:
            # Common fields for all purchase documents
            base_data = {
                'partner': partner,
                'location': location,
                'document_date': kwargs.get('document_date', timezone.now().date()),
                'notes': kwargs.get('comments', ''),
                'created_by': self.user,
                'updated_by': self.user
                # ✅ НЕ сетай status! DocumentService go прави!
            }

            # Document-specific fields
            if doc_type == 'delivery':
                from purchases.models import DeliveryReceipt
                base_data.update({
                    'received_by': kwargs.get('received_by', self.user),
                    'delivery_date': kwargs.get('delivery_date', kwargs.get('document_date', timezone.now().date())),
                    'supplier_delivery_reference': kwargs.get('supplier_delivery_reference', ''),
                })
                return DeliveryReceipt(**base_data)  # ✅ БЕЗ .create.html()!

            elif doc_type == 'order':
                from purchases.models import PurchaseOrder
                base_data.update({
                    'expected_delivery_date': kwargs.get('expected_delivery_date'),
                    'supplier_order_reference': kwargs.get('supplier_order_reference', ''),
                })
                return PurchaseOrder(**base_data)  # ✅ БЕЗ .create.html()!

            elif doc_type == 'request':
                from purchases.models import PurchaseRequest
                base_data.update({
                    'requested_by': kwargs.get('requested_by', self.user),
                    'priority': kwargs.get('priority', 'normal'),
                    'justification': kwargs.get('justification', ''),
                })
                return PurchaseRequest(**base_data)  # ✅ БЕЗ .create.html()!

            else:
                logger.error(f"Unknown document type: {doc_type}")
                return None

        except Exception as e:
            logger.error(f"Empty instance creation failed for {doc_type}: {e}")
            return None

    # =================================================
    # SEMANTIC ACTIONS - PURE DELEGATION
    # =================================================

    def approve(self, comments: str = '') -> Result:
        """✅ PURE DELEGATION: Approve document"""
        return self.facade.approve(comments)

    def submit_for_approval(self, comments: str = '') -> Result:
        """✅ PURE DELEGATION: Submit for approval"""
        return self.facade.submit_for_approval(comments)

    def reject(self, comments: str = '') -> Result:
        """✅ PURE DELEGATION: Reject document"""
        return self.facade.reject(comments)

    def return_to_draft(self, comments: str = '') -> Result:
        """✅ PURE DELEGATION: Return to draft"""
        return self.facade.return_to_draft(comments)

    def cancel(self, comments: str = '') -> Result:
        """✅ PURE DELEGATION: Cancel document"""
        return self.facade.cancel(comments)

    # =================================================
    # QUERY/VALIDATION DELEGATION METHODS  
    # =================================================

    def can_edit(self) -> bool:
        """✅ PURE DELEGATION: Check if document can be edited"""
        return self.facade.can_edit()
    
    def can_delete(self) -> bool:
        """✅ PURE DELEGATION: Check if document can be deleted"""
        return self.facade.can_delete()


    # =================================================
    # PURCHASE-SPECIFIC BUSINESS LOGIC
    # =================================================

    def convert_to_delivery(self, delivery_data: Dict) -> Result:
        """
        Convert PurchaseOrder → DeliveryReceipt
        ТОВА е purchase-specific логика която ОСТАВА тук
        """
        try:
            if not hasattr(self.document, 'lines'):
                return Result.error('NO_LINES', 'Source document has no lines')

            # Validate conversion is allowed
            if self.document.status not in ['approved', 'confirmed', 'sent']:
                return Result.error(
                    'INVALID_STATUS_FOR_CONVERSION',
                    f'Cannot convert document with status: {self.document.status}'
                )

            # Map order lines to delivery lines
            delivery_lines = []
            for order_line in self.document.lines.all():
                delivery_lines.append({
                    'product': order_line.product,
                    'quantity': order_line.quantity,
                    'unit_price': order_line.unit_price,
                    'source_line': order_line  # Reference to original
                })

            # Create delivery with proper linking - use class method!
            result = DeliveryReceiptService.create(
                user=self.user,  # ✅ Pass user as parameter
                partner=self.document.partner,
                location=self.document.location,
                lines=delivery_lines,
                source_document=self.document,  # Link to order
                **delivery_data
            )

            if result.ok:
                # Update order status to 'delivered' or similar
                delivered_result = self.facade.transition_to('delivered', 'Converted to delivery')
                if not delivered_result.ok:
                    logger.warning(f"Failed to update order status: {delivered_result.msg}")

            return result

        except Exception as e:
            logger.error(f"Order to delivery conversion failed: {e}")
            return Result.error('CONVERSION_FAILED', f'Conversion failed: {str(e)}')

    def _prepare_lines_data(self, lines: List[dict]) -> List[dict]:
        """
        Purchase-specific line preparation
        ТОВА също остава - purchase domain logic
        """
        prepared_lines = []

        for line in lines:
            if not line.get('product') or not line.get('quantity'):
                continue

            line_data = {
                'product': line['product'],
                'quantity': line['quantity'],
                'unit_price': line.get('unit_price', 0),
                'vat_rate': line.get('vat_rate', Decimal('0.20')),
                'discount_rate': line.get('discount_rate', 0),
                'notes': line.get('notes', '')
            }

            # Include unit if provided
            if 'unit' in line:
                line_data['unit'] = line['unit']

            # Purchase-specific calculations
            if hasattr(line['product'], 'purchase_price'):
                line_data['cost_price'] = line['product'].purchase_price

            prepared_lines.append(line_data)

        return prepared_lines

    def _validate_creation_data(self, doc_type: str, partner, location, lines_data: List[dict]) -> Result:
        """
        🆕 Enhanced validation using new Result pattern with field-level errors
        """
        validation_errors = {}
        field_errors = {}
        
        try:
            # 1. Partner validation
            if not partner:
                field_errors['partner_id'] = [get_error_message(PurchaseErrorCodes.DELIVERY_PARTNER_REQUIRED)]
            elif not getattr(partner, 'is_active', True):
                field_errors['partner_id'] = [get_error_message(PurchaseErrorCodes.SUPPLIER_NOT_ACTIVE)]

            # 2. Location validation  
            if not location:
                field_errors['location_id'] = [get_error_message(PurchaseErrorCodes.DELIVERY_LOCATION_REQUIRED)]
            elif not getattr(location, 'is_active', True):
                field_errors['location_id'] = [get_error_message(PurchaseErrorCodes.LOCATION_NOT_AVAILABLE)]

            # 3. Lines validation with field-level errors
            if not lines_data:
                return Result.validation_error(
                    get_error_message(PurchaseErrorCodes.DELIVERY_NO_LINES),
                    field_errors={'__all__': [get_error_message(PurchaseErrorCodes.DELIVERY_NO_LINES)]}
                )

            line_field_errors = {}
            total_amount = Decimal('0.00')
            
            for i, line in enumerate(lines_data):
                line_errors = {}
                
                # Product validation
                product = line.get('product')
                if not product:
                    line_errors['product'] = [get_error_message(PurchaseErrorCodes.DELIVERY_PRODUCT_REQUIRED)]
                elif not getattr(product, 'is_active', True):
                    line_errors['product'] = ['Този продукт вече не е активен']
                elif not getattr(product, 'is_purchasable', True):
                    line_errors['product'] = [get_error_message(PurchaseErrorCodes.PRODUCT_NOT_PURCHASABLE)]

                # Quantity validation
                quantity = line.get('quantity', 0)
                if not quantity or quantity <= 0:
                    line_errors['quantity'] = [get_error_message(PurchaseErrorCodes.DELIVERY_QUANTITY_INVALID)]
                elif quantity > Decimal('10000'):
                    line_errors['quantity'] = [get_error_message(PurchaseErrorCodes.QUANTITY_EXCEEDS_LIMIT)]

                # Price validation
                unit_price = line.get('unit_price', 0)
                if unit_price < 0:
                    line_errors['unit_price'] = ['Цената не може да е отрицателна']
                elif unit_price > Decimal('100000'):
                    line_errors['unit_price'] = [get_error_message(PurchaseErrorCodes.PRICE_OUT_OF_RANGE)]

                # Business rules validation
                if product and quantity and unit_price:
                    line_total = Decimal(str(quantity)) * Decimal(str(unit_price))
                    total_amount += line_total
                    
                    # Warn for very high line totals
                    if line_total > Decimal('50000'):
                        if 'unit_price' not in line_errors:
                            line_errors['unit_price'] = []
                        line_errors['unit_price'].append('Общата сума за реда е много висока')

                if line_errors:
                    line_field_errors[f'line_{i}'] = line_errors

            # 4. Document-level validation
            if total_amount > Decimal('1000000'):
                validation_errors['total_too_high'] = 'Общата сума на документа е твърде висока'

            # 5. Compile all validation errors
            if field_errors or line_field_errors or validation_errors:
                all_field_errors = {**field_errors}
                all_field_errors.update(line_field_errors)
                
                error_msg = 'Моля поправете грешките във формата'
                if validation_errors:
                    error_msg += f': {", ".join(validation_errors.values())}'

                return Result.validation_error(
                    error_msg,
                    field_errors=all_field_errors,
                    context={
                        'validation_errors': validation_errors,
                        'total_amount': str(total_amount),
                        'line_count': len(lines_data)
                    }
                )

            logger.info(f"✅ All validation passed for {doc_type} (amount: {total_amount})")
            return Result.success({
                'expected_amount': total_amount, 
                'line_count': len(lines_data),
                'validation_passed': True
            })
            
        except Exception as e:
            logger.error(f"Validation system error: {e}")
            return Result.error(
                ErrorCodes.CONFIGURATION_ERROR,
                f'Validation system failed: {str(e)}',
                category=ErrorCategory.SYSTEM,
                context={'exception': str(e), 'doc_type': doc_type}
            )


# =================================================
# SPECIALIZED PURCHASE SERVICES - THIN WRAPPERS
# =================================================

class DeliveryReceiptService(PurchaseDocumentService):
    """Delivery Receipt operations"""

    @classmethod
    def create(cls, user: User, partner, location, lines: List[dict], target_status: str = None, **kwargs) -> Result:
        """Create new delivery receipt with optional target status"""
        logger.info(f"🔥 DeliveryReceiptService.create.html called with target_status='{target_status}'")
        service = cls(None, user)  # No document yet
        
        # Create document first
        result = service.create_document('delivery', partner, location, lines, **kwargs)
        
        if not result.ok:
            return result
            
        document = result.data['document']
        
        # If target_status is specified and different from current, transition to it
        logger.info(f"Checking target_status: '{target_status}' vs current status: '{document.status}'")
        
        if target_status and document.status != target_status:
            logger.info(f"Transitioning from '{document.status}' to '{target_status}'")
            service.document = document  # Set document for transition
            transition_result = service.facade.transition_to(target_status)
            
            if not transition_result.ok:
                logger.error(f"Status transition failed: {transition_result.msg}")
                return Result.error(
                    'STATUS_TRANSITION_FAILED',
                    f"Document created but status transition failed: {transition_result.msg}",
                    data={'document': document, 'transition_error': transition_result.msg}
                )
            
            # Refresh document from database to get updated status
            document.refresh_from_db()
            logger.info(f"Status transition successful. New status: '{document.status}'")
            # Update result with final status
            result.data['status'] = document.status
            result.data['final_status'] = document.status
        else:
            logger.info(f"No status transition needed. target_status='{target_status}', current='{document.status}'")
            result.data['final_status'] = document.status
            
        return result


class PurchaseOrderService(PurchaseDocumentService):
    """Purchase Order operations"""

    @classmethod
    def create(cls, user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        """Create new purchase order"""
        service = cls(None, user)  # No document yet
        return service.create_document('order', partner, location, lines, **kwargs)


class PurchaseRequestService(PurchaseDocumentService):
    """Purchase Request operations"""

    @classmethod
    def create(cls, user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        """Create new purchase request"""
        service = cls(None, user)  # No document yet
        return service.create_document('request', partner, location, lines, **kwargs)


# =================================================
# BACKWARD COMPATIBILITY EXPORTS
# =================================================

__all__ = [
    'PurchaseDocumentService',
    'DeliveryReceiptService',
    'PurchaseOrderService',
    'PurchaseRequestService'
]