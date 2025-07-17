# nomenclatures/models/documents.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from decimal import Decimal
from .base import BaseNomenclature, ActiveManager


class DocumentTypeManager(ActiveManager):
    """Manager for document types"""

    def for_app(self, app_name):
        """Get document types for specific app"""
        return self.active().filter(app_name=app_name)

    def purchase_types(self):
        """Purchase document types"""
        return self.for_app('purchases')

    def sales_types(self):
        """Sales document types"""
        return self.for_app('sales')

    def inventory_types(self):
        """Inventory document types"""
        return self.for_app('inventory')

    def by_type_key(self, type_key):
        """Filter by type key"""
        return self.active().filter(type_key=type_key)

    def affecting_inventory(self):
        """Document types that affect inventory"""
        return self.active().filter(affects_inventory=True)

    def fiscal_types(self):
        """Fiscal document types"""
        return self.active().filter(is_fiscal=True)


class DocumentType(BaseNomenclature):
    """
    Universal document type configuration for all apps

    Defines workflow, numbering, business rules for any document type:
    - Purchase documents (REQ, ORD, DEL)
    - Sales documents (QUO, SO, INV)
    - Inventory documents (ADJ, TRN, CNT)
    - Contract documents (CON, REN, AMD)
    - HR documents (LEV, EXP, BON)
    """

    # =====================
    # BASIC IDENTIFICATION
    # =====================

    type_key = models.CharField(
        _('Type Key'),
        max_length=50,
        help_text=_('Unique identifier: request, order, delivery, quote, contract, etc.')
    )

    app_name = models.CharField(
        _('App Name'),
        max_length=50,
        help_text=_('Django app name: purchases, sales, inventory, contracts, hr')
    )

    model_name = models.CharField(
        _('Model Name'),
        max_length=50,
        blank=True,
        help_text=_('Model class name (optional): PurchaseOrder, SalesQuote, Contract')
    )

    sort_order = models.PositiveIntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('Order for display in lists')
    )

    # =====================
    # NUMBERING SYSTEM
    # =====================

    number_prefix = models.CharField(
        _('Number Prefix'),
        max_length=10,
        help_text=_('Document prefix: REQ, ORD, DEL, QUO, CON, etc.')
    )

    current_number = models.PositiveIntegerField(
        _('Current Number'),
        default=0,
        help_text=_('Last used sequential number')
    )

    number_format = models.CharField(
        _('Number Format'),
        max_length=100,
        default='{prefix}-{year}-{number:04d}',
        help_text=_('Format template: {prefix}-{year}-{number:04d}')
    )

    reset_numbering_yearly = models.BooleanField(
        _('Reset Yearly'),
        default=True,
        help_text=_('Reset numbering sequence each year')
    )

    last_reset_year = models.PositiveIntegerField(
        _('Last Reset Year'),
        null=True,
        blank=True,
        help_text=_('Year when numbering was last reset')
    )

    # =====================
    # WORKFLOW CONFIGURATION
    # =====================

    allowed_statuses = models.JSONField(
        _('Allowed Statuses'),
        default=list,
        help_text=_('Valid status values: ["draft", "confirmed", "completed"]')
    )

    default_status = models.CharField(
        _('Default Status'),
        max_length=30,
        default='draft',
        help_text=_('Initial status for new documents')
    )

    status_transitions = models.JSONField(
        _('Status Transitions'),
        default=dict,
        help_text=_('Allowed transitions: {"draft": ["submitted", "cancelled"]}')
    )



    final_statuses = models.JSONField(
        _('Final Statuses'),
        default=list,
        help_text=_('Statuses that prevent further changes: ["completed", "cancelled"]')
    )

    # =====================
    # APPROVAL WORKFLOW
    # =====================

    requires_approval = models.BooleanField(
        _('Requires Approval'),
        default=False,
        help_text=_('Document needs approval before processing')
    )

    approval_limit = models.DecimalField(
        _('Approval Limit'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Amount above which approval is required (BGN)')
    )

    approval_levels = models.PositiveIntegerField(
        _('Approval Levels'),
        default=1,
        help_text=_('Number of approval levels required')
    )

    auto_approve_conditions = models.JSONField(
        _('Auto Approve Conditions'),
        default=dict,
        blank=True,
        null=True,
        help_text=_('Conditions for automatic approval')
    )

    # =====================
    # BUSINESS BEHAVIOR
    # =====================

    # Inventory Impact
    affects_inventory = models.BooleanField(
        _('Affects Inventory'),
        default=False,
        help_text=_('Creates inventory movements')
    )

    inventory_direction = models.CharField(
        _('Inventory Direction'),
        max_length=10,
        choices=[
            ('in', _('Incoming - Increases Stock')),
            ('out', _('Outgoing - Decreases Stock')),
            ('both', _('Both Directions Possible'))
        ],
        blank=True,
        help_text=_('Direction of inventory impact')
    )

    inventory_timing = models.CharField(
        _('Inventory Timing'),
        max_length=20,
        choices=[
            ('immediate', _('Immediate - On Creation')),
            ('on_confirm', _('On Confirmation')),
            ('on_process', _('On Processing')),
            ('on_complete', _('On Completion')),
            ('manual', _('Manual Trigger'))
        ],
        default='on_process',
        blank=True,
        help_text=_('When to create inventory movements')
    )

    # Financial Impact
    is_fiscal = models.BooleanField(
        _('Is Fiscal Document'),
        default=False,
        help_text=_('Requires fiscal device/NAP reporting')
    )

    requires_vat_calculation = models.BooleanField(
        _('Requires VAT'),
        default=True,
        help_text=_('Document must calculate VAT')
    )

    requires_payment = models.BooleanField(
        _('Requires Payment'),
        default=False,
        help_text=_('Payment must be processed')
    )

    supports_foreign_currency = models.BooleanField(
        _('Foreign Currency'),
        default=False,
        help_text=_('Supports non-BGN currencies')
    )

    # Customer/Supplier Requirements
    requires_customer = models.BooleanField(
        _('Requires Customer'),
        default=False,
        help_text=_('Customer must be specified')
    )

    requires_supplier = models.BooleanField(
        _('Requires Supplier'),
        default=False,
        help_text=_('Supplier must be specified')
    )

    allows_anonymous = models.BooleanField(
        _('Allow Anonymous'),
        default=True,
        help_text=_('Allows documents without customer/supplier')
    )

    # =====================
    # DOCUMENT RELATIONSHIPS
    # =====================

    can_be_source = models.BooleanField(
        _('Can Be Source'),
        default=False,
        help_text=_('Can create other documents from this type')
    )

    can_reference_multiple_sources = models.BooleanField(
        _('Multiple Sources'),
        default=False,
        help_text=_('Can be created from multiple source documents')
    )

    allowed_source_types = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='allowed_target_types',
        help_text=_('Document types that can be sources for this type')
    )

    # =====================
    # QUALITY & COMPLIANCE
    # =====================

    requires_batch_tracking = models.BooleanField(
        _('Batch Tracking'),
        default=False,
        help_text=_('Mandatory batch numbers')
    )

    requires_expiry_dates = models.BooleanField(
        _('Expiry Dates'),
        default=False,
        help_text=_('Mandatory expiry date tracking')
    )

    requires_serial_numbers = models.BooleanField(
        _('Serial Numbers'),
        default=False,
        help_text=_('Mandatory serial number tracking')
    )

    requires_quality_check = models.BooleanField(
        _('Quality Check'),
        default=False,
        help_text=_('Quality control before processing')
    )

    requires_certificates = models.BooleanField(
        _('Certificates Required'),
        default=False,
        help_text=_('Requires certificates (origin, health, etc.)')
    )

    # =====================
    # ADVANCED FEATURES
    # =====================

    # Returns & Reversals
    handles_returns = models.BooleanField(
        _('Handles Returns'),
        default=False,
        help_text=_('Document type for returns/reversals')
    )

    reverses_original = models.BooleanField(
        _('Reverses Original'),
        default=False,
        help_text=_('Reverses effects of original document')
    )

    # Delivery Management
    allows_partial_delivery = models.BooleanField(
        _('Partial Delivery'),
        default=True,
        help_text=_('Allows multiple partial deliveries')
    )

    delivery_tolerance_percent = models.DecimalField(
        _('Delivery Tolerance %'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Allowed variance in delivery quantity')
    )

    # Cost Management
    supports_landed_cost = models.BooleanField(
        _('Landed Cost'),
        default=False,
        help_text=_('Supports freight and duties allocation')
    )

    handles_price_variances = models.BooleanField(
        _('Price Variances'),
        default=False,
        help_text=_('Handles price differences vs original')
    )

    # =====================
    # POS INTEGRATION
    # =====================

    pos_document = models.BooleanField(
        _('POS Document'),
        default=False,
        help_text=_('Can be created from POS terminal')
    )

    prints_receipt = models.BooleanField(
        _('Prints Receipt'),
        default=False,
        help_text=_('Automatically prints receipt')
    )

    opens_cash_drawer = models.BooleanField(
        _('Opens Cash Drawer'),
        default=False,
        help_text=_('Opens cash drawer on completion')
    )

    # =====================
    # AUTOMATION SETTINGS
    # =====================

    auto_confirm = models.BooleanField(
        _('Auto Confirm'),
        default=False,
        help_text=_('Automatically confirm on creation')
    )

    auto_number = models.BooleanField(
        _('Auto Number'),
        default=True,
        help_text=_('Automatically generate document numbers')
    )

    requires_lines = models.BooleanField(
        _('Requires Lines'),
        default=True,
        help_text=_('Document must have line items')
    )

    # =====================
    # VALIDATION RULES
    # =====================

    min_total_amount = models.DecimalField(
        _('Min Total Amount'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Minimum allowed total amount')
    )

    max_total_amount = models.DecimalField(
        _('Max Total Amount'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Maximum allowed total amount')
    )

    custom_validation_rules = models.JSONField(
        _('Custom Validation Rules'),
        default=dict,
        blank=True,
        null=True,
        help_text=_('Additional validation rules in JSON format')
    )

    # =====================
    # MANAGERS
    # =====================

    objects = DocumentTypeManager()

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['app_name', 'sort_order', 'name']
        unique_together = [
            ('app_name', 'type_key'),
            ('number_prefix', 'app_name')
        ]
        indexes = [
            models.Index(fields=['app_name', 'type_key']),
            models.Index(fields=['affects_inventory', 'is_active']),
            models.Index(fields=['is_fiscal', 'pos_document']),
            models.Index(fields=['requires_approval', 'approval_limit']),
        ]

    def __str__(self):
        return f"{self.number_prefix} - {self.name} ({self.app_name})"

    # =====================
    # NUMBERING METHODS
    # =====================

    def get_next_number(self) -> str:
        """Generate next sequential document number"""
        current_year = timezone.now().year

        # Check if we need yearly reset
        if (self.reset_numbering_yearly and
                self.last_reset_year and
                self.last_reset_year != current_year):
            self.current_number = 0
            self.last_reset_year = current_year
        elif not self.last_reset_year:
            self.last_reset_year = current_year

        self.current_number += 1
        self.save(update_fields=['current_number', 'last_reset_year'])

        # Format the number
        return self.number_format.format(
            prefix=self.number_prefix,
            year=current_year,
            month=timezone.now().month,
            day=timezone.now().day,
            number=self.current_number
        )

    def reset_numbering(self, start_from: int = 0):
        """Reset numbering sequence"""
        self.current_number = start_from
        self.last_reset_year = timezone.now().year
        self.save(update_fields=['current_number', 'last_reset_year'])

    # =====================
    # WORKFLOW METHODS
    # =====================

    def get_allowed_transitions(self) -> dict:
        """Get allowed status transitions"""
        if self.status_transitions:
            return self.status_transitions

        # Default transitions if not configured
        if len(self.allowed_statuses) <= 2:
            # Simple workflow
            return {
                'draft': ['confirmed', 'cancelled'],
                'confirmed': ['completed', 'cancelled']
            }
        else:
            # Standard workflow
            statuses = self.allowed_statuses
            transitions = {}
            for i, status in enumerate(statuses[:-1]):
                next_statuses = [statuses[i + 1]]
                if 'cancelled' in statuses:
                    next_statuses.append('cancelled')
                transitions[status] = next_statuses
            return transitions

    def can_transition_to(self, from_status: str, to_status: str) -> bool:
        """Check if status transition is allowed"""
        transitions = self.get_allowed_transitions()
        return to_status in transitions.get(from_status, [])

    def get_next_statuses(self, current_status: str) -> list:
        """Get possible next statuses from current status"""
        transitions = self.get_allowed_transitions()
        return transitions.get(current_status, [])

    def is_final_status(self, status: str) -> bool:
        """Check if status is final (no further transitions)"""
        return status in self.final_statuses

    # =====================
    # BUSINESS LOGIC METHODS
    # =====================

    def should_affect_inventory(self, document_status: str = None) -> bool:
        """Check if document should affect inventory at given status"""
        if not self.affects_inventory:
            return False

        if not document_status:
            return True

        if self.inventory_timing == 'immediate':
            return True
        elif self.inventory_timing == 'on_confirm':
            return document_status == 'confirmed'
        elif self.inventory_timing == 'on_process':
            return document_status == 'processed'
        elif self.inventory_timing == 'on_complete':
            return document_status in ['completed', 'finished']

        return False

    def get_inventory_movement_type(self) -> str:
        """Get inventory movement type for this document"""
        if not self.affects_inventory:
            return None

        if self.inventory_direction == 'in':
            return 'IN'
        elif self.inventory_direction == 'out':
            return 'OUT'
        elif self.handles_returns and self.reverses_original:
            return 'ADJUSTMENT'  # Reversal

        return 'ADJUSTMENT'

    def needs_approval(self, amount: Decimal = None) -> bool:
        """Check if document needs approval based on amount"""
        if not self.requires_approval:
            return False

        if not amount or not self.approval_limit:
            return self.requires_approval

        return amount >= self.approval_limit

    def validate_document_data(self, data: dict) -> list:
        """Validate document data against this document type rules"""
        errors = []

        # Amount validation
        total = data.get('total', 0)
        if self.min_total_amount and total < self.min_total_amount:
            errors.append(f'Total amount must be at least {self.min_total_amount}')

        if self.max_total_amount and total > self.max_total_amount:
            errors.append(f'Total amount cannot exceed {self.max_total_amount}')

        # Customer/Supplier validation
        if self.requires_customer and not data.get('customer'):
            errors.append('Customer is required for this document type')

        if self.requires_supplier and not data.get('supplier'):
            errors.append('Supplier is required for this document type')

        # Lines validation
        if self.requires_lines and not data.get('lines'):
            errors.append('Document must have line items')

        return errors

    # =====================
    # RELATIONSHIP METHODS
    # =====================

    def can_create_from_source(self, source_document_type) -> bool:
        """Check if this document type can be created from source type"""
        return source_document_type in self.allowed_source_types.all()

    def get_possible_source_types(self):
        """Get document types that can be sources for this type"""
        return self.allowed_source_types.filter(is_active=True)

    def get_possible_target_types(self):
        """Get document types that can be created from this type"""
        return self.allowed_target_types.filter(is_active=True)

    # =====================
    # VALIDATION
    # =====================

    def clean(self):
        """Validate document type configuration"""
        super().clean()

        # Code should be uppercase
        if self.code:
            self.code = self.code.upper()

        if self.number_prefix:
            self.number_prefix = self.number_prefix.upper()

        # Type key should be lowercase
        if self.type_key:
            self.type_key = self.type_key.lower()

        # App name should be lowercase
        if self.app_name:
            self.app_name = self.app_name.lower()

        # Validate app exists
        try:
            from django.apps import apps
            apps.get_app_config(self.app_name)
        except LookupError:
            raise ValidationError({
                'app_name': f'App "{self.app_name}" does not exist'
            })

        # Validate allowed_statuses is not empty
        if not self.allowed_statuses:
            self.allowed_statuses = ['draft', 'confirmed']

        # Validate default_status is in allowed_statuses
        if self.default_status not in self.allowed_statuses:
            raise ValidationError({
                'default_status': f'Default status "{self.default_status}" must be in allowed statuses'
            })

        # Inventory validation
        if self.affects_inventory and not self.inventory_direction:
            raise ValidationError({
                'inventory_direction': 'Inventory direction required when affects_inventory is True'
            })

        # Approval validation
        if self.approval_limit and not self.requires_approval:
            raise ValidationError({
                'approval_limit': 'Approval limit can only be set when requires_approval is True'
            })

        # Numbering validation
        if not self.number_prefix:
            raise ValidationError({
                'number_prefix': 'Number prefix is required'
            })

        # POS validation
        if self.pos_document and not self.is_fiscal:
            raise ValidationError({
                'is_fiscal': 'POS documents must be fiscal'
            })

    # =====================
    # SYSTEM METHODS
    # =====================

    @classmethod
    def create_purchases_defaults(cls):
        """Create default document types for purchases app"""
        defaults = [
            {
                'code': 'REQ',
                'name': 'Purchase Request',
                'type_key': 'request',
                'app_name': 'purchases',
                'number_prefix': 'REQ',
                'allowed_statuses': ['draft', 'submitted', 'approved', 'rejected', 'converted', 'cancelled'],
                'requires_approval': True,
                'approval_limit': Decimal('500.00'),
                'can_be_source': True,
                'affects_inventory': False,
            },
            {
                'code': 'ORD',
                'name': 'Purchase Order',
                'type_key': 'order',
                'app_name': 'purchases',
                'number_prefix': 'ORD',
                'allowed_statuses': ['draft', 'sent', 'confirmed', 'receiving', 'completed', 'cancelled'],
                'requires_approval': True,
                'approval_limit': Decimal('1000.00'),
                'can_be_source': True,
                'affects_inventory': False,
                'requires_supplier': True,
            },
            {
                'code': 'DEL',
                'name': 'Delivery Receipt',
                'type_key': 'delivery',
                'app_name': 'purchases',
                'number_prefix': 'DEL',
                'allowed_statuses': ['scheduled', 'received', 'quality_check', 'processed', 'cancelled'],
                'affects_inventory': True,
                'inventory_direction': 'in',
                'inventory_timing': 'on_process',
                'requires_quality_check': True,
                'can_reference_multiple_sources': True,
                'requires_supplier': True,
            }
        ]

        created_types = []
        for data in defaults:
            doc_type, created = cls.objects.get_or_create(
                app_name=data['app_name'],
                type_key=data['type_key'],
                defaults=data
            )
            if created:
                created_types.append(doc_type)

        return created_types