# purchases/models/transactions.py - CORRECTED VERSION

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocumentLine, LineManager


class PurchaseDocumentLineManager(LineManager):
    """Enhanced manager for purchase document lines with workflow support"""

    def from_orders(self):
        """Return lines created from orders"""
        return self.filter(line_type='from_order')

    def additional_items(self):
        """Return additional lines not from orders"""
        return self.filter(line_type__in=['additional', 'replacement'])

    def with_variance(self):
        """Return lines with quantity variance (for delivery lines)"""
        return self.exclude(
            models.Q(ordered_quantity__isnull=True) |
            models.Q(received_quantity=models.F('ordered_quantity'))
        ).filter(ordered_quantity__isnull=False)

    def over_received(self):
        """Return lines with more received than ordered"""
        return self.filter(
            ordered_quantity__isnull=False,
            received_quantity__gt=models.F('ordered_quantity')
        )

    def under_received(self):
        """Return lines with less received than ordered"""
        return self.filter(
            ordered_quantity__isnull=False,
            received_quantity__lt=models.F('ordered_quantity')
        )

    def quality_issues(self):
        """Return lines with quality issues"""
        return self.filter(quality_approved=False)

    def by_supplier(self, supplier):
        """Lines for specific supplier"""
        return self.filter(document__supplier=supplier)

    def recent_purchases(self, days=30):
        """Recent purchase lines for price analysis"""
        cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
        return self.filter(
            document__delivery_date__gte=cutoff_date,
            document__status='received'
        ).select_related('product', 'document__supplier')


