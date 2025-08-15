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

    def save(self, *args, **kwargs):
        # Автоматично номериране
        if not self.pk and not self.document_number:
            from nomenclatures.services.document_service import DocumentService
            self.document_number = DocumentService.generate_number_for(self)

        super().save(*args, **kwargs)

    # =====================
    # READ-ONLY HELPERS (без промени)
    # =====================

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
    def is_initial(self):
        """Check if document is in initial status - CONFIGURATION DRIVEN"""
        try:
            from nomenclatures.models import DocumentTypeStatus
            config = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                status__code=self.status,
                is_initial=True,
                is_active=True
            ).first()
            return bool(config)
        except:
            # Fallback за compatibility
            return self.status in ['draft', 'new']

    @property
    def is_final(self):
        """Check if document is in final status - CONFIGURATION DRIVEN"""
        try:
            from nomenclatures.models import DocumentTypeStatus
            config = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                status__code=self.status,
                is_final=True,
                is_active=True
            ).first()
            return bool(config)
        except:
            # Fallback за compatibility
            return self.status in ['completed', 'closed', 'cancelled', 'archived']

    @property
    def is_cancellation(self):
        """Check if document is in cancellation status - CONFIGURATION DRIVEN"""
        try:
            from nomenclatures.models import DocumentTypeStatus
            config = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                status__code=self.status,
                is_cancellation=True,
                is_active=True
            ).first()
            return bool(config)
        except:
            # Fallback за compatibility
            return self.status in ['cancelled']

    @property
    def can_edit(self):
        """Smart edit check - delegates to DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, _ = DocumentService.can_edit_document(self, user=None)
            return can_edit
        except:
            # Fallback за compatibility
            return not self.is_final

    def get_status_config(self):
        """Get DocumentTypeStatus configuration for current status"""
        try:
            from nomenclatures.models import DocumentTypeStatus
            return DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                status__code=self.status,
                is_active=True
            ).first()
        except:
            return None

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
        Product,
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


class FinancialMixin(models.Model):
    """
    Financial fields mixin - REFACTORED VERSION

    ВАЖНО: Не прави изчисления! Само държи полета.
    Всички изчисления се правят от VATCalculationService
    """

    # === TOTALS (всички суми се записват БЕЗ ДДС в базата) ===
    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total before VAT and discounts')
    )

    discount_total = models.DecimalField(
        _('Discount Total'),
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

    total = models.DecimalField(
        _('Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Final total including VAT')
    )

    # === VAT SETTINGS ===
    prices_entered_with_vat = models.BooleanField(
        _('Prices Include VAT'),
        null=True,
        blank=True,
        help_text=_('Override location settings. NULL means use location defaults')
    )

    class Meta:
        abstract = True

    def recalculate_totals(self, save=True):
        """
        Преизчислява всички totals от линиите
        Делегира на VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService

        # Делегира изчислението
        totals = VATCalculationService.recalculate_document_totals(self)

        # Update полетата
        self.subtotal = totals['subtotal']
        self.vat_total = totals['vat_total']
        self.discount_total = totals['discount_total']
        self.total = totals['total']

        if save:
            self.save(update_fields=['subtotal', 'vat_total', 'discount_total', 'total'])

        return totals

    def get_price_entry_mode(self) -> bool:
        """
        Делегира на VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        return VATCalculationService.get_price_entry_mode(self)

    def validate_totals(self) -> bool:
        """
        Валидира че totals са правилни
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        is_valid, error = VATCalculationService.validate_vat_consistency(self)
        if not is_valid:
            raise ValueError(f"VAT calculation error: {error}")
        return is_valid


