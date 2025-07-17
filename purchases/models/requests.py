import logging
import warnings

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .base import BaseDocument, BaseDocumentLine

logger = logging.getLogger(__name__)

class PurchaseRequestManager(models.Manager):
    """Manager for Purchase Requests with specific queries"""

    def pending_approval(self):
        """Requests waiting for approval"""
        return self.filter(status='submitted')

    def approved(self):
        """Approved requests ready for conversion"""
        return self.filter(status='approved')

    def converted(self):
        """Requests that have been converted to orders"""
        return self.filter(status='converted')

    def by_urgency(self, level):
        """Filter by urgency level"""
        return self.filter(urgency_level=level)

    def this_month(self):
        """Requests created this month"""
        today = timezone.now().date()
        return self.filter(
            created_at__month=today.month,
            created_at__year=today.year
        )

    def overdue_approval(self, days=3):
        """Requests waiting for approval too long"""
        cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
        return self.filter(
            status='submitted',
            document_date__lte=cutoff_date
        )


class PurchaseRequest(BaseDocument):
    """
    Purchase Request - Заявка за покупка

    Логика: Заявка е САМО искане за стоки, БЕЗ финансови данни!
    Използва само BaseDocument - НЕ използва FinancialMixin или PaymentMixin.

    Workflow се управлява от DocumentType:
    - Статуси идват от DocumentType.allowed_statuses
    - Transitions се валидират от DocumentType.status_transitions
    - Business rules идват от DocumentType настройки
    """

    # =====================
    # REQUEST TYPE
    # =====================
    REQUEST_TYPE_CHOICES = [
        ('regular', _('Regular Purchase')),
        ('urgent', _('Urgent Purchase')),
        ('emergency', _('Emergency Purchase')),
        ('consumables', _('Consumables Restock')),
        ('maintenance', _('Maintenance Supplies')),
        ('project', _('Project Materials')),
    ]

    request_type = models.CharField(
        _('Request Type'),
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='regular',
        help_text=_('Type of purchase request')
    )

    # =====================
    # URGENCY
    # =====================
    URGENCY_CHOICES = [
        ('low', _('Low')),
        ('normal', _('Normal')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]

    urgency_level = models.CharField(
        _('Urgency Level'),
        max_length=10,
        choices=URGENCY_CHOICES,
        default='normal',
        help_text=_('How urgent is this request')
    )


    # =====================
    # BUSINESS JUSTIFICATION
    # =====================
    business_justification = models.TextField(
        _('Business Justification'),
        blank=True,
        null=True,
        help_text=_('Why is this purchase needed?')
    )

    expected_usage = models.TextField(
        _('Expected Usage'),
        blank=True,
        help_text=_('How will these items be used?')
    )

    # =====================
    # APPROVAL WORKFLOW
    # =====================
    approval_required = models.BooleanField(
        _('Approval Required'),
        default=True,
        help_text=_('Does this request need approval?')
    )

    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='purchase_requests_made',
        verbose_name=_('Requested By'),
        help_text=_('Person who made the request')
    )

    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_requests_approved',
        verbose_name=_('Approved By')
    )

    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True
    )

    rejection_reason = models.TextField(
        _('Rejection Reason'),
        blank=True,
        help_text=_('Why was this request rejected?')
    )

    # =====================
    # CONVERSION TRACKING
    # =====================
    converted_to_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_from_request',
        verbose_name=_('Converted to Order')
    )

    converted_at = models.DateTimeField(
        _('Converted At'),
        null=True,
        blank=True
    )

    converted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_requests_converted',
        verbose_name=_('Converted By')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseRequestManager()

    class Meta:
        verbose_name = _('Purchase Request')
        verbose_name_plural = _('Purchase Requests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'urgency_level']),
            models.Index(fields=['requested_by', '-created_at']),
            models.Index(fields=['approved_by', '-approved_at']),
            models.Index(fields=['request_type', 'urgency_level']),
        ]

    def __str__(self):
        return f"REQ {self.document_number} - {self.supplier.name}"

    def get_document_prefix(self):
        """Override to return REQ prefix"""
        return "REQ"

    # =====================
    # ЗАЯВКА-СПЕЦИФИЧНА ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Request-specific validation - БЕЗ workflow validation"""
        super().clean()


        if self.status == 'approved':
            if not self.approved_by:
                raise ValidationError({
                    'approved_by': _('Approved by is required when status is approved')
                })
            if not self.approved_at:
                self.approved_at = timezone.now()

        if self.status == 'rejected':
            if not self.rejection_reason:
                raise ValidationError({
                    'rejection_reason': _('Rejection reason is required when status is rejected')
                })

        if self.status == 'converted':
            if not self.converted_to_order:
                raise ValidationError({
                    'converted_to_order': _('Converted to order is required when status is converted')
                })

    # =====================
    # WORKFLOW METHODS - DOCUMENTTYPE DRIVEN
    # =====================
    def submit_for_approval(self, user=None):
        """
        ЕДИНСТВЕН workflow метод - submit за approval
        Останалите операции се правят през ApprovalService
        """
        from nomenclatures.services.approval_service import ApprovalService

        # Business validation
        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        # Използваме ApprovalService за прехода
        result = ApprovalService.execute_transition(
            document=self,
            to_status='submitted',
            user=user,
            comments="Submitted for approval"
        )

        if not result['success']:
            raise ValidationError(result['message'])

        return True



    def cancel(self, user=None, reason=''):
        """Cancel the request"""
        if not self.can_transition_to('cancelled'):
            raise ValidationError("Cannot cancel request in current status")

        self.status = 'cancelled'
        if reason:
            self.notes = (self.notes + f'\nCancelled: {reason}').strip()
        self.updated_by = user
        self.save()

        return True

    # =====================
    # BUSINESS LOGIC CHECKS - DOCUMENTTYPE DRIVEN
    # =====================
    def can_be_edited(self):
        """Check if request can be edited - enhanced with DocumentType logic"""
        # Use parent DocumentType logic first
        if not super().can_be_edited():
            return False

        # Additional request-specific logic
        return not self.is_converted and not self.is_cancelled

    def can_be_submitted(self):
        """Check if request can be submitted"""
        return (
                self.can_transition_to('submitted') and
                self.lines.exists()
        )

    def can_be_approved(self):
        """Check if request can be approved"""
        return self.can_transition_to('approved')

    def can_be_rejected(self):
        """Check if request can be rejected"""
        return self.can_transition_to('rejected')

    def can_be_converted(self):
        """Check if request can be converted to order"""
        return self.can_transition_to('converted')

    def can_be_cancelled(self):
        """Check if request can be cancelled - enhanced with DocumentType logic"""
        return self.can_transition_to('cancelled')

    # =====================
    # PROPERTIES - DOCUMENTTYPE DRIVEN
    # =====================
    @property
    def is_pending_approval(self):
        return self.status == 'submitted'

    @property
    def is_approved(self):
        return self.status == 'approved'

    @property
    def is_converted(self):
        return self.status == 'converted'

    @property
    def is_rejected(self):
        return self.status == 'rejected'

    @property
    def is_cancelled(self):
        return self.status == 'cancelled'

    @property
    def is_draft(self):
        return self.status == 'draft'

    @property
    def approval_duration_days(self):
        """Days between submission and approval"""
        if self.approved_at and self.created_at:
            return (self.approved_at.date() - self.created_at.date()).days
        return None

    @property
    def total_estimated_cost(self):
        """Сума на всички estimated цени - само за информация!"""
        return sum(
            line.estimated_price * line.requested_quantity
            for line in self.lines.all()
            if line.estimated_price
        )

    def get_estimated_total(self):
        """Get total estimated cost for this request"""
        from decimal import Decimal

        total = sum(
            line.estimated_price * line.requested_quantity
            for line in self.lines.all()
            if line.estimated_price
        )

        return Decimal(str(total)) if total else Decimal('0.00')

    # =====================
    # STATUS DISPLAY METHODS
    # =====================
    def get_status_display_with_context(self):
        """Enhanced status display with additional context"""
        status_display = self.status.title()

        if self.is_pending_approval and self.approval_required:
            return f"{status_display} (Awaiting Approval)"
        elif self.is_approved and not self.is_converted:
            return f"{status_display} (Ready for Order)"
        elif self.is_converted and self.converted_to_order:
            return f"{status_display} (Order: {self.converted_to_order.document_number})"

        return status_display

    def get_urgency_color(self):
        """Get color for urgency level"""
        colors = {
            'low': 'green',
            'normal': 'blue',
            'high': 'orange',
            'critical': 'red'
        }
        return colors.get(self.urgency_level, 'gray')

    # =====================
    # WORKFLOW INFORMATION
    # =====================
    def get_available_actions(self, user=None):
        """Get available workflow actions for this request"""
        actions = []

        if self.can_be_submitted():
            actions.append({
                'action': 'submit_for_approval',
                'label': _('Submit for Approval'),
                'method': 'POST',
                'requires_confirmation': False
            })

        if self.can_be_approved() and user:
            # Additional check: user has approval permissions
            actions.append({
                'action': 'approve',
                'label': _('Approve'),
                'method': 'POST',
                'requires_confirmation': True,
                'requires_notes': True
            })

        if self.can_be_rejected():
            actions.append({
                'action': 'reject',
                'label': _('Reject'),
                'method': 'POST',
                'requires_confirmation': True,
                'requires_reason': True
            })

        if self.can_be_converted():
            actions.append({
                'action': 'convert_to_order',
                'label': _('Convert to Order'),
                'method': 'POST',
                'requires_confirmation': True
            })

        if self.can_be_cancelled():
            actions.append({
                'action': 'cancel',
                'label': _('Cancel'),
                'method': 'POST',
                'requires_confirmation': True,
                'requires_reason': True
            })

        return actions

    def get_workflow_history(self):
        """Get workflow transition history"""
        # This would integrate with audit/logging system
        history = []

        if self.created_at:
            history.append({
                'status': 'draft',
                'timestamp': self.created_at,
                'user': self.created_by,
                'action': 'created'
            })

        if self.approved_at and self.approved_by:
            history.append({
                'status': 'approved',
                'timestamp': self.approved_at,
                'user': self.approved_by,
                'action': 'approved'
            })

        if self.converted_at and self.converted_by:
            history.append({
                'status': 'converted',
                'timestamp': self.converted_at,
                'user': self.converted_by,
                'action': 'converted'
            })

        return sorted(history, key=lambda x: x['timestamp'])

    def get_available_workflow_actions(self, user):
        """
        НОВ HELPER: Wrapper around ApprovalService за convenience
        """
        from nomenclatures.services.approval_service import ApprovalService

        transitions = ApprovalService.get_available_transitions(self, user)

        # Превръщаме в по-простa структура
        actions = []
        for transition in transitions:
            actions.append({
                'action': f"transition_to_{transition['to_status']}",
                'display_name': transition['name'],
                'target_status': transition['to_status'],
                'description': transition['description'],
                'level': transition['level']
            })

        return actions

    def execute_workflow_action(self, action, user, **kwargs):
        """
        НОВ HELPER: Unified method за workflow actions
        """
        from nomenclatures.services.approval_service import ApprovalService

        # Мапваме action към target status
        if action.startswith('transition_to_'):
            target_status = action.replace('transition_to_', '')

            if target_status == 'rejected':
                reason = kwargs.get('reason', 'No reason provided')
                return ApprovalService.reject_document(self, user, reason)
            else:
                comments = kwargs.get('comments', f'Action: {action}')
                return ApprovalService.execute_transition(self, target_status, user, comments)

        elif action == 'submit_for_approval':
            return self.submit_for_approval(user)

        else:
            raise ValidationError(f"Unknown workflow action: {action}")

    def approve_via_service(self, user, notes=''):
        """
        LEGACY WRAPPER: За код който още вика request.approve()
        """
        import warnings
        warnings.warn(
            "approve_via_service() is deprecated. Use ApprovalService.execute_transition() directly",
            DeprecationWarning,
            stacklevel=2
        )

        from nomenclatures.services.approval_service import ApprovalService

        # Намираме най-подходящия approval status
        available_transitions = ApprovalService.get_available_transitions(self, user)
        approval_transitions = [t for t in available_transitions if 'approv' in t['to_status']]

        if not approval_transitions:
            raise ValidationError("No approval transitions available for this user")

        target_status = approval_transitions[0]['to_status']

        result = ApprovalService.execute_transition(self, target_status, user, notes)

        if not result['success']:
            raise ValidationError(result['message'])

        return True

    def reject_via_service(self, user, reason):
        """
        LEGACY WRAPPER: За код който още вика request.reject()
        """
        import warnings
        warnings.warn(
            "reject_via_service() is deprecated. Use ApprovalService.reject_document() directly",
            DeprecationWarning,
            stacklevel=2
        )

        from nomenclatures.services.approval_service import ApprovalService

        result = ApprovalService.reject_document(self, user, reason)

        if not result['success']:
            raise ValidationError(result['message'])

        return True

    def approve(self, user, notes=''):
        """
        LEGACY WRAPPER: Use ApprovalService.execute_transition() instead

        This method is deprecated but kept for backward compatibility.
        All approval logic now goes through ApprovalService for consistency.
        """
        warnings.warn(
            "PurchaseRequest.approve() is deprecated. "
            "Use ApprovalService.execute_transition(document, 'approved', user, notes) for better error handling and audit trail.",
            DeprecationWarning,
            stacklevel=2
        )

        try:
            from nomenclatures.services.approval_service import ApprovalService

            result = ApprovalService.execute_transition(
                document=self,
                to_status='approved',
                user=user,
                comments=notes or 'Approved via legacy method'
            )

            if not result['success']:
                raise ValidationError(result['message'])

            logger.info(f"Request {self.document_number} approved via legacy method by {user}")
            return True

        except ImportError:
            # Fallback if ApprovalService not available
            logger.warning("ApprovalService not available, falling back to direct status change")

            if self.status != 'submitted':
                raise ValidationError("Can only approve submitted requests")

            self.status = 'approved'
            self.approved_by = user
            self.approved_at = timezone.now()
            if notes:
                self.notes = (self.notes + '\n' + notes).strip() if self.notes else notes
            self.updated_by = user
            self.save()

            return True

    def reject(self, user, reason):
        """
        LEGACY WRAPPER: Use ApprovalService.execute_transition() instead
        """
        warnings.warn(
            "PurchaseRequest.reject() is deprecated. "
            "Use ApprovalService.execute_transition(document, 'rejected', user, reason)",
            DeprecationWarning,
            stacklevel=2
        )

        if not reason:
            raise ValidationError("Rejection reason is required")

        try:
            from nomenclatures.services.approval_service import ApprovalService

            result = ApprovalService.execute_transition(
                document=self,
                to_status='rejected',
                user=user,
                comments=reason
            )

            if not result['success']:
                raise ValidationError(result['message'])

            logger.info(f"Request {self.document_number} rejected via legacy method by {user}")
            return True

        except ImportError:
            # Fallback if ApprovalService not available
            logger.warning("ApprovalService not available, falling back to direct status change")

            if self.status != 'submitted':
                raise ValidationError("Can only reject submitted requests")

            self.status = 'rejected'
            self.rejection_reason = reason
            self.updated_by = user
            self.save()

            return True

    def submit_for_approval(self, user=None):
        """
        LEGACY WRAPPER: Use ApprovalService.execute_transition() instead
        """
        warnings.warn(
            "PurchaseRequest.submit_for_approval() is deprecated. "
            "Use ApprovalService.execute_transition(document, 'submitted', user)",
            DeprecationWarning,
            stacklevel=2
        )

        try:
            from nomenclatures.services.approval_service import ApprovalService

            result = ApprovalService.execute_transition(
                document=self,
                to_status='submitted',
                user=user,
                comments='Submitted for approval via legacy method'
            )

            if not result['success']:
                raise ValidationError(result['message'])

            return True

        except ImportError:
            # Fallback logic
            if self.status != 'draft':
                raise ValidationError("Can only submit draft requests")

            if not self.lines.exists():
                raise ValidationError("Cannot submit request without lines")

            self.status = 'submitted'
            self.updated_by = user
            self.save()

            return True

    def convert_to_order(self, user=None, **kwargs):
        """
        LEGACY WRAPPER: Use OrderService.create_from_request() instead

        This method is kept for backward compatibility but now uses
        the improved OrderService logic with proper workflow handling.
        """
        warnings.warn(
            "PurchaseRequest.convert_to_order() is deprecated. "
            "Use OrderService.create_from_request() directly for better error handling and workflow support.",
            DeprecationWarning,
            stacklevel=2
        )

        try:
            from ..services.order_service import OrderService

            result = OrderService.create_from_request(self, user, **kwargs)

            if not result['success']:
                raise ValidationError(result['message'])

            return result['order']

        except ImportError:
            raise ValidationError("OrderService not available")



