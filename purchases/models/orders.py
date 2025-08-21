# purchases/models/orders.py - REFACTORED WITH SERVICE DELEGATION
"""
PurchaseOrder Model - Clean Architecture Implementation

CHANGES:
❌ REMOVED: Fat business logic methods from model
✅ ADDED: Thin wrapper methods that delegate to services
✅ PRESERVED: 100% backward compatibility
✅ ENHANCED: Better error handling and logging

PRINCIPLE:
Model = Data + Simple Operations
Services = Business Logic + Complex Operations
"""


from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nomenclatures.models import BaseDocument
from nomenclatures.mixins import FinancialMixin, PaymentMixin
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PurchaseOrderManager(models.Manager):
    """Enhanced manager with service integration"""

    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type', 'location_content_type', 'document_type', 'created_by'
        )

    # =====================
    # BUSINESS QUERY METHODS - Enhanced
    # =====================

    def ready_to_send(self):
        """Orders ready to send to supplier"""
        return self.filter(
            status='draft'
        ).exclude(
            lines__isnull=True
        )

    def awaiting_confirmation(self):
        """Orders sent but not confirmed by supplier"""
        return self.filter(
            status='sent',
            supplier_confirmed=False
        )

    def ready_for_delivery(self):
        """Orders ready for delivery creation"""
        return self.filter(
            status='confirmed',
            supplier_confirmed=True,
            delivery_status__in=['pending', 'partial']
        )

    def overdue_delivery(self):
        """Orders past expected delivery date"""
        today = timezone.now().date()
        return self.filter(
            expected_delivery_date__lt=today,
            status='confirmed'
        )

    def by_partner(self, partner):
        return self.filter(partner=partner)

    def from_requests(self):
        """Orders created from requests"""
        return self.filter(source_request__isnull=False)

    def direct_orders(self):
        """Orders created directly (not from requests)"""
        return self.filter(source_request__isnull=True)

    # =====================
    # SERVICE INTEGRATION METHODS
    # =====================

    def bulk_send_to_supplier(self, user=None):
        """Bulk send draft orders - delegates to PurchaseWorkflowService"""
        try:
            from purchases.services.workflow_service import PurchaseWorkflowService

            draft_orders = self.ready_to_send()
            results = []

            for order in draft_orders:
                result = PurchaseWorkflowService.send_order_to_supplier(order, user)
                results.append((order, result))

            return results

        except ImportError:
            logger.warning("PurchaseWorkflowService not available for bulk operations")
            return []

    def workflow_analysis(self):
        """Get workflow analysis - delegates to PurchaseWorkflowService"""
        try:
            from purchases.services.workflow_service import PurchaseWorkflowService
            return PurchaseWorkflowService.get_workflow_analysis(self.all())
        except ImportError:
            logger.warning("PurchaseWorkflowService not available")
            return None


