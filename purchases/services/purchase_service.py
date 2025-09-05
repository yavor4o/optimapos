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

from core.utils.result import Result
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
        Create purchase document with proper DocumentService integration

        CHANGED:
        - БЕЗ hardcoded status
        - БЕЗ manual save в DB
        - DocumentService контролира lifecycle
        """
        try:
            logger.info(f"Creating {doc_type} document for partner {partner}")

            # 1. ✅ Purchase-specific validation
            lines_data = self._prepare_lines_data(lines)
            if not lines_data:
                return Result.error('INVALID_LINES', 'No valid lines provided')

            # 2. ✅ Create EMPTY instance (БЕЗ save!)
            doc_instance = self._create_empty_instance(doc_type, partner, location, **kwargs)
            if not doc_instance:
                return Result.error('INSTANCE_CREATION_FAILED', f'Failed to create {doc_type} instance')

            # 3. ✅ DocumentService управлява всичко
            doc_facade = DocumentService(doc_instance, self.user)

            # Create document (sets proper status via StatusResolver)
            creation_result = doc_facade.create()
            if not creation_result.ok:
                return creation_result

            # 4. ✅ Add lines чрез facade
            for line_data in lines_data:
                line_result = doc_facade.add_line(**line_data)
                if not line_result.ok:
                    logger.warning(f"Failed to add line: {line_result.msg}")

            # 5. ✅ Calculate totals чрез facade
            totals_result = doc_facade.calculate_totals()
            if not totals_result.ok:
                logger.warning(f"Totals calculation failed: {totals_result.msg}")

            logger.info(f"Successfully created {doc_type} {doc_instance.document_number}")

            return Result.success({
                'document': doc_instance,
                'status': doc_instance.status,
                'number': doc_instance.document_number
            })

        except Exception as e:
            logger.error(f"Document creation failed: {e}")
            return Result.error('CREATION_FAILED', f'Document creation failed: {str(e)}')

    def _create_empty_instance(self, doc_type: str, partner, location, **kwargs):
        """
        Create document instance WITHOUT saving to database

        CHANGED:
        - БЕЗ 'status': 'draft' hardcoding!
        - БЕЗ .objects.create() calls
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
                return DeliveryReceipt(**base_data)  # ✅ БЕЗ .create()!

            elif doc_type == 'order':
                from purchases.models import PurchaseOrder
                base_data.update({
                    'expected_delivery_date': kwargs.get('expected_delivery_date'),
                    'supplier_order_reference': kwargs.get('supplier_order_reference', ''),
                })
                return PurchaseOrder(**base_data)  # ✅ БЕЗ .create()!

            elif doc_type == 'request':
                from purchases.models import PurchaseRequest
                base_data.update({
                    'requested_by': kwargs.get('requested_by', self.user),
                    'priority': kwargs.get('priority', 'normal'),
                    'justification': kwargs.get('justification', ''),
                })
                return PurchaseRequest(**base_data)  # ✅ БЕЗ .create()!

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
    
    # ❌ REMOVED: Semantic action methods - Templates will use facade.get_available_actions() directly
    
    # ❌ REMOVED: get_status_info() - No longer needed, use facade.get_available_actions() directly

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

            # Purchase-specific calculations
            if hasattr(line['product'], 'purchase_price'):
                line_data['cost_price'] = line['product'].purchase_price

            prepared_lines.append(line_data)

        return prepared_lines


# =================================================
# SPECIALIZED PURCHASE SERVICES - THIN WRAPPERS
# =================================================

class DeliveryReceiptService(PurchaseDocumentService):
    """Delivery Receipt operations"""

    @classmethod
    def create(cls, user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        """Create new delivery receipt"""
        service = cls(None, user)  # No document yet
        return service.create_document('delivery', partner, location, lines, **kwargs)


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