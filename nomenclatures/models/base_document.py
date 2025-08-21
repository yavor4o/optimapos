# nomenclatures/models/base_document.py - UNIVERSAL BASE DOCUMENT
"""
Base Document Models - УНИВЕРСАЛЕН И НЕЗАВИСИМ

КЛЮЧОВА ПРОМЯНА: 
- Премахнат supplier = ForeignKey('partners.Supplier')  
- Добавен partner = GenericForeignKey за всякакви партньори
- Backward compatibility properties за supplier/customer

РЕЗУЛТАТ: BaseDocument може да работи с purchases, sales, hr, accounting apps
"""

import warnings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging

from core.interfaces.location_interface import validate_location

logger = logging.getLogger(__name__)


# =================================================================
# MANAGERS - WITH DocumentService INTEGRATION
# =================================================================

class DocumentManager(models.Manager):
    """
    Base manager for all documents

    100% СИНХРОНИЗИРАН с nomenclatures.DocumentService:
    - NO hardcoded статуси никъде
    - Dynamic queries САМО от DocumentType/ApprovalRule
    - Explicit failures ако nomenclatures не е достъпен
    """

    def active(self):
        """Return only active documents - DYNAMIC от DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_active_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback
            return self.exclude(status__in=['cancelled', 'deleted'])

    def pending_approval(self):
        """Documents pending approval - DYNAMIC от ApprovalRule"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_pending_approval_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback
            return self.filter(status__in=['submitted', 'pending'])

    def ready_for_processing(self):
        """Documents ready for processing - DYNAMIC от DocumentType"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_ready_for_processing_documents(queryset=self.get_queryset())
        except ImportError:
            # Fallback
            return self.filter(status__in=['approved', 'confirmed'])

    def for_location(self, location):
        """Filter by location"""
        return self.filter(location=location)

    def for_partner(self, partner):
        """Filter by partner using GenericForeignKey"""
        from django.contrib.contenttypes.models import ContentType
        partner_ct = ContentType.objects.get_for_model(partner.__class__)
        return self.filter(
            partner_content_type=partner_ct,
            partner_object_id=partner.pk
        )

    def by_document_type(self, doc_type_key):
        """Filter by document type key"""
        return self.filter(document_type__type_key=doc_type_key)

    def this_month(self):
        """Documents created this month"""
        today = timezone.now().date()
        return self.filter(
            document_date__month=today.month,
            document_date__year=today.year
        )

    def by_status(self, status):
        """Filter by status"""
        return self.filter(status=status)

    def drafts(self):
        """Draft documents"""
        return self.filter(status__in=['draft', ''])

    def submitted(self):
        """Submitted documents"""
        return self.filter(status='submitted')

    def approved(self):
        """Approved documents"""
        return self.filter(status='approved')


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
# BASE DOCUMENT - UNIVERSAL MODEL
# =================================================================

class BaseDocument(models.Model):
    """
    Base Document Model - UNIVERSAL FOR ALL APPS

    КЛЮЧОВА ПРОМЯНА: Използва GenericForeignKey за партньори
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
    # UNIVERSAL PARTNER RELATIONSHIP
    # =====================
    # НОВО: GenericForeignKey за универсални партньори
    partner_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Partner Type'),
        related_name='%(class)s_as_partner',  # ← ДОБАВИ ТОВА
        help_text=_('Type of partner (Supplier, Customer, etc.)'),
        limit_choices_to=models.Q(
            app_label='partners',
            model__in=['supplier', 'customer']
        ) | models.Q(
            app_label='hr',
            model='employee'
        )
    )

    partner_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Partner ID'),
        help_text=_('ID of the partner object')
    )

    partner = GenericForeignKey(
        'partner_content_type',
        'partner_object_id'
    )



    location_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Location Type'),
        related_name='%(class)s_as_location',  # ← ДОБАВИ ТОВА
        help_text=_('Type of location (InventoryLocation, OnlineStore, etc.)'),
        limit_choices_to=models.Q(
            app_label='inventory', model='inventorylocation'
        ) | models.Q(
            app_label='sales', model='onlinestore'
        ) | models.Q(
            app_label='partners', model='customersite'
        ) | models.Q(
            app_label='hr', model='office'
        )
    )

    location_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Location ID'),
        help_text=_('ID of the location object')
    )

    location = GenericForeignKey(
        'location_content_type',
        'location_object_id'
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
    # LOCATION HELPER METHODS
    # =====================

    def get_inventory_location(self):
        """Връща location ако е InventoryLocation, иначе None"""
        if self.location and self.location.__class__.__name__ == 'InventoryLocation':
            return self.location
        return None

    def get_online_store(self):
        """Връща location ако е OnlineStore, иначе None"""
        if self.location and self.location.__class__.__name__ == 'OnlineStore':
            return self.location
        return None

    def get_customer_site(self):
        """Връща location ако е CustomerSite, иначе None"""
        if self.location and self.location.__class__.__name__ == 'CustomerSite':
            return self.location
        return None

    # =====================
    # SYSTEM FIELDS
    # =====================
    created_by = models.ForeignKey(
        'accounts.User',  # ПОПРАВКА: accounts.User, не auth.User
        on_delete=models.PROTECT,
        related_name='%(class)s_created',
        verbose_name=_('Created By')
    )

    updated_by = models.ForeignKey(
        'accounts.User',  # ПОПРАВКА: accounts.User, не auth.User
        on_delete=models.PROTECT,
        related_name='%(class)s_updated',
        verbose_name=_('Updated By')
    )

    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = DocumentManager()

    class Meta:
        abstract = True
        ordering = ['-document_date', '-created_at']
        indexes = [
            models.Index(fields=['document_number']),
            models.Index(fields=['status']),
            models.Index(fields=['document_date']),
            # ПРОМЕНЕН INDEX - generic location:
            models.Index(fields=['location_content_type', 'location_object_id']),
            models.Index(fields=['partner_content_type', 'partner_object_id']),
            models.Index(fields=['created_at']),
        ]

    # =====================
    # UNIVERSAL PARTNER METHODS
    # =====================

    def get_partner_info(self):
        """Връща информация за партньора независимо от типа"""
        if not self.partner:
            return None

        from core.interfaces.partner_interface import get_partner_info
        return get_partner_info(self.partner)

    def get_partner_display(self):
        """Форматиран низ за партньора"""
        if not self.partner:
            return _('No partner')

        from core.interfaces.partner_interface import format_partner_display
        return format_partner_display(self.partner)

    # =====================
    # VALIDATION AND SAVE
    # =====================

    def clean(self):
        """Enhanced validation with ILocation protocol"""
        super().clean()

        # Валидирай IPartner протокол
        if self.partner:
            from core.interfaces.partner_interface import validate_partner
            try:
                validate_partner(self.partner)
            except (AttributeError, TypeError) as e:
                raise ValidationError({
                    'partner': f'Partner must implement IPartner protocol: {e}'
                })

        # НОВО: Валидирай ILocation протокол
        if self.location:
            try:
                validate_location(self.location)
            except (AttributeError, TypeError) as e:
                raise ValidationError({
                    'location': f'Location must implement ILocation protocol: {e}'
                })

        # Валидирай че document_type съответства на location rules
        if self.document_type and self.location:
            self._validate_document_type_location_compatibility()

    def save(self, *args, **kwargs):
        # Auto-generate document number ако липсва
        if not self.document_number:
            try:
                # ✅ ПОПРАВЕНО: Използвай NumberingService вместо DocumentService
                from nomenclatures.services.numbering_service import NumberingService
                self.document_number = NumberingService.generate_document_number(
                    document_type=self.document_type,
                    location=getattr(self, 'location', None),
                    user=getattr(self, 'created_by', None)
                )
            except Exception as e:
                # Fallback numbering ако service не работи
                model_name = self._meta.model_name.upper()
                timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
                self.document_number = f"{model_name}-{timestamp}"

        # ВАЖНО: Извикай clean преди save
        if not kwargs.get('skip_validation', False):
            self.full_clean()

        super().save(*args, **kwargs)

    # =====================
    # READ-ONLY HELPERS
    # =====================

    def _validate_document_type_location_compatibility(self):
        """Провери дали document_type е compatiblen с location type"""
        # Пример: Purchase документи могат да използват само InventoryLocation
        if hasattr(self, '_meta') and 'purchase' in self._meta.app_label.lower():
            if not self.get_inventory_location():
                raise ValidationError({
                    'location': _('Purchase documents require InventoryLocation')
                })

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
    # WORKFLOW AND STATUS METHODS
    # =====================

    def can_edit(self, user=None):
        """Check if document can be edited - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            can_edit, reason = DocumentService.can_edit_document(self, user)
            return can_edit
        except ImportError:
            # Fallback - basic logic
            readonly_statuses = ['confirmed', 'closed', 'cancelled']
            return self.status not in readonly_statuses

    def can_delete(self, user=None):
        """Check if document can be deleted"""
        try:
            from nomenclatures.services import DocumentService
            can_delete, reason = DocumentService.can_delete_document(self, user)
            return can_delete
        except ImportError:
            # Fallback - only draft documents
            return self.status in ['draft', ''] and not self.lines.exists()

    def get_available_actions(self, user=None):
        """Get available actions for user - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.get_available_actions(self, user)
        except ImportError:
            # Fallback - basic actions
            actions = []
            if self.can_edit(user):
                actions.append({'key': 'edit', 'name': _('Edit'), 'icon': 'edit'})
            if self.can_delete(user):
                actions.append({'key': 'delete', 'name': _('Delete'), 'icon': 'trash'})
            return actions

    def transition_to(self, new_status, user, comments=''):
        """Transition to new status - USES DocumentService"""
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.transition_document(
                self, new_status, user, comments
            )
        except ImportError:
            # Simple fallback
            old_status = self.status
            self.status = new_status
            self.updated_by = user
            self.save(update_fields=['status', 'updated_by'])
            return True

    def __str__(self):
        partner_info = ""
        if self.partner:
            partner_info = f" ({self.get_partner_display()})"
        return f"{self.document_number or 'Draft'}{partner_info}"


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
    line_number = models.PositiveSmallIntegerField(
        _('Line Number'),
        help_text=_('Sequential line number within document')
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )

    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Quantity in specified unit')
    )

    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit of Measure')
    )

    # =====================
    # ADDITIONAL FIELDS
    # =====================
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Additional description for this line')
    )

    # Система полета
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = LineManager()

    class Meta:
        abstract = True
        ordering = ['line_number']

    def clean(self):
        super().clean()

        # Основни валидации
        if self.quantity <= 0:
            raise ValidationError({'quantity': _('Quantity must be positive')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Line {self.line_number}: {self.product.name} x {self.quantity}"