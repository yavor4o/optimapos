# purchases/models/base.py - ИНТЕГРИРАН С DocumentType

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta


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
        verbose_name=_('Document Type'),
        help_text=_('Type defines workflow, numbering and business rules'),
        limit_choices_to={'app_name': 'purchases', 'is_active': True}
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
            'approval_limit': self.document_type.approval_limit,
            'auto_confirm': self.document_type.auto_confirm,
            'affects_inventory': self.document_type.affects_inventory,
            'inventory_direction': self.document_type.inventory_direction,
            'inventory_timing': self.document_type.inventory_timing,
            'auto_transitions': self.document_type.auto_transitions,
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

    # =====================
    # DOCUMENT NUMBER GENERATION
    # =====================

    def generate_document_number(self):
        """Generate unique document number using DocumentType configuration"""
        if not self.document_type:
            # Fallback if no DocumentType
            prefix = self.get_document_prefix()
            year = timezone.now().year

            last_doc = self.__class__.objects.filter(
                document_number__startswith=f"{prefix}-{year}-"
            ).order_by('-document_number').first()

            if last_doc:
                try:
                    last_number = int(last_doc.document_number.split('-')[-1])
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    new_number = 1
            else:
                new_number = 1

            return f"{prefix}-{year}-{new_number:04d}"

        # Use DocumentType numbering
        return self.document_type.get_next_number()

    def get_document_prefix(self):
        """Get document prefix - override in subclasses or use DocumentType"""
        if self.document_type:
            return self.document_type.number_prefix
        return "DOC"  # Fallback

    # =====================
    # BUSINESS LOGIC METHODS
    # =====================

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

    # =====================
    # VALIDATION METHODS
    # =====================

    def clean(self):
        """Enhanced validation with DocumentType integration"""
        super().clean()

        if not self.document_type:
            raise ValidationError({
                'document_type': _('Document type is required')
            })

        # Validate status against DocumentType
        if self.status and self.status not in self.get_allowed_statuses():
            raise ValidationError({
                'status': f'Status "{self.status}" not allowed for document type "{self.document_type.name}"'
            })

        # Validate business rules from DocumentType
        if hasattr(self, 'grand_total'):
            total = getattr(self, 'grand_total', 0)
            validation_errors = self.document_type.validate_document_data({
                'total': total,
                'supplier': self.supplier,
                'customer': getattr(self, 'customer', None),
                'lines': hasattr(self, 'lines') and self.lines.exists()
            })

            if validation_errors:
                raise ValidationError({'__all__': validation_errors})

        # Supplier validation based on DocumentType
        if self.document_type.requires_supplier and not self.supplier:
            raise ValidationError({
                'supplier': _('Supplier is required for this document type')
            })

    # purchases/models/base.py - ENHANCED save() method

    def save(self, *args, **kwargs):
        """
        Enhanced save with DocumentType integration

        🎯 Добавена auto_confirm логика за пропускане на draft статус
        🎯 Добавена _skip_validation флаг за пропускане на validation при създаване
        """

        user = getattr(self, '_current_user', None)
        if user and user.is_authenticated:
            if not self.pk:  # New record
                self.created_by = user
            self.updated_by = user

        # ENHANCED: Set default status from DocumentType with auto_confirm support
        if not self.status and self.document_type:
            if self.document_type.auto_confirm:
                # AUTO-CONFIRM: Пропускаме draft, отиваме директно към submit/confirm статус
                allowed_statuses = self.document_type.allowed_statuses
                non_draft_statuses = [s for s in allowed_statuses if s not in ['draft', 'cancelled']]

                if non_draft_statuses:
                    auto_status = non_draft_statuses[0]  # Първия достъпен статус
                    self.status = auto_status

                    # Логваме за debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"AUTO-CONFIRM: {self.__class__.__name__} {self.document_number} starts with status '{auto_status}' (skipped draft)")
                else:
                    # Fallback към default ако няма други статуси
                    self.status = self.document_type.default_status
            else:
                # Normal: Start with default status (usually draft)
                self.status = self.document_type.default_status

        # Generate document number if needed
        if not self.document_number and self.document_type and self.document_type.auto_number:
            self.document_number = self.generate_document_number()

        # ✅ SKIP full_clean ако е flag-нато
        skip_validation = getattr(self, '_skip_validation', False)

        if not skip_validation:
            # Full clean before saving (включва DocumentType validation)
            self.full_clean()

        # ✅ SAVE
        super().save(*args, **kwargs)

        # ✅ Ако сме пропуснали validation, правим я СЛЕД save (когато order има ID)
        if skip_validation and self.pk:
            try:
                self.full_clean()
            except ValidationError as e:
                # Ако validation се провали СЛЕД save, логваме предупреждение
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Post-save validation failed for {self}: {e}")

    # =====================
    # UTILITY METHODS
    # =====================

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




# =================================================================
# MIXIN CLASSES - ЗА СПЕЦИФИЧНИ ФУНКЦИОНАЛНОСТИ
# =================================================================

class FinancialMixin(models.Model):
    """
    Mixin за документи с финансови данни

    Използва се от PurchaseOrder и DeliveryReceipt.
    НЕ се използва от PurchaseRequest (заявките нямат финансови данни).
    """

    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Sum of all line totals before VAT')
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

    grand_total = models.DecimalField(
        _('Grand Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Final total including VAT')
    )

    class Meta:
        abstract = True

    def recalculate_totals(self):
        """Recalculate all financial totals from lines"""
        if not hasattr(self, 'lines'):
            return

        lines = self.lines.all()
        subtotal = sum(getattr(line, 'line_total', 0) for line in lines)
        discount_total = sum(getattr(line, 'discount_amount', 0) for line in lines)
        vat_total = sum(getattr(line, 'vat_amount', 0) for line in lines)

        self.subtotal = subtotal
        self.discount_total = discount_total
        self.vat_total = vat_total
        self.grand_total = subtotal + vat_total

        self.save(update_fields=[
            'subtotal', 'discount_total', 'vat_total', 'grand_total'
        ])

    def clean(self):
        """Financial validation enhanced with DocumentType"""
        super().clean()

        # VAT validation based on DocumentType
        if hasattr(self, 'document_type') and self.document_type:
            if self.document_type.requires_vat_calculation and self.vat_total < 0:
                raise ValidationError({
                    'vat_total': _('VAT total cannot be negative')
                })


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
    Mixin за редове с финансови данни
    """

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text=_('Price per unit excluding VAT')
    )

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

    vat_rate = models.DecimalField(
        _('VAT Rate %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        help_text=_('VAT rate percentage')
    )

    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Calculated VAT amount')
    )

    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total including VAT')
    )

    class Meta:
        abstract = True

    def calculate_totals(self):
        """Calculate line totals"""
        # ✅ FIXED: Use get_quantity() method instead of hardcoded quantity
        quantity = self.get_quantity() if hasattr(self, 'get_quantity') else Decimal('0')

        if quantity and self.unit_price:
            gross_amount = quantity * self.unit_price
            self.discount_amount = gross_amount * (self.discount_percent / 100)
            net_amount = gross_amount - self.discount_amount
            self.vat_amount = net_amount * (self.vat_rate / 100)
            self.line_total = net_amount + self.vat_amount
        else:
            # Zero out calculations if no quantity or price
            self.discount_amount = Decimal('0.00')
            self.vat_amount = Decimal('0.00')
            self.line_total = Decimal('0.00')

    def save(self, *args, **kwargs):
        """Auto-calculate totals before saving"""
        self.calculate_totals()
        super().save(*args, **kwargs)