# purchases/models/base.py - ИНТЕГРИРАН С DocumentType

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime

from core.models.company import Company


class DocumentManager(models.Manager):
    """Base manager for all purchase documents"""

    def active(self):
        """Return only active documents (not cancelled/closed)"""
        return self.exclude(status__in=['cancelled', 'closed'])

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

    def pending_approval(self):
        """Documents pending approval"""
        return self.filter(status__in=['submitted', 'pending_approval'])

    def ready_for_processing(self):
        """Documents ready for processing"""
        return self.filter(status__in=['confirmed', 'approved', 'received'])


class LineManager(models.Manager):
    """Base manager for document lines"""

    def for_product(self, product):
        """Lines for specific product"""
        return self.filter(product=product)

    def with_variances(self):
        """Lines with quantity variances"""
        return self.filter(variance_quantity__gt=0)


# =================================================================
# BASE DOCUMENT - ИНТЕГРИРАН С DocumentType
# =================================================================

class BaseDocument(models.Model):
    """
    Базов клас за всички purchase документи

    ИНТЕГРИРАН С nomenclatures.DocumentType за:
    - Configuration-driven workflow
    - Automatic numbering
    - Business rules validation
    - Status management
    """

    # =====================
    # DOCUMENT TYPE INTEGRATION
    # =====================
    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.PROTECT,
        null=True,  # ← ДОБАВИ
        blank=True,  # ← ДОБАВИ
        verbose_name=_('Document Type'),
        help_text=_('Auto-detected from model name, or manually override'),
        limit_choices_to={'is_active': True}  # ← ПРЕМАХНИ app_name ограничението
    )
    # =====================
    # CORE FIELDS
    # =====================
    document_number = models.CharField(
        _('Document Number'),
        max_length=50,
        unique=True,
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
        help_text=_('Current document status - validated by document type')
        # БЕЗ choices - идват динамично от DocumentType!
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
        help_text=_('PO number, contract reference, etc.')
    )

    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes and comments')
    )

    # =====================
    # AUDIT FIELDS
    # =====================
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_%(class)s_documents',
        verbose_name=_('Created By')
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='updated_%(class)s_documents',
        verbose_name=_('Updated By')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = DocumentManager()

    class Meta:
        abstract = True
        get_latest_by = 'created_at'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document_number} - {self.supplier.name}"

    # =====================
    # DOCUMENT TYPE INTEGRATION METHODS
    # =====================

    def get_allowed_statuses(self):
        """Get allowed statuses from DocumentType"""
        return self.document_type.allowed_statuses if self.document_type else ['draft']

    def get_next_statuses(self):
        """Get possible next statuses from current status"""
        if not self.document_type:
            return []
        return self.document_type.get_next_statuses(self.status)

    def can_transition_to(self, new_status):
        """Check if status transition is allowed by DocumentType"""
        if not self.document_type:
            return False
        return self.document_type.can_transition_to(self.status, new_status)

    def is_final_status(self):
        """Check if current status is final"""
        if not self.document_type:
            return False
        return self.document_type.is_final_status(self.status)

    def get_workflow_rules(self):
        """Get workflow configuration from DocumentType"""
        if not self.document_type:
            return {}

        return {
            'requires_approval': self.document_type.requires_approval,
            'auto_confirm': self.document_type.auto_confirm,
            'affects_inventory': self.document_type.affects_inventory,
            'inventory_direction': self.document_type.inventory_direction,
            'inventory_timing': self.document_type.inventory_timing,
        }

    def needs_approval(self, amount=None):
        """Check if document needs approval based on DocumentType rules"""
        if not self.document_type or not self.document_type.requires_approval:
            return False

        if not amount:
            # Try to get amount from document
            amount = getattr(self, 'grand_total', None) or getattr(self, 'total', 0)

        return self.document_type.needs_approval(amount)

    def should_affect_inventory(self):
        """Check if document should affect inventory at current status"""
        if not self.document_type:
            return False
        return self.document_type.should_affect_inventory(self.status)

    def get_inventory_movement_type(self):
        """Get inventory movement type for this document"""
        if not self.document_type:
            return None
        return self.document_type.get_inventory_movement_type()

    def can_be_edited(self):
        """Check if document can be edited based on DocumentType and status"""
        if not self.document_type:
            return True  # Fallback

        # Check if status is final
        if self.is_final_status():
            return False

        # Check DocumentType rules
        workflow_rules = self.get_workflow_rules()
        if workflow_rules.get('auto_confirm') and self.status != self.document_type.default_status:
            return False

        # Default logic
        return self.status in ['draft', 'submitted']

    def can_be_cancelled(self):
        """Check if document can be cancelled"""
        if self.is_final_status():
            return False

        return 'cancelled' in self.get_next_statuses()

    def can_be_approved(self):
        """Check if document can be approved"""
        if not self.document_type or not self.document_type.requires_approval:
            return False

        return 'approved' in self.get_next_statuses()

    def can_be_confirmed(self):
        """Check if document can be confirmed"""
        return 'confirmed' in self.get_next_statuses()

    def clean(self):
        """
        ФИКСВАНО: Enhanced validation БЕЗ document_type validation

        document_type се валидира в save(), НЕ в clean()
        """
        super().clean()

        # ПРЕМАХНАТО: if not self.document_type validation
        # SmartDocumentTypeMixin се грижи за document_type в save()

        # Validate status against DocumentType САМО ако document_type вече е налично
        if self.document_type and self.status:
            allowed_statuses = self.get_allowed_statuses()
            if self.status not in allowed_statuses:
                raise ValidationError({
                    'status': f'Status "{self.status}" not allowed for document type "{self.document_type.name}". Allowed: {allowed_statuses}'
                })

        # ФИКСВАНО: БАЗОВА валидация БЕЗ DocumentType dependencies
        if self.document_date:
            try:
                # FIX: Конвертираме и двете към date за сравнение
                today = timezone.now().date()

                # Ако document_date е datetime, вземи само date частта
                if isinstance(self.document_date, datetime):
                    doc_date = self.document_date.date()
                else:
                    doc_date = self.document_date

                if doc_date > today:
                    raise ValidationError({
                        'document_date': _('Document date cannot be in the future')
                    })
            except Exception as e:
                # DEBUG: Временно catch за да видим точната грешка
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Date comparison error: {e}")
                logger.error(f"document_date type: {type(self.document_date)}")
                logger.error(f"document_date value: {self.document_date}")
                logger.error(f"today type: {type(today)}")
                logger.error(f"today value: {today}")
                # Re-raise original error
                raise

    def save(self, *args, **kwargs):
        """
        Enhanced save с DocumentType integration

        ВАЖНО: SmartDocumentTypeMixin.save() ще извика auto_detect_document_type()
        ПРЕДИ BaseDocument.save()
        """

        # Set user tracking
        user = getattr(self, '_current_user', None)
        if user and user.is_authenticated:
            if not self.pk:  # New record
                self.created_by = user
            self.updated_by = user

        # АВТОМАТИЧЕН СТАТУС - слага default_status от DocumentType
        if not self.status and self.document_type:
            self.status = self.document_type.default_status

        # Generate document number ДИРЕКТНО - БЕЗ wrapper!
        if not self.document_number and self.document_type and self.document_type.auto_number:
            self.document_number = self.document_type.get_next_number()

        # Validation САМО ако не е skip-вана
        skip_validation = getattr(self, '_skip_validation', False)
        if not skip_validation:
            self.full_clean()

        # Save
        super().save(*args, **kwargs)

        # Post-save validation if needed
        if skip_validation and self.pk:
            try:
                self.full_clean()
            except ValidationError as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Post-save validation failed for {self}: {e}")

    def get_workflow_info(self):
        """Get complete workflow information for this document"""
        return {
            'document_type': {
                'code': self.document_type.code if self.document_type else None,
                'name': self.document_type.name if self.document_type else None,
                'type_key': self.document_type.type_key if self.document_type else None,
            },
            'current_status': self.status,
            'allowed_statuses': self.get_allowed_statuses(),
            'next_statuses': self.get_next_statuses(),
            'is_final': self.is_final_status(),
            'can_edit': self.can_be_edited(),
            'can_cancel': self.can_be_cancelled(),
            'can_approve': self.can_be_approved(),
            'can_confirm': self.can_be_confirmed(),
            'needs_approval': self.needs_approval(),
            'affects_inventory': self.should_affect_inventory(),
            'workflow_rules': self.get_workflow_rules(),
        }

    def get_company(self):
        """Get current company instance"""

        return Company.get_current()

    def get_price_entry_mode(self) -> bool:
        """
        Get effective price entry mode for this document

        Returns:
            bool: True if prices include VAT, False if exclude VAT
        """
        # Document-level override has priority (if this is a financial document)
        if hasattr(self, 'prices_entered_with_vat') and self.prices_entered_with_vat is not None:
            return self.prices_entered_with_vat

        # Fallback to location setting
        if self.location:
            # Determine document type based on model name
            model_name = self._meta.model_name.lower()

            if 'purchase' in model_name or 'request' in model_name:
                return getattr(self.location, 'purchase_prices_include_vat', False)
            elif 'sale' in model_name or 'invoice' in model_name:
                return getattr(self.location, 'sales_prices_include_vat', True)

        # Last fallback - prices without VAT
        return False

    def get_supplier_vat_status(self) -> bool:
        """Check if supplier is VAT registered"""
        if self.supplier:
            return getattr(self.supplier, 'vat_registered', False)
        return False

    def get_company_vat_status(self) -> bool:
        """Check if company is VAT registered"""
        company = self.get_company()
        if company:
            return company.is_vat_applicable()
        return False

    def is_vat_applicable(self) -> bool:
        """
        Check if VAT calculations should be applied

        Returns:
            bool: True if VAT should be calculated, False otherwise
        """
        # Company VAT registration is the primary check
        if not self.get_company_vat_status():
            return False

        # If company is VAT registered, then apply VAT
        # (supplier VAT status affects how we interpret prices, not whether we calculate VAT)
        return True

    def get_vat_context_info(self) -> dict:
        """Get complete VAT context for this document"""
        return {
            'company_vat_registered': self.get_company_vat_status(),
            'supplier_vat_registered': self.get_supplier_vat_status(),
            'prices_entered_with_vat': self.get_price_entry_mode(),
            'document_override': getattr(self, 'prices_entered_with_vat', None),
            'location_default_purchase': getattr(self.location, 'purchase_prices_include_vat',
                                                 False) if self.location else None,
            'location_default_sales': getattr(self.location, 'sales_prices_include_vat',
                                              True) if self.location else None,
            'vat_applicable': self.is_vat_applicable()
        }


