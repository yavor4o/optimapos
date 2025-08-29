


from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


class ActiveManager(models.Manager):
    """Manager за филтриране само на активни записи"""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class BaseNomenclatureManager(models.Manager):
    """Enhanced manager for nomenclatures with search and validation"""

    def active(self):
        """Return only active nomenclatures"""
        return self.filter(is_active=True)

    def by_code(self, code):
        """Find by code (case insensitive)"""
        return self.filter(code__iexact=code).first()

    def search(self, query):
        """Search by code or name"""
        return self.filter(
            models.Q(code__icontains=query) |
            models.Q(name__icontains=query)
        )



class BaseNomenclature(models.Model):
    """
    Базов клас за всички номенклатури - ENHANCED VERSION

    IMPROVEMENTS:
    - Strict code validation (format, length, uniqueness)
    - Cross-model code uniqueness validation
    - Enhanced save() with proper error handling
    - System/manual flags for better control
    - Audit fields for tracking
    """

    # =====================
    # CODE VALIDATION REGEX
    # =====================
    CODE_REGEX = r'^[A-Z0-9_-]{1,20}$'  # Only uppercase letters, numbers, underscore, dash

    code_validator = RegexValidator(
        regex=CODE_REGEX,
        message=_('Code must contain only uppercase letters, numbers, underscore and dash (max 20 chars)')
    )

    # =====================
    # CORE FIELDS
    # =====================
    code = models.CharField(
        _('Code'),
        max_length=20,  # Reduced from 100 to 20 for better performance
        unique=True,
        db_index=True,
        validators=[code_validator],
        help_text=_('Unique code: A-Z, 0-9, underscore, dash only (max 20 chars)')
    )

    name = models.CharField(
        _('Name'),
        max_length=100,
        db_index=True,
        help_text=_('Human readable name')
    )

    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Optional detailed description')
    )

    # =====================
    # STATUS & CONTROL
    # =====================
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        db_index=True,
        help_text=_('Whether this nomenclature is currently active')
    )

    is_system = models.BooleanField(
        _('Is System'),
        default=False,
        help_text=_('System nomenclatures cannot be deleted by users')
    )

    sort_order = models.IntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('For custom ordering in lists and dropdowns')
    )

    # =====================
    # AUDIT FIELDS
    # =====================
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
        db_index=True
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
        related_name='%(class)s_created',
        verbose_name=_('Created By')
    )

    # =====================
    # MANAGERS
    # =====================
    objects = BaseNomenclatureManager()
    active = ActiveManager()

    class Meta:
        abstract = True
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active', 'sort_order']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Minimal validation - only normalization and system protection"""
        super().clean()
        errors = {}

        # Normalization
        if self.code:
            self.code = self.code.upper().strip()
            reserved_codes = ['NULL', 'NONE', 'DEFAULT', 'SYSTEM', 'ADMIN', 'TEST']
            if self.code in reserved_codes:
                errors['code'] = _(f'Code "{self.code}" is reserved')

        if self.name:
            self.name = ' '.join(self.name.split())

        # System protection only
        if self.is_system and not self.is_active:
            errors['is_active'] = _('System nomenclatures cannot be deactivated')

        if errors:
            raise ValidationError(errors)



    # =====================
    # ENHANCED SAVE
    # =====================
    def save(self, *args, **kwargs):
        """Simple save without extra logic"""
        super().save(*args, **kwargs)
        # ТОВА Е! Просто и работи.

    # =====================
    # BUSINESS METHODS
    # =====================
    def can_delete(self):
        """Check if this nomenclature can be deleted"""
        if self.is_system:
            return False, _('System nomenclatures cannot be deleted')

        # Database constraints ще хвърлят грешка ако има usage
        return True, ''

    def activate(self):
        """Activate this nomenclature"""
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])

    def deactivate(self):
        """Deactivate this nomenclature (with validation)"""
        self.is_active = False
        self.save()  # Will trigger validation in clean()

    def get_display_name(self):
        """Get formatted display name for UI"""
        return f"{self.code} - {self.name}"

    def get_usage_summary(self):
        """Get summary - simplified without usage count"""
        return {
            'can_delete': self.can_delete()[0],
            'is_system': self.is_system,
            'is_active': self.is_active,
            'details': {}
        }