class PurchaseOrder(BaseDocument, FinancialMixin, PaymentMixin):
    """
    Purchase Order - Clean Model Implementation

    PHILOSOPHY:
    - Model handles data persistence and simple operations
    - Complex business logic delegated to services
    - Backward compatibility maintained through wrapper methods
    - Service integration through composition, not inheritance
    """

    # =====================
    # ORDER-SPECIFIC STATUS CHOICES
    # =====================
    DRAFT = 'draft'
    SENT = 'sent'
    CONFIRMED = 'confirmed'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (SENT, _('Sent to Supplier')),
        (CONFIRMED, _('Confirmed by Supplier')),
        (COMPLETED, _('Completed')),
        (CANCELLED, _('Cancelled')),
    ]

    # =====================
    # ORDER-SPECIFIC FIELDS
    # =====================

    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        help_text=_('When we expect this order to be delivered')
    )

    is_urgent = models.BooleanField(
        _('Urgent Order'),
        default=False,
        help_text=_('Mark as urgent for priority processing')
    )

    # =====================
    # SUPPLIER INTERACTION FIELDS
    # =====================

    supplier_order_reference = models.CharField(
        _('Supplier Order Reference'),
        max_length=100,
        blank=True,
        help_text=_('Reference number from supplier system')
    )

    supplier_confirmed = models.BooleanField(
        _('Supplier Confirmed'),
        default=False,
        help_text=_('Has supplier confirmed this order?')
    )

    supplier_confirmed_date = models.DateField(
        _('Supplier Confirmed Date'),
        null=True,
        blank=True,
        help_text=_('When supplier confirmed the order')
    )

    sent_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sent_purchase_orders',
        verbose_name=_('Sent By'),
        help_text=_('User who sent the order to supplier')
    )

    sent_to_supplier_at = models.DateTimeField(
        _('Sent to Supplier At'),
        null=True,
        blank=True,
        help_text=_('When order was sent to supplier')
    )

    # =====================
    # DELIVERY TRACKING FIELDS
    # =====================

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

    # =====================
    # SOURCE TRACKING
    # =====================

    source_request = models.ForeignKey(
        'purchases.PurchaseRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sourced_orders',  # ✅ ДОБАВИ ТОВА
        verbose_name=_('Source Request'),
        help_text=_('Request this order was created from (if any)'))

    # =====================
    # MANAGER AND META
    # =====================

    objects = PurchaseOrderManager()

    class Meta:
        verbose_name = _('Purchase Order')
        verbose_name_plural = _('Purchase Orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['supplier_confirmed', 'supplier_confirmed_date']),
            models.Index(fields=['expected_delivery_date']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['source_request']),
        ]

        permissions = [
            ('can_send_to_supplier', 'Can send orders to supplier'),
            ('can_confirm_from_supplier', 'Can confirm orders from supplier'),
            ('can_create_delivery', 'Can create deliveries from orders'),
            ('can_view_supplier_details', 'Can view supplier details'),
        ]

    def __str__(self):
        if self.partner:
            return f"Order {self.document_number} - {self.partner.name}"
        else:
            return f"Order {self.document_number}"

    # =====================
    # MODEL VALIDATION - Keep in Model
    # =====================

    def clean(self):
        """Model-level validation"""
        super().clean()

        # Status-specific validation
        if self.status == self.CONFIRMED:
            if not self.supplier_confirmed:
                raise ValidationError({
                    'supplier_confirmed': _('Supplier confirmation required when status is confirmed')
                })

        # Business validation
        if self.expected_delivery_date and self.expected_delivery_date < timezone.now().date():
            raise ValidationError({
                'expected_delivery_date': _('Expected delivery date cannot be in the past')
            })

        # Source request validation
        if self.source_request:
            if self.source_request.status != 'approved':
                raise ValidationError({
                    'source_request': _('Source request must be approved')
                })

            if self.partner != self.source_request.partner:
                raise ValidationError({
                    'partner': _('Partner must match source request partner')
                })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-timestamps"""
        # Auto-set supplier confirmation timestamp
        if self.status == self.CONFIRMED and not self.supplier_confirmed_date:
            self.supplier_confirmed_date = timezone.now().date()

        super().save(*args, **kwargs)

    # =====================
    # SIMPLE MODEL PROPERTIES - Keep in Model
    # =====================

    @property
    def is_draft(self):
        """Simple status check - stays in model"""
        return self.status == self.DRAFT

    @property
    def is_sent(self):
        """Simple status check - stays in model"""
        return self.status == self.SENT

    @property
    def is_confirmed(self):
        """Simple status check - stays in model"""
        return self.status == self.CONFIRMED

    @property
    def can_be_sent(self):
        """Simple business rule - stays in model"""
        return self.status == self.DRAFT and self.lines.exists()

    @property
    def can_be_confirmed(self):
        """Simple business rule - stays in model"""
        return self.status == self.SENT

    @property
    def is_overdue(self):
        """Simple calculation - stays in model"""
        if not self.expected_delivery_date:
            return False
        return self.expected_delivery_date < timezone.now().date() and self.status == self.CONFIRMED

    @property
    def days_until_delivery(self):
        """Simple calculation - stays in model"""
        if not self.expected_delivery_date:
            return None
        delta = self.expected_delivery_date - timezone.now().date()
        return delta.days



    # =====================
    # ENHANCED ANALYSIS METHODS - Delegate to Services
    # =====================

    def get_financial_analysis(self):
        """
        Get detailed financial analysis - delegates to DocumentService

        Returns:
            Result object with financial breakdown
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.analyze_document_financial_impact(
                self, compare_to_budget=True
            )
        except ImportError:
            from core.utils.result import Result
            return Result.error(
                'SERVICE_NOT_AVAILABLE',
                'DocumentService not available for financial analysis'
            )

    def validate_integrity(self, deep_validation=True):
        """
        Validate document integrity - delegates to DocumentService

        Returns:
            Result object with validation details
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.validate_document_integrity(
                self, deep_validation=deep_validation
            )
        except ImportError:
            from core.utils.result import Result
            return Result.error(
                'SERVICE_NOT_AVAILABLE',
                'DocumentService not available for validation'
            )

    def recalculate_lines(self, user=None, update_pricing=True):
        """
        Recalculate all lines - delegates to DocumentService

        Returns:
            Result object with recalculation details
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.recalculate_document_lines(
                self, user=user,
                recalc_vat=True,
                update_pricing=update_pricing
            )
        except ImportError:
            from core.utils.result import Result
            return Result.error(
                'SERVICE_NOT_AVAILABLE',
                'DocumentService not available for recalculation'
            )

    def synchronize_delivery_status(self):
        """
        Synchronize delivery status - delegates to PurchaseWorkflowService

        Returns:
            Result object with synchronization details
        """
        try:
            from purchases.services.workflow_service import PurchaseWorkflowService
            return PurchaseWorkflowService.synchronize_order_delivery_status(self)
        except ImportError:
            from core.utils.result import Result
            return Result.error(
                'SERVICE_NOT_AVAILABLE',
                'PurchaseWorkflowService not available for synchronization'
            )

    # =====================
    # DELIVERY STATUS MANAGEMENT - Keep Simple Aggregation in Model
    # =====================

    def update_delivery_status(self):
        """
        Update delivery status based on lines - SIMPLE AGGREGATION (Keep in Model)

        This is simple aggregation logic that can stay in the model.
        For complex synchronization with actual deliveries, use synchronize_delivery_status()
        """
        total_ordered = self.lines.aggregate(
            total=models.Sum('ordered_quantity')
        )['total'] or Decimal('0')

        total_delivered = self.lines.aggregate(
            total=models.Sum('delivered_quantity')
        )['total'] or Decimal('0')

        if total_delivered == 0:
            self.delivery_status = 'pending'
        elif total_delivered >= total_ordered:
            self.delivery_status = 'completed'
        else:
            self.delivery_status = 'partial'

        self.save(update_fields=['delivery_status'])
        return self.delivery_status

    # =====================
    # WORKFLOW INTEGRATION METHODS
    # =====================

    def get_workflow_status(self):
        """
        Get current workflow status and available actions

        Returns:
            Dict with workflow information
        """
        try:
            from nomenclatures.services import ApprovalService

            if hasattr(ApprovalService, 'get_workflow_information'):
                result = ApprovalService.get_workflow_information(self)

                if result.ok:
                    return result.data
                else:
                    return {
                        'current_status': self.status,
                        'available_transitions': self._get_simple_transitions(),
                        'error': result.msg
                    }
            else:
                return {
                    'current_status': self.status,
                    'available_transitions': self._get_simple_transitions(),
                    'service_available': True,
                    'method_available': False
                }

        except (ImportError, AttributeError):
            return {
                'current_status': self.status,
                'available_transitions': self._get_simple_transitions(),
                'service_available': False
            }

    def _get_simple_transitions(self):
        """Simple fallback for available transitions"""
        if self.status == self.DRAFT:
            return ['sent'] if self.lines.exists() else []
        elif self.status == self.SENT:
            return ['confirmed', 'cancelled']
        elif self.status == self.CONFIRMED:
            return ['completed', 'cancelled']
        else:
            return []


