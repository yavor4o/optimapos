# purchases/models/procurement.py - CORRECTED VERSION

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocument, DocumentManager


class DocumentType(models.Model):
    """Document types for purchases - enhanced for new workflow"""

    # Predefined type keys
    REQUEST = 'request'
    ORDER = 'order'
    DELIVERY = 'delivery'
    INVOICE = 'invoice'
    ADJUSTMENT = 'adjustment'
    TRANSFER = 'transfer'

    TYPE_CHOICES = [
        (REQUEST, _('Purchase Request')),
        (ORDER, _('Purchase Order')),
        (DELIVERY, _('Delivery Receipt')),
        (INVOICE, _('Invoice')),
        (ADJUSTMENT, _('Stock Adjustment')),
        (TRANSFER, _('Internal Transfer')),
    ]

    # Basic information
    code = models.CharField(
        _('Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like REQ, ORD, DEL, INV')
    )
    name = models.CharField(
        _('Document Type Name'),
        max_length=100
    )
    type_key = models.CharField(
        _('Type Key'),
        max_length=20,
        choices=TYPE_CHOICES
    )

    # Stock impact
    stock_effect = models.IntegerField(
        _('Stock Effect'),
        choices=[
            (1, _('Increases stock')),
            (-1, _('Decreases stock')),
            (0, _('No effect'))
        ],
        default=0,
        help_text=_('How this document type affects inventory levels')
    )

    # Special settings - KEEPING EXISTING FIELD
    allow_reverse_operations = models.BooleanField(
        _('Allow Reverse Operations'),
        default=False,
        help_text=_('Allow negative quantities to reverse the stock effect')
    )
    requires_batch = models.BooleanField(
        _('Requires Batch'),
        default=False,
        help_text=_('Whether batch numbers are mandatory')
    )
    requires_expiry = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Whether expiry dates are mandatory')
    )

    # NEW workflow settings for enhanced workflow
    can_be_source = models.BooleanField(
        _('Can Be Source'),
        default=False,
        help_text=_('Whether this document type can be source for other documents')
    )
    can_reference_multiple_sources = models.BooleanField(
        _('Can Reference Multiple Sources'),
        default=False,
        help_text=_('Whether this document can be created from multiple source documents')
    )

    # EXISTING workflow settings
    auto_confirm = models.BooleanField(
        _('Auto Confirm'),
        default=False,
        help_text=_('Automatically confirm document on creation')
    )
    auto_receive = models.BooleanField(
        _('Auto Receive'),
        default=False,
        help_text=_('Automatically receive document on confirmation')
    )

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['type_key', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def auto_create_inventory_movements(self):
        """Automatically determine from stock_effect - avoiding duplication"""
        return self.stock_effect != 0

    def clean(self):
        """Document type validation"""
        super().clean()

        # Check auto operation logic
        if self.auto_receive and not self.auto_confirm:
            raise ValidationError({
                'auto_receive': _('Cannot auto-receive without auto-confirm')
            })

        # Validate workflow logic
        if self.can_reference_multiple_sources and not self.can_be_source:
            # This is OK - delivery can reference multiple orders but not be source itself
            pass

    def get_stock_effect_display_badge(self):
        """Return HTML badge for stock effect"""
        colors = {
            1: '#28A745',  # Green for increase
            -1: '#DC3545',  # Red for decrease
            0: '#6C757D'  # Gray for no effect
        }

        symbols = {
            1: '+',
            -1: '-',
            0: '='
        }

        color = colors.get(self.stock_effect, '#6C757D')
        symbol = symbols.get(self.stock_effect, '?')

        return f'<span style="background-color: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{symbol} Stock</span>'


class PurchaseDocumentManager(DocumentManager):
    """Enhanced manager for purchase documents with workflow support"""

    def requests(self):
        """Return only request documents"""
        return self.filter(document_type__code='REQ')

    def orders(self):
        """Return only order documents"""
        return self.filter(document_type__code='ORD')

    def deliveries(self):
        """Return only delivery documents (GRN for now, DEL in future)"""
        return self.filter(document_type__code__in=['GRN', 'DEL'])

    def ready_for_delivery(self, supplier=None):
        """Return orders ready to be included in deliveries"""
        queryset = self.filter(
            document_type__code='ORD',
            workflow_status='ord_confirmed'
        )
        if supplier:
            queryset = queryset.filter(supplier=supplier)
        return queryset

    def pending_approval(self):
        """Return requests pending approval"""
        return self.filter(
            document_type__code='REQ',
            workflow_status='req_submitted'
        )

    def dashboard_summary(self):
        """Enhanced dashboard summary with workflow data"""
        base_summary = super().dashboard_summary()

        workflow_summary = self.aggregate(
            pending_requests=models.Count(
                'id',
                filter=models.Q(workflow_status='req_submitted')
            ),
            ready_orders=models.Count(
                'id',
                filter=models.Q(workflow_status='ord_confirmed')
            ),
            today_deliveries=models.Count(
                'id',
                filter=models.Q(
                    delivery_date=timezone.now().date(),
                    workflow_status__in=['ord_confirmed', 'ord_in_delivery']
                )
            )
        )

        return {**base_summary, **workflow_summary}


class PurchaseDocument(BaseDocument):
    """Enhanced purchase document supporting REQ/ORD workflow"""

    # =====================
    # WORKFLOW STATUS CHOICES
    # =====================
    # Request statuses
    REQ_DRAFT = 'req_draft'
    REQ_SUBMITTED = 'req_submitted'
    REQ_APPROVED = 'req_approved'
    REQ_REJECTED = 'req_rejected'
    REQ_CONVERTED = 'req_converted'

    # Order statuses
    ORD_DRAFT = 'ord_draft'
    ORD_SENT = 'ord_sent'
    ORD_CONFIRMED = 'ord_confirmed'
    ORD_IN_DELIVERY = 'ord_in_delivery'
    ORD_COMPLETED = 'ord_completed'

    # General statuses
    CANCELLED = 'cancelled'
    CLOSED = 'closed'

    WORKFLOW_STATUS_CHOICES = [
        # Request statuses
        (REQ_DRAFT, _('Request: Draft')),
        (REQ_SUBMITTED, _('Request: Submitted for Approval')),
        (REQ_APPROVED, _('Request: Approved')),
        (REQ_REJECTED, _('Request: Rejected')),
        (REQ_CONVERTED, _('Request: Converted to Order')),

        # Order statuses
        (ORD_DRAFT, _('Order: Draft')),
        (ORD_SENT, _('Order: Sent to Supplier')),
        (ORD_CONFIRMED, _('Order: Confirmed by Supplier')),
        (ORD_IN_DELIVERY, _('Order: In Delivery Process')),
        (ORD_COMPLETED, _('Order: Completed')),

        # General statuses
        (CANCELLED, _('Cancelled')),
        (CLOSED, _('Closed')),
    ]

    # =====================
    # PURCHASE-SPECIFIC FIELDS
    # =====================

    # Essential purchase fields
    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were/will be delivered')
    )

    # Relations
    supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.PROTECT,
        related_name='purchase_documents',
        verbose_name=_('Supplier')
    )
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        related_name='purchase_documents',
        verbose_name=_('Location')
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        verbose_name=_('Document Type')
    )

    # Reference numbers
    supplier_document_number = models.CharField(
        _('Supplier Document Number'),
        max_length=50,
        blank=True,
        help_text=_('Supplier\'s invoice/delivery note number')
    )
    external_reference = models.CharField(
        _('External Reference'),
        max_length=100,
        blank=True,
        help_text=_('PO number, contract reference, etc.')
    )

    # =====================
    # NEW WORKFLOW FIELDS
    # =====================

    # Workflow tracking
    workflow_status = models.CharField(
        _('Workflow Status'),
        max_length=20,
        choices=WORKFLOW_STATUS_CHOICES,
        default=REQ_DRAFT,
        help_text=_('Detailed workflow status based on document type')
    )

    # Source tracking
    source_document = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derived_documents',
        verbose_name=_('Source Document'),
        help_text=_('Reference to the document this was created from (REQ→ORD workflow)')
    )

    # Request-specific fields
    requested_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='purchase_requests',
        verbose_name=_('Requested By'),
        help_text=_('User who created the request')
    )
    approved_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='approved_requests',
        verbose_name=_('Approved By'),
        help_text=_('Manager who approved the request')
    )
    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True,
        help_text=_('When the request was approved')
    )
    urgency_level = models.CharField(
        _('Urgency Level'),
        max_length=10,
        choices=[
            ('low', _('Low Priority')),
            ('normal', _('Normal Priority')),
            ('high', _('High Priority')),
            ('urgent', _('Urgent')),
        ],
        default='normal',
        help_text=_('Priority level for request processing')
    )

    # Order-specific fields
    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When we expect to receive this order')
    )
    supplier_confirmed = models.BooleanField(
        _('Supplier Confirmed'),
        default=False,
        help_text=_('Whether supplier has confirmed this order')
    )
    supplier_confirmed_date = models.DateField(
        _('Supplier Confirmed Date'),
        null=True,
        blank=True,
        help_text=_('When supplier confirmed the order')
    )
    order_reference = models.CharField(
        _('Order Reference'),
        max_length=100,
        blank=True,
        help_text=_('Internal order reference or PO number')
    )

    # =====================
    # EXISTING IMPORTANT FIELDS TO KEEP
    # =====================

    # KEEPING existing auto invoice functionality for backward compatibility
    auto_create_invoice = models.BooleanField(
        _('Auto Create Invoice'),
        default=False,
        help_text=_('Automatically create invoice when document is received')
    )

    # Managers
    objects = PurchaseDocumentManager()

    class Meta:
        verbose_name = _('Purchase Document')
        verbose_name_plural = _('Purchase Documents')
        ordering = ['-delivery_date', '-document_date']
        indexes = [
            models.Index(fields=['document_type', 'workflow_status']),
            models.Index(fields=['source_document', 'document_type']),
            models.Index(fields=['supplier', 'workflow_status', 'document_type']),
            models.Index(fields=['delivery_date', 'status']),
            models.Index(fields=['location', 'document_date']),
        ]

    # =====================
    # PROPERTIES
    # =====================

    @property
    def is_request(self):
        """Check if this is a request document"""
        return self.document_type.code == 'REQ'

    @property
    def is_order(self):
        """Check if this is an order document"""
        return self.document_type.code == 'ORD'

    @property
    def is_delivery(self):
        """Check if this is a delivery document"""
        return self.document_type.code in ['GRN', 'DEL']

    @property
    def can_be_converted_to_order(self):
        """Check if request can be converted to order"""
        return (
                self.is_request and
                self.workflow_status == self.REQ_APPROVED and
                not self.derived_documents.filter(document_type__code='ORD').exists()
        )

    @property
    def can_be_included_in_delivery(self):
        """Check if order can be included in delivery"""
        return (
                self.is_order and
                self.workflow_status == self.ORD_CONFIRMED
        )

    @property
    def fulfillment_percentage(self):
        """Calculate delivery fulfillment percentage for orders"""
        if not self.is_order:
            return None

        total_ordered = sum(line.quantity for line in self.lines.all())
        if total_ordered == 0:
            return 0

        # Calculate from delivery lines when available
        # For now, basic calculation based on received_quantity
        total_received = sum(line.received_quantity for line in self.lines.all())
        return (total_received / total_ordered) * 100 if total_ordered > 0 else 0

    # =====================
    # WORKFLOW METHODS
    # =====================

    def convert_to_order(self, user=None):
        """Convert approved request to order"""
        if not self.can_be_converted_to_order:
            raise ValidationError(
                "Can only convert approved requests that haven't been converted yet"
            )

        # Get or create ORDER document type
        order_type, created = DocumentType.objects.get_or_create(
            code='ORD',
            defaults={
                'name': 'Purchase Order',
                'type_key': DocumentType.ORDER,
                'stock_effect': 0,
                'can_be_source': True,
                'can_reference_multiple_sources': False,
                'is_active': True,
            }
        )

        # Create order document
        order = PurchaseDocument.objects.create(
            document_type=order_type,
            source_document=self,
            supplier=self.supplier,
            location=self.location,
            document_date=timezone.now().date(),
            delivery_date=self.delivery_date,
            expected_delivery_date=self.delivery_date,
            workflow_status=self.ORD_DRAFT,
            created_by=user or self.created_by,
            order_reference=f"FROM-{self.document_number}",
            notes=f"Converted from request {self.document_number}\n{self.notes or ''}"
        )

        # Copy lines
        for req_line in self.lines.all():
            # Import here to avoid circular import
            from .transactions import PurchaseDocumentLine
            PurchaseDocumentLine.objects.create(
                document=order,
                line_number=req_line.line_number,
                product=req_line.product,
                quantity=req_line.quantity,
                unit=req_line.unit,
                unit_price=req_line.unit_price,
                discount_percent=req_line.discount_percent,
                batch_number=req_line.batch_number,
                expiry_date=req_line.expiry_date,
                # New fields for workflow
                line_type='from_order'
            )

        # Update request status
        self.workflow_status = self.REQ_CONVERTED
        self.save()

        # Recalculate totals for new order
        order.recalculate_totals()

        return order

    def submit_for_approval(self, user=None):
        """Submit request for approval"""
        if not self.is_request or self.workflow_status != self.REQ_DRAFT:
            raise ValidationError("Can only submit draft requests")

        if not self.lines.exists():
            raise ValidationError("Cannot submit request without line items")

        self.workflow_status = self.REQ_SUBMITTED
        self.updated_by = user
        self.save()

    def approve_request(self, user=None):
        """Approve submitted request"""
        if self.workflow_status != self.REQ_SUBMITTED:
            raise ValidationError("Can only approve submitted requests")

        self.workflow_status = self.REQ_APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.updated_by = user
        self.save()

    def reject_request(self, user=None, reason=""):
        """Reject submitted request"""
        if self.workflow_status != self.REQ_SUBMITTED:
            raise ValidationError("Can only reject submitted requests")

        self.workflow_status = self.REQ_REJECTED
        self.updated_by = user
        if reason:
            self.notes = f"{self.notes or ''}\nREJECTION REASON: {reason}"
        self.save()

    def send_to_supplier(self, user=None):
        """Send order to supplier"""
        if not self.is_order or self.workflow_status != self.ORD_DRAFT:
            raise ValidationError("Can only send draft orders")

        self.workflow_status = self.ORD_SENT
        self.updated_by = user
        self.save()

    def confirm_by_supplier(self, user=None, confirmed_date=None):
        """Mark order as confirmed by supplier"""
        if self.workflow_status != self.ORD_SENT:
            raise ValidationError("Can only confirm sent orders")

        self.workflow_status = self.ORD_CONFIRMED
        self.supplier_confirmed = True
        self.supplier_confirmed_date = confirmed_date or timezone.now().date()
        self.updated_by = user
        self.save()

    # =====================
    # ENHANCED METHODS
    # =====================

    def clean(self):
        """Enhanced validation"""
        super().clean()

        # Validate workflow status based on document type
        if self.is_request and not self.workflow_status.startswith('req_'):
            if self.workflow_status not in [self.CANCELLED, self.CLOSED]:
                raise ValidationError({
                    'workflow_status': 'Invalid workflow status for request document'
                })

        if self.is_order and not self.workflow_status.startswith('ord_'):
            if self.workflow_status not in [self.CANCELLED, self.CLOSED]:
                raise ValidationError({
                    'workflow_status': 'Invalid workflow status for order document'
                })

        # Validate source document relationship
        if self.source_document:
            if self.source_document.pk == self.pk:
                raise ValidationError({
                    'source_document': 'Document cannot be source of itself'
                })

            # Source document should be approved for conversion
            if (self.is_order and self.source_document.is_request and
                    self.source_document.workflow_status != self.REQ_APPROVED):
                raise ValidationError({
                    'source_document': 'Source request must be approved'
                })

        # Validate required fields based on document type
        if self.is_request and not self.requested_by:
            # Auto-set to creator if not specified
            self.requested_by = self.created_by

    def save(self, *args, **kwargs):
        """Enhanced save with workflow logic"""
        is_new = self.pk is None

        # Set default workflow status based on document type for new documents
        if is_new and self.workflow_status == self.REQ_DRAFT:
            if self.is_order:
                self.workflow_status = self.ORD_DRAFT

        # Auto-generate document number if needed
        if is_new and not self.document_number:
            self.document_number = self.generate_document_number()

        # Sync old status field with workflow_status for backward compatibility
        self._sync_status_fields()

        # Handle auto operations from document type
        if is_new and self.document_type:
            if self.document_type.auto_confirm:
                if self.is_request:
                    self.workflow_status = self.REQ_APPROVED
                elif self.is_order:
                    self.workflow_status = self.ORD_CONFIRMED

            if self.document_type.auto_receive:
                if self.is_order:
                    self.workflow_status = self.ORD_COMPLETED

        super().save(*args, **kwargs)

        # Handle auto invoice creation if needed (existing functionality)
        if (is_new and self.auto_create_invoice and
                self.document_type.code == 'GRN' and self.supplier_document_number):
            self._trigger_auto_invoice_creation()

    def _sync_status_fields(self):
        """Sync old status field with new workflow_status for backward compatibility"""
        if self.workflow_status.startswith('req_'):
            if self.workflow_status == self.REQ_DRAFT:
                self.status = self.DRAFT
            elif self.workflow_status in [self.REQ_SUBMITTED, self.REQ_APPROVED]:
                self.status = self.CONFIRMED
            elif self.workflow_status == self.REQ_CONVERTED:
                self.status = self.RECEIVED
        elif self.workflow_status.startswith('ord_'):
            if self.workflow_status == self.ORD_DRAFT:
                self.status = self.DRAFT
            elif self.workflow_status in [self.ORD_SENT, self.ORD_CONFIRMED]:
                self.status = self.CONFIRMED
            elif self.workflow_status in [self.ORD_IN_DELIVERY, self.ORD_COMPLETED]:
                self.status = self.RECEIVED

    def generate_document_number(self):
        """Generate unique document number based on document type"""
        prefix = self.document_type.code if self.document_type else 'PUR'
        year = timezone.now().year

        # Find last number for this year and type
        last_doc = PurchaseDocument.objects.filter(
            document_number__startswith=f"{prefix}{year}",
            document_type=self.document_type
        ).order_by('-document_number').first()

        if last_doc:
            try:
                # Extract number from last document
                last_number = int(last_doc.document_number.split(f"{prefix}{year}")[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}{year}{new_number:04d}"

    def _trigger_auto_invoice_creation(self):
        """Trigger auto invoice creation via service (existing functionality)"""
        try:
            from ..services import DocumentService
            DocumentService.create_invoice_from_grn(self)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Auto invoice creation failed for {self.document_number}: {e}")

    # =====================
    # ENHANCED STATUS TRANSITION METHODS
    # =====================

    def confirm(self, user=None):
        """Enhanced confirm method with workflow support"""
        if self.is_request:
            self.approve_request(user)
        elif self.is_order:
            self.confirm_by_supplier(user)
        else:
            # Default behavior for other document types
            super().confirm(user)

    def receive(self, user=None):
        """Enhanced receive method with workflow and stock movement support"""
        if not self.can_be_received():
            raise ValidationError("Document cannot be received in current state")

        # Update workflow status
        if self.is_order:
            self.workflow_status = self.ORD_COMPLETED

        # Call parent method
        super().receive(user)

        # Create stock movements if document type requires it
        if self.document_type.stock_effect != 0:
            self._create_stock_movements()

    def _create_stock_movements(self):
        """Create stock movements based on document type stock_effect"""
        try:
            from ..services import DocumentService
            return DocumentService.create_stock_movements(self)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Stock movement creation failed for {self.document_number}: {e}")
            return {'success': False, 'error': str(e)}

    def __str__(self):
        type_display = 'REQ' if self.is_request else 'ORD' if self.is_order else self.document_type.code
        return f"{type_display}-{self.document_number} | {self.supplier.name}"