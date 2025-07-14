# purchases/models/document_types.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class DocumentType(models.Model):
    """
    Configuration for different types of purchase documents

    Defines the behavior and rules for:
    - REQ (Purchase Requests)
    - ORD (Purchase Orders)
    - DEL (Delivery Receipts)
    - INV (Purchase Invoices)
    """

    # =====================
    # BASIC IDENTIFICATION
    # =====================
    code = models.CharField(
        _('Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique code like REQ, ORD, DEL, INV')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Human readable name')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of this document type')
    )

    # =====================
    # TYPE CLASSIFICATION
    # =====================
    TYPE_KEY_CHOICES = [
        ('request', _('Request')),  # Purchase requests
        ('order', _('Order')),  # Purchase orders
        ('delivery', _('Delivery')),  # Delivery receipts
        ('invoice', _('Invoice')),  # Purchase invoices
        ('adjustment', _('Adjustment')),  # Stock adjustments
        ('transfer', _('Transfer')),  # Inter-location transfers
        ('stock_out', _('Stock Out')),  # Stock reductions
    ]

    type_key = models.CharField(
        _('Type Key'),
        max_length=20,
        choices=TYPE_KEY_CHOICES,
        help_text=_('Classification of document behavior')
    )

    # =====================
    # STOCK IMPACT
    # =====================
    STOCK_EFFECT_CHOICES = [
        (1, _('Increases stock')),
        (-1, _('Decreases stock')),
        (0, _('No effect')),
    ]

    stock_effect = models.IntegerField(
        _('Stock Effect'),
        choices=STOCK_EFFECT_CHOICES,
        default=0,
        help_text=_('How this document type affects inventory levels')
    )

    allow_reverse_operations = models.BooleanField(
        _('Allow Reverse Operations'),
        default=False,
        help_text=_('Allow negative quantities to reverse the stock effect')
    )

    # =====================
    # WORKFLOW SETTINGS
    # =====================
    can_be_source = models.BooleanField(
        _('Can Be Source'),
        default=False,
        help_text=_('Whether this document type can be source for other documents')
    )

    can_reference_multiple_sources = models.BooleanField(
        _('Can Reference Multiple Sources'),
        default=False,
        help_text=_('Whether this document can be created from multiple source documents')
    )

    auto_confirm = models.BooleanField(
        _('Auto Confirm'),
        default=False,
        help_text=_('Automatically confirm document upon creation')
    )

    auto_receive = models.BooleanField(
        _('Auto Receive'),
        default=False,
        help_text=_('Automatically mark as received when confirmed')
    )

    # =====================
    # PRODUCT REQUIREMENTS
    # =====================
    requires_batch = models.BooleanField(
        _('Requires Batch'),
        default=False,
        help_text=_('Whether batch numbers are required for products')
    )

    requires_expiry = models.BooleanField(
        _('Requires Expiry'),
        default=False,
        help_text=_('Whether expiry dates are required for products')
    )

    requires_quality_check = models.BooleanField(
        _('Requires Quality Check'),
        default=False,
        help_text=_('Whether quality approval is required')
    )

    # =====================
    # SYSTEM SETTINGS
    # =====================
    is_system_type = models.BooleanField(
        _('System Type'),
        default=False,
        help_text=_('System-defined type that cannot be deleted')
    )

    is_active = models.BooleanField(
        _('Active'),
        default=True,
        help_text=_('Whether this document type is available for use')
    )

    # =====================
    # ORDERING AND DISPLAY
    # =====================
    sort_order = models.PositiveIntegerField(
        _('Sort Order'),
        default=10,
        help_text=_('Order for displaying in lists')
    )

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['type_key']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """Validate document type configuration"""
        super().clean()

        # Code should be uppercase
        if self.code:
            self.code = self.code.upper()

        # Validation rules based on type_key
        if self.type_key == 'request':
            # Requests don't affect stock
            if self.stock_effect != 0:
                raise ValidationError({
                    'stock_effect': _('Request documents should not affect stock')
                })

        elif self.type_key == 'order':
            # Orders don't affect stock until received
            if self.stock_effect != 0:
                raise ValidationError({
                    'stock_effect': _('Order documents should not affect stock')
                })

        elif self.type_key == 'delivery':
            # Deliveries should increase stock
            if self.stock_effect != 1:
                raise ValidationError({
                    'stock_effect': _('Delivery documents should increase stock')
                })

    # =====================
    # PROPERTIES
    # =====================
    @property
    def auto_create_inventory_movements(self):
        """Determines if inventory movements should be auto-created"""
        return self.stock_effect != 0

    @property
    def is_request_type(self):
        return self.type_key == 'request'

    @property
    def is_order_type(self):
        return self.type_key == 'order'

    @property
    def is_delivery_type(self):
        return self.type_key == 'delivery'

    @property
    def is_invoice_type(self):
        return self.type_key == 'invoice'

    # =====================
    # WORKFLOW METHODS
    # =====================
    def get_allowed_source_types(self):
        """Get document types that can be sources for this type"""
        if self.type_key == 'order':
            # Orders can be created from requests
            return DocumentType.objects.filter(type_key='request', is_active=True)

        elif self.type_key == 'delivery':
            # Deliveries can be created from orders
            return DocumentType.objects.filter(type_key='order', is_active=True)

        elif self.type_key == 'invoice':
            # Invoices can be created from deliveries
            return DocumentType.objects.filter(type_key='delivery', is_active=True)

        return DocumentType.objects.none()

    def get_next_document_types(self):
        """Get document types that can be created from this type"""
        if self.type_key == 'request':
            # Requests can create orders
            return DocumentType.objects.filter(type_key='order', is_active=True)

        elif self.type_key == 'order':
            # Orders can create deliveries
            return DocumentType.objects.filter(type_key='delivery', is_active=True)

        elif self.type_key == 'delivery':
            # Deliveries can create invoices
            return DocumentType.objects.filter(type_key='invoice', is_active=True)

        return DocumentType.objects.none()

    def get_default_status(self):
        """Get default status for documents of this type"""
        if self.auto_confirm:
            return 'confirmed'
        return 'draft'

    def get_number_prefix(self):
        """Get prefix for document numbering"""
        return self.code

    # =====================
    # VALIDATION HELPERS
    # =====================
    def validate_line_requirements(self, line_data):
        """Validate line data against document type requirements"""
        errors = {}

        if self.requires_batch and not line_data.get('batch_number'):
            errors['batch_number'] = _('Batch number is required for this document type')

        if self.requires_expiry and not line_data.get('expiry_date'):
            errors['expiry_date'] = _('Expiry date is required for this document type')

        if errors:
            raise ValidationError(errors)

        return True

    def can_create_from_source(self, source_document_type):
        """Check if this document type can be created from source type"""
        allowed_sources = self.get_allowed_source_types()
        return source_document_type in allowed_sources

    # =====================
    # MANAGER METHODS
    # =====================
    @classmethod
    def get_request_types(cls):
        """Get all request document types"""
        return cls.objects.filter(type_key='request', is_active=True)

    @classmethod
    def get_order_types(cls):
        """Get all order document types"""
        return cls.objects.filter(type_key='order', is_active=True)

    @classmethod
    def get_delivery_types(cls):
        """Get all delivery document types"""
        return cls.objects.filter(type_key='delivery', is_active=True)

    @classmethod
    def get_by_code(cls, code):
        """Get document type by code"""
        try:
            return cls.objects.get(code=code.upper(), is_active=True)
        except cls.DoesNotExist:
            return None

    @classmethod
    def create_system_types(cls):
        """Create default system document types"""
        system_types = [
            {
                'code': 'REQ',
                'name': 'Purchase Request',
                'type_key': 'request',
                'stock_effect': 0,
                'can_be_source': True,
                'description': 'Purchase requests from stores/departments',
                'sort_order': 10,
                'is_system_type': True,
            },
            {
                'code': 'ORD',
                'name': 'Purchase Order',
                'type_key': 'order',
                'stock_effect': 0,
                'can_be_source': True,
                'description': 'Purchase orders sent to suppliers',
                'sort_order': 20,
                'is_system_type': True,
            },
            {
                'code': 'DEL',
                'name': 'Delivery Receipt',
                'type_key': 'delivery',
                'stock_effect': 1,
                'can_reference_multiple_sources': True,
                'requires_batch': True,
                'requires_quality_check': True,
                'description': 'Delivery receipts for goods received',
                'sort_order': 30,
                'is_system_type': True,
            },
            {
                'code': 'INV',
                'name': 'Purchase Invoice',
                'type_key': 'invoice',
                'stock_effect': 0,
                'description': 'Purchase invoices from suppliers',
                'sort_order': 40,
                'is_system_type': True,
            },
        ]

        created_types = []
        for type_data in system_types:
            document_type, created = cls.objects.get_or_create(
                code=type_data['code'],
                defaults=type_data
            )
            if created:
                created_types.append(document_type)

        return created_types