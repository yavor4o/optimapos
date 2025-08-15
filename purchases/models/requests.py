# purchases/models/requests.py - SYNCHRONIZED WITH NOMENCLATURES
import logging
from typing import Dict
from django.db import models, transaction
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from inventory.services import InventoryService
from .base import BaseDocument, BaseDocumentLine, FinancialMixin, FinancialLineMixin

logger = logging.getLogger(__name__)


class PurchaseRequestManager(models.Manager):
    """Manager for Purchase Requests - SYNCHRONIZED WITH NOMENCLATURES"""

    def pending_approval(self):
        """Requests waiting for approval - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_pending_approval_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            # Fallback if nomenclatures not available
            return self.filter(status='submitted')

    def approved(self):
        """Approved requests ready for conversion - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_ready_for_processing_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.filter(status='approved')

    def converted(self):
        """Requests that have been converted to orders"""
        return self.filter(status='converted')

    def active(self):
        """Active requests (not cancelled/completed) - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_active_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.exclude(status__in=['cancelled', 'converted'])

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
        return self.pending_approval().filter(
            document_date__lte=cutoff_date
        )


class PurchaseRequest(BaseDocument, FinancialMixin):
    """
    Purchase Request - SYNCHRONIZED WITH NOMENCLATURES

    CHANGES:
    - Uses DocumentService for workflow
    - Uses ApprovalService for approvals
    - Dynamic status handling
    - Removed hardcoded workflow logic
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
    # REQUESTER INFO (KEEP EXISTING)
    # =====================
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='purchase_requests_made',
        verbose_name=_('Requested By'),
        help_text=_('Person who made the request')
    )

    # =====================
    # LEGACY APPROVAL FIELDS (KEEP FOR COMPATIBILITY)
    # Note: These will be superseded by ApprovalLog but kept for existing data
    # =====================
    approval_required = models.BooleanField(
        _('Approval Required'),
        default=True,
        help_text=_('Does this request need approval?')
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

    def get_document_type_key(self):
        """Return document type key for nomenclatures integration"""
        return 'purchase_request'

    # =====================
    # NOMENCLATURES INTEGRATION METHODS
    # =====================

    def can_edit(self, user=None):
        """Check if request can be edited - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, reason = DocumentService.can_edit_document(self, user)
            return can_edit
        except ImportError:
            # Fallback logic
            return self.status in ['draft', 'returned']

    def get_available_actions(self, user=None):
        """Get available actions for user - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_available_actions(self, user)
        except ImportError:
            return []

    def transition_to(self, new_status, user, comments=''):
        """Transition to new status - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.transition_document(
                self, new_status, user, comments
            )
        except ImportError:
            raise ValidationError("Document workflow service not available")

    def get_workflow_info(self):
        """Get complete workflow information - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_workflow_info(self)
        except ImportError:
            return None

    def get_approval_history(self):
        """Get approval history - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_approval_history(self)
        except ImportError:
            return []

    # =====================
    # VALIDATION - UPDATED TO USE NOMENCLATURES
    # =====================
    def clean(self):
        """Request-specific validation - SYNCHRONIZED"""
        super().clean()

        # REMOVED: Hardcoded status validations
        # The nomenclatures system will handle status transitions

        # Business validation still applies
        if self.urgency_level == 'critical' and not self.business_justification:
            raise ValidationError({
                'business_justification': _('Critical requests must have detailed justification')
            })

        # Legacy field sync (for backward compatibility)
        if self.status == 'converted' and not self.converted_to_order:
            raise ValidationError({
                'converted_to_order': _('Converted to order is required when status is converted')
            })

    # =====================
    # PROPERTIES - UPDATED TO BE DYNAMIC
    # =====================

    @property
    def is_pending_approval(self):
        """Check if pending approval - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            status_info = DocumentService._get_status_info(self)
            # Dynamic check based on configured statuses
            return not status_info.get('is_final') and not status_info.get('is_initial')
        except:
            return self.status == 'submitted'  # fallback

    @property
    def is_approved(self):
        """Check if approved - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            status_info = DocumentService._get_status_info(self)
            return 'approv' in self.status.lower() or status_info.get('is_final')
        except:
            return self.status == 'approved'

    @property
    def is_converted(self):
        return self.status == 'converted'

    @property
    def is_rejected(self):
        return self.status == 'rejected'

    @property
    def was_auto_approved(self):
        """Check if this request was auto-approved - USES NOMENCLATURES"""
        try:
            from nomenclatures.models.approvals import ApprovalLog
            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get_for_model(self.__class__)
            auto_approval_logs = ApprovalLog.objects.filter(
                content_type=content_type,
                object_id=self.pk,
                action='auto_approved'
            )
            return auto_approval_logs.exists()
        except:
            return False

    @property
    def approval_duration_days(self):
        """Days between submission and approval"""
        if self.approved_at and self.created_at:
            return (self.approved_at.date() - self.created_at.date()).days
        return None

    # =====================
    # FINANCIAL METHODS - UNCHANGED
    # =====================

    @property
    def total_estimated_cost(self):
        if not self.pk:
            return Decimal('0.00')

        return sum(
            line.entered_price * line.requested_quantity
            for line in self.lines.all()
            if line.entered_price
        ) or Decimal('0.00')

    def get_planning_cost(self):
        """Calculate planning cost using VATCalculationService"""
        if not self.pk:
            return Decimal('0.00')

        try:
            from nomenclatures.services.vat_calculation_service import VATCalculationService
            total_cost = Decimal('0')

            for line in self.lines.all():
                if line.gross_amount:
                    effective_cost = line.gross_amount
                elif line.entered_price and line.requested_quantity:
                    calc_result = VATCalculationService.calculate_line_totals(
                        line, line.entered_price, line.requested_quantity
                    )
                    effective_cost = calc_result['gross_amount']
                else:
                    effective_cost = Decimal('0')

                total_cost += effective_cost

            return total_cost
        except ImportError:
            return self.total_estimated_cost

    def get_estimated_total(self):
        """Get estimated total uniformly"""
        if not self.pk:
            return Decimal('0.00')

        total = Decimal('0.00')
        for line in self.lines.all():
            qty = line.requested_quantity or 0
            price = line.entered_price or 0
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
# REQUEST LINE MODEL - SYNCHRONIZED
# =====================

class PurchaseRequestLineManager(models.Manager):
    """Manager for Purchase Request Lines - SYNCHRONIZED"""

    def for_request(self, request):
        """Lines for specific request"""
        return self.filter(document=request)

    def pending_approval(self):
        """Lines in requests pending approval - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            pending_requests = DocumentService.get_pending_approval_documents(
                queryset=PurchaseRequest.objects.all()
            )
            return self.filter(document__in=pending_requests)
        except ImportError:
            return self.filter(document__status='submitted')

    def approved(self):
        """Lines in approved requests - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            approved_requests = DocumentService.get_ready_for_processing_documents(
                queryset=PurchaseRequest.objects.all()
            )
            return self.filter(document__in=approved_requests)
        except ImportError:
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
    Purchase Request Line - SYNCHRONIZED WITH NOMENCLATURES

    UNCHANGED: Fields remain the same
    CHANGED: Methods use nomenclatures services
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

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseRequestLineManager()

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
    # VALIDATION - ENHANCED WITH NOMENCLATURES
    # =====================
    def clean(self):
        """Request line validation - ENHANCED"""
        super().clean()

        # Requested quantity must be positive
        if self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Requested quantity must be greater than zero')
            })

        # Price validation
        if self.entered_price is not None and self.entered_price < 0:
            raise ValidationError({
                'entered_price': _('Entered price cannot be negative')
            })

        # Priority validation
        if self.priority < 0:
            raise ValidationError({
                'priority': _('Priority cannot be negative')
            })

        # Product restrictions validation - ENHANCED
        if self.product:
            try:
                from products.services.validation_service import ProductValidationService

                can_purchase, message, details = ProductValidationService.can_purchase_product(
                    product=self.product,
                    quantity=self.requested_quantity
                )

                if not can_purchase:
                    raise ValidationError({
                        'product': f"Cannot purchase this product: {message}"
                    })
            except ImportError:
                # Fallback validation
                pass

    def get_estimated_price(self):
        try:
            from inventory.services import InventoryService
            availability = InventoryService.check_availability(
                self.document.location,  # ✅ FIXED!
                self.product,
                Decimal('0')
            )
            return availability.get('last_purchase_cost') or availability.get('avg_cost') or Decimal('0')
        except:
            return Decimal('0')

    # =====================
    # PROPERTIES - UNCHANGED
    # =====================



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
    # METHODS - UNCHANGED
    # =====================
    def can_be_converted(self):
        """Check if line can be converted to order"""
        return (
                self.document.status == 'approved' and
                not self.is_converted and
                self.requested_quantity > 0
        )

    def convert_to_order_line(self, order, **kwargs):
        """Convert this request line to order line"""
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
            unit_price=kwargs.get('unit_price', self.entered_price or Decimal('0')),
            notes=self.notes or '',
            **kwargs
        )

        # Mark as converted
        self.converted_to_order_line = order_line
        self.save(update_fields=['converted_to_order_line'])

        return order_line