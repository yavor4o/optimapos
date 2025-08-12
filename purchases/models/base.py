# purchases/models/base.py - CLEAN REFACTORED
import warnings

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

import logging

from core.models.company import Company
from products.models import Product

logger = logging.getLogger(__name__)


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
# BASE DOCUMENT - CLEAN MODEL
# =================================================================

class BaseDocument(models.Model):
    """
    Base Document Model - PURE DATA MODEL

    ✅ САМО data fields и validation
    ✅ Read-only helper методи
    ❌ БЕЗ business logic
    ❌ БЕЗ workflow логика
    ❌ БЕЗ document number generation

    Всички документи ТРЯБВА да се създават през DocumentService!
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
        related_name='%(app_label)s_%(class)s_created',
        verbose_name=_('Created By'),
        null=True,  # Може да е null за стари записи
        blank=True,
        help_text=_('Set by DocumentService on creation')
    )

    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_updated',
        verbose_name=_('Updated By'),
        help_text=_('Set automatically on update')
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
    # MANAGERS
    # =====================
    objects = DocumentManager()

    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['supplier', '-document_date']),
            models.Index(fields=['location', 'status']),
            models.Index(fields=['document_type', 'status']),
        ]

    def __str__(self):
        if self.document_number:
            prefix = self.get_document_prefix()
            return f"{prefix}{self.document_number} - {self.supplier.name}"
        return f"New {self.__class__.__name__} - {self.supplier.name if self.supplier else 'No Supplier'}"

    # =====================
    # MINIMAL SAVE & CLEAN
    # =====================

    def clean(self):
        """
        САМО data validation - БЕЗ business logic
        DocumentService handles all business rules
        """
        super().clean()

        # Required fields validation ONLY
        if not self.supplier:
            raise ValidationError({'supplier': _('Supplier is required')})

        if not self.location:
            raise ValidationError({'location': _('Location is required')})

        # ❌ НЕ правим document type detection - DocumentService го прави
        # ❌ НЕ проверяваме статуси - DocumentService го прави
        # ❌ НЕ валидираме workflow - DocumentService го прави

    def save(self, *args, **kwargs):
        """
        MINIMAL save - БЕЗ business logic

        За нови документи: ТРЯБВА да се използва DocumentService.create_document()
        За updates: OK да се използва save()
        """
        is_new = not self.pk
        skip_validation = kwargs.pop('skip_validation', False)

        # ПРОВЕРКА: Нови документи трябва да идват от DocumentService
        if is_new:
            if not self.document_number:
                # В development - warning
                warnings.warn(
                    f"\n"
                    f"{'=' * 60}\n"
                    f"DEPRECATION WARNING:\n"
                    f"{self.__class__.__name__} created without DocumentService!\n"
                    f"This will be an ERROR in production.\n"
                    f"Use: DocumentService.create_document() instead\n"
                    f"{'=' * 60}",
                    DeprecationWarning,
                    stacklevel=2
                )

                # В production може да хвърляме грешка:
                # from django.conf import settings
                # if not settings.DEBUG:
                #     raise ValidationError(
                #         "Documents must be created via DocumentService.create_document()"
                #     )

            if not self.status:
                logger.warning(
                    f"{self.__class__.__name__} created without initial status. "
                    f"DocumentService should set this."
                )

        # Базова валидация (ако не е skip-ната)
        if not skip_validation:
            self.full_clean()

        # Стандартен Django save - БЕЗ допълнителна логика
        super().save(*args, **kwargs)

    # =====================
    # READ-ONLY HELPERS (без промени)
    # =====================

    def get_price_entry_mode(self) -> bool:
        """
        Get effective price entry mode for this document

        Йерархия на проверките:
        1. Document level setting (prices_entered_with_vat)
        2. Location level setting (purchase/sales_prices_include_vat)
        3. System defaults (purchases=False, sales=True)

        Returns:
            bool: True if prices include VAT, False if exclude VAT
        """
        # 1. Document level - най-висок приоритет
        if hasattr(self, 'prices_entered_with_vat'):
            if self.prices_entered_with_vat is not None:
                return self.prices_entered_with_vat

        # 2. Location level - втори приоритет
        if self.location:
            app_label = self._meta.app_label

            if app_label == 'purchases':
                # За purchases проверяваме purchase_prices_include_vat
                return getattr(self.location, 'purchase_prices_include_vat', False)

            elif app_label == 'sales':
                # За sales проверяваме sales_prices_include_vat
                return getattr(self.location, 'sales_prices_include_vat', True)

        # 3. System defaults - последен fallback
        if self._meta.app_label == 'purchases':
            return False  # Purchase prices обикновено БЕЗ ДДС
        elif self._meta.app_label == 'sales':
            return True  # Sales prices обикновено С ДДС
        else:
            return False  # Default за други apps

    def get_document_prefix(self):
        """Get document prefix from DocumentType or fallback"""
        if self.document_type and hasattr(self.document_type, 'prefix'):
            return self.document_type.prefix

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
            'deliveryreceipt': 'delivery_receipt',
        }
        return type_key_map.get(model_name, model_name)

    def get_app_name(self):
        """Get app name for this model"""
        return self._meta.app_label

    # =====================
    # PROPERTIES (read-only)
    # =====================

    @property
    def is_draft(self):
        """Check if document is in draft status"""
        return self.status in ['draft', 'new', 'pending']

    @property
    def is_final(self):
        """Check if document is in final status"""
        return self.status in ['completed', 'closed', 'cancelled', 'archived']

    @property
    def is_active(self):
        """Check if document is active"""
        return self.status not in ['cancelled', 'deleted', 'archived']

    @property
    def can_edit(self):
        """Basic edit check - DocumentService има пълната логика"""
        return self.is_draft and not self.is_final

    def has_lines(self):
        """Check if document has any lines"""
        lines = getattr(self, 'lines', None)
        return lines is not None and lines.exists()

    def get_lines_count(self):
        """Get number of lines"""
        lines = getattr(self, 'lines', None)
        return lines.count() if lines else 0

    def affects_inventory(self):
        """Check if this document type affects inventory"""
        if self.document_type:
            return getattr(self.document_type, 'affects_inventory', False)
        return False

    def get_inventory_direction(self):
        """Get inventory movement direction from DocumentType"""
        if self.document_type:
            return getattr(self.document_type, 'inventory_direction', 'none')
        return 'none'

    # =====================
    # DELEGATE TO SERVICES (не правим логика тук!)
    # =====================

    def get_available_actions(self, user):
        """
        Get available workflow actions for this document
        Delegates to DocumentService
        """
        from nomenclatures.services import DocumentService
        return DocumentService.get_available_actions(self, user)



    def get_workflow_history(self):
        """
        Get workflow history
        Delegates to ApprovalService
        """
        try:
            from nomenclatures.services import ApprovalService
            return ApprovalService.get_approval_history(self)  # Правилният метод!
        except ImportError:
            return []

    def get_next_statuses(self, user=None):
        """
        Get possible next statuses
        Delegates to DocumentService
        """
        from nomenclatures.services import DocumentService
        actions = DocumentService.get_available_actions(self, user)
        return [a['status'] for a in actions if a.get('can_perform', False)]

    # =====================
    # DEPRECATED METHODS (за backward compatibility)
    # =====================

    @classmethod
    def get_possible_document_types(cls):
        """
        DEPRECATED: DocumentService handles this
        Kept for backward compatibility
        """
        warnings.warn(
            "get_possible_document_types() is deprecated. "
            "DocumentService handles document type detection.",
            DeprecationWarning
        )

        try:
            from nomenclatures.models import DocumentType
            return DocumentType.objects.filter(
                app_name=cls._meta.app_label,
                is_active=True
            )
        except ImportError:
            return []

    def get_default_document_type(self):
        """
        DEPRECATED: DocumentService handles this
        """
        warnings.warn(
            "get_default_document_type() is deprecated. "
            "Use DocumentService for document creation.",
            DeprecationWarning
        )
        return None


# =================================================================
# BASE DOCUMENT LINE - CLEAN MODEL
# =================================================================

class BaseDocumentLine(models.Model):
    """
    Base Document Line - CLEAN VERSION WITHOUT quantity field

    ❌ МАХАМЕ generic quantity поле
    ✅ Всеки наследник си дефинира специфични quantity полета
    ✅ Добавяме abstract метод get_quantity_for_display()
    """

    # =====================
    # CORE FIELDS (БЕЗ quantity!)
    # =====================
    line_number = models.PositiveIntegerField(
        _('Line Number'),
        default=0,
        help_text=_('Line number within document (auto-generated)')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product'),
        help_text=_('Product for this line')
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
    # AUDIT FIELDS
    # =====================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        doc_ref = self.get_document_reference()
        qty = self.get_quantity_for_display()
        return f"{doc_ref} Line {self.line_number}: {self.product.code} x {qty} {self.unit.code}"

    # =====================
    # ABSTRACT METHODS - MUST BE IMPLEMENTED
    # =====================

    def get_quantity_for_display(self):
        """
        ABSTRACT: Return primary quantity for display

        Subclasses MUST implement:
        - PurchaseRequestLine: return self.requested_quantity
        - PurchaseOrderLine: return self.confirmed_quantity or self.ordered_quantity
        - DeliveryLine: return self.received_quantity
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_quantity_for_display()"
        )

    def get_document(self):
        """
        Get parent document
        Subclasses should have 'document' FK
        """
        if hasattr(self, 'document'):
            return self.document

        # Fallback - търси FK към document
        for field in self._meta.fields:
            if field.name.endswith('document') and field.many_to_one:
                return getattr(self, field.name, None)

        return None

    def get_document_reference(self):
        """Get document reference for display"""
        doc = self.get_document()
        if doc and hasattr(doc, 'document_number'):
            return doc.document_number
        return "No Document"

    # =====================
    # AUTO-NUMBERING
    # =====================

    def save(self, *args, **kwargs):
        """Auto-generate line number if needed"""

        # Auto-generate line number за нови записи
        if not self.pk and not self.line_number:
            self.line_number = self._get_next_line_number()

        # Auto-set unit from product ако липсва
        if self.product and not self.unit:
            if hasattr(self.product, 'base_unit'):
                self.unit = self.product.base_unit

        # Validation
        if not kwargs.pop('skip_validation', False):
            self.full_clean()

        super().save(*args, **kwargs)

    def _get_next_line_number(self):
        """Get next line number for document"""
        doc = self.get_document()
        if not doc or not hasattr(doc, 'lines'):
            return 1

        max_num = doc.lines.aggregate(
            max_line=models.Max('line_number')
        )['max_line'] or 0

        return max_num + 1

    # =====================
    # VALIDATION
    # =====================

    def clean(self):
        """Base validation - subclasses add quantity validation"""
        super().clean()

        # Product-unit compatibility check
        if self.product and self.unit:
            self._validate_unit_compatibility()

    def _validate_unit_compatibility(self):
        """Check if unit is compatible with product"""

        # Check via product method if available
        if hasattr(self.product, 'is_unit_compatible'):
            if not self.product.is_unit_compatible(self.unit):
                raise ValidationError({
                    'unit': _(f'Unit {self.unit.code} is not compatible with {self.product.code}')
                })

        # Check base unit
        elif hasattr(self.product, 'base_unit') and self.product.base_unit:
            if self.unit != self.product.base_unit:
                # Just log warning, allow flexibility
                logger.info(
                    f"Line {self.pk}: Unit {self.unit.code} differs from "
                    f"product {self.product.code} base unit {self.product.base_unit.code}"
                )

    # =====================
    # HELPER METHODS
    # =====================

    def get_product_info(self):
        """Get extended product information"""
        if not self.product:
            return {}

        return {
            'code': self.product.code,
            'name': self.product.name,
            'group': getattr(self.product.product_group, 'name', None)
            if hasattr(self.product, 'product_group') else None,
            'base_unit': self.product.base_unit.code
            if hasattr(self.product, 'base_unit') else None,
        }

    def get_unit_info(self):
        """Get unit information"""
        if not self.unit:
            return {}

        return {
            'code': self.unit.code,
            'name': self.unit.name,
            'symbol': getattr(self.unit, 'symbol', self.unit.code),
            'decimals': getattr(self.unit, 'decimal_places', 3),
        }

    def duplicate(self, exclude_fields=None):
        """
        Create a copy of this line
        Useful for templates or copying between documents
        """
        exclude = exclude_fields or ['id', 'pk', 'line_number', 'document']

        # Get all field values except excluded
        field_values = {}
        for field in self._meta.fields:
            if field.name not in exclude:
                field_values[field.name] = getattr(self, field.name)

        # Create new instance
        return self.__class__(**field_values)

