# purchases/models/requests.py - CLEAN VERSION БЕЗ estimated_price
import logging
from django.db import models, transaction
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from .base import BaseDocument, BaseDocumentLine, SmartDocumentTypeMixin, FinancialMixin, FinancialLineMixin

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


class PurchaseRequest(SmartDocumentTypeMixin, BaseDocument, FinancialMixin):
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
        """Submit request for approval via ApprovalService"""
        from nomenclatures.services.approval_service import ApprovalService

        # Business validation
        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        # Use ApprovalService
        result = ApprovalService.execute_transition(
            document=self,
            to_status='submitted',
            user=user,
            comments="Submitted for approval"
        )

        if not result['success']:
            raise ValidationError(result['message'])

        return True

    def convert_to_order(self, user=None, **kwargs):
        """Convert approved request to purchase order"""
        if self.status != 'approved':
            raise ValidationError("Can only convert approved requests")

        # Import here to avoid circular imports
        from .orders import PurchaseOrder, PurchaseOrderLine

        with transaction.atomic():
            # Create the order
            order = PurchaseOrder.objects.create(
                supplier=self.supplier,
                location=self.location,
                document_date=timezone.now().date(),
                expected_delivery_date=timezone.now().date() + timedelta(days=7),
                external_reference=self.external_reference,
                notes=f"Created from request {self.document_number}\n{self.notes}".strip(),
                source_request=self,
                created_by=user or self.updated_by,
                updated_by=user or self.updated_by,
            )

            # ✅ FIXED: Copy lines using unit_price (proper VAT processed)
            for req_line in self.lines.all():
                PurchaseOrderLine.objects.create(
                    document=order,
                    line_number=req_line.line_number,
                    product=req_line.product,
                    unit=req_line.unit,
                    ordered_quantity=req_line.requested_quantity,

                    # ✅ USE unit_price (VAT processed) not estimated_price
                    unit_price=req_line.unit_price or Decimal('0.0000'),
                    entered_price=req_line.entered_price or Decimal('0.0000'),

                    source_request_line=req_line,
                )

            # Update request status via ApprovalService
            from nomenclatures.services.approval_service import ApprovalService

            result = ApprovalService.execute_transition(
                document=self,
                to_status='converted',
                user=user,
                comments=f"Converted to order {order.document_number}"
            )

            if result['success']:
                self.converted_to_order = order
                self.converted_at = timezone.now()
                self.converted_by = user
                self.save()

            # Recalculate order totals
            order.recalculate_totals()

            return order

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_edited(self):
        """Check if request can be edited"""
        return super().can_be_edited() and not self.is_converted

    def can_be_submitted(self):
        """Check if request can be submitted"""
        return (
                self.can_transition_to('submitted') and
                self.lines.exists()
        )

    def can_be_converted(self):
        """Check if request can be converted to order"""
        return self.can_transition_to('converted')

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
        """Get planning cost using effective costs for inventory planning"""
        from purchases.services.vat_service import SmartVATService

        total_cost = Decimal('0')
        for line in self.lines.all():
            effective_cost = SmartVATService.get_effective_cost(line)
            quantity = line.get_quantity()
            total_cost += effective_cost * quantity

        return total_cost

    def get_financial_summary(self):
        """Get complete financial summary"""
        return {
            'lines_count': self.lines.count(),
            'subtotal': self.subtotal,  # From FinancialMixin (net amounts)
            'vat_total': self.vat_total,  # From FinancialMixin (VAT amounts)
            'total': self.total,  # From FinancialMixin (gross amounts)
            'planning_cost': self.get_planning_cost()  # For inventory planning
        }

    def get_estimated_total(self):
        """
        Връща общата стойност на заявката въз основа на entered_price и requested_quantity
        """
        from decimal import Decimal

        total = Decimal('0.00')
        for line in self.lines.all():
            qty = line.requested_quantity or 0
            price = line.entered_price or 0
            total += qty * price

        return total


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
    Purchase Request Line - Ред от заявка

    ✅ CLEANED UP: БЕЗ estimated_price, използва само entered_price
    ✅ FIXED: FinancialLineMixin за правилни VAT изчисления
    ✅ AUTO-SUGGESTION: Автоматично предлага цени от product history
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

    suggested_supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Suggested Supplier'),
        help_text=_('Preferred supplier for this item')
    )

    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Priority within this request (higher = more important)')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseRequestLineManager()

    class Meta:
        verbose_name = _('Purchase Request Line')
        verbose_name_plural = _('Purchase Request Lines')
        ordering = ['line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['suggested_supplier']),
        ]

    def __str__(self):
        return f"Line {self.line_number}: {self.product.name} x {self.requested_quantity}"

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

        # Unit validation
        if self.product and self.unit:
            valid_units = self.product.get_valid_purchase_units()
            if self.unit not in valid_units:
                unit_names = [u.name for u in valid_units]
                raise ValidationError({
                    'unit': f'Invalid unit. Valid units: {", ".join(unit_names)}'
                })

    def save(self, *args, **kwargs):
        """
        ✅ CLEANED UP save with auto-suggestion and proper VAT processing
        """

        # ✅ AUTO-SUGGEST entered_price from product history
        if (not self.entered_price or self.entered_price == 0) and self.product:
            try:
                suggested_price = self.product.get_estimated_purchase_price(self.unit)
                if suggested_price and suggested_price > 0:
                    self.entered_price = suggested_price
                    logger.info(f"Auto-suggested price {suggested_price} for {self.product.code}")
            except Exception as e:
                logger.warning(f"Could not auto-suggest price for {self.product.code}: {e}")

        # ✅ SYNC QUANTITIES
        if self.requested_quantity:
            self.quantity = self.requested_quantity

        # ✅ FINANCIAL CALCULATIONS via FinancialLineMixin
        # This automatically calls SmartVATService for proper VAT processing
        super().save(*args, **kwargs)

    # =====================
    # BUSINESS METHODS
    # =====================
    def get_quantity_display(self):
        """Get formatted quantity with unit"""
        if self.unit:
            return f"{self.requested_quantity} {self.unit.code}"
        return str(self.requested_quantity)

    def is_high_value(self, threshold=500):
        """Check if this line has high value"""
        return self.gross_amount and self.gross_amount >= threshold

    def get_quantity(self):
        """Required by FinancialLineMixin"""
        return self.requested_quantity or Decimal('0')

    def has_alternatives(self):
        """Does this line have alternative products specified?"""
        return bool(self.alternative_products.strip())

    def has_pricing(self):
        """Does this line have price information?"""
        return self.entered_price and self.entered_price > 0

    def get_price_source_info(self):
        """Get information about where the price came from"""
        if not self.has_pricing():
            return {
                'has_price': False,
                'source': 'No price entered',
                'auto_suggested': False
            }

        # Check if this might be auto-suggested
        auto_suggested = False
        if self.product:
            try:
                suggested = self.product.get_estimated_purchase_price(self.unit)
                if suggested and abs(suggested - self.entered_price) < Decimal('0.01'):
                    auto_suggested = True
            except:
                pass

        return {
            'has_price': True,
            'source': 'Auto-suggested from history' if auto_suggested else 'Manually entered',
            'auto_suggested': auto_suggested,
            'entered_price': self.entered_price,
            'unit_price': self.unit_price,
            'vat_processed': abs(self.entered_price - self.unit_price) > Decimal('0.01')
        }