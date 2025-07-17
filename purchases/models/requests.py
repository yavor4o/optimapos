
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .base import BaseDocument, BaseDocumentLine


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
        """Request-specific validation"""
        super().clean()

        # Approval validation
        if self.status == 'approved':
            if not self.approved_by:
                raise ValidationError({
                    'approved_by': _('Approved by is required when status is approved')
                })
            if not self.approved_at:
                self.approved_at = timezone.now()

        # Rejection validation
        if self.status == 'rejected':
            if not self.rejection_reason:
                raise ValidationError({
                    'rejection_reason': _('Rejection reason is required when status is rejected')
                })

        # Conversion validation
        if self.status == 'converted':
            if not self.converted_to_order:
                raise ValidationError({
                    'converted_to_order': _('Converted to order is required when status is converted')
                })

    # =====================
    # WORKFLOW METHODS - DOCUMENTTYPE DRIVEN
    # =====================
    def submit_for_approval(self, user=None):
        """Submit request for approval"""
        if not self.can_transition_to('submitted'):
            raise ValidationError("Cannot submit request in current status")

        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        self.status = 'submitted'
        self.updated_by = user
        self.save()

        return True

    def approve(self, user, notes=''):
        """Approve the request"""
        if not self.can_transition_to('approved'):
            raise ValidationError("Cannot approve request in current status")

        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes = (self.notes + '\n' + notes).strip()
        self.updated_by = user
        self.save()

        return True

    def reject(self, user, reason):
        """Reject the request"""
        if not self.can_transition_to('rejected'):
            raise ValidationError("Cannot reject request in current status")

        self.status = 'rejected'
        self.rejection_reason = reason
        self.updated_by = user
        self.save()

        return True

    def convert_to_order(self, user=None):
        """Convert approved request to purchase order"""
        if not self.can_transition_to('converted'):
            raise ValidationError("Cannot convert request in current status")

        # Import here to avoid circular imports
        from .orders import PurchaseOrder, PurchaseOrderLine

        # Create the order
        order = PurchaseOrder.objects.create(
            supplier=self.supplier,
            location=self.location,
            expected_delivery_date=timezone.now().date() + timezone.timedelta(days=7),
            external_reference=self.external_reference,
            notes=f"Created from request {self.document_number}\n{self.notes}".strip(),
            source_request=self,
            created_by=user or self.updated_by,
            updated_by=user or self.updated_by,
        )

        # Copy lines
        for req_line in self.lines.all():
            PurchaseOrderLine.objects.create(
                document=order,
                line_number=req_line.line_number,
                product=req_line.product,
                quantity=req_line.requested_quantity,
                unit=req_line.unit,
                ordered_quantity=req_line.requested_quantity,
                unit_price=req_line.estimated_price or Decimal('0.0000'),
                source_request_line=req_line,
            )

        # Update request status
        self.status = 'converted'
        self.converted_to_order = order
        self.converted_at = timezone.now()
        self.converted_by = user
        self.save()

        # Recalculate order totals
        order.recalculate_totals()

        return order

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