class FinancialMixin(models.Model):
    """
    Enhanced Financial mixin for documents with financial data

    FIXED: Correct VAT calculation logic
    RENAMED: grand_total → total
    ADDED: prices_entered_with_vat field
    """

    # PRICE ENTRY CONTROL
    prices_entered_with_vat = models.BooleanField(
        _('Prices Entered With VAT'),
        null=True,
        blank=True,
        help_text=_('Override location setting. null = use location default, True/False = override for this document')
    )

    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Sum of all net amounts (excluding VAT)')  # ENHANCED help text
    )

    discount_total = models.DecimalField(
        _('Total Discount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total discount amount')
    )

    vat_total = models.DecimalField(
        _('VAT Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total VAT amount')
    )

    # RENAMED: grand_total → total
    total = models.DecimalField(
        _('Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Final total including VAT')
    )

    class Meta:
        abstract = True

    def recalculate_totals(self):
        """
        ✅ SAFE: Skip if object has no PK yet
        """
        if not self.pk or not hasattr(self, 'lines'):
            self.subtotal = Decimal('0.00')
            self.discount_total = Decimal('0.00')
            self.vat_total = Decimal('0.00')
            self.total = Decimal('0.00')
            return

        lines = self.lines.all()

        # Calculate totals from lines
        self.subtotal = sum(getattr(line, 'net_amount', 0) for line in lines)
        self.discount_total = sum(getattr(line, 'discount_amount', 0) for line in lines)
        self.vat_total = sum(getattr(line, 'vat_amount', 0) for line in lines)
        self.total = self.subtotal + self.vat_total

    def refresh_totals(self):
        """
        ✅ ПРОФЕСИОНАЛНО: Explicit method за manual totals refresh

        Use when you want to recalculate AND save in one operation
        """
        self.recalculate_totals()  # Calculate
        self.save(update_fields=['subtotal', 'discount_total', 'vat_total', 'total'])

    def clean(self):
        """Enhanced financial validation"""
        super().clean()

        # Basic financial validation
        if self.vat_total < 0:
            raise ValidationError({
                'vat_total': _('VAT total cannot be negative')
            })

        # Logical consistency validation
        if self.total < self.subtotal:
            raise ValidationError({
                'total': _('Total cannot be less than subtotal')
            })

    def get_financial_summary(self) -> dict:
        """Get financial summary for this document"""
        return {
            'subtotal': self.subtotal,
            'discount_total': self.discount_total,
            'vat_total': self.vat_total,
            'total': self.total,
            'lines_count': getattr(self, 'lines', None).count() if hasattr(self, 'lines') else 0
        }