class FinancialLineMixin(models.Model):
    """
    Financial fields for document lines - REFACTORED VERSION

    ВАЖНО: Не прави изчисления! Само държи полета.
    """

    # === PRICES (всички цени БЕЗ ДДС в базата) ===
    entered_price = models.DecimalField(
        _('Entered Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Price as entered by user (may include VAT)')
    )

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Unit price WITHOUT VAT (stored value)')
    )

    unit_price_with_vat = models.DecimalField(
        _('Unit Price with VAT'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Unit price INCLUDING VAT (calculated)')
    )

    # === VAT ===
    vat_rate = models.DecimalField(
        _('VAT Rate'),
        max_digits=5,
        decimal_places=3,
        default=Decimal('0.200'),
        help_text=_('VAT rate (0.20 = 20%)')
    )

    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('VAT amount for this line')
    )

    # === DISCOUNTS ===
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
        help_text=_('Discount amount')
    )

    # === TOTALS ===
    net_amount = models.DecimalField(
        _('Net Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount excluding VAT')
    )

    gross_amount = models.DecimalField(
        _('Gross Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount including VAT')
    )

    class Meta:
        abstract = True

    def get_quantity_for_calculation(self) -> Decimal:
        """
        Връща количеството за изчисления
        Override в наследниците според техните полета
        """
        # За PurchaseRequestLine -> requested_quantity
        if hasattr(self, 'requested_quantity'):
            return self.requested_quantity or Decimal('1')

        # За PurchaseOrderLine -> ordered_quantity
        if hasattr(self, 'ordered_quantity'):
            return self.ordered_quantity or Decimal('1')

        # За DeliveryLine -> received_quantity
        if hasattr(self, 'received_quantity'):
            return self.received_quantity or Decimal('1')

        # Default
        return Decimal('1')

    # purchases/models/base.py - FinancialLineMixin

    # purchases/models/base.py - FinancialLineMixin

    def process_entered_price(self):
        """
        ✅ FIXED: Обработва въведената цена със unified VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService

        # Намери entered_price
        entered_price = getattr(self, 'entered_price', None)
        if entered_price is None:
            return

        # ✅ FIXED: Намери quantity - но НЕ излизай при 0!
        if hasattr(self, 'requested_quantity'):
            quantity = self.requested_quantity or Decimal('1')  # Default ако е None
        elif hasattr(self, 'ordered_quantity'):
            quantity = self.ordered_quantity or Decimal('1')
        elif hasattr(self, 'received_quantity'):
            quantity = self.received_quantity or Decimal('1')
        else:
            quantity = Decimal('1')



        try:
            calc_result = VATCalculationService.calculate_line_totals(
                line=self,
                entered_price=entered_price,
                quantity=quantity,  # Винаги подавай количество >= 1
                document=getattr(self, 'document', None)
            )

            # Apply results - unit_price е важен дори при 0 quantity!
            if hasattr(self, 'unit_price'):
                self.unit_price = calc_result['unit_price']
            if hasattr(self, 'vat_rate'):
                self.vat_rate = calc_result['vat_rate']
            if hasattr(self, 'vat_amount'):
                # ✅ За 0 quantity, vat_amount трябва да е 0
                if self.get_effective_quantity() == 0:
                    self.vat_amount = Decimal('0.00')
                else:
                    self.vat_amount = calc_result['vat_amount']
            if hasattr(self, 'net_amount'):
                # ✅ За 0 quantity, net_amount трябва да е 0
                if self.get_effective_quantity() == 0:
                    self.net_amount = Decimal('0.00')
                else:
                    self.net_amount = calc_result['net_amount']
            if hasattr(self, 'gross_amount'):
                # ✅ За 0 quantity, gross_amount трябва да е 0
                if self.get_effective_quantity() == 0:
                    self.gross_amount = Decimal('0.00')
                else:
                    self.gross_amount = calc_result['gross_amount']

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"VAT calculation failed: {e}")

    def get_effective_quantity(self) -> Decimal:
        """
        ✅ NEW: Връща реалното количество за документа
        """
        if hasattr(self, 'requested_quantity'):
            return self.requested_quantity or Decimal('0')
        elif hasattr(self, 'ordered_quantity'):
            return self.ordered_quantity or Decimal('0')
        elif hasattr(self, 'received_quantity'):
            return self.received_quantity or Decimal('0')
        else:
            return Decimal('0')

    def save(self, *args, **kwargs):
        """
        Преизчислява при save
        """
        # Изчисли преди save
        if self.entered_price is not None or self.unit_price:
            self.process_entered_price()

        super().save(*args, **kwargs)

        # Update document totals след save
        if hasattr(self, 'document') and self.document:
            if hasattr(self.document, 'recalculate_totals'):
                self.document.recalculate_totals(save=True)