class PurchaseDocumentLine(BaseDocumentLine):
    """Enhanced purchase document line with workflow support"""

    # =====================
    # LINE TYPE CHOICES
    # =====================
    FROM_ORDER = 'from_order'
    ADDITIONAL = 'additional'
    REPLACEMENT = 'replacement'

    LINE_TYPE_CHOICES = [
        (FROM_ORDER, _('From Purchase Order')),
        (ADDITIONAL, _('Additional Item')),
        (REPLACEMENT, _('Replacement Item')),
    ]

    # =====================
    # DOCUMENT RELATIONSHIP
    # =====================

    # Import here to avoid circular import issues
    document = models.ForeignKey(
        'PurchaseDocument',  # String reference to avoid circular import
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Document')
    )

    # =====================
    # NEW WORKFLOW FIELDS
    # =====================

    # Source tracking for workflow
    source_order_line = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derived_lines',
        verbose_name=_('Source Order Line'),
        help_text=_('Reference to the order line this delivery line came from')
    )

    # Line type classification
    line_type = models.CharField(
        _('Line Type'),
        max_length=20,
        choices=LINE_TYPE_CHOICES,
        default=FROM_ORDER,
        help_text=_('How this line was created')
    )

    # Quantity tracking for delivery workflow
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Original ordered quantity (for delivery lines from orders)')
    )

    # =====================
    # EXISTING PURCHASE-SPECIFIC FIELDS
    # =====================

    # Specialized fields for purchases
    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Actually received quantity (may differ from ordered)')
    )

    # Quality control - KEEPING EXISTING FUNCTIONALITY
    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Whether the received goods passed quality control')
    )
    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Notes about quality issues or inspections')
    )

    # KEEPING EXISTING pricing analysis fields
    old_sale_price = models.DecimalField(
        _('Current Sale Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Current selling price before this purchase')
    )
    new_sale_price = models.DecimalField(
        _('Suggested Sale Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Suggested selling price based on purchase cost')
    )
    markup_percentage = models.DecimalField(
        _('Markup Percentage'),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Calculated markup percentage')
    )

    # Enhanced managers
    objects = PurchaseDocumentLineManager()

    class Meta:
        verbose_name = _('Purchase Document Line')
        verbose_name_plural = _('Purchase Document Lines')
        unique_together = ('document', 'line_number')
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['source_order_line', 'line_type']),
            models.Index(fields=['document', 'line_type']),
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product', 'document']),
            models.Index(fields=['batch_number']),
        ]

    # =====================
    # PROPERTIES FOR WORKFLOW
    # =====================

    @property
    def is_from_order(self):
        """Check if this line came from an order"""
        return self.source_order_line is not None

    @property
    def variance_quantity(self):
        """Calculate quantity variance (received - ordered)"""
        if self.ordered_quantity is not None and self.received_quantity is not None:
            return self.received_quantity - self.ordered_quantity
        return None

    @property
    def variance_percent(self):
        """Calculate variance percentage"""
        if self.ordered_quantity and self.ordered_quantity > 0:
            variance = self.variance_quantity
            if variance is not None:
                return (variance / self.ordered_quantity) * 100
        return None

    @property
    def has_variance(self):
        """Check if there's a quantity variance"""
        variance = self.variance_quantity
        return variance is not None and variance != 0

    @property
    def variance_status(self):
        """Get variance status description"""
        if not self.is_from_order:
            return 'N/A'

        variance = self.variance_quantity
        if variance is None:
            return 'Unknown'
        elif variance == 0:
            return 'Perfect'
        elif variance > 0:
            return 'Over-received'
        else:
            return 'Under-received'

    # KEEPING existing properties
    @property
    def current_stock_display(self):
        """Display current stock from product"""
        return self.product.current_stock_qty if self.product else 0

    @property
    def last_purchase_price_display(self):
        """Display last purchase price from product"""
        return self.product.last_purchase_cost if self.product else 0

    # =====================
    # WORKFLOW METHODS
    # =====================

    def create_from_order_line(self, order_line, received_quantity=None):
        """Create delivery line from order line"""
        self.source_order_line = order_line
        self.line_type = self.FROM_ORDER
        self.product = order_line.product
        self.unit = order_line.unit
        self.unit_price = order_line.unit_price
        self.discount_percent = order_line.discount_percent
        self.ordered_quantity = order_line.quantity
        self.quantity = received_quantity or order_line.quantity
        self.received_quantity = received_quantity or order_line.quantity
        self.batch_number = order_line.batch_number
        self.expiry_date = order_line.expiry_date
        self.line_number = order_line.line_number

    def validate_variance(self, tolerance_percent=5.0):
        """Validate if variance is within acceptable tolerance"""
        if not self.is_from_order:
            return True

        variance_pct = self.variance_percent
        if variance_pct is None:
            return True

        return abs(variance_pct) <= tolerance_percent

    def get_variance_explanation(self):
        """Get human-readable variance explanation"""
        if not self.is_from_order:
            return "Direct delivery item - no variance tracking"

        variance = self.variance_quantity
        if variance is None:
            return "Variance cannot be calculated"
        elif variance == 0:
            return "Received exactly as ordered"
        elif variance > 0:
            return f"Received {variance} more than ordered (+{self.variance_percent:.1f}%)"
        else:
            return f"Received {abs(variance)} less than ordered ({self.variance_percent:.1f}%)"

    # =====================
    # ENHANCED VALIDATION
    # =====================

    def clean(self):
        """Enhanced validation"""
        super().clean()

        # Validate line type consistency
        if self.line_type == self.FROM_ORDER and not self.source_order_line:
            raise ValidationError({
                'source_order_line': 'Source order line is required for "from_order" line type'
            })

        if self.line_type != self.FROM_ORDER and self.source_order_line:
            raise ValidationError({
                'line_type': 'Line type should be "from_order" when source order line is specified'
            })

        # Validate ordered quantity
        if self.source_order_line and not self.ordered_quantity:
            raise ValidationError({
                'ordered_quantity': 'Ordered quantity is required when source order line is specified'
            })

        # Validate product consistency
        if self.source_order_line and self.product != self.source_order_line.product:
            raise ValidationError({
                'product': 'Product must match the source order line product'
            })

        # KEEPING EXISTING validation logic
        # Check if received quantity exceeds ordered (with tolerance)
        if (self.ordered_quantity and self.received_quantity and
                self.received_quantity > self.ordered_quantity * Decimal('1.1')):  # 10% tolerance
            raise ValidationError({
                'received_quantity': _('Received quantity significantly exceeds ordered quantity')
            })

        # Batch number validation based on document type
        if (self.document and self.document.document_type and
                self.document.document_type.requires_batch and not self.batch_number):
            raise ValidationError({
                'batch_number': _('Batch number is required for this document type')
            })

        # Expiry date validation based on document type
        if (self.document and self.document.document_type and
                self.document.document_type.requires_expiry and not self.expiry_date):
            raise ValidationError({
                'expiry_date': _('Expiry date is required for this document type')
            })

        # Validate unit compatibility with product
        if self.product and self.unit:
            valid_units = [self.product.base_unit]
            if hasattr(self.product, 'packagings'):
                valid_units.extend([p.unit for p in self.product.packagings.all()])

            if self.unit not in valid_units:
                raise ValidationError({
                    'unit': _('This unit is not valid for the selected product')
                })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-calculations and workflow logic"""

        # Auto-populate from source order line if available
        if self.source_order_line and not self.ordered_quantity:
            self.ordered_quantity = self.source_order_line.quantity

        # Auto-set line type based on source
        if self.source_order_line and self.line_type != self.FROM_ORDER:
            self.line_type = self.FROM_ORDER
        elif not self.source_order_line and self.line_type == self.FROM_ORDER:
            self.line_type = self.ADDITIONAL

        # Set received_quantity to quantity if not specified (for non-delivery docs)
        if self.received_quantity == 0 and self.quantity > 0:
            if not self.document or not self.document.is_delivery:
                self.received_quantity = self.quantity

        # KEEPING existing pricing analysis logic
        self._calculate_pricing_analysis()

        # Call parent save which handles base calculations
        super().save(*args, **kwargs)

        # Update product costs if this is a received purchase
        if (self.document and self.document.status == 'received' and
                self.received_quantity > 0 and self.unit_price > 0):
            self._update_product_costs()

    def _calculate_pricing_analysis(self):
        """Calculate pricing analysis fields - KEEPING EXISTING LOGIC"""
        if self.product and self.unit_price > 0:
            # Calculate suggested markup based on product category or default
            default_markup = Decimal('25.0')  # 25% default markup

            if self.markup_percentage is None:
                self.markup_percentage = default_markup

            # Calculate suggested sale price
            markup_multiplier = 1 + (self.markup_percentage / 100)
            self.new_sale_price = self.unit_price * markup_multiplier

            # Store current sale price for comparison
            if hasattr(self.product, 'current_sale_price'):
                self.old_sale_price = self.product.current_sale_price

    def _update_product_costs(self):
        """Update product cost information - KEEPING EXISTING LOGIC"""
        if self.product and self.unit_price > 0:
            # Update last purchase cost
            self.product.last_purchase_cost = self.unit_price

            # Update moving average cost
            old_qty = self.product.current_stock_qty
            old_cost = self.product.current_avg_cost
            new_qty = self.received_quantity
            new_cost = self.unit_price

            if old_qty > 0:
                total_value = (old_qty * old_cost) + (new_qty * new_cost)
                total_qty = old_qty + new_qty
                self.product.current_avg_cost = total_value / total_qty if total_qty > 0 else new_cost
            else:
                self.product.current_avg_cost = new_cost

            # Update current stock quantity
            self.product.current_stock_qty += new_qty

            self.product.save(update_fields=[
                'last_purchase_cost', 'current_avg_cost', 'current_stock_qty'
            ])

    def __str__(self):
        variance_info = ""
        if self.is_from_order and self.variance_quantity is not None:
            variance_info = f" (Var: {self.variance_quantity:+.1f})"

        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code} x {self.received_quantity or self.quantity}{variance_info}"


# =====================
# AUDIT LOG MODEL - KEEPING EXISTING FUNCTIONALITY
# =====================

class PurchaseAuditLog(models.Model):
    """Enhanced audit log for purchase workflow tracking"""

    # Action types - ENHANCED with workflow actions
    CREATED = 'created'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CONVERTED = 'converted'
    SENT = 'sent'
    CONFIRMED = 'confirmed'
    RECEIVED = 'received'
    CANCELLED = 'cancelled'
    MODIFIED = 'modified'
    # KEEPING existing actions
    STATUS_CHANGED = 'status_changed'
    PAYMENT_UPDATED = 'payment_updated'

    ACTION_CHOICES = [
        (CREATED, _('Document Created')),
        (SUBMITTED, _('Request Submitted')),
        (APPROVED, _('Request Approved')),
        (REJECTED, _('Request Rejected')),
        (CONVERTED, _('Request Converted to Order')),
        (SENT, _('Order Sent to Supplier')),
        (CONFIRMED, _('Order Confirmed by Supplier')),
        (RECEIVED, _('Document Received')),
        (CANCELLED, _('Document Cancelled')),
        (MODIFIED, _('Document Modified')),
        (STATUS_CHANGED, _('Status Changed')),
        (PAYMENT_UPDATED, _('Payment Updated')),
    ]

    document = models.ForeignKey(
        'PurchaseDocument',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name=_('Document')
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        verbose_name=_('User')
    )
    action = models.CharField(
        _('Action'),
        max_length=20,
        choices=ACTION_CHOICES
    )
    timestamp = models.DateTimeField(
        _('Timestamp'),
        auto_now_add=True
    )
    old_status = models.CharField(
        _('Old Status'),
        max_length=20,
        blank=True
    )
    new_status = models.CharField(
        _('New Status'),
        max_length=20,
        blank=True
    )
    old_workflow_status = models.CharField(
        _('Old Workflow Status'),
        max_length=20,
        blank=True
    )
    new_workflow_status = models.CharField(
        _('New Workflow Status'),
        max_length=20,
        blank=True
    )
    notes = models.TextField(
        _('Notes'),
        blank=True
    )
    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        null=True,
        blank=True
    )
    additional_data = models.JSONField(
        _('Additional Data'),
        null=True,
        blank=True,
        help_text=_('Additional data related to the action')
    )

    class Meta:
        verbose_name = _('Purchase Audit Log')
        verbose_name_plural = _('Purchase Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['document', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - {self.get_action_display()} by {self.user.username}"

    @classmethod
    def log_action(cls, document, action, user, old_status=None, new_status=None,
                   old_workflow_status=None, new_workflow_status=None, notes=None,
                   ip_address=None, additional_data=None):
        """Helper method to create audit log entries"""
        return cls.objects.create(
            document=document,
            user=user,
            action=action,
            old_status=old_status or '',
            new_status=new_status or '',
            old_workflow_status=old_workflow_status or '',
            new_workflow_status=new_workflow_status or '',
            notes=notes or '',
            ip_address=ip_address,
            additional_data=additional_data
        )