class PaymentMixin(models.Model):
    """
    Mixin за документи с плащания

    Използва се главно от DeliveryReceipt и понякога от PurchaseOrder.
    НЕ се използва от PurchaseRequest.
    """

    is_paid = models.BooleanField(
        _('Is Paid'),
        default=False,
        help_text=_('Whether this document has been paid')
    )

    payment_date = models.DateField(
        _('Payment Date'),
        null=True,
        blank=True,
        help_text=_('When payment was made')
    )

    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        blank=True,
        help_text=_('How payment was made')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Payment validation enhanced with DocumentType"""
        super().clean()

        # Payment validation
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()

        # DocumentType payment validation
        if hasattr(self, 'document_type') and self.document_type:
            if self.document_type.requires_payment and not self.is_paid:
                if self.status in ['completed', 'processed']:
                    raise ValidationError({
                        'is_paid': _('Payment is required for this document type')
                    })


class DeliveryMixin(models.Model):
    """
    Mixin за документи с delivery информация

    Използва се от DeliveryReceipt.
    НЕ се използва от PurchaseRequest или PurchaseOrder.
    """

    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were delivered')
    )

    delivery_instructions = models.TextField(
        _('Delivery Instructions'),
        blank=True,
        help_text=_('Special instructions for delivery')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Delivery validation"""
        super().clean()
        # Delivery date може да е във всякакво време - това е реалната дата


