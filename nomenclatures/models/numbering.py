# nomenclatures/models/numbering.py - NEW FILE
"""
Document Numbering System - Bulgarian Standard

АРХИТЕКТУРА:
- NumberingConfiguration: основни настройки за номерация
- LocationNumberingAssignment: връзка между location и numbering config
- UserNumberingPreference: user preferences за избор на numbering

ФИСКАЛНО СЪОТВЕТСТВИЕ:
- Фискални документи: 10 цифри БЕЗ префикс (1000000001)
- Вътрешни документи: гъвкави с префикс (REQ001, PO023)
- Multi-location support със separate броячи

ПРИМЕРИ:
- София фактури: 1000000001, 1000000002, 1000000003...
- Варна фактури: 2100000001, 2100000002, 2100000003...
- София заявки: REQ001, REQ002, REQ003...
- Варна заявки: VAR-REQ001, VAR-REQ002...
"""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from .base import BaseNomenclature, BaseNomenclatureManager
import re

User = get_user_model()


# =================================================================
# NUMBERING CONFIGURATION - CORE
# =================================================================

class NumberingConfigurationManager(BaseNomenclatureManager):
    """Manager за numbering configurations"""

    def for_document_type(self, document_type):
        """Get configs for specific document type"""
        return self.active().filter(document_type=document_type)

    def for_location(self, location):
        """Get configs for specific location"""
        return self.active().filter(
            locationnumberingassignment__location=location,
            locationnumberingassignment__is_active=True
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


class NumberingConfiguration(BaseNomenclature):
    """
    Numbering Configuration - Microinvest Style

    Конфигурира как се номерират документите:
    - Фискални: 10 цифри без префикс (Bulgarian law)
    - Вътрешни: гъвкави с префикс
    - Per location или global
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
        """Business rules validation"""
        super().clean()

        # Fiscal document validation
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

        # Prefix validation
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
    # NUMBERING METHODS
    # =====================

    @transaction.atomic
    def get_next_number(self):
        """
        Thread-safe number generation

        Returns:
            str: Formatted document number (e.g., "REQ0001", "1000000001")
        """
        # Lock record for update to prevent race conditions
        config = NumberingConfiguration.objects.select_for_update().get(pk=self.pk)

        # Check yearly reset
        current_year = timezone.now().year
        if config.reset_yearly and config.last_reset_year != current_year:
            config.current_number = 0
            config.last_reset_year = current_year

        # Increment counter
        config.current_number += 1

        # Check max number limit
        if config.max_number and config.current_number > config.max_number:
            raise ValidationError(f'Number limit exceeded. Max: {config.max_number}')

        # Save updated counter
        config.save(update_fields=['current_number', 'last_reset_year'])

        # Format and return number
        return config.format_number(config.current_number)

    def format_number(self, number):
        """
        Format number according to configuration

        Args:
            number (int): Raw number to format

        Returns:
            str: Formatted number
        """
        # Zero-pad the number
        padded_number = str(number).zfill(self.digits_count)

        # Add prefix if exists
        if self.prefix:
            return f"{self.prefix}{padded_number}"
        else:
            return padded_number

    def preview_next_numbers(self, count=5):
        """
        Preview next N numbers without incrementing counter

        Args:
            count (int): How many numbers to preview

        Returns:
            list: List of next formatted numbers
        """
        preview_numbers = []
        for i in range(1, count + 1):
            next_num = self.current_number + i
            if self.max_number and next_num > self.max_number:
                break
            preview_numbers.append(self.format_number(next_num))

        return preview_numbers

    def reset_counter(self, new_start=0):
        """
        Reset numbering counter

        Args:
            new_start (int): New starting number
        """
        self.current_number = new_start
        self.last_reset_year = timezone.now().year
        self.save(update_fields=['current_number', 'last_reset_year'])

    # =====================
    # BUSINESS METHODS
    # =====================

    def is_fiscal_compliant(self):
        """Check if config meets Bulgarian fiscal requirements"""
        if self.numbering_type != 'fiscal':
            return True

        return (
                not self.prefix and  # No prefix
                self.digits_count >= 10 and  # At least 10 digits
                not self.reset_yearly  # No yearly reset (recommended)
        )

    def get_microinvest_display(self):
        """Get Microinvest-style display string"""
        prefix_display = f'Префикс: {self.prefix}' if self.prefix else 'Без префикс'
        return f"{self.document_type.name} ({self.series_number}) - {prefix_display}, Следващ: {self.format_number(self.current_number + 1)}"


# =================================================================
# LOCATION NUMBERING ASSIGNMENT
# =================================================================

class LocationNumberingAssignment(models.Model):
    """
    Връзка между Location и NumberingConfiguration

    Позволява на всяка локация да използва различни numbering configs
    за различни document types.
    """

    # =====================
    # CORE RELATIONS
    # =====================

    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='numbering_assignments',
        verbose_name=_('Location')
    )

    numbering_config = models.ForeignKey(
        NumberingConfiguration,
        on_delete=models.CASCADE,
        related_name='location_assignments',
        verbose_name=_('Numbering Configuration')
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
        verbose_name=_('Assigned By')
    )

    # =====================
    # META
    # =====================

    class Meta:
        verbose_name = _('Location Numbering Assignment')
        verbose_name_plural = _('Location Numbering Assignments')
        ordering = ['location', 'numbering_config']
        indexes = [
            models.Index(fields=['location', 'is_active']),
            models.Index(fields=['numbering_config', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['location', 'numbering_config'],
                name='unique_location_numbering'
            )
        ]

    def __str__(self):
        status = "✓" if self.is_active else "✗"
        return f"{status} {self.location.name} → {self.numbering_config.name}"


# =================================================================
# USER NUMBERING PREFERENCES
# =================================================================

class UserNumberingPreference(models.Model):
    """
    User preferences за numbering

    Позволява на users да избират кои numbering configs да използват
    за различни document types.
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
# HELPER FUNCTIONS
# =================================================================

def get_numbering_config_for_document(document_type, location=None, user=None):
    """
    Get appropriate numbering configuration for document creation

    Priority:
    1. User preference (if specified)
    2. Location assignment (if specified)
    3. Default config for document type

    Args:
        document_type: DocumentType instance
        location: Location instance (optional)
        user: User instance (optional)

    Returns:
        NumberingConfiguration instance or None
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
        assignment = LocationNumberingAssignment.objects.filter(
            location=location,
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


def generate_document_number(document_type, location=None, user=None):
    """
    Generate next document number

    Args:
        document_type: DocumentType instance
        location: Location instance (optional)
        user: User instance (optional)

    Returns:
        str: Generated document number

    Raises:
        ValidationError: If no numbering config found or number generation fails
    """

    config = get_numbering_config_for_document(document_type, location, user)

    if not config:
        raise ValidationError(
            f'No numbering configuration found for {document_type.name}. '
            f'Please create a NumberingConfiguration for this document type.'
        )

    try:
        return config.get_next_number()
    except ValidationError as e:
        raise ValidationError(f'Number generation failed: {e}')


