# purchases/models/orders.py - REFACTORED WITH SERVICE DELEGATION



from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nomenclatures.models import BaseDocument, BaseDocumentLine
from nomenclatures.mixins import FinancialMixin, PaymentMixin, FinancialLineMixin
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
    # SOURCE TRACKING
    # =====================

    source_request = models.ForeignKey(
        'purchases.PurchaseRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sourced_orders',
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


        super().save(*args, **kwargs)

    # =====================
    # SIMPLE MODEL PROPERTIES - Keep in Model
    # =====================

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



# =====================
# RELATED MODELS - Order Lines
# =====================

class PurchaseOrderLineManager(models.Manager):
    """Manager for purchase order lines"""

    def get_queryset(self):
        return super().get_queryset().select_related('document', 'product', 'source_request_line')

    def pending_orders(self):
        """Lines in pending orders"""
        return self.filter(document__status='pending')

    def confirmed_orders(self):
        """Lines in confirmed orders"""
        return self.filter(document__status='confirmed')

    def for_supplier(self, supplier):
        """Lines for specific supplier"""
        return self.filter(document__partner=supplier)

    def total_order_value(self):
        """Total value of all order lines"""
        from django.db.models import Sum
        return self.aggregate(
            total=Sum('line_total')
        )['total'] or Decimal('0')

    def by_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)


class PurchaseOrderLine(BaseDocumentLine, FinancialLineMixin):


    # =====================
    # PARENT DOCUMENT
    # =====================
    document = models.ForeignKey(
        'PurchaseOrder',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Order')
    )

    # =====================
    # СПЕЦИФИЧНО QUANTITY ПОЛЕ
    # =====================
    ordered_quantity = models.DecimalField(
        _('Ordered Quantity'),
        max_digits=15,
        decimal_places=3,
        help_text=_('Quantity ordered from supplier')
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
        verbose_name=_('Source Request Line'),
        help_text=_('Original request line this order line was created from')
    )

    # =====================
    # MANAGER
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
        ]

    def __str__(self):
        return f"{self.document.document_number} L{self.line_number}: {self.product.code} x {self.ordered_quantity}"

    # =====================
    # ВАЛИДАЦИЯ
    # =====================
    def clean(self):
        """Order line specific validation"""
        super().clean()  # BaseDocumentLine + FinancialLineMixin validation

        # Ordered quantity must be positive
        if self.ordered_quantity <= 0:
            raise ValidationError({
                'ordered_quantity': _('Ordered quantity must be greater than zero')
            })

        # Unit price must be positive
        if hasattr(self, 'unit_price') and self.unit_price and self.unit_price <= 0:
            raise ValidationError({
                'unit_price': _('Unit price must be greater than zero')
            })

    # =====================
    # OVERRIDE FinancialLineMixin methods for custom quantity
    # =====================
    def get_quantity_for_calculation(self):
        """Override FinancialLineMixin method to use ordered_quantity"""
        return self.ordered_quantity or Decimal('1')



