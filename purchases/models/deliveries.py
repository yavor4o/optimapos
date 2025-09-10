# purchases/models/delivery.py - REFACTORED WITH SERVICE DELEGATION
import datetime
from datetime import date
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nomenclatures.models import BaseDocument, BaseDocumentLine
from nomenclatures.mixins import FinancialMixin, PaymentMixin, FinancialLineMixin
from core.interfaces import ServiceResolverMixin
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class DeliveryReceiptManager(models.Manager):
    """Enhanced manager with service integration"""

    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type', 'location_content_type', 'source_order', 'received_by'
        )

    # =====================
    # BUSINESS QUERY METHODS - Enhanced
    # =====================

    def pending_quality_control(self):
        """Deliveries pending quality control - FIXED: Dynamic quality resolution"""
        # Note: quality_status is separate from document status
        # This is business-specific logic that's acceptable to keep hardcoded
        # since it's not part of the configurable status system
        return self.filter(quality_status='pending')

    def quality_approved(self):
        """Deliveries with approved quality - Business rule, not configurable status"""
        return self.filter(quality_status='approved')

    def quality_rejected(self):
        """Deliveries with quality issues - Business rule, not configurable status"""
        return self.filter(quality_status='rejected')

    def partial_quality(self):
        """Deliveries with partial quality approval - Business rule, not configurable status"""
        return self.filter(quality_status='partial')

    def ready_for_inventory(self):
        """Deliveries ready for inventory processing"""
        return self.quality_approved()

    def by_partner(self, partner):
        return self.filter(partner=partner)

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






