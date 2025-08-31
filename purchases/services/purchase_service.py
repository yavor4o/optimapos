# purchases/services/purchase_service.py - REFACTORED TO WORK THROUGH DocumentService

"""
Purchase Services - TRUE FACADE PATTERN

ПРИНЦИП:
- DocumentService създава и управлява ВСИЧКО
- PurchaseDocumentService САМО подготвя purchase-specific данни
- НЕ bypass-ва nomenclatures архитектурата
- НЕ hardcode-ва статуси, номера или business logic
"""

from typing import List, Dict
from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

from core.utils.result import Result
from nomenclatures.services import DocumentService

User = get_user_model()
logger = logging.getLogger(__name__)


class PurchaseDocumentService:
    """
    TRUE thin wrapper за purchase documents

    Подготвя purchase-specific данни и делегира ВСИЧКО към DocumentService
    """

    def __init__(self, document=None, user: User = None):
        self.document = document
        self.user = user

        # Facade се създава при нужда, не винаги
        self._facade = None

    @property
    def facade(self) -> DocumentService:
        """Lazy facade creation"""
        if self._facade is None:
            self._facade = DocumentService(self.document, self.user)
        return self._facade

    def create_document(self, doc_type: str, partner, location, lines: List[dict], **kwargs) -> Result:
        """
        Create purchase document using PURE DocumentService delegation

        АРХИТЕКТУРЕН ПРИНЦИП:
        - DocumentService създава документа с правилен статус
        - PurchaseDocumentService САМО подготвя данните
        """
        try:
            # 1. Подготви данни за DocumentService
            lines_data = self._prepare_lines_data(lines)

            # 2. Създай EMPTY model instance (БЕЗ save в database)
            doc_instance = self._create_empty_instance(doc_type, partner, location, **kwargs)
            if not doc_instance:
                return Result.error('INSTANCE_CREATION_FAILED', f'Could not create {doc_type} instance')

            # 3. DocumentService управлява ЦЕЛИЯ lifecycle
            doc_facade = DocumentService(doc_instance, self.user)

            # 4. DocumentService се грижи за validation, status, numbering, save
            creation_result = doc_facade.create(**kwargs)
            if not creation_result.ok:
                return creation_result

            # 5. Add lines чрез DocumentService
            added_lines = []
            for line_data in lines_data:
                line_result = doc_facade.add_line(**line_data)
                if line_result.ok:
                    added_lines.append(line_result.data['line'])
                else:
                    logger.warning(f"Line add failed: {line_result.msg}")

            # 6. Calculate totals чрез DocumentService
            totals_result = doc_facade.calculate_totals()
            if not totals_result.ok:
                logger.warning(f"Failed to calculate totals: {totals_result.msg}")

            # Update our facade reference
            self.document = doc_instance
            self._facade = doc_facade

            return Result.success(
                data={'document': doc_instance, 'lines': added_lines},
                msg=f'{doc_type.title()} created with {len(added_lines)} lines'
            )

        except Exception as e:
            logger.error(f"Error creating {doc_type}: {e}")
            return Result.error('CREATION_ERROR', str(e))

    def _prepare_lines_data(self, lines: List[dict]) -> List[dict]:
        """Prepare line items data for DocumentService"""
        lines_data = []
        for line in lines:
            line_data = {
                'product': line['product'],
                'quantity': Decimal(str(line['quantity'])),
                **{k: v for k, v in line.items() if k not in ['product', 'quantity']}
            }
            lines_data.append(line_data)
        return lines_data

    def _create_empty_instance(self, doc_type: str, partner, location, **kwargs):
        """
        Create model instance WITHOUT saving to database

        КЛЮЧОВ ПРИНЦИП: САМО подготвя instance, DocumentService go save-ва
        """
        try:
            # Base data БЕЗ status! DocumentService го сеща от конфигурация
            base_data = {
                'partner': partner,
                'location': location,
                'document_date': kwargs.get('document_date', timezone.now().date()),
                'notes': kwargs.get('comments', ''),
                'created_by': self.user,
                'updated_by': self.user,
                # НЕ СЕТАЙ STATUS! DocumentService използва StatusResolver!
            }

            if doc_type == 'request':
                from purchases.models import PurchaseRequest
                base_data['required_by_date'] = (
                        kwargs.get('required_by_date') or
                        kwargs.get('expected_delivery_date')
                )
                return PurchaseRequest(**base_data)  # БЕЗ .objects.create()!

            elif doc_type == 'order':
                from purchases.models import PurchaseOrder
                base_data['expected_delivery_date'] = kwargs.get('expected_delivery_date')
                return PurchaseOrder(**base_data)  # БЕЗ .objects.create()!

            elif doc_type == 'delivery':
                from purchases.models import DeliveryReceipt
                # САМО delivery-specific полета
                base_data.update({
                    'received_by': self.user,
                    'delivery_date': kwargs.get('delivery_date', kwargs.get('document_date', timezone.now().date())),
                    'supplier_delivery_reference': kwargs.get('supplier_delivery_reference', ''),
                })
                return DeliveryReceipt(**base_data)  # БЕЗ .objects.create()!
            else:
                logger.error(f"Unknown document type: {doc_type}")
                return None

        except Exception as e:
            logger.error(f"Empty instance creation failed for {doc_type}: {e}")
            return None

    # =================================================
    # PURE DELEGATION METHODS - НЕ hardcode-ват нищо
    # =================================================

    def submit_for_approval(self, comments='') -> Result:
        """Submit for approval using dynamic status resolution"""
        try:
            # Let DocumentService determine the approval status
            from nomenclatures.services._status_resolver import StatusResolver

            if self.document.document_type:
                approval_statuses = StatusResolver.get_statuses_by_semantic_type(
                    self.document.document_type, 'approval'
                )
                if approval_statuses:
                    target_status = list(approval_statuses)[0]  # First approval status
                else:
                    target_status = 'pending_approval'  # Fallback
            else:
                target_status = 'pending_approval'  # Fallback

            return self.facade.transition_to(target_status, comments)

        except Exception as e:
            logger.warning(f"Dynamic approval status failed: {e}, using fallback")
            return self.facade.transition_to('pending_approval', comments)

    def approve(self, comments='') -> Result:
        """Approve document using dynamic status resolution"""
        try:
            # Let StatusResolver determine completion status
            from nomenclatures.services._status_resolver import StatusResolver

            if self.document.document_type:
                final_statuses = StatusResolver.get_final_statuses(self.document.document_type)
                if final_statuses:
                    # Find a completion-like status
                    for status in final_statuses:
                        if any(word in status.lower() for word in ['complet', 'finish', 'done']):
                            target_status = status
                            break
                    else:
                        target_status = list(final_statuses)[0]  # First final status
                else:
                    target_status = 'completed'  # Fallback
            else:
                target_status = 'completed'  # Fallback

            logger.info(f"Approving {self.document.document_number} -> {target_status}")
            return self.facade.transition_to(target_status, comments)

        except Exception as e:
            logger.warning(f"Dynamic approval status failed: {e}, using fallback")
            return self.facade.transition_to('completed', comments)

    def reject(self, comments='') -> Result:
        """Reject document using dynamic status resolution"""
        try:
            # Let StatusResolver determine cancellation status
            from nomenclatures.services._status_resolver import StatusResolver

            if self.document.document_type:
                cancellation_statuses = StatusResolver.get_statuses_by_semantic_type(
                    self.document.document_type, 'cancellation'
                )
                if cancellation_statuses:
                    target_status = list(cancellation_statuses)[0]  # First cancellation status
                else:
                    target_status = 'cancelled'  # Fallback
            else:
                target_status = 'cancelled'  # Fallback

            logger.info(f"Rejecting {self.document.document_number} -> {target_status}")
            return self.facade.transition_to(target_status, comments)

        except Exception as e:
            logger.warning(f"Dynamic rejection status failed: {e}, using fallback")
            return self.facade.transition_to('cancelled', comments)

    # Pure delegation methods - no business logic
    def add_line(self, product, quantity, **kwargs) -> Result:
        return self.facade.add_line(product, Decimal(str(quantity)), **kwargs)

    def remove_line(self, line_number: int) -> Result:
        return self.facade.remove_line(line_number)

    def calculate_totals(self) -> Result:
        return self.facade.calculate_totals()

    def can_edit(self) -> bool:
        return self.facade.can_edit()

    def can_delete(self) -> bool:
        return self.facade.can_delete()

    def transition_to(self, status: str, comments='') -> Result:
        return self.facade.transition_to(status, comments)

    # =================================================
    # DOMAIN-SPECIFIC: Purchase conversions (unchanged)
    # =================================================

    @transaction.atomic
    def convert_to_order(self, **order_data) -> Result:
        """Convert Request → Order using facade operations"""
        try:
            if not self.document:
                return Result.error('INVALID_CONVERSION', 'No document provided')

            doc_type_key = getattr(self.document.document_type, 'type_key', None)
            if doc_type_key not in ['purchase_request', 'purchaserequest']:
                if self.document.__class__.__name__ != 'PurchaseRequest':
                    return Result.error('INVALID_CONVERSION', 'Only PurchaseRequest can convert to Order')

            if not self.facade.can_edit():
                return Result.error('CANNOT_CONVERT', 'Request cannot be modified')

            # Подготви order data
            lines = []
            for req_line in self.document.lines.all():
                lines.append({
                    'product': req_line.product,
                    'quantity': req_line.requested_quantity,
                    'unit_price': order_data.get('unit_price_override') or req_line.estimated_price or Decimal('0'),
                    'unit': req_line.unit
                })

            # Създай order чрез service
            order_result = self.create_document(
                'order',
                self.document.partner,
                self.document.location,
                lines,
                expected_delivery_date=order_data.get('expected_delivery_date') or self.document.expected_delivery_date,
                comments=f'Converted from request {self.document.document_number}'
            )

            if order_result.ok:
                self.transition_to('converted', 'Converted to order')
                return Result.success(
                    data={'order': order_result.data['document'], 'request': self.document},
                    msg=f'Request converted to order'
                )
            else:
                return order_result

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return Result.error('CONVERSION_ERROR', str(e))

    @transaction.atomic
    def convert_to_delivery(self, **delivery_data) -> Result:
        """Convert Order → Delivery using facade operations"""
        try:
            if not self.document:
                return Result.error('INVALID_CONVERSION', 'No document provided')

            doc_type_key = getattr(self.document.document_type, 'type_key', None)
            if doc_type_key not in ['purchase_order', 'purchaseorder']:
                if self.document.__class__.__name__ != 'PurchaseOrder':
                    return Result.error('INVALID_CONVERSION', 'Only PurchaseOrder can convert to Delivery')

            if not self.facade.can_edit():
                return Result.error('CANNOT_CONVERT', 'Order cannot be modified')

            # Подготви delivery lines
            lines = []
            for order_line in self.document.lines.all():
                received_qty = delivery_data.get('received_quantities', {}).get(
                    str(order_line.line_number), order_line.ordered_quantity
                )
                lines.append({
                    'product': order_line.product,
                    'quantity': received_qty,
                    'unit_price': order_line.unit_price,
                    'entered_price': order_line.unit_price,
                    'unit': order_line.unit
                })

            # Създай delivery чрез service
            delivery_result = self.create_document(
                'delivery',
                self.document.partner,
                self.document.location,
                lines,
                delivery_date=delivery_data.get('delivery_date', timezone.now().date()),
                comments=f'Converted from order {self.document.document_number}'
            )

            if delivery_result.ok:
                self.transition_to('converted', 'Converted to delivery')
                return Result.success(
                    data={'delivery': delivery_result.data['document'], 'order': self.document},
                    msg=f'Order converted to delivery'
                )
            else:
                return delivery_result

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return Result.error('CONVERSION_ERROR', str(e))


# =================================================================
# CONVENIENCE SERVICES - Ultra-thin wrappers (unchanged)
# =================================================================

class PurchaseRequestService:
    """Convenience wrapper за requests"""

    @staticmethod
    def create(user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        service = PurchaseDocumentService(user=user)
        return service.create_document('request', partner, location, lines, **kwargs)

    @staticmethod
    def convert_to_order(request, user: User, **order_data) -> Result:
        service = PurchaseDocumentService(request, user)
        return service.convert_to_order(**order_data)


class PurchaseOrderService:
    """Convenience wrapper за orders"""

    @staticmethod
    def create(user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        service = PurchaseDocumentService(user=user)
        return service.create_document('order', partner, location, lines, **kwargs)

    @staticmethod
    def convert_to_delivery(order, user: User, **delivery_data) -> Result:
        service = PurchaseDocumentService(order, user)
        return service.convert_to_delivery(**delivery_data)


class DeliveryReceiptService:
    """Convenience wrapper за deliveries"""

    @staticmethod
    def create(user: User, partner, location, lines: List[dict], **kwargs) -> Result:
        service = PurchaseDocumentService(user=user)
        return service.create_document('delivery', partner, location, lines, **kwargs)