# purchases/models/orders.py - FIXED WITH NEW ARCHITECTURE
import logging
import warnings

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
logger = logging.getLogger(__name__)
from .base import BaseDocument, BaseDocumentLine, FinancialMixin, PaymentMixin, FinancialLineMixin


class PurchaseOrderManager(models.Manager):
    """Manager for Purchase Orders with specific queries"""

    def confirmed(self):
        """Confirmed orders ready for delivery"""
        return self.filter(status='confirmed')

    def sent_to_supplier(self):
        """Orders sent to suppliers but not yet confirmed"""
        return self.filter(status='sent')

    def awaiting_delivery(self):
        """Orders confirmed and awaiting delivery"""
        return self.filter(status='confirmed', supplier_confirmed=True)

    def ready_for_delivery_creation(self):
        """Orders that can be used for delivery creation"""
        return self.filter(
            status='confirmed',
            supplier_confirmed=True
        ).exclude(
            delivery_status='completed'
        )

    def by_supplier(self, supplier):
        """Orders for specific supplier"""
        return self.filter(supplier=supplier)

    def for_delivery_on(self, date):
        """Orders expected for delivery on specific date"""
        return self.filter(expected_delivery_date=date, status='confirmed')

    def overdue_delivery(self):
        """Orders past expected delivery date"""
        today = timezone.now().date()
        return self.filter(
            expected_delivery_date__lt=today,
            status='confirmed'
        )

    def from_requests(self):
        """Orders created from requests"""
        return self.filter(source_request__isnull=False)

    def direct_orders(self):
        """Orders created directly (not from requests)"""
        return self.filter(source_request__isnull=True)


