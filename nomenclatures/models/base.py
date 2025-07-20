from django.db import models
from django.utils.translation import gettext_lazy as _

# nomenclatures/models/base.py - ENHANCED VERSION

import re
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

    def validate_code_uniqueness_across_nomenclatures(self, code, exclude_pk=None):
        """
        Check if code is unique across ALL nomenclature types

        Returns:
            tuple: (is_unique: bool, conflicts: list)
        """
        from django.apps import apps

        conflicts = []

        # Get all models that inherit from BaseNomenclature
        nomenclature_models = []
        for model in apps.get_models():
            if (hasattr(model, '_meta') and
                    hasattr(model._meta, 'abstract') and
                    not model._meta.abstract and
                    issubclass(model, BaseNomenclature)):
                nomenclature_models.append(model)

        # Check each model for conflicts
        for model_class in nomenclature_models:
            existing = model_class.objects.filter(code__iexact=code)
            if exclude_pk:
                existing = existing.exclude(pk=exclude_pk)

            if existing.exists():
                conflicts.append({
                    'model': model_class.__name__,
                    'objects': list(existing.values('id', 'code', 'name'))
                })

        return len(conflicts) == 0, conflicts


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
        """Enhanced validation with cross-model checks"""
        super().clean()
        errors = {}

        # =====================
        # 1. CODE VALIDATION
        # =====================
        if self.code:
            # Normalize code
            self.code = self.code.upper().strip()

            # Check format
            if not re.match(self.CODE_REGEX, self.code):
                errors['code'] = _(
                    'Code must contain only uppercase letters, numbers, '
                    'underscore and dash (max 20 characters)'
                )

            # Check reserved words
            reserved_codes = ['NULL', 'NONE', 'DEFAULT', 'SYSTEM', 'ADMIN', 'TEST']
            if self.code in reserved_codes:
                errors['code'] = _(f'Code "{self.code}" is reserved and cannot be used')

            # Check cross-model uniqueness
            if not errors.get('code'):  # Only if format is valid
                is_unique, conflicts = self.objects.validate_code_uniqueness_across_nomenclatures(
                    self.code, exclude_pk=self.pk
                )
                if not is_unique:
                    conflict_info = []
                    for conflict in conflicts:
                        conflict_info.append(f"{conflict['model']}: {len(conflict['objects'])} records")
                    errors['code'] = _(
                        f'Code "{self.code}" already exists in: {", ".join(conflict_info)}'
                    )
        else:
            errors['code'] = _('Code is required')

        # =====================
        # 2. NAME VALIDATION
        # =====================
        if self.name:
            # Normalize name
            self.name = ' '.join(self.name.split())  # Remove extra whitespace

            # Length check
            if len(self.name) < 2:
                errors['name'] = _('Name must be at least 2 characters long')
            elif len(self.name) > 100:
                errors['name'] = _('Name cannot exceed 100 characters')
        else:
            errors['name'] = _('Name is required')

        # =====================
        # 3. BUSINESS RULES
        # =====================

        # Cannot deactivate if used in other records
        if hasattr(self, 'pk') and self.pk and not self.is_active:
            usage_count = self._get_usage_count()
            if usage_count > 0:
                errors['is_active'] = _(
                    f'Cannot deactivate: this nomenclature is used in {usage_count} records'
                )

        # System nomenclatures cannot be deactivated
        if self.is_system and not self.is_active:
            errors['is_active'] = _('System nomenclatures cannot be deactivated')

        if errors:
            raise ValidationError(errors)

    def _get_usage_count(self):
        """
        Count how many times this nomenclature is used in other models
        Override in subclasses for specific counting logic
        """
        # Default implementation - override in subclasses
        return 0

    # =====================
    # ENHANCED SAVE
    # =====================
    def save(self, *args, **kwargs):
        """Enhanced save with validation and audit"""

        # Force full clean before save
        self.full_clean()

        # Auto-generate sort_order if not set
        if self.sort_order == 0 and not self.pk:
            max_order = self.__class__.objects.aggregate(
                max_order=models.Max('sort_order')
            )['max_order'] or 0
            self.sort_order = max_order + 10

        super().save(*args, **kwargs)

    # =====================
    # BUSINESS METHODS
    # =====================
    def can_delete(self):
        """Check if this nomenclature can be deleted"""
        if self.is_system:
            return False, _('System nomenclatures cannot be deleted')

        usage_count = self._get_usage_count()
        if usage_count > 0:
            return False, _(f'Cannot delete: used in {usage_count} records')

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
        """Get summary of where this nomenclature is used"""
        # Override in subclasses for detailed usage info
        return {
            'total_usage': self._get_usage_count(),
            'can_delete': self.can_delete()[0],
            'details': {}
        }


class ActiveManager(models.Manager):
    """Manager за филтриране само на активни записи"""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)