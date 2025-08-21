# purchases/models/delivery.py - REFACTORED WITH SERVICE DELEGATION

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


class DeliveryReceiptManager(models.Manager):
    """Enhanced manager with service integration"""

    def get_queryset(self):
        return super().get_queryset().select_related(
            'supplier', 'location', 'source_order', 'received_by'
        )

    # =====================
    # BUSINESS QUERY METHODS - Enhanced
    # =====================

    def pending_quality_control(self):
        """Deliveries pending quality control"""
        return self.filter(quality_status='pending')

    def quality_approved(self):
        """Deliveries with approved quality"""
        return self.filter(quality_status='approved')

    def quality_rejected(self):
        """Deliveries with quality issues"""
        return self.filter(quality_status='rejected')

    def partial_quality(self):
        """Deliveries with partial quality approval"""
        return self.filter(quality_status='partial')

    def ready_for_inventory(self):
        """Deliveries ready for inventory processing"""
        return self.quality_approved()

    def by_supplier(self, supplier):
        """Deliveries from specific supplier"""
        return self.filter(supplier=supplier)

    def from_orders(self):
        """Deliveries created from orders"""
        return self.filter(source_order__isnull=False)

    def direct_deliveries(self):
        """Direct deliveries (not from orders)"""
        return self.filter(source_order__isnull=True)

    def today(self):
        """Deliveries received today"""
        today = timezone.now().date()
        return self.filter(delivery_date=today)

    # =====================
    # SERVICE INTEGRATION METHODS
    # =====================

    def bulk_quality_approve(self, user=None):
        """Bulk approve quality for pending deliveries"""
        try:
            from purchases.services.workflow_service import PurchaseWorkflowService

            pending_deliveries = self.pending_quality_control()
            results = []

            for delivery in pending_deliveries:
                # Auto-approve all lines
                quality_decisions = {}
                for line in delivery.lines.all():
                    quality_decisions[str(line.id)] = {'approved': True}

                result = PurchaseWorkflowService.process_quality_control(
                    delivery, quality_decisions, user
                )
                results.append((delivery, result))

            return results

        except ImportError:
            logger.warning("PurchaseWorkflowService not available for bulk operations")
            return []