# =================================================================
# MINIMAL BASE DOCUMENT LINE
# =================================================================

class BaseDocumentLine(models.Model):
    """
    Базов клас за редове в документи
    """

    # =====================
    # CORE FIELDS
    # =====================
    line_number = models.PositiveIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product'),
        help_text=_('Product being purchased')
    )

    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit'),
        help_text=_('Unit of measure for this line')
    )

    # =====================
    # BATCH/QUALITY TRACKING (Optional based on DocumentType)
    # =====================

    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        blank=True,
        help_text=_('Batch/Lot number for tracking')
    )

    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Product expiry date')
    )

    serial_numbers = models.TextField(
        _('Serial Numbers'),
        blank=True,
        help_text=_('Serial numbers (one per line)')
    )

    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Passed quality control')
    )

    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Quality control notes')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = LineManager()

    class Meta:
        abstract = True
        ordering = ['line_number']

    def __str__(self):
        # ✅ FIXED: Use get_quantity() method instead of hardcoded quantity
        quantity = self.get_quantity()
        return f"Line {self.line_number}: {self.product.code} x {quantity}"

    def get_quantity(self):
        """
        Get quantity for this line - different subclasses have different quantity fields

        Returns:
            Decimal: The quantity for this line
        """
        # Try different quantity field names used by subclasses
        if hasattr(self, 'ordered_quantity'):
            return self.ordered_quantity
        elif hasattr(self, 'requested_quantity'):
            return self.requested_quantity
        elif hasattr(self, 'received_quantity'):
            return self.received_quantity
        elif hasattr(self, 'quantity'):
            return self.quantity
        else:
            return Decimal('0.000')

    def clean(self):
        """Validation based on document's DocumentType requirements"""
        super().clean()

        # Get document's DocumentType for validation
        document = getattr(self, 'document', None)
        if document and document.document_type:
            doc_type = document.document_type

            # Batch tracking validation
            if doc_type.requires_batch_tracking and not self.batch_number:
                raise ValidationError({
                    'batch_number': _('Batch number is required for this document type')
                })

            # Expiry date validation
            if doc_type.requires_expiry_dates and not self.expiry_date:
                raise ValidationError({
                    'expiry_date': _('Expiry date is required for this document type')
                })

            # Serial number validation
            if doc_type.requires_serial_numbers and not self.serial_numbers:
                raise ValidationError({
                    'serial_numbers': _('Serial numbers are required for this document type')
                })

            # Quality check validation
            if doc_type.requires_quality_check and not hasattr(self, '_skip_quality_check'):
                if not self.quality_approved and not self.quality_notes:
                    raise ValidationError({
                        'quality_notes': _('Quality notes required when not approved')
                    })

    def save(self, *args, **kwargs):
        """Auto-set line number - ПРОФЕСИОНАЛЕН ПОДХОД"""
        if not self.line_number:
            if hasattr(self, 'document') and self.document:
                # Намери най-високия line_number за този документ
                max_line = self.__class__.objects.filter(
                    document=self.document
                ).aggregate(
                    max_num=models.Max('line_number')
                )['max_num']

                # Следващия номер
                self.line_number = (max_line or 0) + 1
            else:
                # Fallback ако няма document
                self.line_number = 1

        super().save(*args, **kwargs)