class FinancialLineMixin(models.Model):
    """
    Enhanced Financial line mixin with VAT-aware price processing

    NEW FIELDS:
    - entered_price: Price as entered by user
    - net_amount: Amount excluding VAT

    RENAMED:
    - line_total → gross_amount: Amount including VAT

    ENHANCED:
    - Smart VAT processing based on company/document settings
    """

    # NEW: Price as entered by user
    entered_price = models.DecimalField(
        _('Entered Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price as entered by user (before VAT processing)')
    )

    # Unit price (ALWAYS excluding VAT in database)
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price per unit ALWAYS excluding VAT')
    )

    # Discount fields
    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Discount percentage')
    )

    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Calculated discount amount')
    )

    # VAT fields
    vat_rate = models.DecimalField(
        _('VAT Rate %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('VAT rate percentage from product tax group')
    )

    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Calculated VAT amount')
    )

    # NEW: Net amount (quantity × unit_price - discount, excluding VAT)
    net_amount = models.DecimalField(
        _('Net Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount excluding VAT (after discount)')
    )

    # RENAMED: line_total → gross_amount
    gross_amount = models.DecimalField(
        _('Gross Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount including VAT')
    )

    class Meta:
        abstract = True




    def _process_entered_price(self):
        """
        Process entered price → unit price (VAT-aware)

        FIXED: Handle zero entered_price with smart fallback logic
        """
        try:
            from purchases.services.vat_service import SmartVATService

            # =====================
            # SMART FALLBACK for zero entered_price
            # =====================
            effective_entered_price = self.entered_price

            if not self.entered_price or self.entered_price == 0:
                # Try to get fallback price using smart logic
                fallback_price = self._get_fallback_price()

                if fallback_price and fallback_price > 0:
                    effective_entered_price = fallback_price
                    # Optional: Log that we used fallback
                    print(f"💡 Using fallback price {fallback_price} for {self.product.code}")
                else:
                    # No fallback available - set minimal values and return
                    self.unit_price = Decimal('0.00')
                    self.vat_rate = self._get_default_vat_rate()
                    return

            # =====================
            # NORMAL VAT PROCESSING
            # =====================
            result = SmartVATService.calculate_line_vat(
                self, effective_entered_price, self.document
            )

            # Apply results
            self.unit_price = result['unit_price']
            self.vat_rate = result['vat_rate']
            # Note: vat_amount and gross_amount calculated in calculate_totals()

            # Update entered_price if we used fallback
            if effective_entered_price != self.entered_price:
                self.entered_price = effective_entered_price

        except ImportError:
            # Fallback if SmartVATService not available
            if self.entered_price:
                self.unit_price = self.entered_price
            else:
                self.unit_price = self._get_fallback_price() or Decimal('0.00')
            self.vat_rate = self._get_default_vat_rate()

    def _get_fallback_price(self) -> Decimal:
        """
        Get fallback price when entered_price is zero

        IMPORTANT: Adjusts for VAT entry mode using existing system methods!
        """
        if not self.product:
            return Decimal('0.00')

        # Get base price (always excluding VAT from database)
        base_price_excl_vat = None

        # PRIORITY 1: Last purchase cost
        if hasattr(self.product, 'last_purchase_cost') and self.product.last_purchase_cost:
            base_price_excl_vat = self.product.last_purchase_cost

        # PRIORITY 2: Current average cost
        elif hasattr(self.product, 'current_avg_cost') and self.product.current_avg_cost:
            base_price_excl_vat = self.product.current_avg_cost

        # PRIORITY 3: Source order line price (for delivery lines)
        elif hasattr(self, 'source_order_line') and self.source_order_line:
            if hasattr(self.source_order_line, 'unit_price') and self.source_order_line.unit_price:
                base_price_excl_vat = self.source_order_line.unit_price

        # PRIORITY 4: Try product's get_estimated_purchase_price if available
        elif hasattr(self.product, 'get_estimated_purchase_price'):
            try:
                estimated = self.product.get_estimated_purchase_price(self.unit)
                if estimated and estimated > 0:
                    base_price_excl_vat = estimated
            except:
                pass

        if not base_price_excl_vat or base_price_excl_vat <= 0:
            return Decimal('0.00')

        # =====================
        # ADJUST FOR VAT ENTRY MODE using existing system
        # =====================
        prices_entered_with_vat = self.document.get_price_entry_mode()

        if prices_entered_with_vat:
            # User enters prices INCLUDING VAT, so convert database price (excl VAT) → incl VAT
            from purchases.services.vat_service import SmartVATService
            vat_rate = SmartVATService._get_product_vat_rate(self)
            fallback_price_incl_vat = base_price_excl_vat * (1 + vat_rate / 100)
            return fallback_price_incl_vat
        else:
            # User enters prices EXCLUDING VAT, so use database price directly
            return base_price_excl_vat

    def _get_default_vat_rate(self) -> Decimal:
        """Get default VAT rate using existing system method"""
        from purchases.services.vat_service import SmartVATService
        return SmartVATService._get_product_vat_rate(self)

    def calculate_totals(self):
        """
        Calculate all line totals with enhanced VAT logic
        """
        # Get quantity using polymorphic method
        quantity = self.get_quantity() if hasattr(self, 'get_quantity') else Decimal('0')

        if quantity and self.unit_price:
            # Calculate base amounts (excluding VAT)
            gross_amount_excl_vat = quantity * self.unit_price
            self.discount_amount = gross_amount_excl_vat * (self.discount_percent / 100)
            self.net_amount = gross_amount_excl_vat - self.discount_amount

            # Calculate VAT
            self.vat_amount = self.net_amount * (self.vat_rate / 100)

            # Calculate gross amount (including VAT)
            self.gross_amount = self.net_amount + self.vat_amount
        else:
            # Zero out calculations if no quantity or price
            self.discount_amount = Decimal('0.00')
            self.net_amount = Decimal('0.00')
            self.vat_amount = Decimal('0.00')
            self.gross_amount = Decimal('0.00')

    def save(self, *args, **kwargs):
        """
        Enhanced save with VAT-aware price processing
        """
        # Process entered price → unit price (VAT-aware)
        self._process_entered_price()

        # Calculate all totals
        self.calculate_totals()

        super().save(*args, **kwargs)

    def get_effective_cost(self) -> Decimal:
        """
        Get effective cost for inventory calculations

        Returns:
            Decimal: Cost amount according to company VAT status
        """
        if not hasattr(self, 'document'):
            return self.unit_price

        company = self.document.get_company()
        if company and company.is_vat_applicable():
            # VAT registered company → use net amount (excluding VAT)
            return self.unit_price
        else:
            # Non-VAT company → use gross amount (real cost including VAT)
            quantity = self.get_quantity() if hasattr(self, 'get_quantity') else Decimal('1')
            return self.gross_amount / quantity if quantity else self.gross_amount

    def get_vat_breakdown(self) -> dict:
        """Get detailed VAT breakdown for this line"""
        return {
            'entered_price': self.entered_price,
            'unit_price': self.unit_price,
            'quantity': self.get_quantity() if hasattr(self, 'get_quantity') else None,
            'net_amount': self.net_amount,
            'vat_rate': self.vat_rate,
            'vat_amount': self.vat_amount,
            'gross_amount': self.gross_amount,
            'effective_cost': self.get_effective_cost()
        }