class DeliveryReceipt(BaseDocument, FinancialMixin,PaymentMixin):
    """
    Delivery Receipt - Clean Model Implementation

    PHILOSOPHY:
    - Model handles data persistence and simple operations
    - Complex quality control delegated to services
    - Backward compatibility maintained through wrapper methods
    - Focus on quality control and inventory integration
    """

    # =====================
    # DELIVERY-SPECIFIC STATUS CHOICES
    # =====================
    DRAFT = 'draft'
    RECEIVED = 'received'
    QUALITY_CHECKED = 'quality_checked'
    PROCESSED = 'processed'
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (RECEIVED, _('Received')),
        (QUALITY_CHECKED, _('Quality Checked')),
        (PROCESSED, _('Processed to Inventory')),
        (CANCELLED, _('Cancelled')),
    ]

    # =====================
    # DELIVERY-SPECIFIC FIELDS
    # =====================

    delivery_date = models.DateField(
        _('Delivery Date'),
        default=timezone.now,
        help_text=_('Date when goods were delivered')
    )

    received_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='received_deliveries',
        verbose_name=_('Received By'),
        help_text=_('User who received the delivery')
    )

    received_at = models.DateTimeField(
        _('Received At'),
        auto_now_add=True,
        help_text=_('Timestamp when delivery was recorded')
    )

    # =====================
    # QUALITY CONTROL FIELDS
    # =====================

    QUALITY_STATUS_CHOICES = [
        ('pending', _('Pending Quality Control')),
        ('approved', _('Quality Approved')),
        ('rejected', _('Quality Rejected')),
        ('partial', _('Partially Approved')),
    ]

    quality_status = models.CharField(
        _('Quality Status'),
        max_length=20,
        choices=QUALITY_STATUS_CHOICES,
        default='pending',
        help_text=_('Overall quality control status')
    )

    quality_checked_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quality_checked_deliveries',
        verbose_name=_('Quality Checked By')
    )

    quality_checked_at = models.DateTimeField(
        _('Quality Checked At'),
        null=True,
        blank=True
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Notes about quality control process')
    )

    # =====================
    # SOURCE TRACKING
    # =====================

    source_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deliveries',
        verbose_name=_('Source Order')
    )

    # =====================
    # SUPPLIER DELIVERY INFO
    # =====================

    supplier_delivery_reference = models.CharField(
        _('Supplier Delivery Reference'),
        max_length=100,
        blank=True,
        help_text=_('Supplier reference for this delivery')
    )

    delivery_driver_name = models.CharField(
        _('Delivery Driver Name'),
        max_length=100,
        blank=True
    )

    delivery_vehicle_number = models.CharField(
        _('Vehicle Number'),
        max_length=50,
        blank=True
    )

    # =====================
    # MANAGER AND META
    # =====================

    objects = DeliveryReceiptManager()

    class Meta:
        verbose_name = _('Delivery Receipt')
        verbose_name_plural = _('Delivery Receipts')
        ordering = ['-delivery_date', '-received_at']
        indexes = [
            models.Index(fields=['quality_status', 'quality_checked_at']),
            models.Index(fields=['source_order']),
            models.Index(fields=['received_by', 'received_at']),
            models.Index(fields=['status', 'delivery_date']),
        ]

        permissions = [
            ('can_receive_delivery', 'Can receive deliveries'),
            ('can_perform_quality_control', 'Can perform quality control'),
            ('can_process_to_inventory', 'Can process deliveries to inventory'),
            ('can_view_quality_details', 'Can view quality control details'),
        ]

    def __str__(self):
        if self.partner:
            return f"Delivery {self.document_number} - {self.partner.name} ({self.delivery_date})"
        else:
            return f"Delivery {self.document_number} ({self.delivery_date})"

    # =====================
    # MODEL VALIDATION - Keep in Model
    # =====================

    def clean(self):
        """Model-level validation"""
        super().clean()

        # Quality control validation
        if self.quality_status != 'pending':
            if not self.quality_checked_by:
                raise ValidationError({
                    'quality_checked_by': _('Quality checked by is required when quality status is not pending')
                })

        # Source order validation
        if self.source_order:
            if self.partner != self.source_order.partner:
                raise ValidationError({
                    'partner': _('Partner must match source order partner')
                })

            if self.source_order.status != 'confirmed':
                raise ValidationError({
                    'source_order': _('Source order must be confirmed')
                })

        # Business validation
        if self.delivery_date > timezone.now().date():
            raise ValidationError({
                'delivery_date': _('Delivery date cannot be in the future')
            })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-timestamps"""
        # Auto-set quality check timestamp
        if self.quality_status != 'pending' and not self.quality_checked_at:
            self.quality_checked_at = timezone.now()

        super().save(*args, **kwargs)

    # =====================
    # SIMPLE MODEL PROPERTIES - Keep in Model
    # =====================

    @property
    def is_quality_pending(self):
        """Simple status check - stays in model"""
        return self.quality_status == 'pending'

    @property
    def is_quality_approved(self):
        """Simple status check - stays in model"""
        return self.quality_status == 'approved'

    @property
    def has_quality_issues(self):
        """Simple status check - stays in model"""
        return self.quality_status in ['rejected', 'partial']

    @property
    def can_be_processed_to_inventory(self):
        """Simple business rule - stays in model"""
        return self.quality_status in ['approved', 'partial'] and self.status != 'processed'

    @property
    def total_approved_quantity(self):
        """Simple aggregation - stays in model"""
        return self.lines.filter(quality_approved=True).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

    @property
    def total_rejected_quantity(self):
        """Simple aggregation - stays in model"""
        return self.lines.filter(quality_approved=False).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

    @property
    def quality_approval_rate(self):
        """Simple calculation - stays in model"""
        total = self.total_approved_quantity + self.total_rejected_quantity
        if total > 0:
            return float(self.total_approved_quantity / total * 100)
        return 0.0

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

    def update_source_order_status(self):
        """
        Update source order delivery status - delegates to PurchaseWorkflowService

        Returns:
            Result object with synchronization details
        """
        if not self.source_order:
            from core.utils.result import Result
            return Result.success(
                {'no_source_order': True},
                'No source order to update'
            )

        try:
            from purchases.services.workflow_service import PurchaseWorkflowService
            return PurchaseWorkflowService.synchronize_order_delivery_status(self.source_order)
        except ImportError:
            from core.utils.result import Result
            return Result.error(
                'SERVICE_NOT_AVAILABLE',
                'PurchaseWorkflowService not available for synchronization'
            )

    # =====================
    # QUALITY CONTROL WORKFLOW METHODS
    # =====================

    def get_quality_summary(self):
        """
        Get quality control summary

        Returns:
            Dict with quality statistics
        """
        summary = {
            'total_lines': self.lines.count(),
            'approved_lines': self.lines.filter(quality_approved=True).count(),
            'rejected_lines': self.lines.filter(quality_approved=False).count(),
            'pending_lines': self.lines.filter(quality_approved__isnull=True).count(),
            'total_quantity': self.lines.aggregate(models.Sum('quantity'))['quantity__sum'] or Decimal('0'),
            'approved_quantity': self.total_approved_quantity,
            'rejected_quantity': self.total_rejected_quantity,
            'approval_rate': self.quality_approval_rate
        }

        # Add quality issues breakdown
        quality_issues = {}
        for line in self.lines.filter(quality_approved=False).exclude(quality_issue_type=''):
            issue_type = line.quality_issue_type
            if issue_type not in quality_issues:
                quality_issues[issue_type] = {'count': 0, 'quantity': Decimal('0')}
            quality_issues[issue_type]['count'] += 1
            quality_issues[issue_type]['quantity'] += line.quantity

        summary['quality_issues'] = quality_issues

        return summary


# =====================
# RELATED MODELS - Delivery Lines
# =====================

class DeliveryLineManager(models.Manager):
    """Manager for delivery lines"""

    def get_queryset(self):
        return super().get_queryset().select_related('document', 'product', 'source_order_line')

    def quality_approved(self):
        """Lines with approved quality"""
        return self.filter(quality_approved=True)

    def quality_rejected(self):
        """Lines with quality issues"""
        return self.filter(quality_approved=False)

    def quality_pending(self):
        """Lines pending quality control"""
        return self.filter(quality_approved__isnull=True)


class DeliveryLine(FinancialMixin):
    """
    Delivery Line - Simple data model with quality control

    PRINCIPLE: Keep line models simple - they're primarily data containers
    Quality control logic belongs in services
    """

    document = models.ForeignKey(
        DeliveryReceipt,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Delivery')
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
        _('Delivered Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Actual delivered quantity')
    )

    unit = models.CharField(
        _('Unit'),
        max_length=20,
        help_text=_('Unit of measure for this line')
    )

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=15,
        decimal_places=4,
        help_text=_('Price per unit from order')
    )

    # =====================
    # QUALITY CONTROL FIELDS
    # =====================

    quality_approved = models.BooleanField(
        _('Quality Approved'),
        null=True,  # Allows for pending state
        help_text=_('True=approved, False=rejected, None=pending')
    )

    QUALITY_ISSUE_CHOICES = [
        ('', _('No Issues')),
        ('damaged', _('Damaged')),
        ('expired', _('Expired')),
        ('wrong_product', _('Wrong Product')),
        ('wrong_quantity', _('Wrong Quantity')),
        ('poor_quality', _('Poor Quality')),
        ('packaging_issues', _('Packaging Issues')),
        ('other', _('Other Issues')),
    ]

    quality_issue_type = models.CharField(
        _('Quality Issue Type'),
        max_length=20,
        choices=QUALITY_ISSUE_CHOICES,
        blank=True,
        help_text=_('Type of quality issue if rejected')
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Detailed notes about quality issues')
    )

    quality_checked_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quality_checked_delivery_lines',
        verbose_name=_('Quality Checked By')
    )

    quality_checked_at = models.DateTimeField(
        _('Quality Checked At'),
        null=True,
        blank=True
    )

    # =====================
    # BATCH AND EXPIRY TRACKING
    # =====================

    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        blank=True,
        help_text=_('Batch/lot number for traceability')
    )

    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Product expiry date for this batch')
    )

    # =====================
    # SOURCE TRACKING
    # =====================

    source_order_line = models.ForeignKey(
        'purchases.PurchaseOrderLine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='delivery_lines',
        verbose_name=_('Source Order Line')
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

    objects = DeliveryLineManager()

    class Meta:
        verbose_name = _('Delivery Line')
        verbose_name_plural = _('Delivery Lines')
        unique_together = [['document', 'line_number']]
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product']),
            models.Index(fields=['quality_approved', 'quality_checked_at']),
            models.Index(fields=['source_order_line']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['expiry_date']),
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.quantity}"

    # =====================
    # SIMPLE CALCULATIONS - Keep in Model
    # =====================

    @property
    def line_total(self):
        """Simple calculation - stays in model"""
        if self.quantity and self.unit_price:
            return self.quantity * self.unit_price
        return Decimal('0')

    @property
    def is_quality_pending(self):
        """Simple status check - stays in model"""
        return self.quality_approved is None

    @property
    def is_quality_approved(self):
        """Simple status check - stays in model"""
        return self.quality_approved is True

    @property
    def is_quality_rejected(self):
        """Simple status check - stays in model"""
        return self.quality_approved is False

    @property
    def is_near_expiry(self, days=30):
        """Simple calculation - stays in model"""
        if not self.expiry_date:
            return False
        return (self.expiry_date - timezone.now().date()).days <= days

    @property
    def is_expired(self):
        """Simple calculation - stays in model"""
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.now().date()

    def clean(self):
        """Model-level validation"""
        super().clean()

        if self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be positive')
            })

        if self.unit_price < 0:
            raise ValidationError({
                'unit_price': _('Unit price cannot be negative')
            })

        # Quality validation
        if self.quality_approved is False and not self.quality_issue_type:
            raise ValidationError({
                'quality_issue_type': _('Quality issue type is required when quality is rejected')
            })

        # Expiry validation
        if self.expiry_date and self.expiry_date < self.document.delivery_date:
            raise ValidationError({
                'expiry_date': _('Expiry date cannot be before delivery date')
            })

        # Source order line validation
        if self.source_order_line:
            if self.source_order_line.product != self.product:
                raise ValidationError({
                    'product': _('Product must match source order line product')
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
                quantity=self.quantity
            )

            if result.ok:
                return result.data.get('final_price')
            else:
                return None

        except ImportError:
            return None

    def validate_expiry_compliance(self):
        """Validate expiry compliance - delegates to ProductValidationService"""
        try:
            from products.services import ProductValidationService

            # Check if product requires expiry tracking
            validation_result = ProductValidationService.validate_sale(
                self.product, self.quantity
            )

            if validation_result.ok:
                # Additional expiry validation could go here
                return validation_result
            else:
                return validation_result

        except ImportError:
            from core.utils.result import Result
            return Result.success({}, 'ProductValidationService not available')


