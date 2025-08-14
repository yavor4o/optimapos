# purchases/models/requests.py - CLEAN & SYNCHRONIZED VERSION
"""
Purchase Request Models - ПЪЛНО СИНХРОНИЗИРАНИ С NOMENCLATURES

ПРОМЕНИ:
- ПРЕМАХНАТО: status поле (използва BaseDocument.status)
- ПРЕМАХНАТО: approval полета (използва ApprovalLog)
- ПРЕМАХНАТО: hardcoded workflow методи
- ДОБАВЕНО: пълна интеграция с DocumentService
- ДОБАВЕНО: dynamic managers използващи nomenclatures

АРХИТЕКТУРА:
- PurchaseRequest: BaseDocument + FinancialMixin (за estimated calculations)
- PurchaseRequestLine: BaseDocumentLine + FinancialLineMixin
- Всички статуси и workflow през nomenclatures система
"""

from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone

from .base import BaseDocument, BaseDocumentLine, FinancialMixin, FinancialLineMixin


# =================================================================
# PURCHASE REQUEST MANAGER - DYNAMIC & SYNCHRONIZED
# =================================================================

class PurchaseRequestManager(models.Manager):
    """
    Manager for Purchase Requests - SYNCHRONIZED WITH NOMENCLATURES

    ВСИЧКИ методи използват DocumentService вместо hardcoded статуси
    """

    def pending_approval(self):
        """Requests waiting for approval - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_pending_approval_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            # Fallback ако nomenclatures не е налична
            return self.filter(status='submitted')

    def approved(self):
        """Approved requests ready for conversion - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_ready_for_processing_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.filter(status='approved')

    def converted(self):
        """Requests that have been converted to orders"""
        return self.filter(converted_to_order__isnull=False)

    def active(self):
        """Active requests (not cancelled/completed) - DYNAMIC"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_active_documents(
                queryset=self.get_queryset()
            )
        except ImportError:
            return self.exclude(status__in=['cancelled', 'converted'])

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
        from datetime import timedelta
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return self.pending_approval().filter(
            document_date__lte=cutoff_date
        )

    def by_requester(self, user):
        """Requests by specific user"""
        return self.filter(requested_by=user)

    def high_priority(self):
        """High urgency requests"""
        return self.filter(urgency_level__in=['high', 'critical'])

    def needs_supplier_assignment(self):
        """Requests without supplier assigned"""
        return self.active().filter(
            lines__suggested_supplier__isnull=True
        ).distinct()


# =================================================================
# PURCHASE REQUEST - CLEAN MODEL
# =================================================================

class PurchaseRequest(BaseDocument, FinancialMixin):
    """
    Purchase Request - Заявка за покупка

    LOGIC:
    - Наследява BaseDocument (има document_type, status управлявани от nomenclatures)
    - Използва FinancialMixin за estimated финансови данни
    - БЕЗ PaymentMixin (заявките не са плащания)
    - БЕЗ DeliveryMixin (заявките не са доставки)

    WORKFLOW:
    - Управлявано изцяло от nomenclatures.DocumentService
    - Статуси динамични от DocumentType конфигурация
    - Approval rules от ApprovalRule система
    """

    # =====================
    # REQUEST TYPE CLASSIFICATION
    # =====================
    REQUEST_TYPE_CHOICES = [
        ('regular', _('Regular Purchase')),
        ('urgent', _('Urgent Purchase')),
        ('emergency', _('Emergency Purchase')),
        ('consumables', _('Consumables Restock')),
        ('maintenance', _('Maintenance Supplies')),
        ('project', _('Project Materials')),
        ('capital', _('Capital Equipment')),
        ('services', _('Services')),
    ]

    request_type = models.CharField(
        _('Request Type'),
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='regular',
        help_text=_('Type of purchase request')
    )

    # =====================
    # URGENCY & PRIORITY
    # =====================
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

    # =====================
    # BUSINESS JUSTIFICATION
    # =====================
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
    # REQUESTER INFORMATION
    # =====================
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='purchase_requests_made',
        verbose_name=_('Requested By'),
        help_text=_('Person who made the request')
    )

    requested_for = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_requests_for',
        verbose_name=_('Requested For'),
        help_text=_('Person who will use the items (if different from requester)')
    )

    # =====================
    # CONVERSION TRACKING
    # =====================
    converted_to_order = models.ForeignKey(
        'purchases.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_from_request',
        verbose_name=_('Converted to Order'),
        help_text=_('Generated purchase order from this request')
    )

    converted_at = models.DateTimeField(
        _('Converted At'),
        null=True,
        blank=True,
        help_text=_('When request was converted to order')
    )

    converted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_requests_converted',
        verbose_name=_('Converted By'),
        help_text=_('User who converted request to order')
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
            # Status queries (използва BaseDocument.status)
            models.Index(fields=['status', 'urgency_level']),
            models.Index(fields=['status', 'request_type']),

            # User queries
            models.Index(fields=['requested_by', '-created_at']),
            models.Index(fields=['requested_for', '-created_at']),

            # Business queries
            models.Index(fields=['request_type', 'urgency_level']),
            models.Index(fields=['urgency_level', '-created_at']),

            # Conversion tracking
            models.Index(fields=['converted_to_order']),
            models.Index(fields=['converted_at']),

            # Document type queries (от BaseDocument)
            models.Index(fields=['document_type', 'status']),
        ]

    def __str__(self):
        return f"REQ-{self.document_number} | {self.supplier.name if self.supplier else 'No Supplier'}"

    # =====================
    # DOCUMENT TYPE INTEGRATION
    # =====================
    def get_document_type_key(self):
        """Return the document type key for this model"""
        return 'purchase_request'

    def get_document_prefix(self):
        """Return prefix for document numbering"""
        return "REQ"

    # =====================
    # BUSINESS VALIDATION - ENHANCED
    # =====================
    def clean(self):
        """Enhanced validation using nomenclatures integration"""
        super().clean()

        # Request-specific validation
        if self.urgency_level == 'critical' and not self.business_justification:
            raise ValidationError({
                'business_justification': _('Critical requests must have detailed justification')
            })

        # Conversion validation
        if self.converted_to_order and not self.converted_at:
            self.converted_at = timezone.now()

        if self.converted_at and not self.converted_by:
            raise ValidationError({
                'converted_by': _('Converted by is required when converted_at is set')
            })

        # DocumentService validation будет проверено автоматично

    # =====================
    # WORKFLOW INTEGRATION METHODS
    # =====================
    def can_edit(self, user=None):
        """Check if request can be edited - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, reason = DocumentService.can_edit_document(self, user)
            return can_edit
        except ImportError:
            # Fallback
            return self.status in ['draft', 'returned']

    def get_available_actions(self, user=None):
        """Get available actions for user - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_available_actions(self, user)
        except ImportError:
            return []

    def transition_to(self, new_status, user, comments=''):
        """Transition to new status - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.transition_document(
                self, new_status, user, comments
            )
        except ImportError:
            raise ValidationError("Document workflow service not available")

    # =====================
    # BUSINESS LOGIC METHODS
    # =====================
    def get_total_estimated_cost(self):
        """Calculate total estimated cost from lines"""
        total = Decimal('0.00')
        for line in self.lines.all():
            if line.entered_price and line.requested_quantity:
                total += line.entered_price * line.requested_quantity
        return total

    def get_items_count(self):
        """Get total number of different items"""
        return self.lines.count()

    def get_total_quantity(self):
        """Get total quantity of all items"""
        return sum(
            line.requested_quantity
            for line in self.lines.all()
        ) or Decimal('0.00')

    def has_complete_pricing(self):
        """Check if all lines have pricing information"""
        return not self.lines.filter(
            models.Q(entered_price__isnull=True) |
            models.Q(entered_price=0)
        ).exists()

    def get_lines_without_suppliers(self):
        """Get lines that don't have suggested suppliers"""
        return self.lines.filter(suggested_supplier__isnull=True)

    def mark_converted(self, order, user):
        """Mark request as converted to order"""
        self.converted_to_order = order
        self.converted_at = timezone.now()
        self.converted_by = user
        self.save(update_fields=['converted_to_order', 'converted_at', 'converted_by'])

        # Transition через nomenclatures
        try:
            self.transition_to('converted', user, f'Converted to order {order.document_number}')
        except:
            pass  # Fallback ако nomenclatures не работи

    def get_approval_history(self):
        """Get approval history - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_approval_history(self)
        except ImportError:
            return []

    def get_workflow_info(self):
        """Get complete workflow information - USES NOMENCLATURES"""
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_workflow_info(self)
        except ImportError:
            return None


# =================================================================
# PURCHASE REQUEST LINE MANAGER
# =================================================================

class PurchaseRequestLineManager(models.Manager):
    """Manager for Purchase Request Lines"""

    def for_request(self, request):
        """Lines for specific request"""
        return self.filter(document=request)

    def pending_approval(self):
        """Lines in requests pending approval"""
        try:
            from nomenclatures.services import DocumentService
            pending_requests = DocumentService.get_pending_approval_documents(
                queryset=PurchaseRequest.objects.all()
            )
            return self.filter(document__in=pending_requests)
        except ImportError:
            return self.filter(document__status='submitted')

    def approved(self):
        """Lines in approved requests"""
        try:
            from nomenclatures.services import DocumentService
            approved_requests = DocumentService.get_ready_for_processing_documents(
                queryset=PurchaseRequest.objects.all()
            )
            return self.filter(document__in=approved_requests)
        except ImportError:
            return self.filter(document__status='approved')

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)

    def with_pricing(self):
        """Lines that have entered prices"""
        return self.filter(entered_price__isnull=False, entered_price__gt=0)

    def missing_pricing(self):
        """Lines missing price information"""
        return self.filter(
            models.Q(entered_price__isnull=True) |
            models.Q(entered_price=0)
        )

    def high_value(self, threshold=1000):
        """Lines with high estimated value"""
        return self.filter(
            entered_price__isnull=False,
            requested_quantity__isnull=False
        ).extra(
            where=["entered_price * requested_quantity > %s"],
            params=[threshold]
        )

    def by_urgency(self, level):
        """Lines from requests with specific urgency"""
        return self.filter(document__urgency_level=level)

    def without_suppliers(self):
        """Lines without suggested suppliers"""
        return self.filter(suggested_supplier__isnull=True)


# =================================================================
# PURCHASE REQUEST LINE - CLEAN MODEL
# =================================================================

class PurchaseRequestLine(BaseDocumentLine, FinancialLineMixin):
    """
    Purchase Request Line - Ред на заявка за покупка

    LOGIC:
    - Наследява BaseDocumentLine (product, unit, etc.)
    - Използва FinancialLineMixin за ценови данни
    - БЕЗ delivery полета (това е само заявка)
    """

    # =====================
    # DOCUMENT RELATIONSHIP
    # =====================
    document = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Purchase Request')
    )

    # =====================
    # REQUEST-SPECIFIC QUANTITY
    # =====================
    requested_quantity = models.DecimalField(
        _('Requested Quantity'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity requested for purchase')
    )

    # =====================
    # SUPPLIER SUGGESTION
    # =====================
    suggested_supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Suggested Supplier'),
        help_text=_('Preferred supplier for this item')
    )

    # =====================
    # PRIORITY & JUSTIFICATION
    # =====================
    priority = models.IntegerField(
        _('Priority'),
        default=0,
        help_text=_('Priority within request (0=normal, higher=more urgent)')
    )

    item_justification = models.TextField(
        _('Item Justification'),
        blank=True,
        help_text=_('Why is this specific item needed?')
    )

    # =====================
    # DELIVERY REQUIREMENTS
    # =====================
    required_by_date = models.DateField(
        _('Required By Date'),
        null=True,
        blank=True,
        help_text=_('When is this item needed by?')
    )

    delivery_location = models.CharField(
        _('Delivery Location'),
        max_length=200,
        blank=True,
        help_text=_('Specific delivery location for this item')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = PurchaseRequestLineManager()

    class Meta:
        verbose_name = _('Purchase Request Line')
        verbose_name_plural = _('Purchase Request Lines')
        ordering = ['document', 'line_number']
        indexes = [
            # Document queries
            models.Index(fields=['document', 'line_number']),

            # Product queries
            models.Index(fields=['product', 'requested_quantity']),

            # Supplier queries
            models.Index(fields=['suggested_supplier']),

            # Priority queries
            models.Index(fields=['document', 'priority']),
            models.Index(fields=['priority', 'required_by_date']),

            # Financial queries (от FinancialLineMixin)
            models.Index(fields=['entered_price']),

            # Date queries
            models.Index(fields=['required_by_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(requested_quantity__gt=0),
                name='positive_requested_quantity'
            ),
            models.CheckConstraint(
                check=models.Q(priority__gte=0),
                name='non_negative_priority'
            ),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.name if self.product else 'No Product'}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced line validation"""
        super().clean()

        # Quantity validation
        if self.requested_quantity and self.requested_quantity <= 0:
            raise ValidationError({
                'requested_quantity': _('Requested quantity must be positive')
            })

        # Date validation
        if self.required_by_date and self.required_by_date < timezone.now().date():
            raise ValidationError({
                'required_by_date': _('Required by date cannot be in the past')
            })

        # Priority validation for urgent requests
        if self.document and self.document.urgency_level in ['high', 'critical']:
            if not self.item_justification:
                raise ValidationError({
                    'item_justification': _('High priority items require justification')
                })

    # =====================
    # BUSINESS METHODS
    # =====================
    def get_estimated_total(self):
        """Get estimated total for this line"""
        if self.entered_price and self.requested_quantity:
            return self.entered_price * self.requested_quantity
        return Decimal('0.00')

    def get_estimated_total_with_vat(self):
        """Get estimated total with VAT"""
        total = self.get_estimated_total()
        if total and self.vat_rate:
            return total * (1 + self.vat_rate / 100)
        return total

    def is_high_value(self, threshold=1000):
        """Check if this is a high value line"""
        return self.get_estimated_total() > threshold

    def is_urgent(self):
        """Check if this line is urgent"""
        return (
                self.document.urgency_level in ['high', 'critical'] or
                self.priority > 0 or
                (self.required_by_date and
                 self.required_by_date <= timezone.now().date() + timezone.timedelta(days=7))
        )

    def can_suggest_supplier(self):
        """Check if supplier can be suggested for this line"""
        return self.product and not self.suggested_supplier

    def get_product_info(self):
        """Get detailed product information"""
        if not self.product:
            return {}

        return {
            'code': getattr(self.product, 'code', ''),
            'name': getattr(self.product, 'name', ''),
            'category': getattr(self.product.category, 'name', None) if hasattr(self.product,
                                                                                'category') and self.product.category else None,
            'base_unit': getattr(self.product.base_unit, 'code', None) if hasattr(self.product,
                                                                                  'base_unit') and self.product.base_unit else None,
            'default_supplier': getattr(self.product.default_supplier, 'name', None) if hasattr(self.product,
                                                                                                'default_supplier') and self.product.default_supplier else None,
        }

    def copy_to_order_line(self, order):
        """Create order line from this request line"""
        # Import here to avoid circular imports
        from .orders import PurchaseOrderLine

        return PurchaseOrderLine.objects.create(
            document=order,
            product=self.product,
            unit=self.unit,
            ordered_quantity=self.requested_quantity,
            entered_price=self.entered_price,
            vat_rate=self.vat_rate,
            discount_percent=self.discount_percent,
            notes=f"From request {self.document.document_number}, line {self.line_number}. {self.item_justification}".strip(),
            line_number=self.line_number,
        )