# =================================================================
# MIXIN CLASSES - ЗА СПЕЦИФИЧНИ ФУНКЦИОНАЛНОСТИ
# =================================================================

# REPLACE the FinancialMixin class in purchases/models/base.py

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
        FIXED: Correct VAT calculation logic

        subtotal = sum of net amounts (excluding VAT)
        vat_total = sum of VAT amounts
        total = subtotal + vat_total
        """
        if not hasattr(self, 'lines'):
            return

        lines = self.lines.all()

        # FIXED: Use net_amount (excluding VAT) for subtotal, not line_total/gross_amount
        subtotal = sum(getattr(line, 'net_amount', 0) for line in lines)
        discount_total = sum(getattr(line, 'discount_amount', 0) for line in lines)
        vat_total = sum(getattr(line, 'vat_amount', 0) for line in lines)

        self.subtotal = subtotal
        self.discount_total = discount_total
        self.vat_total = vat_total
        self.total = subtotal + vat_total  # FIXED: use 'total' not 'grand_total'

        self.save(update_fields=[
            'subtotal', 'discount_total', 'vat_total', 'total'
        ])

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
        Convert entered_price to unit_price - SIMPLIFIED using SmartVATService
        """
        if not self.entered_price or not hasattr(self, 'document'):
            return

        try:
            # Delegate to SmartVATService - no duplication!
            from purchases.services.vat_service import SmartVATService

            result = SmartVATService.calculate_line_vat(
                self, self.entered_price, self.document
            )

            # Apply results
            self.unit_price = result['unit_price']
            self.vat_rate = result['vat_rate']
            # Note: vat_amount and gross_amount calculated in calculate_totals()

        except ImportError:
            # Fallback if SmartVATService not available
            self.unit_price = self.entered_price
            self.vat_rate = Decimal('0.00')

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


