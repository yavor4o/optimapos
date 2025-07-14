# purchases/models/requests.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocument, BaseDocumentLine
from .document_types import DocumentType


class PurchaseRequestManager(models.Manager):
    """Manager for Purchase Requests with specific queries"""

    def pending_approval(self):
        """Requests waiting for approval"""
        return self.filter(status='submitted')

    def approved(self):
        """Approved requests ready for conversion"""
        return self.filter(status='approved')

    def converted(self):
        """Requests that were converted to orders"""
        return self.filter(status='converted')

    def by_requester(self, user):
        """Requests created by specific user"""
        return self.filter(requested_by=user)

    def urgent(self):
        """Urgent requests"""
        return self.filter(urgency_level='urgent')

    def for_approval_by(self, user):
        """Requests that can be approved by specific user"""
        # TODO: Implement approval hierarchy when we have it
        return self.filter(status='submitted')

    def overdue_approval(self, days=3):
        """Requests submitted but not approved within timeframe"""
        cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
        return self.filter(
            status='submitted',
            document_date__lte=cutoff_date
        )


class PurchaseRequest(BaseDocument):
    """
    Purchase Request - Заявки за покупка

    Workflow: draft → submitted → approved → converted

    Created by: Store managers, department heads
    Approved by: Regional managers, procurement team
    Converted to: PurchaseOrder
    """

    # =====================
    # REQUEST-SPECIFIC FIELDS
    # =====================
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='purchase_requests',
        verbose_name=_('Requested By'),
        help_text=_('User who created this request')
    )

    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_purchase_requests',
        verbose_name=_('Approved By'),
        help_text=_('User who approved this request')
    )

    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True,
        help_text=_('When the request was approved')
    )

    # =====================
    # REQUEST CLASSIFICATION
    # =====================
    URGENCY_CHOICES = [
        ('normal', _('Normal')),
        ('urgent', _('Urgent')),
        ('emergency', _('Emergency')),
    ]

    urgency_level = models.CharField(
        _('Urgency Level'),
        max_length=20,
        choices=URGENCY_CHOICES,
        default='normal',
        help_text=_('Priority level for this request')
    )

    REQUEST_TYPE_CHOICES = [
        ('regular', _('Regular Replenishment')),
        ('new_product', _('New Product')),
        ('promotional', _('Promotional Stock')),
        ('emergency', _('Emergency Stock')),
        ('seasonal', _('Seasonal Stock')),
    ]

    request_type = models.CharField(
        _('Request Type'),
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='regular',
        help_text=_('Type of purchase request')
    )

    # =====================
    # JUSTIFICATION
    # =====================
    business_justification = models.TextField(
        _('Business Justification'),
        blank=True,
        help_text=_('Reason for this purchase request')
    )

    expected_usage = models.TextField(
        _('Expected Usage'),
        blank=True,
        help_text=_('How the requested items will be used')
    )

    # =====================
    # APPROVAL WORKFLOW
    # =====================
    approval_required = models.BooleanField(
        _('Approval Required'),
        default=True,
        help_text=_('Whether this request requires approval')
    )

    approval_amount_limit = models.DecimalField(
        _('Approval Amount Limit'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Amount limit that triggered approval requirement')
    )

    rejection_reason = models.TextField(
        _('Rejection Reason'),
        blank=True,
        help_text=_('Reason for rejecting this request')
    )

    # =====================
    # CONVERSION TRACKING
    # =====================
    converted_to_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_request',
        verbose_name=_('Converted to Order'),
        help_text=_('Order created from this request')
    )

    converted_at = models.DateTimeField(
        _('Converted At'),
        null=True,
        blank=True,
        help_text=_('When this request was converted to order')
    )

    converted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='converted_purchase_requests',
        verbose_name=_('Converted By'),
        help_text=_('User who converted this request to order')
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

    # =====================
    # DOCUMENT TYPE SETUP
    # =====================
    def save(self, *args, **kwargs):
        # Auto-set document type to REQ if not set
        if not hasattr(self, 'document_type') or not self.document_type:
            self.document_type = DocumentType.get_by_code('REQ')

        super().save(*args, **kwargs)

    def get_document_prefix(self):
        """Override to return REQ prefix"""
        return "REQ"

    # =====================
    # STATUS VALIDATIONS
    # =====================
    def clean(self):
        """Enhanced validation for requests"""
        super().clean()

        # Approval validation
        if self.status == 'approved':
            if not self.approved_by:
                raise ValidationError({
                    'approved_by': _('Approved by is required when status is approved')
                })
            if not self.approved_at:
                self.approved_at = timezone.now()

        # Conversion validation
        if self.status == 'converted':
            if not self.converted_to_order:
                raise ValidationError({
                    'converted_to_order': _('Converted order reference is required')
                })

        # Rejection validation
        if self.status == 'rejected':
            if not self.rejection_reason:
                raise ValidationError({
                    'rejection_reason': _('Rejection reason is required')
                })

    # =====================
    # WORKFLOW METHODS
    # =====================
    def submit_for_approval(self, user=None):
        """Submit request for approval"""
        if self.status != self.DRAFT:
            raise ValidationError("Can only submit draft requests")

        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        self.status = 'submitted'
        self.updated_by = user
        self.save()

        return True

    def approve(self, user, notes=''):
        """Approve the request"""
        if self.status != 'submitted':
            raise ValidationError("Can only approve submitted requests")

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
        if self.status not in ['submitted']:
            raise ValidationError("Can only reject submitted requests")

        self.status = 'rejected'
        self.rejection_reason = reason
        self.updated_by = user
        self.save()

        return True

    def convert_to_order(self, user=None):
        """Convert approved request to purchase order"""
        if self.status != 'approved':
            raise ValidationError("Can only convert approved requests")

        # Import here to avoid circular imports
        from .orders import PurchaseOrder, PurchaseOrderLine

        # Create the order
        order = PurchaseOrder.objects.create(
            supplier=self.supplier,
            location=self.location,
            delivery_date=self.delivery_date,
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
                quantity=req_line.quantity,
                unit=req_line.unit,
                unit_price=req_line.unit_price,
                discount_percent=req_line.discount_percent,
                notes=req_line.quality_notes,
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

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_submitted(self):
        """Check if request can be submitted"""
        return (
                self.status == self.DRAFT and
                self.lines.exists()
        )

    def can_be_approved(self):
        """Check if request can be approved"""
        return self.status == 'submitted'

    def can_be_rejected(self):
        """Check if request can be rejected"""
        return self.status == 'submitted'

    def can_be_converted(self):
        """Check if request can be converted to order"""
        return self.status == 'approved'

    def can_be_edited(self):
        """Override parent method with request-specific logic"""
        return self.status in [self.DRAFT]

    def can_be_cancelled(self):
        """Override parent method"""
        return self.status in [self.DRAFT, 'submitted']

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

    @property
    def is_overdue_approval(self, days=3):
        """Check if approval is overdue"""
        if self.status != 'submitted':
            return False

        cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
        return self.document_date <= cutoff_date


class PurchaseRequestLineManager(models.Manager):
    """Manager for Purchase Request Lines"""

    def for_request(self, request):
        """Lines for specific request"""
        return self.filter(document=request)

    def pending_approval(self):
        """Lines in requests pending approval"""
        return self.filter(document__status='submitted')

    def approved_not_ordered(self):
        """Lines from approved requests not yet converted"""
        return self.filter(
            document__status='approved'
        ).exclude(
            document__status='converted'
        )


class PurchaseRequestLine(BaseDocumentLine):
    """
    Purchase Request Line - Редове на заявка за покупка

    Contains requested products with quantities and basic pricing
    """

    # =====================
    # FOREIGN KEY TO PARENT
    # =====================
    document = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Request')
    )

    # =====================
    # REQUEST-SPECIFIC FIELDS
    # =====================
    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Originally requested quantity')
    )

    current_stock_level = models.DecimalField(
        _('Current Stock Level'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Stock level when request was created')
    )

    minimum_stock_level = models.DecimalField(
        _('Minimum Stock Level'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Minimum stock level for this product')
    )

    suggested_supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Suggested Supplier'),
        help_text=_('Recommended supplier for this product')
    )

    estimated_price = models.DecimalField(
        _('Estimated Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Estimated unit price')
    )

    # =====================
    # JUSTIFICATION
    # =====================
    line_justification = models.TextField(
        _('Line Justification'),
        blank=True,
        help_text=_('Specific reason for requesting this item')
    )

    # =====================
    # TRACKING
    # =====================
    converted_to_order_line = models.ForeignKey(
        'purchases.PurchaseOrderLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_request_line',
        verbose_name=_('Converted to Order Line'),
        help_text=_('Order line created from this request line')
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
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation for request lines"""
        super().clean()

        # Set quantity from requested_quantity if not set
        if not self.quantity and self.requested_quantity:
            self.quantity = self.requested_quantity

        # Ensure requested_quantity is set
        if not self.requested_quantity and self.quantity:
            self.requested_quantity = self.quantity

    def save(self, *args, **kwargs):
        """Enhanced save with stock level capture"""
        # Capture current stock levels if new line
        if not self.pk and self.product:
            self.current_stock_level = self.product.current_stock_qty
            # Get minimum stock level from product or inventory settings
            if hasattr(self.product, 'minimum_stock_level'):
                self.minimum_stock_level = self.product.minimum_stock_level

        super().save(*args, **kwargs)

    # =====================
    # PROPERTIES
    # =====================
    @property
    def stock_deficit(self):
        """Calculate how much stock is needed"""
        if self.minimum_stock_level > self.current_stock_level:
            return self.minimum_stock_level - self.current_stock_level
        return Decimal('0.000')

    @property
    def is_emergency_request(self):
        """Check if this is an emergency stock request"""
        return self.current_stock_level <= self.minimum_stock_level

    @property
    def estimated_total(self):
        """Calculate estimated total if estimated price is available"""
        if self.estimated_price and self.quantity:
            return self.estimated_price * self.quantity
        return None

    @property
    def is_converted(self):
        """Check if this line was converted to order"""
        return self.converted_to_order_line is not None