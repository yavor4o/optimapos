
# nomenclatures/models/base_document.py - EXACT COPY ОТ purchases/models/base.py
"""
Base Document Models - MOVED FROM purchases.models.base

MIGRATION: Moved to nomenclatures for logical coherence
- BaseDocument: Core document functionality
- BaseDocumentLine: Core line functionality
- DocumentManager: Dynamic queries via DocumentService
- LineManager: Standard line operations

USAGE: Used by purchases, sales, inventory apps
"""

import warnings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging


logger = logging.getLogger(__name__)


# =================================================================
# MANAGERS - WITH DocumentService INTEGRATION
# =================================================================

class DocumentManager(models.Manager):
    """
    Base manager for all purchase documents

    100% СИНХРОНИЗИРАН с nomenclatures.DocumentService:
    - NO hardcoded статуси никъде
    - Dynamic queries САМО от DocumentType/ApprovalRule
    - Explicit failures ако nomenclatures не е достъпен
    """

    def active(self):
        """Return only active documents - DYNAMIC от DocumentService"""
        from nomenclatures.services import DocumentService
        return DocumentService.get_active_documents(queryset=self.get_queryset())

    def pending_approval(self):
        """Documents pending approval - DYNAMIC от ApprovalRule"""
        from nomenclatures.services import DocumentService
        return DocumentService.get_pending_approval_documents(queryset=self.get_queryset())

    def ready_for_processing(self):
        """Documents ready for processing - DYNAMIC от ApprovalRule"""
        from nomenclatures.services import DocumentService
        return DocumentService.get_ready_for_processing_documents(queryset=self.get_queryset())

    def by_document_type(self, type_key):
        """Filter by DocumentType.type_key"""
        return self.filter(document_type__type_key=type_key)

    def for_app(self, app_name):
        """Filter by DocumentType.app_name"""
        return self.filter(document_type__app_name=app_name)

    def requiring_approval(self):
        """Documents that require approval workflow"""
        return self.filter(document_type__requires_approval=True)

    def affecting_inventory(self):
        """Documents that affect inventory"""
        return self.filter(document_type__affects_inventory=True)

    def fiscal_documents(self):
        """Fiscal documents (Bulgarian legal requirement)"""
        return self.filter(document_type__is_fiscal=True)

    def search(self, query):
        """Enhanced search across multiple fields"""
        if not query:
            return self.all()

        return self.filter(
            models.Q(document_number__icontains=query) |
            models.Q(supplier__name__icontains=query) |
            models.Q(external_reference__icontains=query) |
            models.Q(notes__icontains=query)
        )

    def by_status(self, status):
        """Filter by specific status"""
        return self.filter(status=status)

    def in_statuses(self, statuses):
        """Filter by multiple statuses"""
        return self.filter(status__in=statuses)

    def by_date_range(self, date_from=None, date_to=None):
        """Filter by document date range"""
        queryset = self.all()
        if date_from:
            queryset = queryset.filter(document_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(document_date__lte=date_to)
        return queryset

    def by_supplier(self, supplier):
        """Filter by supplier"""
        return self.filter(supplier=supplier)

    def by_location(self, location):
        """Filter by location"""
        return self.filter(location=location)

    def recent(self, days=30):
        """Documents from last N days"""
        from django.utils import timezone
        from datetime import timedelta
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return self.filter(document_date__gte=cutoff_date)





    def get_status_summary(self):
        """Get count by status for dashboard"""
        return self.values('status').annotate(
            count=models.Count('id')
        ).order_by('status')

    def get_supplier_summary(self):
        """Get count by supplier"""
        return self.values('supplier__name').annotate(
            count=models.Count('id'),
            total_value=models.Sum('total')  # If FinancialMixin
        ).order_by('-count')

    def get_monthly_stats(self, year=None):
        """Get monthly statistics"""
        from django.utils import timezone

        if not year:
            year = timezone.now().year

        return self.filter(
            document_date__year=year
        ).extra(
            select={'month': 'EXTRACT(month FROM document_date)'}
        ).values('month').annotate(
            count=models.Count('id')
        ).order_by('month')


class LineManager(models.Manager):
    """Base manager for document lines"""

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)

    def with_variances(self):
        """Lines with quantity variances"""
        return self.filter(
            models.Q(variance_quantity__gt=0) |
            models.Q(variance_quantity__lt=0)
        )

