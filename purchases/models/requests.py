# purchases/models/requests.py - CLEAN VERSION БЕЗ estimated_price
import logging
from typing import Dict
from django.db import models, transaction
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from .base import BaseDocument, BaseDocumentLine, FinancialMixin, FinancialLineMixin

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
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return self.filter(
            status='submitted',
            document_date__lte=cutoff_date
        )


class PurchaseRequest(BaseDocument, FinancialMixin):
    """
    Purchase Request - Заявка за покупка

    ✅ FIXED: Заявката ИЗПОЛЗВА FinancialMixin за точни финансови изчисления
    ✅ Workflow се управлява от DocumentType + ApprovalService
    ✅ Auto-suggestion на цени от product history
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
    # VALIDATION
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
    # WORKFLOW METHODS
    # =====================
    def submit_for_approval(self, user=None):
        """
        UPDATED: Submit request with auto-approve check

        Now uses the enhanced ApprovalService for automatic approval
        """
        from nomenclatures.services.approval_service import ApprovalService

        # Use the new enhanced submit method
        result = ApprovalService.submit_document_with_auto_approve(self, user)

        if not result['success']:
            raise ValidationError(result['message'])

        # Log the result for debugging
        import logging
        logger = logging.getLogger(__name__)

        if result['auto_approved']:
            logger.info(
                f"Request {self.document_number} was auto-approved: {result['auto_approve_details']['message']}")
        else:
            logger.info(f"Request {self.document_number} submitted for manual approval")

        return result

    def approve(self, user, notes=''):
        """
        UPDATED: Manual approval method

        Now checks if document was already auto-approved
        """
        if self.status == 'approved':
            # Document was already auto-approved
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Attempt to manually approve already approved request {self.document_number}")
            return {
                'success': False,
                'message': 'Request is already approved',
                'was_auto_approved': True
            }

        if self.status != 'submitted':
            raise ValidationError("Can only approve submitted requests")

        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes = (self.notes + '\n' + notes).strip()
        self.updated_by = user
        self.save()

        return {
            'success': True,
            'message': 'Request manually approved',
            'was_auto_approved': False
        }

    # =====================
    # NEW HELPER METHODS
    # =====================

    def is_auto_approvable(self, user=None) -> Dict:
        """
        NEW: Check if request can be auto-approved without executing

        Useful for UI to show if auto-approval would happen
        """
        from nomenclatures.services.approval_service import ApprovalService
        from nomenclatures.models.approvals import ApprovalRule

        # Find auto-approve rules
        auto_rules = ApprovalRule.objects.for_document(self).filter(
            from_status=self.status,
            to_status='approved',
            is_active=True
        ).exclude(
            auto_approve_conditions__isnull=True
        ).exclude(
            auto_approve_conditions__exact={}
        )

        if not auto_rules.exists():
            return {
                'can_auto_approve': False,
                'reason': 'No auto-approve rules configured',
                'applicable_rules': []
            }

        applicable_rules = []
        for rule in auto_rules:
            check_result = ApprovalService._check_auto_conditions(self, rule)
            applicable_rules.append({
                'rule_name': rule.name,
                'eligible': check_result['eligible'],
                'details': check_result['details'],
                'conditions': rule.auto_approve_conditions
            })

        # Check if any rule would pass
        can_auto_approve = any(rule['eligible'] for rule in applicable_rules)

        return {
            'can_auto_approve': can_auto_approve,
            'reason': 'Auto-approve conditions met' if can_auto_approve else 'Auto-approve conditions not met',
            'applicable_rules': applicable_rules
        }

    def get_auto_approve_preview(self) -> str:
        """
        NEW: Get human-readable preview of auto-approve status

        For use in admin interface or API responses
        """
        preview_result = self.is_auto_approvable()

        if not preview_result['applicable_rules']:
            return "❌ No auto-approve rules configured"

        preview_lines = []
        for rule in preview_result['applicable_rules']:
            status = "✅" if rule['eligible'] else "❌"
            preview_lines.append(f"{status} {rule['rule_name']}: {rule['details']}")

        if preview_result['can_auto_approve']:
            preview_lines.insert(0, "🎯 AUTO-APPROVE: Will be automatically approved")
        else:
            preview_lines.insert(0, "⏳ MANUAL APPROVAL: Requires human approval")

        return "\n".join(preview_lines)

    # =====================
    # ENHANCED PROPERTIES
    # =====================

    @property
    def was_auto_approved(self):
        """Check if this request was auto-approved"""
        if self.status != 'approved':
            return False

        # Check ApprovalLog for auto_approved action
        from nomenclatures.models.approvals import ApprovalLog
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(self.__class__)

        auto_approval_logs = ApprovalLog.objects.filter(
            content_type=content_type,
            object_id=self.pk,
            action='auto_approved'
        )

        return auto_approval_logs.exists()

    @property
    def auto_approval_rule_used(self):
        """Get the rule that was used for auto-approval"""
        if not self.was_auto_approved:
            return None

        from nomenclatures.models.approvals import ApprovalLog
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(self.__class__)

        auto_approval_log = ApprovalLog.objects.filter(
            content_type=content_type,
            object_id=self.pk,
            action='auto_approved'
        ).first()

        return auto_approval_log.rule if auto_approval_log else None

    @property
    def total_estimated_cost(self):
        if not self.pk:
            return Decimal('0.00')

        return sum(
            line.entered_price * line.requested_quantity
            for line in self.lines.all()
            if line.entered_price
        ) or Decimal('0.00')



    # =====================
    # PROPERTIES
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
    def approval_duration_days(self):
        """Days between submission and approval"""
        if self.approved_at and self.created_at:
            return (self.approved_at.date() - self.created_at.date()).days
        return None

    # =====================
    # FINANCIAL PLANNING
    # =====================
    def get_planning_cost(self):
        """✅ FIXED: Use new VATCalculationService"""
        if not self.pk:
            return Decimal('0.00')

        from nomenclatures.services.vat_calculation_service import VATCalculationService
        total_cost = Decimal('0')

        for line in self.lines.all():
            # Use effective cost from line gross amount or calculate
            if line.gross_amount:
                effective_cost = line.gross_amount
            elif line.entered_price and line.requested_quantity:
                # Calculate on-the-fly
                calc_result = VATCalculationService.calculate_line_totals(
                    line, line.entered_price, line.requested_quantity
                )
                effective_cost = calc_result['gross_amount']
            else:
                effective_cost = Decimal('0')

            total_cost += effective_cost

        return total_cost

    def get_estimated_total(self):
        """✅ FIXED: Use entered_price uniformly"""
        if not self.pk:
            return Decimal('0.00')

        total = Decimal('0.00')
        for line in self.lines.all():
            qty = line.requested_quantity or 0
            price = line.entered_price or 0  # Use entered_price consistently
            total += qty * price

        return total

    def get_financial_summary(self):
        if not self.pk:
            return {
                'lines_count': 0,
                'subtotal': Decimal('0.00'),
                'vat_total': Decimal('0.00'),
                'total': Decimal('0.00'),
                'planning_cost': Decimal('0.00')
            }

        return {
            'lines_count': self.lines.count(),
            'subtotal': self.subtotal,
            'vat_total': self.vat_total,
            'total': self.total,
            'planning_cost': self.get_planning_cost()
        }




# =====================
# REQUEST LINE MODEL - CLEANED UP
# =====================

class PurchaseRequestLineManager(models.Manager):
    """Manager for Purchase Request Lines"""

    def for_request(self, request):
        """Lines for specific request"""
        return self.filter(document=request)

    def pending_approval(self):
        """Lines in requests pending approval"""
        return self.filter(document__status='submitted')

    def approved(self):
        """Lines in approved requests"""
        return self.filter(document__status='approved')

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)

    def with_pricing(self):
        """Lines that have entered prices"""
        return self.filter(entered_price__isnull=False, entered_price__gt=0)

    def missing_pricing(self):
        """Lines missing price information"""
        return self.filter(
            models.Q(entered_price__isnull=True) |
            models.Q(entered_price=0)
        )


class PurchaseRequestLine(BaseDocumentLine, FinancialLineMixin):
    """
    Purchase Request Line - CLEAN VERSION

    ✅ САМО requested_quantity (БЕЗ generic quantity поле)
    ✅ Tracking за conversion to order
    ✅ Clean validation
    """

    # =====================
    # DOCUMENT RELATIONSHIP
    # =====================
    document = models.ForeignKey(
        'PurchaseRequest',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Request')
    )

    # =====================
    # REQUEST-SPECIFIC QUANTITY
    # =====================
    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity requested for purchase')
    )




    # =====================
    # SUPPLIER SUGGESTION
    # =====================
    suggested_supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Suggested Supplier'),
        help_text=_('Preferred supplier for this item')
    )

    # =====================
    # PRIORITY & JUSTIFICATION
    # =====================
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Priority within request (0=normal, higher=more urgent)')
    )

    item_justification = models.TextField(
        _('Item Justification'),
        blank=True,
        help_text=_('Why is this specific item needed?')
    )

    # =====================
    # CONVERSION TRACKING
    # =====================
    converted_to_order_line = models.ForeignKey(
        'PurchaseOrderLine',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='source_request_line_ref',
        help_text=_('Order line created from this request')
    )

    class Meta:
        verbose_name = _('Purchase Request Line')
        verbose_name_plural = _('Purchase Request Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['suggested_supplier']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.requested_quantity}"

    # =====================
    # IMPLEMENT ABSTRACT METHOD
    # =====================

    def get_quantity_for_display(self):
        """Return requested quantity for display"""
        return self.requested_quantity

    # =====================
    # VALIDATION
    # =====================

    def clean(self):
        """Request line validation"""
        super().clean()

        # Requested quantity must be positive
        if self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Requested quantity must be greater than zero')
            })

        # Estimated price validation (if provided)
        if self.entered_price is not None and self.entered_price < 0:
            raise ValidationError({
                'entered_price': _('Entered price cannot be negative')
            })

        # Priority validation
        if self.priority < 0:
            raise ValidationError({
                'priority': _('Priority cannot be negative')
            })

    # =====================
    # PROPERTIES
    # =====================

    # ✅ FIXED PROPERTY
    @property
    def estimated_line_total(self):
        """Calculate estimated total from entered_price"""
        if self.entered_price and self.requested_quantity:
            return self.entered_price * self.requested_quantity
        return None

    @property
    def has_suggested_supplier(self):
        """Check if line has supplier suggestion"""
        return self.suggested_supplier is not None

    @property
    def is_high_priority(self):
        """Check if line is high priority"""
        return self.priority > 0

    @property
    def is_converted(self):
        """Check if line has been converted to order"""
        return self.converted_to_order_line is not None

    @property
    def conversion_status(self):
        """Get conversion status"""
        if self.converted_to_order_line:
            return 'converted'
        elif self.document.status == 'approved':
            return 'ready_to_convert'
        else:
            return 'not_ready'

    # =====================
    # METHODS
    # =====================

    def can_be_converted(self):
        """Check if line can be converted to order"""
        return (
                self.document.status == 'approved' and
                not self.is_converted and
                self.requested_quantity > 0
        )

    def convert_to_order_line(self, order, **kwargs):
        """
        Convert this request line to order line

        Args:
            order: PurchaseOrder instance
            **kwargs: Additional fields for order line

        Returns:
            PurchaseOrderLine instance
        """
        if self.is_converted:
            raise ValidationError(f"Line {self.line_number} already converted to order")

        if not self.can_be_converted():
            raise ValidationError(f"Line {self.line_number} cannot be converted")

        # Create order line
        from .orders import PurchaseOrderLine

        order_line = PurchaseOrderLine.objects.create(
            document=order,
            source_request_line=self,
            product=self.product,
            unit=self.unit,
            ordered_quantity=self.requested_quantity,
            unit_price=kwargs.get('unit_price', self.entered_price or Decimal('0')),  # ✅ FIXED
            notes=self.notes or '',
            **kwargs
        )

        # Mark as converted
        self.converted_to_order_line = order_line
        self.save(update_fields=['converted_to_order_line'])

        return order_line