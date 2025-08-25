# purchases/models/requests.py - REFACTORED

from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from nomenclatures.models import BaseDocument, BaseDocumentLine
from nomenclatures.mixins import FinancialMixin
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PurchaseRequestManager(models.Manager):
    """Enhanced manager with service integration"""

    def get_queryset(self):
        return super().get_queryset().select_related(
            'partner_content_type', 'location_content_type', 'document_type', 'created_by'
        )

    # =====================
    # BUSINESS QUERY METHODS - Enhanced
    # =====================

    def pending_approval(self):
        """Requests waiting for approval"""
        return self.filter(status='submitted')

    def approved_unconverted(self):
        """Approved requests not yet converted to orders"""
        return self.filter(
            status='approved',
            converted_to_order__isnull=True
        )

    def ready_for_conversion(self):
        """Requests that can be converted to orders (with validation)"""
        return self.approved_unconverted().exclude(
            lines__isnull=True
        ).distinct()

    def by_partner(self, partner):
        return self.filter(partner=partner)

    def this_month(self):
        """Requests created this month"""
        today = timezone.now().date()
        return self.filter(
            created_at__month=today.month,
            created_at__year=today.year
        )

    # =====================
    # SERVICE INTEGRATION METHODS
    # =====================

    def bulk_submit_for_approval(self, user=None):
        """Bulk submit draft requests - delegates to DocumentService"""
        try:
            from nomenclatures.services import DocumentService

            draft_requests = self.filter(status='draft').exclude(lines__isnull=True)
            results = []

            for request in draft_requests:
                result = DocumentService.transition_document(
                    request, 'submitted', user, 'Bulk submission'
                )
                results.append((request, result))

            return results

        except ImportError:
            logger.warning("DocumentService not available for bulk operations")
            return []

    def workflow_analysis(self):
        """Get workflow analysis - delegates to PurchaseWorkflowService"""
        try:
            from purchases.services.workflow_service import PurchaseWorkflowService
            return PurchaseWorkflowService.get_workflow_analysis(self.all())
        except ImportError:
            logger.warning("PurchaseWorkflowService not available")
            return None


class PurchaseRequest(BaseDocument, FinancialMixin):

    # =====================
    # REQUEST-SPECIFIC FIELDS
    # =====================

    priority = models.CharField(
        _('Priority'),
        max_length=20,
        choices=[
            ('low', _('Low')),
            ('normal', _('Normal')),
            ('high', _('High')),
            ('urgent', _('Urgent')),
        ],
        default='normal',
        help_text=_('Request priority level')
    )

    required_by_date = models.DateField(
        _('Required By Date'),
        null=True,
        blank=True,
        help_text=_('When the items are needed')
    )

    # =====================
    # APPROVAL WORKFLOW FIELDS
    # =====================

    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_purchase_requests',
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
        help_text=_('Reason for rejection if applicable')
    )

    # =====================
    # CONVERSION TRACKING FIELDS
    # =====================


    converted_to_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Converted to Order')
    )

    converted_at = models.DateTimeField(
        _('Converted At'),
        null=True,
        blank=True
    )

    converted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='converted_purchase_requests',
        verbose_name=_('Converted By')
    )

    # =====================
    # MANAGER AND META
    # =====================

    objects = PurchaseRequestManager()

    class Meta:
        verbose_name = _('Purchase Request')
        verbose_name_plural = _('Purchase Requests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['approved_by', 'approved_at']),
            models.Index(fields=['required_by_date']),
        ]

        permissions = [
            ('can_approve_purchase_request', 'Can approve purchase requests'),
            ('can_convert_to_order', 'Can convert requests to orders'),
            ('can_view_financial_summary', 'Can view financial summary'),
        ]

    def __str__(self):
        if self.partner:
            return f"Request {self.document_number} - {self.partner.name}"
        else:
            return f"Request {self.document_number}"

    # =====================
    # MODEL VALIDATION - Keep in Model
    # =====================

    def clean(self):
        """Model-level validation"""
        super().clean()

        # Business validation
        if self.required_by_date and self.required_by_date < timezone.now().date():
            raise ValidationError({
                'required_by_date': _('Required by date cannot be in the past')
            })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-timestamps"""
        super().save(*args, **kwargs)


    @property
    def approval_duration_days(self):
        """Simple calculation - stays in model"""
        if self.approved_at and self.created_at:
            return (self.approved_at.date() - self.created_at.date()).days
        return None

    @property
    def total_estimated_cost(self):
        """Simple aggregation - stays in model"""
        return self.lines.aggregate(
            total=models.Sum(
                models.F('requested_quantity') * models.F('estimated_price')
            )
        )['total'] or Decimal('0')


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
            # Fallback with basic info
            from core.utils.result import Result
            return Result.success(
                {
                    'total_estimated_cost': float(self.total_estimated_cost),
                    'lines_count': self.lines.count(),
                    'partner': self.partner.name if self.partner else None,
                    'status': self.status
                },
                'Basic financial analysis (DocumentService not available)'
            )

    def validate_integrity(self, deep_validation=True):
        """
        Validate document integrity - delegates to DocumentService  # ← ПОПРАВИ КОМЕНТАРА!

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


# =====================
# RELATED MODELS - Request Lines
# =====================

class PurchaseRequestLineManager(models.Manager):
    """Manager for purchase request lines"""

    def get_queryset(self):
        return super().get_queryset().select_related('document', 'product')

    def with_financial_data(self):
        """Include calculated financial fields"""
        return self.annotate(
            line_total=models.F('requested_quantity') * models.F('estimated_price')
        )


class PurchaseRequestLine(BaseDocumentLine):
    """
    Purchase Request Line - Simple data model

    PRINCIPLE: Keep line models simple - they're primarily data containers
    Complex calculations and business logic belong in services
    """

    document = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Request')
    )


    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Quantity requested in specified unit')
    )


    estimated_price = models.DecimalField(
        _('Estimated Price'),
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Estimated unit price for budgeting')
    )


    # =====================
    # TRACKING FIELDS
    # =====================


    updated_at = models.DateTimeField(auto_now=True)

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
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.requested_quantity}"

    # =====================
    # SIMPLE CALCULATIONS - Keep in Model
    # =====================

    @property
    def line_total(self):
        """Simple calculation - stays in model"""
        if self.requested_quantity and self.estimated_price:
            return self.requested_quantity * self.estimated_price
        return Decimal('0')

    @property
    def has_valid_pricing(self):
        """Simple validation - stays in model"""
        return bool(self.estimated_price and self.estimated_price > 0)

    def clean(self):
        """Model-level validation"""
        super().clean()

        if self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Quantity must be positive')
            })

        if self.estimated_price is not None and self.estimated_price < 0:
            raise ValidationError({
                'estimated_price': _('Price cannot be negative')
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
                quantity=self.requested_quantity
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
                self.requested_quantity,
                self.document.partner
            )

        except ImportError:
            from core.utils.result import Result
            return Result.success({}, 'ProductValidationService not available')