# =================================================================
# BASE DOCUMENT - CORE MODEL
# =================================================================

class BaseDocument(models.Model):
    """
    Base Document Model - UNIVERSAL FOR ALL APPS

    Used by: purchases, sales, inventory, hr apps
    """

    # =====================
    # DOCUMENT TYPE INTEGRATION
    # =====================
    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Document Type'),
        help_text=_('Set by DocumentService on creation'),
        limit_choices_to={'is_active': True}
    )

    # =====================
    # CORE FIELDS
    # =====================
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True,
        blank=True,  # DocumentService ще генерира
        help_text=_('Generated by DocumentService')
    )

    document_date = models.DateField(
        _('Document Date'),
        default=timezone.now,
        help_text=_('Date when document was created')
    )

    status = models.CharField(
        _('Status'),
        max_length=30,
        blank=True,  # DocumentService ще сетне
        help_text=_('Managed by DocumentService')
        # NO choices - dynamic from DocumentType!
    )

    # =====================
    # BUSINESS RELATIONSHIPS
    # =====================
    supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Supplier'),
        help_text=_('The supplier for this document')
    )

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        verbose_name=_('Location'),
        help_text=_('Business location')
    )

    # =====================
    # REFERENCE FIELDS
    # =====================
    external_reference = models.CharField(
        _('External Reference'),
        max_length=100,
        blank=True,
        help_text=_('External PO number, contract reference, etc.')
    )

    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes and comments')
    )

    # =====================
    # AUDIT FIELDS
    # =====================
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='%(class)s_created',
        verbose_name=_('Created By')
    )

    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='%(class)s_updated',
        verbose_name=_('Updated By')
    )

    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    # =====================
    # MANAGER
    # =====================
    objects = DocumentManager()

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document_number or 'Draft'} - {self.get_document_prefix()}"

    def clean(self):
        """
        САМО data validation - БЕЗ business logic
        DocumentService handles all business rules
        """
        super().clean()

        # Required fields validation ONLY
        if not self.location:
            raise ValidationError({'location': _('Location is required')})

    def save(self, *args, **kwargs):
        # Автоматично номериране
        if not self.pk and not self.document_number:
            try:
                from nomenclatures.services import DocumentService
                self.document_number = DocumentService.generate_number_for(self)
            except ImportError:
                # Fallback numbering
                model_name = self._meta.model_name.upper()
                self.document_number = f"{model_name}-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        super().save(*args, **kwargs)

    # =====================
    # READ-ONLY HELPERS
    # =====================

    def get_document_prefix(self):
        """Get document prefix from DocumentType or fallback"""
        if self.document_type and hasattr(self.document_type, 'number_prefix'):
            return self.document_type.number_prefix

        # Fallback mapping
        model_name = self._meta.model_name.lower()
        prefix_map = {
            'purchaserequest': 'REQ',
            'purchaseorder': 'ORD',
            'deliveryreceipt': 'DEL',
            'salesinvoice': 'INV',
        }
        return prefix_map.get(model_name, 'DOC')

    def get_document_type_key(self):
        """Get document type key for this model"""
        if self.document_type and hasattr(self.document_type, 'type_key'):
            return self.document_type.type_key

        # Fallback
        model_name = self._meta.model_name.lower()
        type_key_map = {
            'purchaserequest': 'purchase_request',
            'purchaseorder': 'purchase_order',
            'deliveryreceipt': 'delivery_receipt'
        }
        return type_key_map.get(model_name, 'document')

    # =====================
    # BUSINESS LOGIC INTEGRATION (will be moved to services)
    # =====================

    def transition_to(self, new_status, user, comments=''):
        """Transition to new status - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.transition_document(
                self, new_status, user, comments
            )
        except ImportError:
            # Simple fallback
            self.status = new_status
            self.updated_by = user
            self.save(update_fields=['status', 'updated_by'])
            return True

    def can_edit(self, user=None):
        """Check if document can be edited - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, reason = DocumentService.can_edit_document(self, user)
            return can_edit
        except ImportError:
            # Fallback
            return self.status in ['draft']

    def get_available_actions(self, user=None):
        """Get available actions for user - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_available_actions(self, user)
        except ImportError:
            return []


# =================================================================
# BASE DOCUMENT LINE - CORE MODEL
# =================================================================

class BaseDocumentLine(models.Model):
    """
    Base Document Line - CLEAN VERSION

    САМО essential line behavior:
    - Core fields
    - Basic validation
    - Helper methods

    NO complex calculations - moved to services!
    """

    # =====================
    # CORE FIELDS
    # =====================
    line_number = models.PositiveIntegerField(
        _('Line Number'),
        help_text=_('Line number within document (auto-generated)')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product'),
        help_text=_('Product for this line')
    )

    quantity = models.DecimalField(
        _('Quantity'),
        null=True,
        blank=True,
        max_digits=10,
        decimal_places=3,
        help_text=_('Quantity for this line')
    )

    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit'),
        help_text=_('Unit of measure')
    )

    notes = models.TextField(
        _('Line Notes'),
        blank=True,
        help_text=_('Notes specific to this line')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = LineManager()

    class Meta:
        abstract = True
        ordering = ['line_number']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['line_number']),
        ]

    def __str__(self):
        return f"Line {self.line_number}: {self.product.code} x {self.quantity} {self.unit.code}"

    # =====================
    # BASIC VALIDATION
    # =====================

    def clean(self):
        """Basic line validation - tolerant to None quantity"""
        super().clean()


        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be greater than zero')
            })

        # Product-unit compatibility validation
        if self.product and self.unit:
            # Check if Product has unit compatibility method
            if hasattr(self.product, 'is_unit_compatible'):
                if not self.product.is_unit_compatible(self.unit):
                    raise ValidationError({
                        'unit': _(f'Unit {self.unit.code} is not compatible with product {self.product.code}')
                    })
            # Basic fallback: check if unit matches product's base_unit
            elif hasattr(self.product, 'base_unit') and self.product.base_unit:
                if self.unit != self.product.base_unit:
                    # Warning but not error - allow different units for flexibility
                    logger.warning(
                        f"Unit {self.unit.code} differs from product {self.product.code} base unit {self.product.base_unit.code}")

    def save(self, *args, **kwargs):
        """Enhanced save with auto-line numbering"""
        # Auto-generate line number if not set
        if not self.line_number and hasattr(self, 'document'):
            document = getattr(self, 'document', None)
            if document and hasattr(document, 'lines'):
                max_line = document.lines.aggregate(
                    max_line=models.Max('line_number')
                )['max_line'] or 0
                self.line_number = max_line + 1

        # Auto-set unit from product if not provided
        if self.product and not self.unit:
            base_unit = getattr(self.product, 'base_unit', None)
            if base_unit:
                self.unit = base_unit

        super().save(*args, **kwargs)

    # =====================
    # HELPER METHODS
    # =====================

    def get_product_info(self):
        """Get extended product information"""
        if not self.product:
            return {}

        return {
            'code': getattr(self.product, 'code', ''),
            'name': getattr(self.product, 'name', ''),
            'category': getattr(self.product.category, 'name', None) if hasattr(self.product,
                                                                                'category') and self.product.category else None,
            'base_unit': getattr(self.product.base_unit, 'code', None) if hasattr(self.product,
                                                                                  'base_unit') and self.product.base_unit else None,
        }

    def get_unit_info(self):
        """Get unit information"""
        if not self.unit:
            return {}

        return {
            'code': getattr(self.unit, 'code', ''),
            'name': getattr(self.unit, 'name', ''),
            'symbol': getattr(self.unit, 'symbol', ''),
            'unit_type': getattr(self.unit, 'unit_type', ''),
            'allow_decimals': getattr(self.unit, 'allow_decimals', True),
            'decimal_places': getattr(self.unit, 'decimal_places', 3),
        }