# =====================
# REQUEST LINE MODEL
# =====================
class PurchaseRequestLineManager(models.Manager):
    """Manager for Purchase Request Lines"""

    def with_estimated_cost(self):
        """Lines with estimated cost information"""
        return self.filter(estimated_price__isnull=False, estimated_price__gt=0)

    def without_estimated_cost(self):
        """Lines missing estimated cost"""
        return self.filter(
            models.Q(estimated_price__isnull=True) |
            models.Q(estimated_price=0)
        )


class PurchaseRequestLine(BaseDocumentLine):
    """
    Purchase Request Line - редове от заявка

    Логика: Редовете съдържат САМО искания за количества, БЕЗ финансови данни!
    Estimated price е опционална информация за планиране.
    """

    # =====================
    # REQUEST LINE FIELDS
    # =====================
    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('How many units are requested')
    )

    estimated_price = models.DecimalField(
        _('Estimated Unit Price'),
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Estimated price per unit (optional, for planning)')
    )

    document = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Request'),
        help_text=_('Parent purchase request')
    )

    # =====================
    # BUSINESS JUSTIFICATION
    # =====================
    usage_description = models.TextField(
        _('Usage Description'),
        blank=True,
        help_text=_('How will this specific item be used?')
    )

    alternative_products = models.TextField(
        _('Alternative Products'),
        blank=True,
        help_text=_('Acceptable alternative products if this one is not available')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseRequestLineManager()

    class Meta:
        verbose_name = _('Purchase Request Line')
        verbose_name_plural = _('Purchase Request Lines')
        ordering = ['line_number']

    def __str__(self):
        return f"Line {self.line_number}: {self.product.name} x {self.requested_quantity}"

    # =====================
    # CALCULATED PROPERTIES
    # =====================
    @property
    def estimated_total(self):
        """Estimated total cost for this line"""
        if self.estimated_price:
            return self.estimated_price * self.requested_quantity
        return None

    @property
    def has_alternatives(self):
        """Does this line have alternative products specified?"""
        return bool(self.alternative_products.strip())

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Request line validation"""
        super().clean()

        if self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Requested quantity must be positive')
            })

        if self.estimated_price is not None and self.estimated_price < 0:
            raise ValidationError({
                'estimated_price': _('Estimated price cannot be negative')
            })

    # =====================
    # BUSINESS METHODS
    # =====================
    def get_quantity_display(self):
        """Get formatted quantity with unit"""
        if self.unit:
            return f"{self.requested_quantity} {self.unit.code}"
        return str(self.requested_quantity)

    def get_estimated_total_display(self):
        """Get formatted estimated total"""
        total = self.estimated_total
        if total:
            return f"{total:.2f} лв"
        return "No estimate"

    def is_high_value(self, threshold=500):
        """Check if this line has high estimated value"""
        return self.estimated_total and self.estimated_total >= threshold