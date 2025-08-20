# nomenclatures/models/documents.py - CLEAN REFACTORED
"""
Document Type Definition - SIMPLIFIED & FOCUSED

ТОЗИ ФАЙЛ СЪДЪРЖА САМО:
1. DocumentType - Core document definition (САМО основни полета)

ПРЕМАХНАТО:
- JSON workflow schemas (дублиране с ApprovalRule)
- Complex numbering logic (ще е в numbering.py)
- Workflow transitions (ApprovalRule ги покрива)

ЗАПАЗЕНО:
- Основни document properties
- Business behavior flags
- Integration hooks
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base_nomenclature import BaseNomenclature, BaseNomenclatureManager


# =================================================================
# DOCUMENT TYPE - CLEAN & SIMPLE
# =================================================================

class DocumentTypeManager(BaseNomenclatureManager):
    """Manager for document types with common queries"""

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
        """Fiscal document types (Bulgarian legal requirement)"""
        return self.active().filter(is_fiscal=True)

    def requiring_approval(self):
        """Document types that require approval"""
        return self.active().filter(requires_approval=True)


class DocumentType(BaseNomenclature):
    """
    Document Type Definition - CLEAN & FOCUSED

    Defines ONLY essential document properties:
    - What kind of document is this?
    - How does it behave in the system?
    - What are its business rules?

    NUMBERING: Handled by numbering.py models
    WORKFLOW: Handled by ApprovalRule system
    """

    # =====================
    # CORE IDENTITY
    # =====================

    type_key = models.CharField(
        _('Type Key'),
        max_length=50,
        help_text=_('Unique identifier: purchase_request, sales_invoice, inventory_adjustment, etc.')
    )

    app_name = models.CharField(
        _('App Name'),
        max_length=50,
        help_text=_('Django app: purchases, sales, inventory, hr, contracts')
    )

    # =====================
    # BUSINESS BEHAVIOR
    # =====================

    affects_inventory = models.BooleanField(
        _('Affects Inventory'),
        default=False,
        help_text=_('Does this document type change inventory quantities?')
    )

    INVENTORY_DIRECTION_CHOICES = [
        ('in', _('Increases Stock (IN) - deliveries, production, adjustments+')),
        ('out', _('Decreases Stock (OUT) - sales, consumption, adjustments-')),
        ('both', _('Can be Both - transfers, complex adjustments')),
        ('none', _('No Effect - quotes, requests, reports')),
    ]

    inventory_direction = models.CharField(
        _('Inventory Direction'),
        max_length=10,
        choices=INVENTORY_DIRECTION_CHOICES,
        default='none',
        help_text=_('How this document affects inventory levels')
    )

    requires_approval = models.BooleanField(
        _('Requires Approval'),
        default=False,
        help_text=_('Must be approved before processing (uses ApprovalRule system)')
    )

    is_fiscal = models.BooleanField(
        _('Is Fiscal Document'),
        default=False,
        help_text=_('Subject to Bulgarian fiscal regulations (VAT, 10-digit numbering, NRA requirements)')
    )

    auto_create_movements = models.BooleanField(
        _('Auto Create Movements'),
        default=False,
        help_text=_('Automatically create inventory movements when document is processed')
    )

    # =====================
    # SYSTEM INTEGRATION
    # =====================

    auto_number = models.BooleanField(
        _('Auto Number'),
        default=True,
        help_text=_('Automatically assign document numbers (uses numbering.py configuration)')
    )

    allows_attachments = models.BooleanField(
        _('Allows Attachments'),
        default=True,
        help_text=_('Can attach files to documents of this type')
    )

    statuses = models.ManyToManyField(
        'nomenclatures.DocumentStatus',
        through='DocumentTypeStatus',
        blank=True,
        related_name='document_types',
        help_text=_('Available statuses for this document type')
    )

    allow_edit_completed = models.BooleanField(
        _('Allow Edit When Completed'),
        default=False,
        help_text=_('Can completed documents be edited?')
    )

    # =====================
    # MANAGERS & META
    # =====================

    objects = DocumentTypeManager()

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['app_name', 'sort_order', 'name']
        indexes = [
            models.Index(fields=['app_name', 'type_key']),
            models.Index(fields=['affects_inventory', 'inventory_direction']),
            models.Index(fields=['requires_approval']),
            models.Index(fields=['is_fiscal']),
            models.Index(fields=['auto_create_movements']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['app_name', 'type_key'],
                name='unique_app_type_key'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.app_name})"

    def get_full_identifier(self):
        """Get full identifier for debugging"""
        return f"{self.app_name}.{self.type_key}"

    def clean(self):
        """Business rules validation"""
        super().clean()

        # Inventory direction validation
        if not self.affects_inventory and self.inventory_direction != 'none':
            raise ValidationError({
                'inventory_direction': _(
                    'Must be "none" if document does not affect inventory'
                )
            })

        if self.affects_inventory and self.inventory_direction == 'none':
            raise ValidationError({
                'inventory_direction': _(
                    'Must specify direction if document affects inventory'
                )
            })

        # Auto movements require inventory affect
        if self.auto_create_movements and not self.affects_inventory:
            raise ValidationError({
                'auto_create_movements': _(
                    'Cannot auto-create movements if document does not affect inventory'
                )
            })

        # Fiscal documents validation (Bulgarian requirements)
        if self.is_fiscal:
            if not self.auto_number:
                raise ValidationError({
                    'auto_number': _(
                        'Fiscal documents must have automatic numbering (Bulgarian law)'
                    )
                })

    # =====================
    # BUSINESS METHODS
    # =====================

    def can_create_movements(self):
        """Check if this document type can create inventory movements"""
        return self.affects_inventory and self.inventory_direction != 'none'

    def get_movement_type(self):
        """Get inventory movement type for this document"""
        if not self.affects_inventory:
            return None

        # FIXED: Match inventory app expectations
        direction_map = {
            'in': 'IN',  # ✅ FIXED: inventory app expects 'IN'
            'out': 'OUT',  # ✅ FIXED: inventory app expects 'OUT'
            'both': 'BOTH',  # ✅ For transfer documents
            'none': None
        }
        return direction_map.get(self.inventory_direction)

    def is_purchase_document(self):
        """Check if this is a purchase-related document"""
        return self.app_name == 'purchases'

    def is_sales_document(self):
        """Check if this is a sales-related document"""
        return self.app_name == 'sales'

    def is_inventory_document(self):
        """Check if this is an inventory-related document"""
        return self.app_name == 'inventory'

    def requires_fiscal_compliance(self):
        """Check if document requires Bulgarian fiscal compliance"""
        return self.is_fiscal and self.app_name in ['sales', 'purchases']

    # =====================
    # INTEGRATION METHODS (hooks for other systems)
    # =====================

    def get_approval_rules(self):
        """Get approval rules for this document type"""
        from nomenclatures.models.approvals import ApprovalRule
        return ApprovalRule.objects.filter(
            document_type=self,
            is_active=True
        ).order_by('approval_level', 'sort_order')

    def has_approval_rules(self):
        """Check if this document type has any approval rules"""
        return self.requires_approval and self.get_approval_rules().exists()

    def get_configured_statuses(self):
        """Get all configured statuses ordered by workflow position"""
        return self.statuses.filter(
            type_configurations__document_type=self,
            type_configurations__is_active=True
        ).order_by('type_configurations__sort_order')

    def get_initial_status(self):
        """Get the initial status for new documents"""
        config = self.type_statuses.filter(
            is_initial=True,
            is_active=True
        ).first()

        if config:
            return config.status

        # Fallback
        from .statuses import DocumentStatus
        return DocumentStatus.objects.filter(code='draft').first()

    def get_initial_status_code(self):
        """Get initial status code with fallback"""
        status = self.get_initial_status()
        return status.code if status else 'draft'

    def get_final_statuses(self):
        """Get all final statuses"""
        return self.statuses.filter(
            type_configurations__document_type=self,
            type_configurations__is_final=True,
            type_configurations__is_active=True
        )

    def get_cancellation_status(self):
        """Get the cancellation status for this document type"""
        config = self.type_statuses.filter(
            is_cancellation=True,
            is_active=True
        ).first()

        if config:
            return config.status

        # Fallback
        from .statuses import DocumentStatus
        return DocumentStatus.objects.filter(code='cancelled').first()

    def has_status(self, status_code):
        """Check if this document type has a specific status"""
        return self.statuses.filter(code=status_code).exists()

    def get_status_display_name(self, status_code):
        """Get display name for a status (with custom override)"""
        config = self.type_statuses.filter(
            status__code=status_code,
            is_active=True
        ).first()

        if config:
            return config.get_display_name()

        # Fallback
        return status_code.replace('_', ' ').title()

    def can_edit_in_status(self, status_code):
        """Check if documents can be edited in this status"""
        # Special case for completed
        if status_code == 'completed' and self.allow_edit_completed:
            return True

        # Check status configuration
        status = self.statuses.filter(code=status_code).first()
        return status.allow_edit if status else False


# =================================================================
# HELPER FUNCTIONS
# =================================================================

def get_document_type_by_key(app_name, type_key):
    """
    Get DocumentType by app and type key

    Usage:
        doc_type = get_document_type_by_key('purchases', 'purchase_request')
    """
    try:
        return DocumentType.objects.get(
            app_name=app_name,
            type_key=type_key,
            is_active=True
        )
    except DocumentType.DoesNotExist:
        raise DocumentType.DoesNotExist(
            f"DocumentType '{app_name}.{type_key}' not found or inactive"
        )


def create_basic_document_types():
    """
    Create basic document types for standard POS system

    Usage:
        create_basic_document_types()  # Creates REQ, ORD, DEL, INV, etc.
    """
    basic_types = [
        # PURCHASES
        {
            'code': 'REQ',
            'name': 'Purchase Request',
            'type_key': 'purchase_request',
            'app_name': 'purchases',
            'affects_inventory': False,
            'inventory_direction': 'none',
            'requires_approval': True,
            'is_fiscal': False,
        },
        {
            'code': 'ORD',
            'name': 'Purchase Order',
            'type_key': 'purchase_order',
            'app_name': 'purchases',
            'affects_inventory': False,
            'inventory_direction': 'none',
            'requires_approval': True,
            'is_fiscal': False,
        },
        {
            'code': 'DEL',
            'name': 'Delivery Receipt',
            'type_key': 'delivery_receipt',
            'app_name': 'purchases',
            'affects_inventory': True,
            'inventory_direction': 'in',
            'requires_approval': False,
            'is_fiscal': False,
            'auto_create_movements': True,
        },

        # SALES
        {
            'code': 'INV',
            'name': 'Sales Invoice',
            'type_key': 'sales_invoice',
            'app_name': 'sales',
            'affects_inventory': True,
            'inventory_direction': 'out',
            'requires_approval': False,
            'is_fiscal': True,
            'auto_create_movements': True,
        },

        # INVENTORY
        {
            'code': 'ADJ',
            'name': 'Inventory Adjustment',
            'type_key': 'inventory_adjustment',
            'app_name': 'inventory',
            'affects_inventory': True,
            'inventory_direction': 'both',
            'requires_approval': True,
            'is_fiscal': False,
            'auto_create_movements': True,
        },
    ]

    created_types = []
    for type_data in basic_types:
        doc_type, created = DocumentType.objects.get_or_create(
            app_name=type_data['app_name'],
            type_key=type_data['type_key'],
            defaults=type_data
        )
        if created:
            created_types.append(doc_type)

    return created_types


