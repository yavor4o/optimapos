# nomenclatures/models/numbering.py - CLEANED VERSION
"""
Document Numbering System - Bulgarian Standard

РЕФАКТОРИРАНЕ: Почистена от дублирана логика с NumberingService

АРХИТЕКТУРА:
- NumberingConfiguration: основни настройки за номерация
- LocationNumberingAssignment: връзка между location и numbering config
- UserNumberingPreference: user preferences за избор на numbering

PRINCIPII СЛЕД РЕФАКТОРИРАНЕ:
- Моделът управлява САМО database operations
- NumberingService управлява business logic
- НЕ дублираме formatting logic
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from .base_nomenclature import BaseNomenclature, BaseNomenclatureManager
import re

User = get_user_model()


# =================================================================
# NUMBERING CONFIGURATION MANAGER
# =================================================================

class NumberingConfigurationManager(BaseNomenclatureManager):
    """Manager за numbering configurations - БЕЗ дублирана логика"""

    def for_document_type(self, document_type):
        """Get configs for specific document type"""
        return self.active().filter(document_type=document_type)

    def for_location(self, location):
        """Get configs for specific location - FIXED"""
        content_type = ContentType.objects.get_for_model(location.__class__)
        return self.active().filter(
            location_assignments__location_content_type=content_type,
            location_assignments__location_object_id=location.pk,
            location_assignments__is_active=True
        )

    def fiscal_configs(self):
        """Get fiscal numbering configurations"""
        return self.active().filter(numbering_type='fiscal')

    def internal_configs(self):
        """Get internal numbering configurations"""
        return self.active().filter(numbering_type='internal')

    def default_for_document_type(self, document_type):
        """Get default config for document type"""
        return self.active().filter(
            document_type=document_type,
            is_default=True
        ).first()


# =================================================================
# NUMBERING CONFIGURATION - CORE MODEL
# =================================================================

class NumberingConfiguration(BaseNomenclature):
    """
    Numbering Configuration - CLEANED VERSION

    САМО database schema и basic operations.
    Business logic е преместена в NumberingService!
    """

    # =====================
    # CORE RELATION
    # =====================

    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.CASCADE,
        related_name='numbering_configs',
        verbose_name=_('Document Type')
    )

    # =====================
    # NUMBERING TYPE
    # =====================

    NUMBERING_TYPE_CHOICES = [
        ('fiscal', _('Fiscal (10 digits, no prefix) - Bulgarian law')),
        ('internal', _('Internal (flexible prefix + digits)')),
    ]

    numbering_type = models.CharField(
        _('Numbering Type'),
        max_length=20,
        choices=NUMBERING_TYPE_CHOICES,
        help_text=_('Fiscal documents must use 10-digit format without prefix')
    )

    # =====================
    # FORMAT CONFIGURATION
    # =====================

    prefix = models.CharField(
        _('Prefix'),
        max_length=10,
        blank=True,
        help_text=_('Document prefix: REQ, PO, VAR-REQ (empty for fiscal documents)')
    )

    digits_count = models.PositiveIntegerField(
        _('Digits Count'),
        default=4,
        help_text=_('Number of digits: 4=0001, 10=0000000001 (minimum 10 for fiscal)')
    )

    current_number = models.PositiveIntegerField(
        _('Current Number'),
        default=0,
        help_text=_('Last issued number (next will be current_number + 1)')
    )

    # =====================
    # MICROINVEST COMPATIBILITY
    # =====================

    series_number = models.PositiveIntegerField(
        _('Series Number'),
        default=1,
        help_text=_('Series identifier like Microinvest: (1), (2), (23)')
    )

    series_name = models.CharField(
        _('Series Name'),
        max_length=100,
        blank=True,
        help_text=_('Human-readable series name: "София магазин", "Варна офис"')
    )

    # =====================
    # BEHAVIOR SETTINGS
    # =====================

    reset_yearly = models.BooleanField(
        _('Reset Yearly'),
        default=False,
        help_text=_('Reset counter to 0 each year (not recommended for fiscal)')
    )

    last_reset_year = models.PositiveIntegerField(
        _('Last Reset Year'),
        null=True,
        blank=True,
        help_text=_('Year when counter was last reset')
    )

    is_default = models.BooleanField(
        _('Is Default'),
        default=False,
        help_text=_('Default numbering for this document type (only one per type)')
    )

    # =====================
    # CONSTRAINTS
    # =====================

    max_number = models.PositiveIntegerField(
        _('Max Number'),
        null=True,
        blank=True,
        help_text=_('Maximum allowed number (prevents overflow)')
    )

    # =====================
    # MANAGERS & META
    # =====================

    objects = NumberingConfigurationManager()

    class Meta:
        verbose_name = _('Numbering Configuration')
        verbose_name_plural = _('Numbering Configurations')
        ordering = ['document_type', 'series_number', 'name']
        indexes = [
            models.Index(fields=['document_type', 'numbering_type']),
            models.Index(fields=['document_type', 'is_default']),
            models.Index(fields=['numbering_type', 'is_active']),
            models.Index(fields=['series_number']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['document_type', 'series_number'],
                name='unique_document_type_series'
            ),
            models.UniqueConstraint(
                fields=['document_type', 'is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_per_document_type'
            )
        ]

    def __str__(self):
        if self.series_name:
            return f"{self.document_type.name} ({self.series_number}) - {self.series_name}"
        else:
            return f"{self.document_type.name} ({self.series_number})"

    def clean(self):
        """
        Model validation - САМО schema validations!
        Business rules са в NumberingService.
        """
        super().clean()

        # Basic fiscal document validation
        if self.numbering_type == 'fiscal':
            if self.prefix:
                raise ValidationError({
                    'prefix': _('Fiscal documents cannot have prefix (Bulgarian law)')
                })

            if self.digits_count < 10:
                raise ValidationError({
                    'digits_count': _('Fiscal documents require minimum 10 digits (Bulgarian law)')
                })

        # Internal document validation
        elif self.numbering_type == 'internal':
            if self.digits_count < 1:
                raise ValidationError({
                    'digits_count': _('Must have at least 1 digit')
                })

        # Prefix format validation
        if self.prefix:
            if not re.match(r'^[A-Z0-9\-]+$', self.prefix):
                raise ValidationError({
                    'prefix': _('Prefix can only contain uppercase letters, numbers, and dashes')
                })

        # Max number validation
        if self.max_number and self.current_number > self.max_number:
            raise ValidationError({
                'max_number': _('Current number exceeds maximum allowed number')
            })

    # =====================
    # DATABASE OPERATIONS САМО - БЕЗ BUSINESS LOGIC!
    # =====================

    @transaction.atomic
    def increment_counter(self):
        """
        САМО database increment - БЕЗ formatting!
        Business logic е в NumberingService.

        Returns:
            int: New current_number
        """
        # Lock за update
        config = NumberingConfiguration.objects.select_for_update().get(pk=self.pk)

        # Check yearly reset
        current_year = timezone.now().year
        if config.reset_yearly and config.last_reset_year != current_year:
            config.current_number = 0
            config.last_reset_year = current_year

        # Increment
        config.current_number += 1

        # Limit check
        if config.max_number and config.current_number > config.max_number:
            raise ValidationError(f'Number limit exceeded: {config.max_number}')

        # Save САМО числото
        config.save(update_fields=['current_number', 'last_reset_year'])

        # Refresh self
        self.refresh_from_db()

        return config.current_number

    def reset_counter(self, new_value=0):
        """
        Reset counter to specific value

        Args:
            new_value: New counter value (default 0)
        """
        self.current_number = new_value
        self.last_reset_year = timezone.now().year
        self.save(update_fields=['current_number', 'last_reset_year'])

    def preview_next_number(self):
        """
        Preview next number БЕЗ increment

        Returns:
            int: Next number που ще бъде vydaden
        """
        next_num = self.current_number + 1

        # Check yearly reset
        current_year = timezone.now().year
        if self.reset_yearly and self.last_reset_year != current_year:
            next_num = 1

        return next_num

    # =====================
    # REMOVED: get_next_number() method
    # REASON: Дублира логиката на NumberingService
    # USE: NumberingService.generate_document_number() instead
    # =====================


# =================================================================
# LOCATION NUMBERING ASSIGNMENT - UNCHANGED
# =================================================================

class LocationNumberingAssignment(models.Model):
    """
    Location-specific numbering assignments - НЕ СЕ ПРОМЕНЯ
    """

    # =====================
    # CORE RELATIONS
    # =====================

    numbering_config = models.ForeignKey(
        NumberingConfiguration,
        on_delete=models.CASCADE,
        related_name='location_assignments',
        verbose_name=_('Numbering Configuration')
    )

    location_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name=_('Location Type'),
        limit_choices_to=models.Q(
            app_label='inventory', model='inventorylocation'
        ) | models.Q(
            app_label='sales', model='onlinestore'
        ) | models.Q(
            app_label='partners', model='customersite'
        )
    )

    location_object_id = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name=_('Location ID')
    )

    location = GenericForeignKey(
        'location_content_type', 'location_object_id'
    )

    # =====================
    # SETTINGS
    # =====================

    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this assignment is currently active')
    )

    assigned_at = models.DateTimeField(
        _('Assigned At'),
        auto_now_add=True
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='numbering_assignments_made',
        verbose_name=_('Assigned By'),
        null=True,  # ADDED: За compatibility
        blank=True
    )



    # =====================
    # META
    # =====================

    class Meta:
        verbose_name = _('Location Numbering Assignment')
        verbose_name_plural = _('Location Numbering Assignments')
        ordering = ['location_content_type', 'location_object_id', 'numbering_config']

        # ПРОМЕНИ indexes:
        indexes = [
            models.Index(fields=['location_content_type', 'location_object_id', 'is_active']),
            models.Index(fields=['numbering_config', 'is_active']),
        ]

        # ПРОМЕНИ constraints:
        constraints = [
            models.UniqueConstraint(
                fields=['location_content_type', 'location_object_id', 'numbering_config'],
                name='unique_location_numbering'
            )
        ]

    def __str__(self):
        status = "✓" if self.is_active else "✗"
        return f"{status} {self.location.name} → {self.numbering_config.name}"


# =================================================================
# USER NUMBERING PREFERENCES - UNCHANGED
# =================================================================

class UserNumberingPreference(models.Model):
    """
    User preferences за numbering - НЕ СЕ ПРОМЕНЯ
    """

    # =====================
    # CORE RELATIONS
    # =====================

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='numbering_preferences',
        verbose_name=_('User')
    )

    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.CASCADE,
        related_name='user_numbering_preferences',
        verbose_name=_('Document Type')
    )

    preferred_config = models.ForeignKey(
        NumberingConfiguration,
        on_delete=models.CASCADE,
        related_name='user_preferences',
        verbose_name=_('Preferred Configuration')
    )

    # =====================
    # SETTINGS
    # =====================

    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    # =====================
    # META
    # =====================

    class Meta:
        verbose_name = _('User Numbering Preference')
        verbose_name_plural = _('User Numbering Preferences')
        ordering = ['user', 'document_type']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'document_type'],
                name='unique_user_document_type_preference'
            )
        ]

    def __str__(self):
        return f"{self.user.username} → {self.document_type.name}: {self.preferred_config.name}"


# =================================================================
# HELPER FUNCTIONS - SIMPLIFIED
# =================================================================

def get_numbering_config_for_document(document_type, location=None, user=None):
    """
    Get appropriate numbering configuration - FIXED FOR GENERIC LOCATION

    Priority:
    1. User preference (if specified)
    2. Location assignment (if specified)
    3. Default config for document type
    """

    # Priority 1: User preference
    if user:
        preference = UserNumberingPreference.objects.filter(
            user=user,
            document_type=document_type
        ).select_related('preferred_config').first()

        if preference and preference.preferred_config.is_active:
            return preference.preferred_config

    # Priority 2: Location assignment
    if location:
        # NEW: САМО GenericForeignKey търсене (махаме fallback)
        content_type = ContentType.objects.get_for_model(location.__class__)
        assignment = LocationNumberingAssignment.objects.filter(
            location_content_type=content_type,
            location_object_id=location.pk,
            numbering_config__document_type=document_type,
            is_active=True
        ).select_related('numbering_config').first()

        if assignment:
            return assignment.numbering_config

    # Priority 3: Default config
    default_config = NumberingConfiguration.objects.filter(
        document_type=document_type,
        is_default=True,
        is_active=True
    ).first()

    return default_config


# =================================================================
# DEPRECATED FUNCTION - ЗА BACKWARD COMPATIBILITY
# =================================================================

def generate_document_number(document_type, location=None, user=None):
    """
    DEPRECATED: Use NumberingService.generate_document_number() instead

    Kept only for backward compatibility
    """
    import warnings
    warnings.warn(
        "generate_document_number() in models.numbering is deprecated. "
        "Use NumberingService.generate_document_number() instead.",
        DeprecationWarning,
        stacklevel=2
    )

    # Delegate to NumberingService if available
    try:
        from ..services.numbering_service import NumberingService
        return NumberingService.generate_document_number(document_type, location, user)
    except ImportError:
        # Emergency fallback
        from django.utils import timezone
        timestamp = timezone.now().strftime("%y%m%d%H%M%S")
        return f"FALLBACK{timestamp}"