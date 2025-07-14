# purchases/services/workflow_service.py

from typing import Dict, List, Optional, Union
from django.core.exceptions import ValidationError
from django.db import transaction

from purchases.models.deliveries import DeliveryReceipt
from purchases.models.orders import PurchaseOrder
from purchases.models.requests import PurchaseRequest


class WorkflowService:
    """Service for managing purchase workflows"""

    @staticmethod
    def get_workflow_options(document: Union[PurchaseRequest, PurchaseOrder, DeliveryReceipt]) -> Dict:
        """Get available workflow actions for document"""

        options = {
            'can_edit': document.can_be_edited(),
            'can_cancel': document.can_be_cancelled(),
            'available_actions': []
        }

        if isinstance(document, PurchaseRequest):
            if document.can_be_submitted():
                options['available_actions'].append('submit_for_approval')
            if document.can_be_approved():
                options['available_actions'].append('approve')
            if document.can_be_rejected():
                options['available_actions'].append('reject')
            if document.can_be_converted():
                options['available_actions'].append('convert_to_order')

        elif isinstance(document, PurchaseOrder):
            if document.can_be_sent():
                options['available_actions'].append('send_to_supplier')
            if document.can_be_confirmed():
                options['available_actions'].append('confirm_by_supplier')
            if document.can_be_used_for_delivery():
                options['available_actions'].append('create_delivery')

        elif isinstance(document, DeliveryReceipt):
            if document.can_be_received():
                options['available_actions'].append('receive_delivery')
            if document.can_be_completed():
                options['available_actions'].append('complete_processing')

        return options

    @staticmethod
    def execute_workflow_action(
            document: Union[PurchaseRequest, PurchaseOrder, DeliveryReceipt],
            action: str,
            user=None,
            **kwargs
    ) -> Dict:
        """Execute workflow action on document"""

        try:
            if isinstance(document, PurchaseRequest):
                return WorkflowService._execute_request_action(document, action, user, **kwargs)
            elif isinstance(document, PurchaseOrder):
                return WorkflowService._execute_order_action(document, action, user, **kwargs)
            elif isinstance(document, DeliveryReceipt):
                return WorkflowService._execute_delivery_action(document, action, user, **kwargs)
            else:
                raise ValidationError(f"Unsupported document type: {type(document)}")

        except Exception as e:
            return {
                'success': False,
                'message': str(e),
                'document': document
            }

    @staticmethod
    def _execute_request_action(request: PurchaseRequest, action: str, user=None, **kwargs) -> Dict:
        """Execute request-specific actions"""

        if action == 'submit_for_approval':
            from .request_service import RequestService
            return RequestService.submit_for_approval(request, user)

        elif action == 'approve':
            from .request_service import RequestService
            notes = kwargs.get('notes', '')
            return RequestService.approve_request(request, user, notes)

        elif action == 'reject':
            from .request_service import RequestService
            reason = kwargs.get('reason', '')
            return RequestService.reject_request(request, user, reason)

        elif action == 'convert_to_order':
            from .request_service import RequestService
            return RequestService.convert_to_order(request, user, **kwargs)

        else:
            raise ValidationError(f"Unknown request action: {action}")

    @staticmethod
    def _execute_order_action(order: PurchaseOrder, action: str, user=None, **kwargs) -> Dict:
        """Execute order-specific actions"""

        if action == 'send_to_supplier':
            from .order_service import OrderService
            return OrderService.send_to_supplier(order, user, **kwargs)

        elif action == 'confirm_by_supplier':
            from .order_service import OrderService
            supplier_reference = kwargs.get('supplier_reference', '')
            return OrderService.confirm_by_supplier(order, user, supplier_reference, **kwargs)

        elif action == 'create_delivery':
            # This would redirect to delivery creation workflow
            return {
                'success': True,
                'message': 'Ready for delivery creation',
                'redirect_to': 'delivery_creation',
                'order': order
            }

        else:
            raise ValidationError(f"Unknown order action: {action}")

    @staticmethod
    def _execute_delivery_action(delivery: DeliveryReceipt, action: str, user=None, **kwargs) -> Dict:
        """Execute delivery-specific actions"""

        if action == 'receive_delivery':
            from .delivery_service import DeliveryService
            quality_check = kwargs.get('quality_check', True)
            return DeliveryService.receive_delivery(delivery, user, quality_check)

        elif action == 'complete_processing':
            delivery.complete_processing(user)
            return {
                'success': True,
                'message': f'Delivery {delivery.document_number} processing completed',
                'delivery': delivery
            }

        else:
            raise ValidationError(f"Unknown delivery action: {action}")

    @staticmethod
    def get_workflow_status_summary() -> Dict:
        """Get summary of all workflow statuses across the system"""

        return {
            'requests': {
                'pending_approval': PurchaseRequest.objects.pending_approval().count(),
                'approved': PurchaseRequest.objects.approved().count(),
                'converted': PurchaseRequest.objects.converted().count(),
            },
            'orders': {
                'confirmed': PurchaseOrder.objects.confirmed().count(),
                'ready_for_delivery': PurchaseOrder.objects.ready_for_delivery_creation().count(),
                'overdue_delivery': PurchaseOrder.objects.overdue_delivery().count(),
            },
            'deliveries': {
                'pending_processing': DeliveryReceipt.objects.pending_processing().count(),
                'with_quality_issues': DeliveryReceipt.objects.with_quality_issues().count(),
                'received_today': DeliveryReceipt.objects.today().count(),
            }
        }