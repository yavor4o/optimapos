"""
Document Status System Models

Централизирана система за управление на статуси на документи.
Позволява конфигуриране без код промени.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class DocumentStatus(models.Model):
    """
    Речник на всички възможни статуси в системата.
    Един статус може да се използва от множество типове документи.
    """

    # =====================
    # CORE FIELDS
    # =====================
    code = models.CharField(
        _('Status Code'),
        max_length=30,
        unique=True,
        help_text=_('Unique code like: draft, submitted, approved')
    )

    name = models.CharField(
        _('Display Name'),
        max_length=100,
        help_text=_('Name shown in UI')
    )

    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of this status')
    )

    # =====================
    # PERMISSIONS
    # =====================
    allow_edit = models.BooleanField(
        _('Allow Edit'),
        default=False,
        help_text=_('Can documents in this status be edited?')
    )

    allow_delete = models.BooleanField(
        _('Allow Delete'),
        default=False,
        help_text=_('Can documents in this status be deleted?')
    )

    # =====================
    # UI SETTINGS
    # =====================
    color = models.CharField(
        _('Color'),
        max_length=7,
        default='#6c757d',
        help_text=_('HEX color for badges (#RRGGBB)')
    )

    icon = models.CharField(
        _('Icon Class'),
        max_length=50,
        blank=True,
        help_text=_('CSS class for icon (e.g., fa-check, bi-check-circle)')
    )

    badge_class = models.CharField(
        _('Badge CSS Class'),
        max_length=50,
        default='badge-secondary',
        help_text=_('Bootstrap badge class')
    )

    # =====================
    # SYSTEM FLAGS
    # =====================
    is_system = models.BooleanField(
        _('System Status'),
        default=False,
        help_text=_('System status that cannot be deleted')
    )

    is_active = models.BooleanField(
        _('Active'),
        default=True,
        help_text=_('Is this status available for use?')
    )

    # =====================
    # METADATA
    # =====================
    sort_order = models.IntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('Order for display')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nomenclature_document_status'
        ordering = ['sort_order', 'name']
        verbose_name = _('Document Status')
        verbose_name_plural = _('Document Statuses')
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        """Validate status configuration"""
        # Color validation
        if self.color and not self.color.startswith('#'):
            raise ValidationError({
                'color': _('Color must be in HEX format (#RRGGBB)')
            })

        # System status cannot be inactive
        if self.is_system and not self.is_active:
            raise ValidationError({
                'is_active': _('System statuses cannot be deactivated')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DocumentTypeStatus(models.Model):
    """
    Конфигурация как статус се използва за конкретен тип документ.
    ManyToMany връзка между DocumentType и DocumentStatus.
    """

    # =====================
    # RELATIONSHIPS
    # =====================
    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.CASCADE,
        related_name='type_statuses',
        verbose_name=_('Document Type')
    )

    status = models.ForeignKey(
        DocumentStatus,
        on_delete=models.CASCADE,
        related_name='type_configurations',
        verbose_name=_('Status')
    )

    # =====================
    # ROLE IN WORKFLOW
    # =====================
    is_initial = models.BooleanField(
        _('Initial Status'),
        default=False,
        help_text=_('Is this the starting status for new documents?')
    )

    is_final = models.BooleanField(
        _('Final Status'),
        default=False,
        help_text=_('Is this a final status (no transitions from it)?')
    )

    is_cancellation = models.BooleanField(
        _('Cancellation Status'),
        default=False,
        help_text=_('Is this the cancellation status for this type?')
    )

    # INVENTORY CONTROL FIELDS (добави в края на класа)
    creates_inventory_movements = models.BooleanField(
        _('Creates Inventory Movements'),
        default=False,
        help_text=_('Should inventory movements be created when document enters this status?')
    )

    reverses_inventory_movements = models.BooleanField(
        _('Reverses Inventory Movements'),
        default=False,
        help_text=_('Should existing inventory movements be reversed when document enters this status?')
    )

    allows_movement_correction = models.BooleanField(
        _('Allows Movement Correction'),
        default=False,
        help_text=_('Can inventory movements be corrected when document is in this status?')
    )

    auto_correct_movements_on_edit = models.BooleanField(
        _('Auto Correct Movements on Edit'),
        default=False,
        help_text=_('Automatically sync movements when document content is edited in this status?')
    )

    # =====================
    # CUSTOMIZATION
    # =====================
    custom_name = models.CharField(
        _('Custom Name'),
        max_length=100,
        blank=True,
        help_text=_('Override status name for this document type')
    )

    sort_order = models.IntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('Order in workflow')
    )

    # =====================
    # METADATA
    # =====================
    is_active = models.BooleanField(
        _('Active'),
        default=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nomenclature_document_type_status'
        ordering = ['document_type', 'sort_order']
        verbose_name = _('Document Type Status Configuration')
        verbose_name_plural = _('Document Type Status Configurations')
        unique_together = [['document_type', 'status']]
        indexes = [
            models.Index(fields=['document_type', 'is_initial']),
            models.Index(fields=['document_type', 'is_final']),
            models.Index(fields=['document_type', 'is_cancellation']),
        ]

    def __str__(self):
        name = self.custom_name or self.status.name
        return f"{self.document_type.name} - {name}"

    def clean(self):
        """Validate configuration"""
        # Only one initial status per document type
        if self.is_initial:
            existing = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                is_initial=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError({
                    'is_initial': _('This document type already has an initial status')
                })

        # Only one cancellation status per document type
        if self.is_cancellation:
            existing = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                is_cancellation=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError({
                    'is_cancellation': _('This document type already has a cancellation status')
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_display_name(self):
        """Get the display name (custom or default)"""
        return self.custom_name or self.status.name