# =====================
# RELATED MODELS - Order Lines
# =====================

class PurchaseOrderLineManager(models.Manager):
    """Manager for purchase order lines"""

    def get_queryset(self):
        return super().get_queryset().select_related('document', 'product')

    def pending_delivery(self):
        """Lines with pending deliveries"""
        return self.filter(delivery_status='pending')

    def partially_delivered(self):
        """Lines with partial deliveries"""
        return self.filter(delivery_status='partial')

    def fully_delivered(self):
        """Lines fully delivered"""
        return self.filter(delivery_status='completed')


class PurchaseOrderLine(FinancialMixin):
    """
    Purchase Order Line - Simple data model

    PRINCIPLE: Keep line models simple - they're primarily data containers
    Complex calculations and business logic belong in services
    """

    document = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Order')
    )

    line_number = models.PositiveIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )

    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Quantity in specified unit')
    )

    unit = models.CharField(
        _('Unit'),
        max_length=20,
        help_text=_('Unit of measure for this line')
    )

    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Final ordered quantity')
    )

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=15,
        decimal_places=4,
        help_text=_('Price per unit')
    )

    # =====================
    # DELIVERY TRACKING - Consider for removal/property conversion
    # =====================

    delivered_quantity = models.DecimalField(
        _('Delivered Quantity'),
        max_digits=15,
        decimal_places=3,
        default=Decimal('0'),
        help_text=_('Total quantity delivered (aggregated from delivery lines)')
    )

    DELIVERY_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('partial', _('Partially Delivered')),
        ('completed', _('Fully Delivered')),
    ]

    delivery_status = models.CharField(
        _('Delivery Status'),
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
        help_text=_('Delivery status of this line')
    )

    # =====================
    # SOURCE TRACKING
    # =====================

    source_request_line = models.ForeignKey(
        'purchases.PurchaseRequestLine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='converted_to_order_line',
        verbose_name=_('Source Request Line')
    )

    notes = models.TextField(
        _('Line Notes'),
        blank=True,
        help_text=_('Additional notes for this line')
    )

    # =====================
    # TRACKING FIELDS
    # =====================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PurchaseOrderLineManager()

    class Meta:
        verbose_name = _('Purchase Order Line')
        verbose_name_plural = _('Purchase Order Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['source_request_line']),
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.ordered_quantity}"

    # =====================
    # SIMPLE CALCULATIONS - Keep in Model
    # =====================

    @property
    def line_total(self):
        """Simple calculation - stays in model - NULL-SAFE"""
        ordered = self.ordered_quantity or Decimal('0')
        price = self.unit_price or Decimal('0')
        return ordered * price

    @property
    def delivery_progress(self):
        """Simple calculation - stays in model - NULL-SAFE"""
        ordered = self.ordered_quantity or Decimal('0')
        delivered = self.delivered_quantity or Decimal('0')

        if ordered > 0:
            return float(delivered / ordered * 100)
        return 0.0

    @property
    def remaining_quantity(self):
        """Simple calculation - stays in model - NULL-SAFE"""
        ordered = self.ordered_quantity or Decimal('0')
        delivered = self.delivered_quantity or Decimal('0')
        return max(Decimal('0'), ordered - delivered)

    def clean(self):
        """Model-level validation"""
        super().clean()

        if self.ordered_quantity <= 0:
            raise ValidationError({
                'ordered_quantity': _('Ordered quantity must be positive')
            })

        if self.unit_price < 0:
            raise ValidationError({
                'unit_price': _('Unit price cannot be negative')
            })

        # Delivered quantity validation
        if self.delivered_quantity > self.ordered_quantity:
            raise ValidationError({
                'delivered_quantity': _('Delivered quantity cannot exceed ordered quantity')
            })

    # =====================
    # SERVICE INTEGRATION - When Needed
    # =====================

    def get_current_market_price(self):
        """Get current market price - delegates to PricingService"""
        try:
            from pricing.services import PricingService

            result = PricingService.get_product_pricing(
                self.document.location,
                self.product,
                quantity=self.ordered_quantity
            )

            if result.ok:
                return result.data.get('final_price')
            else:
                return None

        except ImportError:
            return None

    def validate_product_availability(self):
        """Validate product can be purchased - delegates to ProductValidationService"""
        try:
            from products.services import ProductValidationService

            return ProductValidationService.validate_purchase(
                self.product,
                self.ordered_quantity,
                self.document.partner
            )

        except ImportError:
            from core.utils.result import Result
            return Result.success({}, 'ProductValidationService not available')