class PurchaseOrder(BaseDocument, FinancialMixin, PaymentMixin):
    """
    Purchase Order - Поръчка към доставчици

    Логика: Използва FinancialMixin и PaymentMixin защото има финансови данни.
    НЕ използва DeliveryMixin защото има expected_delivery_date, не delivery_date.
    """



    # =====================
    # ПОРЪЧКА-СПЕЦИФИЧНИ ПОЛЕТА
    # =====================


    # DELIVERY DATE - expected, не actual!
    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        help_text=_('When we expect to receive this order')
    )

    requested_delivery_date = models.DateField(
        _('Requested Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When we requested delivery from supplier')
    )

    # ORDER SPECIFIC
    is_urgent = models.BooleanField(
        _('Urgent Order'),
        default=False,
        help_text=_('Whether this is an urgent/emergency order')
    )

    order_method = models.CharField(
        _('Order Method'),
        max_length=50,
        blank=True,
        help_text=_('How this order was placed (phone, email, system, etc.)')
    )

    # DELIVERY TERMS
    delivery_terms = models.CharField(
        _('Delivery Terms'),
        max_length=100,
        blank=True,
        help_text=_('Delivery terms (FOB, CIF, etc.)')
    )

    special_conditions = models.TextField(
        _('Special Conditions'),
        blank=True,
        help_text=_('Any special conditions or requirements')
    )

    # PAYMENT TERMS
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=100,
        blank=True,
        help_text=_('Payment terms for this order')
    )

    # SUPPLIER COMMUNICATION
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

    supplier_order_reference = models.CharField(
        _('Supplier Order Reference'),
        max_length=100,
        blank=True,
        help_text=_("Supplier's reference number for this order")
    )

    # CONTACT INFO
    supplier_contact_person = models.CharField(
        _('Supplier Contact Person'),
        max_length=100,
        blank=True,
        help_text=_('Contact person at supplier for this order')
    )

    supplier_contact_phone = models.CharField(
        _('Supplier Contact Phone'),
        max_length=20,
        blank=True,
        help_text=_('Phone number for order-related contact')
    )

    supplier_contact_email = models.EmailField(
        _('Supplier Contact Email'),
        blank=True,
        help_text=_('Email for order-related contact')
    )

    # ORDER TRACKING
    sent_to_supplier_at = models.DateTimeField(
        _('Sent to Supplier At'),
        null=True,
        blank=True,
        help_text=_('When order was sent to supplier')
    )

    sent_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sent_purchase_orders',
        verbose_name=_('Sent By'),
        help_text=_('User who sent the order to supplier')
    )

    # DELIVERY STATUS TRACKING
    DELIVERY_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('partial', _('Partially Delivered')),
        ('completed', _('Fully Delivered')),
        ('cancelled', _('Cancelled')),
    ]

    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
        help_text=_('Current delivery status of this order')
    )

    # SOURCE TRACKING
    source_request = models.ForeignKey(
        'purchases.PurchaseRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_orders',  # ФИКСИРАНО: различно име
        verbose_name=_('Source Request'),
        help_text=_('Request this order was created from (if any)')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseOrderManager()

    class Meta:
        verbose_name = _('Purchase Order')
        verbose_name_plural = _('Purchase Orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'supplier_confirmed']),
            models.Index(fields=['supplier', 'expected_delivery_date']),
            models.Index(fields=['is_urgent', 'status']),
            models.Index(fields=['delivery_status', 'expected_delivery_date']),
            models.Index(fields=['source_request']),
        ]

    def __str__(self):
        return f"ORD {self.document_number} - {self.supplier.name}"

    def get_document_prefix(self):
        """Override to return ORD prefix"""
        return "ORD"

    # =====================
    # ПОРЪЧКА-СПЕЦИФИЧНА ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Order-specific validation"""
        super().clean()

        # Expected delivery date validation - може да е в бъдещето
        if self.expected_delivery_date:
            today = timezone.now().date()
            days_in_past = (today - self.expected_delivery_date).days

            # За съществуващи поръчки позволяваме до 30 дни в миналото
            if self.pk and days_in_past > 30:
                raise ValidationError({
                    'expected_delivery_date': _(
                        'Expected delivery date cannot be more than 30 days in the past'
                    )
                })
            # За нови поръчки позволяваме до 7 дни назад
            elif not self.pk and days_in_past > 7:
                raise ValidationError({
                    'expected_delivery_date': _(
                        'Expected delivery date for new orders cannot be more than 7 days in the past'
                    )
                })

        # Supplier confirmation validation
        if self.supplier_confirmed and not self.supplier_confirmed_date:
            self.supplier_confirmed_date = timezone.now().date()

    # =====================
    # WORKFLOW METHODS
    # =====================

    def approve(self, user, notes=''):
        """
        LEGACY WRAPPER: Use ApprovalService.execute_transition() instead
        """
        warnings.warn(
            "PurchaseOrder.approve() is deprecated. "
            "Use ApprovalService.execute_transition(document, 'approved', user, notes)",
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

            return True

        except ImportError:
            # Fallback if ApprovalService not available
            if self.status != 'pending_approval':
                raise ValidationError("Can only approve orders pending approval")

            self.status = 'approved'
            self.updated_by = user
            if notes:
                self.notes = (self.notes + '\n' + notes).strip() if self.notes else notes
            self.save()

            return True

    def confirm(self, user, notes=''):
        """
        LEGACY WRAPPER: Confirm order (move to confirmed status)
        """
        warnings.warn(
            "PurchaseOrder.confirm() is deprecated. "
            "Use ApprovalService.execute_transition(document, 'confirmed', user, notes)",
            DeprecationWarning,
            stacklevel=2
        )

        try:
            from nomenclatures.services.approval_service import ApprovalService

            result = ApprovalService.execute_transition(
                document=self,
                to_status='confirmed',
                user=user,
                comments=notes or 'Confirmed via legacy method'
            )

            if not result['success']:
                raise ValidationError(result['message'])

            return True

        except ImportError:
            # Fallback
            if self.status not in ['draft', 'approved']:
                raise ValidationError(f"Cannot confirm order with status '{self.status}'")

            self.status = 'confirmed'
            self.updated_by = user
            if notes:
                self.notes = (self.notes + '\n' + notes).strip() if self.notes else notes
            self.save()

            return True

    def send_to_supplier(self, user, notes=''):
        """
        Business method: Mark order as sent to supplier
        This is NOT deprecated as it's business logic, not approval workflow
        """
        if not self.can_be_sent_to_supplier():
            raise ValidationError(f"Cannot send order with status '{self.status}' to supplier")

        from django.utils import timezone

        self.status = 'sent'
        self.sent_to_supplier_at = timezone.now()
        self.sent_by = user
        if notes:
            self.notes = (self.notes + '\n' + notes).strip() if self.notes else notes
        self.updated_by = user
        self.save()

        logger.info(f"Order {self.document_number} sent to supplier by {user}")
        return True

    def can_be_sent_to_supplier(self):
        """Check if order can be sent to supplier"""
        return self.status == 'confirmed' and not hasattr(self, 'sent_to_supplier_at')







    def update_delivery_status(self):
        """Update delivery status based on line delivery progress"""
        if not hasattr(self, 'lines'):
            return

        lines = self.lines.all()
        if not lines:
            return

        total_ordered = sum(line.ordered_quantity for line in lines)
        total_delivered = sum(getattr(line, 'delivered_quantity', 0) for line in lines)

        if total_delivered == 0:
            self.delivery_status = 'pending'
        elif total_delivered >= total_ordered:
            self.delivery_status = 'completed'
            self.status = self.RECEIVED
        else:
            self.delivery_status = 'partial'

        self.save(update_fields=['delivery_status', 'status'])

    # =====================
    # BUSINESS LOGIC CHECKS
    # =====================
    def can_be_edited(self):
        """Override with order-specific logic"""
        return self.status in [self.DRAFT]

    def can_be_sent(self):
        """Check if order can be sent to supplier"""
        return (
                self.status == self.DRAFT and
                self.lines.exists()
        )

    def can_be_confirmed(self):
        """Check if order can be confirmed"""
        return self.status in [self.SENT, self.DRAFT]

    def can_be_used_for_delivery(self):
        """Check if order can be used for delivery creation"""
        return (
                self.status == self.CONFIRMED and
                self.supplier_confirmed and
                self.delivery_status in ['pending', 'partial']
        )

    def can_be_cancelled(self):
        """Override with order-specific logic"""
        return self.status not in [self.RECEIVED, self.CANCELLED, self.CLOSED]

    def needs_approval(self, amount=None):
        """
        CRITICAL NEW METHOD: Check if order needs approval

        This respects DocumentType configuration and business rules
        """
        # Check DocumentType configuration first
        if not self.document_type or not self.document_type.requires_approval:
            return False

        # Get amount to check
        if amount is None:
            # Try multiple ways to get the total amount
            amount = (
                    getattr(self, 'grand_total', None) or
                    getattr(self, 'total_amount', None) or
                    self.get_estimated_total() or
                    Decimal('0.00')
            )

        # Use DocumentType approval limit if configured
        if self.document_type.approval_limit:
            return amount > self.document_type.approval_limit

        # BUSINESS RULE: Default approval thresholds
        # These can be overridden by DocumentType configuration
        if self.is_urgent:
            # Urgent orders have lower threshold
            default_threshold = Decimal('500.00')
        else:
            # Regular orders
            default_threshold = Decimal('1000.00')

        return amount > default_threshold

    def get_estimated_total(self):
        """
        Get total amount for approval calculations
        This method should return the best available estimate of the order total
        """
        # If we already have calculated totals, use them
        if hasattr(self, 'grand_total') and self.grand_total:
            return self.grand_total

        if hasattr(self, 'total_amount') and self.total_amount:
            return self.total_amount

        # Calculate from lines if no totals exist yet
        if self.lines.exists():
            total = Decimal('0.00')
            for line in self.lines.all():
                line_total = (line.ordered_quantity or 0) * (line.unit_price or 0)
                total += line_total
            return total

        return Decimal('0.00')

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_from_request(self):
        return self.source_request is not None

    @property
    def is_direct_order(self):
        return self.source_request is None

    @property
    def days_until_delivery(self):
        """Days until expected delivery"""
        if not self.expected_delivery_date:
            return None
        delta = self.expected_delivery_date - timezone.now().date()
        return delta.days

    @property
    def is_overdue(self):
        """Is delivery overdue?"""
        if not self.expected_delivery_date:
            return False
        return (
                self.expected_delivery_date < timezone.now().date() and
                self.status == self.CONFIRMED
        )

    @property
    def is_fully_delivered(self):
        return self.delivery_status == 'completed'

    @property
    def is_partially_delivered(self):
        return self.delivery_status == 'partial'


class PurchaseOrderLineManager(models.Manager):
    """Manager for Purchase Order Lines"""

    def for_order(self, order):
        """Lines for specific order"""
        return self.filter(document=order)

    def confirmed_not_delivered(self):
        """Lines from confirmed orders not yet delivered"""
        return self.filter(
            document__status='confirmed',
            document__delivery_status__in=['pending', 'partial']
        )

    def available_for_delivery(self, supplier=None):
        """Lines available for delivery creation"""
        queryset = self.filter(
            document__status='confirmed',
            document__supplier_confirmed=True,
            document__delivery_status__in=['pending', 'partial']
        )

        if supplier:
            queryset = queryset.filter(document__supplier=supplier)

        return queryset.select_related(
            'document__supplier',
            'product',
            'unit'
        )


class PurchaseOrderLine(BaseDocumentLine, FinancialLineMixin):
    """
    Purchase Order Line - Ред на поръчка

    Логика: Използва FinancialLineMixin защото има финансови данни.
    """

    # =====================
    # FOREIGN KEY TO PARENT
    # =====================
    document = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Order')
    )

    # =====================
    # SOURCE TRACKING
    # =====================
    source_request_line = models.ForeignKey(
        'purchases.PurchaseRequestLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_lines',
        verbose_name=_('Source Request Line'),
        help_text=_('Request line this order line was created from (if any)')
    )

    # =====================
    # ORDER-SPECIFIC FIELDS
    # =====================
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity ordered from supplier')
    )

    confirmed_quantity = models.DecimalField(
        _('Confirmed Quantity'),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Quantity confirmed by supplier (if different from ordered)')
    )

    # DELIVERY TRACKING
    delivered_quantity = models.DecimalField(
        _('Delivered Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Total quantity already delivered')
    )

    remaining_quantity = models.DecimalField(
        _('Remaining Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Quantity still to be delivered')
    )

    DELIVERY_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('partial', _('Partially Delivered')),
        ('completed', _('Fully Delivered')),
        ('cancelled', _('Cancelled')),
    ]

    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
        help_text=_('Delivery status for this line')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseOrderLineManager()

    class Meta:
        verbose_name = _('Purchase Order Line')
        verbose_name_plural = _('Purchase Order Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['source_request_line']),
            models.Index(fields=['delivery_status']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    # =====================
    # ORDER LINE ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Order line specific validation"""
        super().clean()



        # Ordered quantity must be positive
        if self.ordered_quantity <= 0:
            raise ValidationError({
                'ordered_quantity': _('Ordered quantity must be greater than zero')
            })

        # Confirmed quantity validation
        if self.confirmed_quantity is not None and self.confirmed_quantity < 0:
            raise ValidationError({
                'confirmed_quantity': _('Confirmed quantity cannot be negative')
            })

        # Delivered quantity validation
        if self.delivered_quantity < 0:
            raise ValidationError({
                'delivered_quantity': _('Delivered quantity cannot be negative')
            })

        if self.delivered_quantity > self.ordered_quantity:
            raise ValidationError({
                'delivered_quantity': _('Delivered quantity cannot exceed ordered quantity')
            })

    def save(self, *args, **kwargs):
        """Enhanced save with delivery calculations"""


        # Calculate remaining quantity
        if self.ordered_quantity and self.delivered_quantity:
            self.remaining_quantity = self.ordered_quantity - self.delivered_quantity
        else:
            self.remaining_quantity = self.ordered_quantity or Decimal('0.000')

        # Update delivery status
        self._update_delivery_status()

        super().save(*args, **kwargs)

    def _update_delivery_status(self):
        """Update delivery status based on delivered vs ordered quantities"""
        if not self.ordered_quantity:
            return

        if self.delivered_quantity >= self.ordered_quantity:
            self.delivery_status = 'completed'
        elif self.delivered_quantity > 0:
            self.delivery_status = 'partial'
        else:
            self.delivery_status = 'pending'

    # =====================
    # DELIVERY TRACKING METHODS
    # =====================
    def add_delivery(self, quantity, delivery_line=None):
        """Add delivered quantity to this line"""
        if quantity <= 0:
            raise ValidationError("Delivery quantity must be positive")

        if self.delivered_quantity + quantity > self.ordered_quantity:
            raise ValidationError("Total delivered cannot exceed ordered quantity")

        self.delivered_quantity += quantity
        self.save()

        # Update parent order delivery status
        self.document.update_delivery_status()

        return True

    def get_quantity(self):
        """Get quantity for financial calculations"""
        return self.ordered_quantity or Decimal('0')

    # =====================
    # PROPERTIES
    # =====================
    @property
    def is_from_request(self):
        return self.source_request_line is not None

    @property
    def delivery_progress_percent(self):
        """Delivery progress as percentage"""
        if not self.ordered_quantity:
            return 0
        return min(100, (self.delivered_quantity / self.ordered_quantity) * 100)

    @property
    def is_fully_delivered(self):
        return self.delivery_status == 'completed'

    @property
    def is_partially_delivered(self):
        return self.delivery_status == 'partial'

    @property
    def effective_quantity(self):
        """Use confirmed quantity if available, otherwise ordered quantity"""
        return self.confirmed_quantity or self.ordered_quantity