class SmartDocumentTypeMixin(models.Model):
    """
    SMART миксин за автоматично присвояване на DocumentType

    Логика:
    1. Търси DocumentType с model_name = точното име на класа
    2. Ако няма, търси по app_name + smart matching на type_key
    3. ValidationError ако не намери подходящ
    """

    class Meta:
        abstract = True

    def auto_detect_document_type(self):
        """Автоматично открива и присвоява DocumentType"""

        # Ако вече има document_type, не прави нищо
        if self.document_type:
            return

        from nomenclatures.models import DocumentType

        # СТЪПКА 1: Търси по точно съвпадение на model_name
        model_class_name = self.__class__.__name__  # 'PurchaseRequest'

        document_type = DocumentType.objects.filter(
            model_name=model_class_name,
            is_active=True
        ).first()

        if document_type:
            self.document_type = document_type
            return

        # СТЪПКА 2: Smart matching по app_name + type_key
        app_name = self._meta.app_label  # 'purchases'

        possible_types = DocumentType.objects.filter(
            app_name=app_name,
            is_active=True
        )

        for doc_type in possible_types:
            if self._smart_match_type_key(doc_type.type_key):
                self.document_type = doc_type
                return

        # СТЪПКА 3: Няма намерен DocumentType
        self._raise_no_document_type_error(model_class_name, app_name)

    def _smart_match_type_key(self, type_key):
        """
        Smart matching между model name и type_key

        Examples:
        - PurchaseRequest matches 'purchase_request'
        - PurchaseOrder matches 'purchase_order'
        - DeliveryReceipt matches 'delivery_receipt'
        """
        model_name = self.__class__.__name__.lower()  # 'purchaserequest'
        type_key_clean = type_key.lower().replace('_', '')  # 'purchaserequest'

        # Директно съвпадение
        if model_name == type_key_clean:
            return True

        # Съвпадение с префикси (purchase, sales, delivery, etc.)
        prefixes = ['purchase', 'sales', 'delivery', 'inventory', 'hr', 'pos']

        for prefix in prefixes:
            if model_name.startswith(prefix):
                model_suffix = model_name[len(prefix):]  # 'request' от 'purchaserequest'
                type_suffix = type_key_clean.replace(prefix, '')  # 'request' от 'purchaserequest'

                if model_suffix == type_suffix:
                    return True

        return False

    def _raise_no_document_type_error(self, model_class_name, app_name):
        """Подробно съобщение за грешка"""
        raise ValidationError(
            f"No DocumentType found for model '{model_class_name}'. "
            f"Please create a DocumentType with:\n"
            f"- model_name='{model_class_name}' OR\n"
            f"- app_name='{app_name}' with matching type_key.\n\n"
            f"Example: DocumentType(code='REQ001', model_name='{model_class_name}', "
            f"app_name='{app_name}', type_key='purchase_request')"
        )

    def save(self, *args, **kwargs):
        """Auto-detect document type преди save"""
        self.auto_detect_document_type()
        super().save(*args, **kwargs)

    # DEBUG/UTILITY METHODS

    @classmethod
    def get_matching_document_types(cls):
        """DEBUG: Покажи всички DocumentTypes които могат да match-нат"""
        from nomenclatures.models import DocumentType

        model_name = cls.__name__
        app_name = cls._meta.app_label

        # Точни съвпадения
        exact_matches = DocumentType.objects.filter(
            model_name=model_name,
            is_active=True
        )

        # Възможни съвпадения
        possible_matches = DocumentType.objects.filter(
            app_name=app_name,
            is_active=True
        )

        return {
            'exact_matches': list(exact_matches),
            'possible_matches': list(possible_matches),
            'model_name': model_name,
            'app_name': app_name
        }

    def get_detection_info(self):
        """DEBUG: Информация за detection процеса"""
        return {
            'model_class': self.__class__.__name__,
            'app_label': self._meta.app_label,
            'current_document_type': self.document_type,
            'would_auto_detect': not bool(self.document_type)
        }


