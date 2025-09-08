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

    # =====================
    # SEMANTIC TYPE FOR UI ACTIONS
    # =====================
    SEMANTIC_TYPE_CHOICES = [
        ('submit', _('Submit')),
        ('approve', _('Approve')),
        ('reject', _('Reject')),
        ('cancel', _('Cancel')),
        ('return_draft', _('Return to Draft')),
        ('generic', _('Generic')),
    ]
    
    semantic_type = models.CharField(
        _('Semantic Type'),
        max_length=50,
        choices=SEMANTIC_TYPE_CHOICES,
        default='generic',
        help_text=_('Semantic type for UI action buttons and transitions')
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

    allows_editing = models.BooleanField(
        _('Allows Editing'),
        default=True,
        help_text=_('Can documents be edited in this status? (overrides DocumentStatus.allow_edit)')
    )

    allows_deletion = models.BooleanField(
        _('Allows Deletion'),
        default=False,
        help_text=_('Can documents be deleted in this status? (overrides DocumentStatus.allow_delete)')
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
        """
        🎯 ENHANCED CONFIGURATION VALIDATION - PHASE 4.1

        Всички възможни логически inconsistencies и business rules!
        """
        super().clean()

        # =====================================================
        # EXISTING VALIDATIONS (запазени)
        # =====================================================

        # Unique initial status per document type
        if self.is_initial:
            existing = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                is_initial=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError({
                    'is_initial': _('This document type already has an initial status')
                })

        # Unique cancellation status per document type
        if self.is_cancellation:
            existing = DocumentTypeStatus.objects.filter(
                document_type=self.document_type,
                is_cancellation=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError({
                    'is_cancellation': _('This document type already has a cancellation status')
                })

        # =====================================================
        # INVENTORY MOVEMENT VALIDATION RULES (existing)
        # =====================================================

        # Movement creation requires inventory-affecting document type
        if self.creates_inventory_movements and not self.document_type.affects_inventory:
            raise ValidationError({
                'creates_inventory_movements': _(
                    'Cannot create.html inventory movements - document type does not affect inventory'
                )
            })

        # Movement reversal requires inventory-affecting document type
        if self.reverses_inventory_movements and not self.document_type.affects_inventory:
            raise ValidationError({
                'reverses_inventory_movements': _(
                    'Cannot reverse inventory movements - document type does not affect inventory'
                )
            })

        # Movement correction requires inventory-affecting document type
        if self.allows_movement_correction and not self.document_type.affects_inventory:
            raise ValidationError({
                'allows_movement_correction': _(
                    'Cannot allow movement correction - document type does not affect inventory'
                )
            })

        # Cannot create.html and reverse movements simultaneously
        if self.creates_inventory_movements and self.reverses_inventory_movements:
            raise ValidationError({
                'reverses_inventory_movements': _(
                    'Cannot both create.html and reverse movements in the same status'
                )
            })

        # Auto-correction requires correction to be allowed
        if self.auto_correct_movements_on_edit and not self.allows_movement_correction:
            raise ValidationError({
                'auto_correct_movements_on_edit': _(
                    'Auto-correction requires movement correction to be allowed'
                )
            })

        # =====================================================
        # BUSINESS RULES VALIDATION (existing)
        # =====================================================

        # Final statuses should not allow editing (business rule)
        if self.is_final and self.allows_editing:
            raise ValidationError({
                'allows_editing': _(
                    'Final statuses should not allow editing (business rule violation)'
                )
            })

        # Initial statuses should allow editing (business rule)
        if self.is_initial and not self.allows_editing:
            raise ValidationError({
                'allows_editing': _(
                    'Initial statuses should typically allow editing'
                )
            })

        # =====================================================
        # 🎯 NEW: EXTENDED BUSINESS RULES (Phase 4.1)
        # =====================================================

        # 1. CANCELLATION STATUS RULES
        if self.is_cancellation:
            if self.is_initial:
                raise ValidationError({
                    'is_cancellation': _(
                        'Cancellation status cannot be initial status'
                    )
                })

            if self.is_final:
                # This is actually OK - cancelled is usually final
                pass

            if self.creates_inventory_movements:
                raise ValidationError({
                    'creates_inventory_movements': _(
                        'Cancellation status should not create.html inventory movements'
                    )
                })

        # 2. INITIAL STATUS RULES
        if self.is_initial:
            if self.reverses_inventory_movements:
                raise ValidationError({
                    'reverses_inventory_movements': _(
                        'Initial status should not reverse inventory movements'
                    )
                })

            if not self.allows_editing:
                raise ValidationError({
                    'allows_editing': _(
                        'Initial status must allow editing (documents start here)'
                    )
                })

        # 3. FINAL STATUS RULES
        if self.is_final:
            if self.allows_editing and not getattr(self.document_type, 'allow_edit_completed', False):
                raise ValidationError({
                    'allows_editing': _(
                        'Final status cannot allow editing unless document type allows editing completed documents'
                    )
                })

            if self.reverses_inventory_movements:
                # This might be OK for some business cases, but warn
                pass

        # 4. INVENTORY DIRECTION CONSISTENCY
        if self.document_type.affects_inventory:
            direction = self.document_type.inventory_direction

            if direction == 'in':
                if self.reverses_inventory_movements and not self.creates_inventory_movements:
                    raise ValidationError({
                        'reverses_inventory_movements': _(
                            'Cannot reverse IN movements without creating them first (direction: in)'
                        )
                    })

            elif direction == 'out':
                if self.creates_inventory_movements and not self.reverses_inventory_movements:
                    # OUT movements should typically be created directly
                    pass

        # 5. AUTO-RECEIVE INTEGRATION
        if hasattr(self.document_type, 'auto_receive') and self.document_type.auto_receive:
            if not self.creates_inventory_movements:
                raise ValidationError({
                    'creates_inventory_movements': _(
                        'Auto-receive document type requires status that creates inventory movements'
                    )
                })

            if self.document_type.inventory_direction not in ['in', 'both']:
                raise ValidationError({
                    'creates_inventory_movements': _(
                        'Auto-receive only works with incoming inventory documents'
                    )
                })

        # 6. FISCAL DOCUMENT RULES
        if self.document_type.is_fiscal:
            if self.allows_editing and self.is_final:
                raise ValidationError({
                    'allows_editing': _(
                        'Fiscal documents cannot be edited after finalization (Bulgarian law)'
                    )
                })

            if self.reverses_inventory_movements:
                # Fiscal documents need special handling for reversals
                # Това може да се разреши с отделен метод за fiscal reversals
                pass

        # 7. APPROVAL INTEGRATION
        if self.document_type.requires_approval:
            # Проверки за approval workflow consistency
            if self.is_final and not self._has_approval_path():
                raise ValidationError({
                    'is_final': _(
                        'Final status in approval-required document type must have approval path'
                    )
                })

        # 8. MOVEMENT CORRECTION BUSINESS RULES
        if self.allows_movement_correction:
            if self.is_initial:
                # Initial documents shouldn't need correction (they just started)
                raise ValidationError({
                    'allows_movement_correction': _(
                        'Initial status should not allow movement correction (no movements to correct yet)'
                    )
                })

            if self.is_cancellation:
                # Cancelled documents might need correction to undo effects
                pass

        # 9. AUTO-CORRECTION SAFETY RULES
        if self.auto_correct_movements_on_edit:
            if self.is_final and not self.allows_editing:
                raise ValidationError({
                    'auto_correct_movements_on_edit': _(
                        'Cannot auto-correct in non-editable final status'
                    )
                })

        # 10. LOGICAL CONSISTENCY CROSS-CHECKS
        if not self.allows_editing and not self.allows_deletion and self.is_initial:
            raise ValidationError({
                'allows_editing': _(
                    'Initial status must allow either editing or deletion (otherwise documents get stuck)'
                )
            })

        # 11. BULGARIAN LEGAL REQUIREMENTS
        if self.document_type.is_fiscal:
            if self.allows_deletion and self.is_final:
                raise ValidationError({
                    'allows_deletion': _(
                        'Final fiscal documents cannot be deleted (Bulgarian law - only reversals allowed)'
                    )
                })



    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_display_name(self):
        """Get the display name (custom or default)"""
        return self.custom_name or self.status.name

    def can_create_movements(self) -> bool:
        """Check if this status can create.html inventory movements"""
        return (
                self.creates_inventory_movements and
                self.document_type.affects_inventory

        )

    def can_reverse_movements(self) -> bool:
        """Check if this status can reverse inventory movements"""
        return (
                self.reverses_inventory_movements and
                self.document_type.affects_inventory
        )

    def can_correct_movements(self) -> bool:
        """Check if movements can be corrected in this status"""
        return (
                self.allows_movement_correction and
                self.document_type.affects_inventory
        )

    def should_auto_correct(self) -> bool:
        """Check if movements should be auto-corrected on edit"""
        return (
                self.auto_correct_movements_on_edit and
                self.can_correct_movements()
        )

    def get_movement_behavior(self) -> dict:
        """Get complete movement behavior summary for this status"""
        return {
            'creates_movements': self.can_create_movements(),
            'reverses_movements': self.can_reverse_movements(),
            'allows_correction': self.can_correct_movements(),
            'auto_correct': self.should_auto_correct(),
            'inventory_direction': self.document_type.inventory_direction,
            'affects_inventory': self.document_type.affects_inventory,
        }

    def _has_approval_path(self):
        """Helper: Check if there's an approval path to this status"""
        try:
            from .approvals import ApprovalRule
            return ApprovalRule.objects.filter(
                document_type=self.document_type,
                to_status_obj__code=self.status.code,
                is_active=True
            ).exists()
        except ImportError:
            return True  # Assume OK if approval system not available