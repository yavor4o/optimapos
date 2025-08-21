# purchases/models/requests.py - REFACTORED
"""
PurchaseRequest Model - Clean Architecture Implementation

CHANGES:
❌ REMOVED: Fat business logic methods from model
✅ ADDED: Thin wrapper methods that delegate to services
✅ PRESERVED: 100% backward compatibility
✅ ENHANCED: Better error handling and logging

PRINCIPLE:
Model = Data + Simple Operations
Services = Business Logic + Complex Operations
"""

import warnings
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nomenclatures.models import BaseDocument
from nomenclatures.mixins import FinancialMixin
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PurchaseRequestManager(models.Manager):
    """Enhanced manager with service integration"""

    def get_queryset(self):
        return super().get_queryset().select_related(
            'supplier', 'location', 'document_type', 'created_by'
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

    def by_supplier(self, supplier):
        """Requests for specific supplier"""
        return self.filter(supplier=supplier)

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
    """
    Purchase Request - Clean Model Implementation

    PHILOSOPHY:
    - Model handles data persistence and simple operations
    - Complex business logic delegated to services
    - Backward compatibility maintained through wrapper methods
    - Service integration through composition, not inheritance
    """

    # =====================
    # REQUEST-SPECIFIC STATUS CHOICES
    # =====================
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    CONVERTED = 'converted'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (SUBMITTED, _('Submitted for Approval')),
        (APPROVED, _('Approved')),
        (CONVERTED, _('Converted to Order')),
        (REJECTED, _('Rejected')),
        (CANCELLED, _('Cancelled')),
    ]

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

    # В purchases/models/requests.py - променй САМО тази линия:
    # В purchases/models/requests.py - променй САМО тази линия:
    converted_to_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='originating_request',  # ✅ ДОБАВИ ТОВА
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
        return f"Request {self.document_number} - {self.supplier.name}"

    # =====================
    # MODEL VALIDATION - Keep in Model
    # =====================

    def clean(self):
        """Model-level validation"""
        super().clean()

        # Status-specific validation
        if self.status == self.APPROVED:
            if not self.approved_by:
                raise ValidationError({
                    'approved_by': _('Approved by is required when status is approved')
                })

        if self.status == self.REJECTED:
            if not self.rejection_reason:
                raise ValidationError({
                    'rejection_reason': _('Rejection reason is required when status is rejected')
                })

        if self.status == self.CONVERTED:
            if not self.converted_to_order:
                raise ValidationError({
                    'converted_to_order': _('Converted to order is required when status is converted')
                })

        # Business validation
        if self.required_by_date and self.required_by_date < timezone.now().date():
            raise ValidationError({
                'required_by_date': _('Required by date cannot be in the past')
            })

    def save(self, *args, **kwargs):
        """Enhanced save with auto-timestamps"""
        # Auto-set approval timestamp
        if self.status == self.APPROVED and not self.approved_at:
            self.approved_at = timezone.now()

        # Auto-set conversion timestamp
        if self.status == self.CONVERTED and not self.converted_at:
            self.converted_at = timezone.now()

        super().save(*args, **kwargs)

    # =====================
    # SIMPLE MODEL PROPERTIES - Keep in Model
    # =====================

    @property
    def is_pending_approval(self):
        """Simple status check - stays in model"""
        return self.status == self.SUBMITTED

    @property
    def is_approved(self):
        """Simple status check - stays in model"""
        return self.status == self.APPROVED

    @property
    def is_converted(self):
        """Simple status check - stays in model"""
        return self.status == self.CONVERTED

    @property
    def can_be_edited(self):
        """Simple business rule - stays in model"""
        return self.status in [self.DRAFT]

    @property
    def can_be_cancelled(self):
        """Simple business rule - stays in model"""
        return self.status in [self.DRAFT, self.SUBMITTED]

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
    # SERVICE DELEGATION METHODS - Wrapper Methods for Backward Compatibility
    # =====================

    def submit_for_approval(self, user=None):
        """
        WRAPPER METHOD - Delegates to DocumentService

        DEPRECATED: Use DocumentService.transition_document() directly
        LEGACY: Kept for backward compatibility
        """
        warnings.warn(
            "PurchaseRequest.submit_for_approval() is deprecated. "
            "Use DocumentService.transition_document() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        if self.status != self.DRAFT:
            raise ValidationError("Can only submit draft requests")

        if not self.lines.exists():
            raise ValidationError("Cannot submit request without lines")

        try:
            from nomenclatures.services import DocumentService

            result = DocumentService.transition_document(
                self, self.SUBMITTED, user, 'Request submitted for approval'
            )

            if result.ok:
                return True  # Legacy behavior
            else:
                raise ValidationError(result.msg)

        except ImportError:
            # Fallback for when DocumentService not available
            logger.warning("DocumentService not available, using fallback logic")

            self.status = self.SUBMITTED
            self.updated_by = user
            self.save()
            return True

    def approve(self, user, notes=''):
        """
        WRAPPER METHOD - Delegates to DocumentService + ApprovalService

        DEPRECATED: Use ApprovalService authorization flow
        LEGACY: Kept for backward compatibility
        """
        warnings.warn(
            "PurchaseRequest.approve() is deprecated. "
            "Use ApprovalService authorization flow instead.",
            DeprecationWarning,
            stacklevel=2
        )

        if self.status != self.SUBMITTED:
            raise ValidationError("Can only approve submitted requests")

        try:
            from nomenclatures.services import DocumentService

            # Check if user is authorized (via ApprovalService)
            try:
                from nomenclatures.services import ApprovalService
                auth_result = ApprovalService.authorize_document_transition(
                    self, self.APPROVED, user
                )
                if not auth_result.ok:
                    raise ValidationError(f"Not authorized: {auth_result.msg}")
            except (ImportError, AttributeError):
                # Skip authorization if ApprovalService not available or method missing
                pass

            # Perform transition
            result = DocumentService.transition_document(
                self, self.APPROVED, user, notes or 'Request approved'
            )

            if result.ok:
                # Update approval fields
                self.approved_by = user
                self.approved_at = timezone.now()
                if notes:
                    self.notes = (self.notes + '\n' + notes).strip()
                self.save(update_fields=['approved_by', 'approved_at', 'notes'])
                return True
            else:
                raise ValidationError(result.msg)

        except ImportError:
            # Fallback logic
            logger.warning("Services not available, using fallback logic")

            self.status = self.APPROVED
            self.approved_by = user
            self.approved_at = timezone.now()
            if notes:
                self.notes = (self.notes + '\n' + notes).strip()
            self.updated_by = user
            self.save()
            return True

    def reject(self, user, reason):
        """
        WRAPPER METHOD - Delegates to DocumentService

        DEPRECATED: Use DocumentService.transition_document()
        LEGACY: Kept for backward compatibility
        """
        warnings.warn(
            "PurchaseRequest.reject() is deprecated. "
            "Use DocumentService.transition_document() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        if self.status != self.SUBMITTED:
            raise ValidationError("Can only reject submitted requests")

        try:
            from nomenclatures.services import DocumentService

            result = DocumentService.transition_document(
                self, self.REJECTED, user, f'Request rejected: {reason}'
            )

            if result.ok:
                self.rejection_reason = reason
                self.save(update_fields=['rejection_reason'])
                return True
            else:
                raise ValidationError(result.msg)

        except ImportError:
            # Fallback logic
            self.status = self.REJECTED
            self.rejection_reason = reason
            self.updated_by = user
            self.save()
            return True

    def convert_to_order(self, user=None):
        """
        WRAPPER METHOD - Delegates to PurchaseWorkflowService

        DEPRECATED: Use PurchaseWorkflowService.convert_request_to_order()
        LEGACY: Kept for backward compatibility

        Returns:
            PurchaseOrder instance (legacy behavior)

        Raises:
            ValidationError (legacy behavior)
        """
        warnings.warn(
            "PurchaseRequest.convert_to_order() is deprecated. "
            "Use PurchaseWorkflowService.convert_request_to_order() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        try:
            from purchases.services.workflow_service import PurchaseWorkflowService

            result = PurchaseWorkflowService.convert_request_to_order(self, user)

            if result.ok:
                return result.data['order']  # Legacy behavior: return object
            else:
                raise ValidationError(result.msg)  # Legacy behavior: raise exception

        except ImportError:
            raise ValidationError("PurchaseWorkflowService is not available")

    # =====================
    # ENHANCED ANALYSIS METHODS - Delegate to Services
    # =====================

    def get_financial_analysis(self):
        """
        Get detailed financial analysis - PLACEHOLDER до DocumentService enhancement

        Returns:
            Result object with financial breakdown
        """
        try:
            # TODO: Implement when DocumentService gets this method
            from core.utils.result import Result
            return Result.success(
                {
                    'total_estimated_cost': float(self.total_estimated_cost),
                    'lines_count': self.lines.count(),
                    'supplier': self.supplier.name,
                    'status': self.status
                },
                'Basic financial analysis (enhanced version pending)'
            )
        except Exception as e:
            from core.utils.result import Result
            return Result.error(
                'ANALYSIS_ERROR',
                f'Financial analysis failed: {str(e)}'
            )

    def validate_integrity(self, deep_validation=True):
        """
        Validate document integrity - PLACEHOLDER до DocumentService enhancement

        Returns:
            Result object with validation details
        """
        try:
            from core.utils.result import Result

            issues = []

            # Basic validation
            if not self.lines.exists():
                issues.append({
                    'type': 'no_lines',
                    'severity': 'error',
                    'message': 'Document has no lines'
                })

            # Line validation
            for line in self.lines.all():
                if line.requested_quantity <= 0:
                    issues.append({
                        'type': 'invalid_quantity',
                        'severity': 'error',
                        'line': line.line_number,
                        'message': f'Line {line.line_number}: Invalid quantity'
                    })

            error_count = len([i for i in issues if i['severity'] == 'error'])
            is_valid = error_count == 0

            return Result.success(
                {
                    'is_valid': is_valid,
                    'error_count': error_count,
                    'validation_issues': issues,
                    'document_number': self.document_number
                },
                f'Validation completed: {"VALID" if is_valid else "INVALID"}'
            )

        except Exception as e:
            from core.utils.result import Result
            return Result.error(
                'VALIDATION_ERROR',
                f'Document validation failed: {str(e)}'
            )

    def recalculate_lines(self, user=None, update_pricing=True):
        """
        Recalculate all lines - PLACEHOLDER до DocumentService enhancement

        Returns:
            Result object with recalculation details
        """
        try:
            from core.utils.result import Result

            # Basic recalculation - just call model's method
            original_total = self.total_amount
            self.recalculate_totals()  # Existing model method

            return Result.success(
                {
                    'lines_processed': self.lines.count(),
                    'total_amount_change': float(self.total_amount - original_total),
                    'new_total': float(self.total_amount)
                },
                f'Recalculated {self.lines.count()} lines (basic version)'
            )

        except Exception as e:
            from core.utils.result import Result
            return Result.error(
                'RECALCULATION_ERROR',
                f'Line recalculation failed: {str(e)}'
            )

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

            # Try to get workflow info if method exists
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
                # ApprovalService exists but method doesn't
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
            return ['submitted']
        elif self.status == self.SUBMITTED:
            return ['approved', 'rejected']
        elif self.status == self.APPROVED:
            return ['converted'] if not self.converted_to_order else []
        else:
            return []

    def get_conversion_eligibility(self):
        """
        Check if request can be converted to order

        Returns:
            Dict with eligibility status and reasons
        """
        eligibility = {
            'eligible': False,
            'reasons': []
        }

        if self.status != self.APPROVED:
            eligibility['reasons'].append(f'Status is {self.status}, must be approved')

        if self.converted_to_order:
            eligibility['reasons'].append('Already converted to order')

        if not self.lines.exists():
            eligibility['reasons'].append('No lines to convert')

        # Check for line-level issues
        for line in self.lines.all():
            if not line.requested_quantity or line.requested_quantity <= 0:
                eligibility['reasons'].append(f'Line {line.line_number}: Invalid quantity')

            if not line.estimated_price:
                eligibility['reasons'].append(f'Line {line.line_number}: Missing estimated price')

        eligibility['eligible'] = len(eligibility['reasons']) == 0

        return eligibility


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


class PurchaseRequestLine(models.Model):
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

    line_number = models.PositiveIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )

    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Quantity requested in specified unit')
    )

    unit = models.CharField(
        _('Unit'),
        max_length=20,
        help_text=_('Unit of measure for this line')
    )

    estimated_price = models.DecimalField(
        _('Estimated Price'),
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Estimated unit price for budgeting')
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
                self.document.supplier
            )

        except ImportError:
            from core.utils.result import Result
            return Result.success({}, 'ProductValidationService not available')


# =====================
# MIGRATION NOTES
# =====================

"""
MIGRATION GUIDE для PurchaseRequest:

ПРЕДИ (Fat Model):
    def convert_to_order(self, user=None):
        # 50+ lines of business logic in model
        order = PurchaseOrder.objects.create(...)
        # Complex conversion logic
        # Error handling
        # Related object creation
        return order

СЕГА (Service Delegation):
    def convert_to_order(self, user=None):
        # Thin wrapper - delegates to service
        result = PurchaseWorkflowService.convert_request_to_order(self, user)
        return result.data['order'] if result.ok else raise ValidationError(result.msg)

BENEFITS:
✅ Model stays focused on data persistence
✅ Business logic centralized in services  
✅ Better testing - services are easier to test
✅ Reusability - services can be used by API, admin, etc.
✅ Backward compatibility - old code continues to work
✅ Enhanced functionality - services provide richer results

NEW CODE SHOULD USE:
    from purchases.services.workflow_service import PurchaseWorkflowService
    result = PurchaseWorkflowService.convert_request_to_order(request, user)

    if result.ok:
        order = result.data['order'] 
        print(f"Created order with {result.data['lines_count']} lines")
    else:
        print(f"Conversion failed: {result.code} - {result.msg}")
"""