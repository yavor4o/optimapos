# purchases/services/purchase_service.py - CLEAN THIN WRAPPER

"""
Purchase Services - 100% Nomenclatures Integration

ПРИНЦИП:
- ВСИЧКО чрез nomenclatures/DocumentService facade
- САМО purchase domain-specific логика (conversions)
- 0% дублирана validation/status/line логика
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
    Thin wrapper за purchase documents - делегира ВСИЧКО към DocumentService
    """
    
    def __init__(self, document=None, user: User = None):
        # ОСНОВЕН ПРИНЦИП: Всичко чрез фасада!
        self.\
            facade = DocumentService(document, user)
        self.document = document
        self.user = user
    
    def create_document(self, doc_type: str, partner, location, lines: List[dict], **kwargs) -> Result:
        """
        Create purchase document using DocumentService facade
        """
        try:
            # 1. Подготви данни за integrated validation
            lines_data = []
            for line in lines:
                line_data = {
                    'product': line['product'],
                    'quantity': Decimal(str(line['quantity'])),
                    **{k: v for k, v in line.items() if k not in ['product', 'quantity']}
                }
                lines_data.append(line_data)
            
            # 2. Валидация чрез фасада с integrated validation
            validation = self.facade.validate_for_purchase_creation(
                partner, location, lines_data
            )
            if not validation.ok:
                logger.error(f"Validation failed for {doc_type}: {validation.msg}")
                logger.error(f"Validation data: {validation.data}")
                return validation
            
            # 3. Създай document instance
            doc_instance = self._create_instance(doc_type, partner, location, **kwargs)
            if not doc_instance:
                return Result.error('INSTANCE_CREATION_FAILED', f'Could not create {doc_type}')
            
            # 4. Setup чрез фасада
            doc_facade = DocumentService(doc_instance, self.user)
            setup_result = doc_facade.create()
            if not setup_result.ok:
                return setup_result
            
            # 5. Добави lines чрез фасада
            added_lines = []
            for line_data in lines_data:
                line_result = doc_facade.add_line(**line_data)
                if line_result.ok:
                    added_lines.append(line_result.data['line'])
                else:
                    logger.warning(f"Line add failed: {line_result.msg}")
            
            # 6. Калкулирай totals чрез фасада
            totals_result = doc_facade.calculate_totals()
            if not totals_result.ok:
                logger.warning(f"Failed to calculate totals: {totals_result.msg}")
            
            return Result.success(
                data={'document': doc_instance, 'lines': added_lines},
                msg=f'{doc_type.title()} created with {len(added_lines)} lines'
            )
            
        except Exception as e:
            logger.error(f"Error creating {doc_type}: {e}")
            return Result.error('CREATION_ERROR', str(e))
    
    def _create_instance(self, doc_type: str, partner, location, **kwargs):
        """Create document instance with correct fields"""
        base_data = {
            'partner': partner,
            'location': location,
            'document_date': kwargs.get('document_date', timezone.now().date()),
            'notes': kwargs.get('comments', ''),
            'status': 'draft',
            'created_by': self.user,
            'updated_by': self.user  # BaseDocument требует updated_by
        }
        
        try:
            
            if doc_type == 'request':
                from purchases.models import PurchaseRequest
                # PurchaseRequest има required_by_date, не expected_delivery_date
                base_data['required_by_date'] = kwargs.get('required_by_date') or kwargs.get('expected_delivery_date')
                return PurchaseRequest.objects.create(**base_data)
                
            elif doc_type == 'order':
                from purchases.models import PurchaseOrder
                base_data['expected_delivery_date'] = kwargs.get('expected_delivery_date')
                return PurchaseOrder.objects.create(**base_data)
                
            elif doc_type == 'delivery':
                from purchases.models import DeliveryReceipt
                # DeliveryReceipt има задължителни полета
                base_data.update({
                    'received_by': self.user,  # Who received the delivery
                    'delivery_date': kwargs.get('document_date', timezone.now().date())
                })
                # Note: received_at has auto_now_add=True so Django sets it automatically
                return DeliveryReceipt.objects.create(**base_data)
                
        except Exception as e:
            logger.error(f"Instance creation failed for {doc_type}: {e}")
            logger.error(f"Base data was: {base_data}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None
    
    # =================================================
    # DELEGATION METHODS - Всичко към фасада
    # =================================================
    
    def submit_for_approval(self, comments='') -> Result:
        return self.facade.transition_to('pending_approval', comments)
    
    def approve(self, comments='') -> Result:
        """Approve document - for Delivery Receipt use 'completed' status"""
        try:
            # For Delivery Receipt documents, approval means completion
            # Based on available statuses: draft, completed, cancelled
            target_status = 'completed'
            
            logger.info(f"Approving {self.document.document_type.name} {self.document.document_number} -> {target_status}")
            
            return self.facade.transition_to(target_status, comments)
            
        except Exception as e:
            logger.error(f"Approval failed for {self.document.document_number}: {e}")
            return Result.error('APPROVAL_ERROR', str(e))
    
    def reject(self, comments='') -> Result:
        """Reject document - for Delivery Receipt use 'cancelled' status"""
        try:
            # For Delivery Receipt documents, rejection means cancellation
            # Based on available statuses: draft, completed, cancelled
            target_status = 'cancelled'
            
            logger.info(f"Rejecting {self.document.document_type.name} {self.document.document_number} -> {target_status}")
            
            return self.facade.transition_to(target_status, comments)
            
        except Exception as e:
            logger.error(f"Rejection failed for {self.document.document_number}: {e}")
            return Result.error('REJECTION_ERROR', str(e))
    
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
    # DOMAIN-SPECIFIC: Purchase conversions
    # =================================================
    
    @transaction.atomic
    def convert_to_order(self, **order_data) -> Result:
        """Convert Request → Order using facade operations"""
        try:
            # Check if document type allows conversion to order using type_key
            if not self.document:
                return Result.error('INVALID_CONVERSION', 'No document provided')
                
            # Use document type key instead of model name
            doc_type_key = getattr(self.document.document_type, 'type_key', None)
            if doc_type_key not in ['purchase_request', 'purchaserequest']:
                # Fallback to model name for backward compatibility
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
                # Update request status
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
            # Check if document type allows conversion to delivery using type_key
            if not self.document:
                return Result.error('INVALID_CONVERSION', 'No document provided')
                
            # Use document type key instead of model name
            doc_type_key = getattr(self.document.document_type, 'type_key', None)
            if doc_type_key not in ['purchase_order', 'purchaseorder']:
                # Fallback to model name for backward compatibility
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
                    'entered_price': order_line.unit_price,  # Trigger VAT calculations  
                    'unit': order_line.unit
                })
            
            # Създай delivery чрез service
            delivery_result = self.create_document(
                'delivery',
                self.document.partner,
                self.document.location,
                lines,
                document_date=delivery_data.get('delivery_date') or timezone.now().date(),
                comments=f'Converted from order {self.document.document_number}'
            )
            
            if delivery_result.ok:
                # Update order status
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
# CONVENIENCE SERVICES - Ultra-thin wrappers
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