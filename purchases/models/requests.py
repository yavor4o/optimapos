# purchases/models/requests.py - FIXED WITH NEW ARCHITECTURE

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
    """

    # =====================
    # STATUS CHOICES - специфични за заявки
    # =====================
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CONVERTED = 'converted'
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (SUBMITTED, _('Submitted for Approval')),
        (APPROVED, _('Approved')),
        (REJECTED, _('Rejected')),
        (CONVERTED, _('Converted to Order')),
        (CANCELLED, _('Cancelled')),
    ]

    # =====================
    # ЗАЯВКА-СПЕЦИФИЧНИ ПОЛЕТА
    # =====================
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=DRAFT
    )

    # REQUEST TYPE
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

    # URGENCY
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

    # BUSINESS JUSTIFICATION
    business_justification = models.TextField(
        _('Business Justification'),
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
        related_name='source_request',
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

        # БЕЗ delivery_date validation - заявките нямат delivery_date!

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
        """Submit request for approval"""
        if self.status != self.DRAFT:
            raise ValidationError("Can only submit draft requests")

        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        self.status = self.SUBMITTED
        self.updated_by = user
        self.save()

        return True

    def approve(self, user, notes=''):
        """Approve the request"""
        if self.status != self.SUBMITTED:
            raise ValidationError("Can only approve submitted requests")

        self.status = self.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes = (self.notes + '\n' + notes).strip()
        self.updated_by = user
        self.save()

        return True

    def reject(self, user, reason):
        """Reject the request"""
        if self.status != self.SUBMITTED:
            raise ValidationError("Can only reject submitted requests")

        self.status = self.REJECTED
        self.rejection_reason = reason
        self.updated_by = user
        self.save()

        return True

    def convert_to_order(self, user=None):
        """Convert approved request to purchase order"""
        if self.status != self.APPROVED:
            raise ValidationError("Can only convert approved requests")

        # Import here to avoid circular imports
        from .orders import PurchaseOrder, PurchaseOrderLine

        # Create the order
        order = PurchaseOrder.objects.create(
            supplier=self.supplier,
            location=self.location,
            # НЕ delivery_date! Поръчката има expected_delivery_date
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
        self.status = self.CONVERTED
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
        """Override with request-specific logic"""
        return self.status in [self.DRAFT]

    def can_be_submitted(self):
        """Check if request can be submitted"""
        return (
                self.status == self.DRAFT and
                self.lines.exists()
        )

    def can_be_approved(self):
        """Check if request can be approved"""
        return self.status == self.SUBMITTED

    def can_be_rejected(self):
        """Check if request can be rejected"""
        return self.status == self.SUBMITTED

    def can_be_converted(self):
        """Check if request can be converted to order"""
        return self.status == self.APPROVED

    def can_be_cancelled(self):
        """Override with request-specific logic"""
        return self.status in [self.DRAFT, self.SUBMITTED]

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_pending_approval(self):
        return self.status == self.SUBMITTED

    @property
    def is_approved(self):
        return self.status == self.APPROVED

    @property
    def is_converted(self):
        return self.status == self.CONVERTED

    @property
    def is_rejected(self):
        return self.status == self.REJECTED

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
        ) or Decimal('0.00')


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


class PurchaseRequestLine(BaseDocumentLine):
    """
    Purchase Request Line - Ред на заявка

    Логика: НЕ използва FinancialLineMixin защото заявките нямат финансови данни!
    Има само estimated_price за ориентировъчни разчети.
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
    # ЗАЯВКА-СПЕЦИФИЧНИ ПОЛЕТА
    # =====================
    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity requested')
    )

    estimated_price = models.DecimalField(
        _('Estimated Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Estimated price per unit (optional)')
    )

    # Suggested supplier for this specific item
    suggested_supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Suggested Supplier'),
        help_text=_('Preferred supplier for this item')
    )

    # Usage justification for this specific item
    item_justification = models.TextField(
        _('Item Justification'),
        blank=True,
        help_text=_('Why is this specific item needed?')
    )

    # Priority within the request
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Priority within this request (higher = more important)')
    )

    # Quality requirements
    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Quality requirements or notes')
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
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # ЗАЯВКА-СПЕЦИФИЧНА ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Request line specific validation"""
        super().clean()

        # Set quantity from requested_quantity for base validation
        if self.requested_quantity and not self.quantity:
            self.quantity = self.requested_quantity

        # Requested quantity must be positive
        if self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Requested quantity must be greater than zero')
            })

        # Estimated price validation (if provided)
        if self.estimated_price is not None and self.estimated_price < 0:
            raise ValidationError({
                'estimated_price': _('Estimated price cannot be negative')
            })

    def save(self, *args, **kwargs):
        """Enhanced save"""
        # Sync quantity with requested_quantity
        if self.requested_quantity:
            self.quantity = self.requested_quantity

        super().save(*args, **kwargs)

    # =====================
    # PROPERTIES
    # =====================
    @property
    def estimated_line_total(self):
        """Estimated total for this line (if price is provided)"""
        if self.estimated_price and self.requested_quantity:
            return self.estimated_price * self.requested_quantity
        return None

    @property
    def has_suggested_supplier(self):
        """Does this line have a suggested supplier?"""
        return self.suggested_supplier is not None

    @property
    def is_high_priority(self):
        """Is this a high priority item?"""
        return self.priority > 0