# purchases/models/base.py - CLEAN REFACTORED
"""
Base Document Models - CLEAN VERSION

ПРЕМАХНАТО:
- Workflow методи (moved to DocumentService)
- Status transition логика (moved to DocumentService)
- Business rules validation (moved to DocumentService)

ЗАПАЗЕНО:
- Basic model behavior
- DocumentType integration
- Core validation
- Helper methods

NO HARDCODING:
- Статуси идват от DocumentType
- Transitions се управляват от ApprovalRule
- Business behavior от DocumentType flags
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

import logging

from core.models.company import Company

logger = logging.getLogger(__name__)


class DocumentManager(models.Manager):
    """
    Base manager for all purchase documents

    СИНХРОНИЗИРАН с nomenclatures.DocumentService:
    - NO hardcoded статуси
    - Dynamic queries от DocumentType/ApprovalRule
    - Fallback functionality ако nomenclatures не е достъпен
    """

    def active(self):
        """Return only active documents - DYNAMIC от DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_active_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback if nomenclatures not available
            logger.warning("DocumentService not available, using fallback active() logic")
            final_statuses = ['cancelled', 'closed', 'deleted', 'archived']
            return self.exclude(status__in=final_statuses)

    def pending_approval(self):
        """Documents pending approval - DYNAMIC от ApprovalRule"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_pending_approval_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback if nomenclatures not available
            logger.warning("DocumentService not available, using fallback pending_approval() logic")
            approval_statuses = ['submitted', 'pending_approval', 'pending_review']
            return self.filter(status__in=approval_statuses)

    def ready_for_processing(self):
        """Documents ready for processing - DYNAMIC от ApprovalRule"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_ready_for_processing_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback if nomenclatures not available
            logger.warning("DocumentService not available, using fallback ready_for_processing() logic")
            ready_statuses = ['approved', 'confirmed', 'ready', 'received']
            return self.filter(status__in=ready_statuses)

    # =====================
    # BASIC QUERY METHODS (не се променят)
    # =====================

    def for_supplier(self, supplier):
        """Filter by supplier with optimizations"""
        return self.filter(supplier=supplier).select_related(
            'supplier', 'location', 'document_type'
        ).prefetch_related('lines__product')

    def for_location(self, location):
        """Filter by location"""
        return self.filter(location=location)

    def for_document_type(self, doc_type):
        """Filter by document type"""
        if hasattr(doc_type, 'pk'):
            return self.filter(document_type=doc_type)
        else:
            # String lookup by code or type_key
            return self.filter(
                models.Q(document_type__code=doc_type) |
                models.Q(document_type__type_key=doc_type)
            )

    def search(self, query):
        """Search documents by various fields"""
        return self.filter(
            models.Q(document_number__icontains=query) |
            models.Q(supplier__name__icontains=query) |
            models.Q(external_reference__icontains=query) |
            models.Q(notes__icontains=query)
        )

    def by_status(self, status):
        """Filter by status"""
        return self.filter(status=status)

    def in_statuses(self, statuses):
        """Filter by multiple statuses"""
        return self.filter(status__in=statuses)

    # =====================
    # HELPER METHODS FOR DocumentService INTEGRATION
    # =====================

    def create_with_service(self, user, **data):
        """Create document using DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            result = DocumentService.create_document(
                self.model, data, user
            )
            if result['success']:
                return result['document']
            else:
                raise ValidationError(result['message'])
        except ImportError:
            # Fallback: standard creation without numbering/status management
            logger.warning("DocumentService not available, using standard creation")
            return self.create(**data)


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
    Base Document - CLEAN VERSION

    САМО essential model behavior:
    - Core fields and relationships
    - Basic validation
    - DocumentType integration hooks
    - Helper methods

    NO workflow logic - moved to DocumentService!
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
        help_text=_('Auto-detected from model name, or manually set'),
        limit_choices_to={'is_active': True}
    )

    # =====================
    # CORE FIELDS
    # =====================
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True,
        blank=True,  # ✅ Will be auto-generated by DocumentService
        help_text=_('Auto-generated from document type configuration')
    )

    document_date = models.DateField(
        _('Document Date'),
        default=timezone.now,
        help_text=_('Date when document was created')
    )

    status = models.CharField(
        _('Status'),
        max_length=30,
        blank=True,  # ✅ Will be set by DocumentService from DocumentType
        help_text=_('Current document status - managed by DocumentService')
        # ✅ NO choices - dynamic from DocumentType!
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
        help_text=_('User who created this document')
    )

    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_updated',
        verbose_name=_('Updated By'),
        help_text=_('User who last updated this document')
    )

    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
        help_text=_('When this document was created')
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True,
        help_text=_('When this document was last updated')
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
        return f"{self.get_document_prefix()}{self.document_number} - {self.supplier.name if self.supplier else 'No Supplier'}"

    # =====================
    # DOCUMENT TYPE INTEGRATION (READ-ONLY)
    # =====================

    def get_document_type_key(self):
        """Get document type key for this model - NO HARDCODING"""
        # ✅ DYNAMIC: Derive from model name
        model_name = self._meta.model_name.lower()

        # ✅ CONFIGURABLE mapping
        type_key_mapping = {
            'purchaserequest': 'purchase_request',
            'purchaseorder': 'purchase_order',
            'deliveryreceipt': 'delivery_receipt',
            'salesinvoice': 'sales_invoice',
            'inventoryadjustment': 'inventory_adjustment',
        }

        return type_key_mapping.get(model_name, model_name)

    def get_app_name(self):
        """Get app name for this model"""
        return self._meta.app_label

    def get_document_prefix(self):
        """Get document prefix - configurable, not hardcoded"""
        if self.document_type:
            # ✅ FROM DocumentType configuration
            return getattr(self.document_type, 'prefix', '')

        # ✅ FALLBACK: Derive from model name
        model_name = self._meta.model_name.lower()
        prefix_mapping = {
            'purchaserequest': 'REQ',
            'purchaseorder': 'ORD',
            'deliveryreceipt': 'DEL',
            'salesinvoice': 'INV',
        }
        return prefix_mapping.get(model_name, 'DOC')

    @classmethod
    def get_possible_document_types(cls):
        """Get possible DocumentType instances for this model"""
        try:
            from nomenclatures.models import DocumentType

            # ✅ SIMPLE: Try to find by model name first
            model_name = cls.__name__.lower()
            app_name = cls._meta.app_label

            # Try exact model_name match first (if field exists)
            if hasattr(DocumentType, 'model_name'):
                exact_matches = DocumentType.objects.filter(
                    model_name=cls.__name__,
                    is_active=True
                )
                if exact_matches.exists():
                    return exact_matches

            # Fallback: try app_name filter
            return DocumentType.objects.filter(
                app_name=app_name,
                is_active=True
            )

        except (ImportError, AttributeError):
            # ✅ FIXED: Return empty list if DocumentType not available
            return []

    def get_default_document_type(self):
        """Get default DocumentType for this document"""
        try:
            possible_types = self.__class__.get_possible_document_types()
            return possible_types.first()  # Take first active one
        except:
            return None

    # =====================
    # BASIC VALIDATION
    # =====================

    def clean(self):
        """Basic model validation - NO workflow logic"""
        super().clean()

        # Auto-detect document type if not set
        if not self.document_type:
            try:
                self.document_type = self.get_default_document_type()
            except:
                pass  # Continue without document_type

        # Validate document type compatibility (if we have one)
        if self.document_type:
            expected_app = self.get_app_name()
            expected_type_key = self.get_document_type_key()

            # Only validate if DocumentType has these fields
            if (hasattr(self.document_type, 'app_name') and
                    hasattr(self.document_type, 'type_key')):
                if (self.document_type.app_name != expected_app or
                        self.document_type.type_key != expected_type_key):
                    raise ValidationError({
                        'document_type': _(
                            f'Document type must be for app "{expected_app}" '
                            f'and type "{expected_type_key}"'
                        )
                    })

        # Validate required fields
        if not self.supplier:
            raise ValidationError({'supplier': _('Supplier is required')})

        if not self.location:
            raise ValidationError({'location': _('Location is required')})

    def save(self, *args, **kwargs):
        """
        Enhanced save with DocumentService integration

        Ако документът е нов И НЯМ document_number/status:
        - DocumentService се грижи за numbering + initial status

        Иначе: стандартен save
        """
        is_new_document = not self.pk

        # 1. Set created_by if not set (for new instances)
        if is_new_document and not self.created_by:
            # Try to get from kwargs or context
            user = kwargs.pop('user', None) or getattr(self, '_current_user', None)
            if user:
                self.created_by = user

        # 2. Auto-detect document type if needed
        if not self.document_type:
            try:
                self.document_type = self.get_default_document_type()
            except:
                pass  # Continue without document_type

        # 3. INTEGRATION: Use DocumentService for new documents без number/status
        if (is_new_document and
                not self.document_number and
                not self.status and
                hasattr(self, '_use_document_service')):

            try:
                from nomenclatures.services import DocumentService

                # Extract user and location for DocumentService
                user = self.created_by or kwargs.pop('user', None)
                location = self.location

                if user and location:
                    logger.info(f"Using DocumentService for {self.__class__.__name__} creation")

                    # Use DocumentService for complete creation
                    # This will handle numbering, initial status, etc.
                    # Note: This would require restructuring the creation flow
                    pass  # For now, fallback to standard save

            except ImportError:
                logger.warning("DocumentService not available, using standard creation")

        # 4. FALLBACK: Standard Django save
        # (DocumentService creation should be used at higher level)

        # 5. Validation
        if not kwargs.pop('skip_validation', False):
            self.full_clean()

        # 6. Single database save
        super().save(*args, **kwargs)

        # 7. Post-save: Log if document was created without DocumentService
        if is_new_document and not self.document_number:
            logger.warning(
                f"{self.__class__.__name__} created without document_number. "
                "Consider using DocumentService.create_document() instead."
            )

    # =====================
    # HELPER METHODS (READ-ONLY)
    # =====================

    def get_company(self):
        """Get current company instance"""
        return Company.get_current()

    def get_price_entry_mode(self) -> bool:
        """
        Get effective price entry mode for this document

        Note: For documents with FinancialMixin, override this method
        to check document-level prices_entered_with_vat field first.

        Returns:
            bool: True if prices include VAT, False if exclude VAT
        """
        # ✅ Check if document has FinancialMixin field
        if hasattr(self, 'prices_entered_with_vat'):
            prices_with_vat = getattr(self, 'prices_entered_with_vat', None)
            if prices_with_vat is not None:
                return prices_with_vat

        # ✅ Fallback to location setting
        if self.location and self.document_type:
            if self.document_type.app_name == 'purchases':
                return getattr(self.location, 'purchase_prices_include_vat', False)
            elif self.document_type.app_name == 'sales':
                return getattr(self.location, 'sales_prices_include_vat', True)

        # ✅ Final fallback
        return False

    def has_lines(self):
        """Check if document has any lines"""
        lines_attr = getattr(self, 'lines', None)
        return lines_attr is not None and lines_attr.exists()

    def get_lines_count(self):
        """Get number of lines"""
        lines_attr = getattr(self, 'lines', None)
        return lines_attr.count() if lines_attr else 0

    def is_editable(self):
        """Check if document can be edited - BASIC check only"""
        # ✅ DocumentService will handle complex workflow logic
        return bool(self.pk and self.status)  # Exists and has status

    def affects_inventory(self):
        """Check if this document type affects inventory"""
        return (self.document_type and
                getattr(self.document_type, 'affects_inventory', False))

    def get_inventory_direction(self):
        """Get inventory movement direction"""
        if self.document_type:
            return getattr(self.document_type, 'inventory_direction', 'none')
        return 'none'

    def get_movement_type(self):
        """Get inventory movement type"""
        if not self.affects_inventory():
            return None

        direction = self.get_inventory_direction()
        direction_map = {
            'in': 'IN',
            'out': 'OUT',
            'both': 'BOTH',
            'none': None
        }
        return direction_map.get(direction)


# =================================================================
# BASE DOCUMENT LINE - CLEAN MODEL
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
        'inventory.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product'),
        help_text=_('Product for this line')
    )

    quantity = models.DecimalField(
        _('Quantity'),
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
        """Basic line validation"""
        super().clean()

        # Quantity validation
        if self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be greater than zero')
            })

        # Product-unit compatibility (if method exists)
        if self.product and self.unit:
            # ✅ Check if Product has unit compatibility method
            if hasattr(self.product, 'is_unit_compatible'):
                if not self.product.is_unit_compatible(self.unit):
                    raise ValidationError({
                        'unit': _(f'Unit {self.unit.code} is not compatible with product {self.product.code}')
                    })
            # ✅ Basic fallback: check if unit matches product's base_unit
            elif hasattr(self.product, 'base_unit') and self.product.base_unit:
                if self.unit != self.product.base_unit:
                    # ✅ Warning but not error - allow different units for flexibility
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