class DeliveryReceipt(BaseDocument, FinancialMixin,PaymentMixin):


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

        # Ensure we're working with date objects
        if self.delivery_date:
            # Force conversion to date
            if isinstance(self.delivery_date, datetime.datetime):
                self.delivery_date = self.delivery_date.date()

            if self.delivery_date > date.today():
                raise ValidationError({
                    'delivery_date': _('Delivery date cannot be in the future')
                })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-timestamps"""
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
    def total_approved_quantity(self):
        return self.lines.filter(quality_approved=True).aggregate(
            total=models.Sum('received_quantity')
        )['total'] or Decimal('0')

    @property
    def total_rejected_quantity(self):
        """Simple aggregation - stays in model"""
        return self.lines.filter(quality_approved=False).aggregate(
            total=models.Sum('received_quantity')
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
            from nomenclatures.services import recalculate_document_lines
            return recalculate_document_lines(
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
            'total_quantity': self.lines.aggregate(models.Sum('received_quantity'))['received_quantity__sum'] or Decimal('0'),
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
            quality_issues[issue_type]['quantity'] += line.received_quantity

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

    def with_variances(self):
        """Lines with delivery variances - MOVED FROM LineManager!"""
        from django.db.models import F
        return self.exclude(
            received_quantity=F('source_order_line__ordered_quantity')
        ).filter(source_order_line__isnull=False)

    def over_delivered(self):
        """Lines with more received than ordered"""
        from django.db.models import F
        return self.filter(
            received_quantity__gt=F('source_order_line__ordered_quantity'),
            source_order_line__isnull=False
        )

    def under_delivered(self):
        """Lines with less received than ordered"""
        from django.db.models import F
        return self.filter(
            received_quantity__lt=F('source_order_line__ordered_quantity'),
            source_order_line__isnull=False
        )

    def expiring_soon(self, days=30):
        """Lines expiring within specified days"""
        from datetime import timedelta
        cutoff = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__isnull=False,
            expiry_date__lte=cutoff
        )

    def with_batch_numbers(self):
        """Lines with batch tracking"""
        return self.exclude(batch_number='')


class DeliveryLine(BaseDocumentLine, FinancialLineMixin, ServiceResolverMixin):

    # =====================
    # PARENT DOCUMENT
    # =====================
    document = models.ForeignKey(
        'DeliveryReceipt',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Delivery Receipt')
    )


    # =====================
    # FIXED: Standardized to QuantityField for consistency
    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=12,  # FIXED: Reduced from 15 to 12 for consistency
        decimal_places=3,  # Keep 3 for quantity precision
        help_text=_('Actual quantity received from supplier (quantity precision)')
    )

    # =====================
    # QUALITY CONTROL FIELDS
    # =====================
    quality_approved = models.BooleanField(
        _('Quality Approved'),
        null=True,  # Allows for pending state
        help_text=_('True=approved, False=rejected, None=pending quality check')
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
        help_text=_('Detailed notes about quality control')
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
        verbose_name=_('Source Order Line'),
        help_text=_('Order line this delivery fulfills')
    )

    # =====================
    # MANAGER
    # =====================
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
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.received_quantity}"

    # =====================
    # ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Model-level validation - ONLY simple field validations"""
        super().clean()

        # DeliveryLine има received_quantity
        if self.received_quantity and self.received_quantity <= 0:
            raise ValidationError({
                'received_quantity': _('Received quantity must be greater than zero')
            })

        # NOTE: Quality business rules (quality_approved + quality_issue_type relationship)
        # are handled in DocumentValidator._validate_deliveryreceipt_rules()

        # Expiry validation
        if self.expiry_date and self.expiry_date < timezone.now().date():
            raise ValidationError({
                'expiry_date': _('Product is already expired')
            })

    # =====================
    # QUANTITY PROPERTIES (с достъп до поръчаното количество)
    # =====================
    @property
    def ordered_quantity(self):
        """Shortcut за поръчаното количество"""
        return self.source_order_line.ordered_quantity if self.source_order_line else Decimal('0')

    @property
    def quantity_variance(self):
        """Отклонение в количеството (received - ordered)"""
        return self.received_quantity - self.ordered_quantity

    @property
    def quantity_variance_percent(self):
        """Отклонение в количеството като процент"""
        if self.ordered_quantity > 0:
            return float(self.quantity_variance / self.ordered_quantity * 100)
        return 0.0

    @property
    def has_variance(self):
        """Има ли отклонение в количеството?"""
        return self.quantity_variance != 0

    @property
    def is_over_delivered(self):
        """Получено ли е повече от поръчаното?"""
        return self.quantity_variance > 0

    @property
    def is_under_delivered(self):
        """Получено ли е по-малко от поръчаното?"""
        return self.quantity_variance < 0

    # =====================
    # QUALITY PROPERTIES
    # =====================
    @property
    def is_quality_pending(self):
        """Чака ли качествен контрол?"""
        return self.quality_approved is None

    @property
    def is_quality_approved(self):
        """Одобрено ли е качеството?"""
        return self.quality_approved is True

    @property
    def is_quality_rejected(self):
        """Отхвърлено ли е качеството?"""
        return self.quality_approved is False

    # =====================
    # EXPIRY PROPERTIES
    # =====================
    @property
    def is_near_expiry(self, days=30):
        """Близо ли е до изтичане (по подразбиране 30 дни)?"""
        if not self.expiry_date:
            return False
        return (self.expiry_date - timezone.now().date()).days <= days

    @property
    def is_expired(self):
        """Изтекъл ли е?"""
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.now().date()

    @property
    def days_to_expiry(self):
        """Дни до изтичане"""
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days

    # =====================
    # OVERRIDE FinancialLineMixin methods for custom quantity
    # =====================
    def get_quantity_for_calculation(self):
        """Override FinancialLineMixin method to use received_quantity"""
        return self.received_quantity or Decimal('1')
    
    @property
    def base_quantity_for_inventory(self):
        """Convert received quantity to base units using ProductService"""
        from decimal import Decimal
        
        try:
            # Use ServiceResolverMixin to get ProductService
            product_service = self.get_product_service()
            converted_qty = product_service.convert_quantity(
                product=self.product,
                quantity=self.received_quantity,
                from_unit=self.unit,
                to_unit=self.product.base_unit
            )
            return converted_qty if converted_qty is not None else self.received_quantity
        except Exception:
            # Fallback: assume unit is already base unit
            return self.received_quantity or Decimal('0')
    
    @property
    def unit_cost_per_base_unit(self):
        """Calculate cost per base unit for inventory valuation"""
        from decimal import Decimal
        
        base_qty = self.base_quantity_for_inventory
        if base_qty > 0:
            total_cost = self.received_quantity * self.unit_price
            return total_cost / base_qty
        return self.unit_price or Decimal('0')



    # =====================
    # SERVICE INTEGRATION
    # =====================
    def get_current_market_price(self):
        """Get current market price - delegates to PricingService"""
        try:
            # Use ServiceResolverMixin to get PricingService
            pricing_service = self.get_pricing_service()
            result = pricing_service.get_product_pricing(
                self.document.location,
                self.product,
                quantity=self.received_quantity
            )

            if result.ok:
                return result.data.get('final_price')
            else:
                return None

        except Exception:
            return None



