# purchases/services/notification_service.py

from typing import List, Dict, Optional
from django.conf import settings
from django.core.mail import send_mail, send_mass_mail
from django.db import models
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from ..models.requests import PurchaseRequest
from ..models.orders import PurchaseOrder
from ..models.deliveries import DeliveryReceipt

User = get_user_model()


class NotificationService:
    """Service for handling purchase workflow notifications"""

    # =====================
    # REQUEST NOTIFICATIONS
    # =====================

    @staticmethod
    def notify_request_approvers(request: PurchaseRequest) -> Dict:
        """Notify users who can approve requests"""

        # Get approvers
        approvers = NotificationService._get_request_approvers(request)

        if not approvers:
            return {'success': False, 'message': 'No approvers found'}

        # Prepare email data
        subject = f'Purchase Request for Approval: {request.document_number}'

        context = {
            'request': request,
            'requester': request.requested_by,
            'estimated_total': request.get_estimated_total(),
            'lines_count': request.lines.count(),
            'urgency_display': request.get_urgency_level_display(),
            'approval_url': NotificationService._get_admin_url('purchases', 'purchaserequest', request.id),
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        # Send emails
        sent_count = 0
        for approver in approvers:
            try:
                # Personalize context
                context['approver'] = approver

                message = render_to_string(
                    'purchases/emails/request_approval_needed.html',
                    context
                )

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[approver.email],
                    html_message=message
                )
                sent_count += 1

            except Exception as e:
                # Log error but continue
                continue

        return {
            'success': sent_count > 0,
            'message': f'Notifications sent to {sent_count} approvers',
            'sent_count': sent_count
        }

    @staticmethod
    def notify_request_approved(request: PurchaseRequest) -> Dict:
        """Notify requester that request was approved"""

        if not request.requested_by or not request.requested_by.email:
            return {'success': False, 'message': 'No requester email found'}

        subject = f'Purchase Request Approved: {request.document_number}'

        context = {
            'request': request,
            'requester': request.requested_by,
            'approver': request.approved_by,
            'approved_at': request.approved_at,
            'estimated_total': request.get_estimated_total(),
            'next_step': 'Your request will now be converted to a purchase order.',
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        try:
            message = render_to_string(
                'purchases/emails/request_approved.html',
                context
            )

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.requested_by.email],
                html_message=message
            )

            return {'success': True, 'message': 'Approval notification sent'}

        except Exception as e:
            return {'success': False, 'message': f'Error sending notification: {str(e)}'}

    @staticmethod
    def notify_request_rejected(request: PurchaseRequest, reason: str) -> Dict:
        """Notify requester that request was rejected"""

        if not request.requested_by or not request.requested_by.email:
            return {'success': False, 'message': 'No requester email found'}

        subject = f'Purchase Request Rejected: {request.document_number}'

        context = {
            'request': request,
            'requester': request.requested_by,
            'rejection_reason': reason,
            'rejected_at': timezone.now(),
            'next_steps': 'Please review the rejection reason and create a new request if needed.',
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        try:
            message = render_to_string(
                'purchases/emails/request_rejected.html',
                context
            )

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.requested_by.email],
                html_message=message
            )

            return {'success': True, 'message': 'Rejection notification sent'}

        except Exception as e:
            return {'success': False, 'message': f'Error sending notification: {str(e)}'}

    @staticmethod
    def notify_request_converted(request: PurchaseRequest, order: PurchaseOrder) -> Dict:
        """Notify stakeholders that request was converted to order"""

        recipients = [request.requested_by]
        if request.approved_by and request.approved_by != request.requested_by:
            recipients.append(request.approved_by)

        # Remove duplicates and filter out users without email
        recipients = list(set([user for user in recipients if user and user.email]))

        if not recipients:
            return {'success': False, 'message': 'No recipients found'}

        subject = f'Purchase Request Converted to Order: {request.document_number} → {order.document_number}'

        context = {
            'request': request,
            'order': order,
            'order_total': order.grand_total,
            'expected_delivery': order.expected_delivery_date,
            'order_url': NotificationService._get_admin_url('purchases', 'purchaseorder', order.id),
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        sent_count = 0
        for recipient in recipients:
            try:
                context['recipient'] = recipient

                message = render_to_string(
                    'purchases/emails/request_converted.html',
                    context
                )

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient.email],
                    html_message=message
                )
                sent_count += 1

            except Exception:
                continue

        return {
            'success': sent_count > 0,
            'message': f'Conversion notifications sent to {sent_count} recipients',
            'sent_count': sent_count
        }

    # =====================
    # ORDER NOTIFICATIONS
    # =====================

    @staticmethod
    def notify_order_sent_to_supplier(order: PurchaseOrder) -> Dict:
        """Notify that order was sent to supplier"""

        # Notify purchasing team
        purchasing_team = NotificationService._get_purchasing_team()

        subject = f'Order Sent to Supplier: {order.document_number}'

        context = {
            'order': order,
            'supplier': order.supplier,
            'order_total': order.grand_total,
            'expected_delivery': order.expected_delivery_date,
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        sent_count = 0
        for team_member in purchasing_team:
            if team_member.email:
                try:
                    message = render_to_string(
                        'purchases/emails/order_sent_to_supplier.html',
                        context
                    )

                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[team_member.email],
                        html_message=message
                    )
                    sent_count += 1

                except Exception:
                    continue

        return {
            'success': sent_count > 0,
            'message': f'Order notifications sent to {sent_count} team members'
        }

    @staticmethod
    def notify_order_confirmed_by_supplier(order: PurchaseOrder) -> Dict:
        """Notify that supplier confirmed the order"""

        # Notify requester if order came from request
        recipients = []
        if order.source_request and order.source_request.requested_by:
            recipients.append(order.source_request.requested_by)

        # Add purchasing team
        recipients.extend(NotificationService._get_purchasing_team())

        # Remove duplicates
        recipients = list(set([user for user in recipients if user and user.email]))

        subject = f'Supplier Confirmed Order: {order.document_number}'

        context = {
            'order': order,
            'supplier': order.supplier,
            'confirmation_date': timezone.now(),
            'expected_delivery': order.expected_delivery_date,
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        # Send notifications
        return NotificationService._send_bulk_notifications(recipients, subject, context,
                                                            'purchases/emails/order_confirmed.html')

    # =====================
    # DELIVERY NOTIFICATIONS
    # =====================

    @staticmethod
    def notify_delivery_received(delivery: DeliveryReceipt) -> Dict:
        """Notify that delivery was received"""

        recipients = []

        # Add requesters from source orders
        for order in delivery.source_orders.all():
            if order.source_request and order.source_request.requested_by:
                recipients.append(order.source_request.requested_by)

        # Add warehouse team
        recipients.extend(NotificationService._get_warehouse_team())

        recipients = list(set([user for user in recipients if user and user.email]))

        subject = f'Delivery Received: {delivery.document_number}'

        context = {
            'delivery': delivery,
            'supplier': delivery.supplier,
            'received_date': delivery.received_date,
            'total_value': delivery.grand_total,
            'quality_status': delivery.quality_check_status,
            'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
        }

        return NotificationService._send_bulk_notifications(recipients, subject, context,
                                                            'purchases/emails/delivery_received.html')

    # =====================
    # ESCALATION NOTIFICATIONS
    # =====================

    @staticmethod
    def notify_overdue_approvals(days_overdue: int = 3) -> Dict:
        """Notify about overdue approval requests"""

        from ..models.requests import PurchaseRequest

        overdue_requests = PurchaseRequest.objects.overdue_approval(days_overdue)

        if not overdue_requests.exists():
            return {'success': True, 'message': 'No overdue requests found'}

        # Group by approver
        approvers = NotificationService._get_request_approvers()

        subject = f'Overdue Purchase Request Approvals ({overdue_requests.count()} requests)'

        sent_count = 0
        for approver in approvers:
            context = {
                'approver': approver,
                'overdue_requests': overdue_requests,
                'days_overdue': days_overdue,
                'total_count': overdue_requests.count(),
                'site_name': getattr(settings, 'SITE_NAME', 'Purchase System')
            }

            try:
                message = render_to_string(
                    'purchases/emails/overdue_approvals.html',
                    context
                )

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[approver.email],
                    html_message=message
                )
                sent_count += 1

            except Exception:
                continue

        return {
            'success': sent_count > 0,
            'message': f'Overdue notifications sent to {sent_count} approvers'
        }

    # =====================
    # HELPER METHODS
    # =====================

    @staticmethod
    def _get_request_approvers(request: Optional[PurchaseRequest] = None) -> List[User]:
        """Get users who can approve requests"""

        # Basic permission check
        approvers = User.objects.filter(
            is_active=True,
            user_permissions__codename='approve_requests'
        ).distinct()

        # If request provided, check approval limits
        if request:
            estimated_total = request.get_estimated_total()
            if estimated_total:
                # Filter by approval limit if set
                approvers = approvers.filter(
                    models.Q(approval_limit__gte=estimated_total) |
                    models.Q(approval_limit__isnull=True)
                )

        return list(approvers)

    @staticmethod
    def _get_purchasing_team() -> List[User]:
        """Get purchasing team members"""
        return list(User.objects.filter(
            is_active=True,
            groups__name='Purchasing Team'
        ).distinct())

    @staticmethod
    def _get_warehouse_team() -> List[User]:
        """Get warehouse team members"""
        return list(User.objects.filter(
            is_active=True,
            groups__name='Warehouse Team'
        ).distinct())

    @staticmethod
    def _get_admin_url(app_label: str, model_name: str, object_id: int) -> str:
        """Generate admin URL for object"""
        try:
            return reverse(f'admin:{app_label}_{model_name}_change', args=[object_id])
        except:
            return ''

    @staticmethod
    def _send_bulk_notifications(recipients: List[User], subject: str, context: Dict, template: str) -> Dict:
        """Send notifications to multiple recipients"""

        if not recipients:
            return {'success': False, 'message': 'No recipients found'}

        sent_count = 0
        for recipient in recipients:
            try:
                context['recipient'] = recipient

                message = render_to_string(template, context)

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient.email],
                    html_message=message
                )
                sent_count += 1

            except Exception:
                continue

        return {
            'success': sent_count > 0,
            'message': f'Notifications sent to {sent_count} recipients',
            'sent_count': sent_count
        }


# =====================
# NOTIFICATION SCHEDULER
# =====================

class NotificationScheduler:
    """Handle scheduled notifications (use with Celery or cron)"""

    @staticmethod
    def send_daily_overdue_notifications():
        """Daily job to send overdue approval notifications"""
        return NotificationService.notify_overdue_approvals(days_overdue=3)

    @staticmethod
    def send_weekly_summary():
        """Weekly summary of pending items"""
        # Implementation for weekly summary
        pass