# core/models/base.py - CORE FOUNDATION MODELS

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from decimal import Decimal
import json


class TimestampedModel(models.Model):
    """
    Abstract base model that provides timestamp fields
    Used across ALL apps for consistent audit trail
    """
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True,
        db_index=True
    )

    class Meta:
        abstract = True


class UserTrackingModel(TimestampedModel):
    """
    Abstract base model that adds user tracking
    Used for documents and transactions that need user audit
    """
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_%(app_label)s_%(class)s',
        verbose_name=_('Created By')
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='updated_%(app_label)s_%(class)s',
        verbose_name=_('Updated By')
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Auto-track user changes"""
        # Get current user from request (if available)
        user = getattr(self, '_current_user', None)

        if user and user.is_authenticated:
            if not self.pk:  # New record
                self.created_by = user
            self.updated_by = user

        super().save(*args, **kwargs)


class BaseAuditLog(TimestampedModel):
    """
    Abstract base for audit logging across all apps
    Provides consistent audit trail structure
    """

    # Generic relation to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_('Content Type')
    )
    object_id = models.PositiveIntegerField(_('Object ID'))
    content_object = GenericForeignKey('content_type', 'object_id')

    # Audit information
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        verbose_name=_('User')
    )
    action = models.CharField(
        _('Action'),
        max_length=50,
        db_index=True
    )

    # Change details
    field_changes = models.JSONField(
        _('Field Changes'),
        default=dict,
        blank=True,
        help_text=_('JSON of field changes: {"field": {"old": "value", "new": "value"}}')
    )

    # Additional context
    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        null=True,
        blank=True
    )
    user_agent = models.TextField(
        _('User Agent'),
        blank=True
    )
    notes = models.TextField(
        _('Notes'),
        blank=True
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action} on {self.content_object} by {self.user}"

    def get_field_changes_display(self):
        """Human readable field changes"""
        if not self.field_changes:
            return "No field changes"

        changes = []
        for field, change in self.field_changes.items():
            old_val = change.get('old', '')
            new_val = change.get('new', '')
            changes.append(f"{field}: '{old_val}' → '{new_val}'")

        return '; '.join(changes)


class BaseConfiguration(UserTrackingModel):
    """
    Abstract base for configuration models
    Provides consistent structure for system settings
    """

    key = models.CharField(
        _('Setting Key'),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_('Unique identifier for this setting')
    )
    display_name = models.CharField(
        _('Display Name'),
        max_length=200,
        help_text=_('Human-readable name for this setting')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of what this setting controls')
    )

    # Value storage
    value = models.JSONField(
        _('Value'),
        help_text=_('The setting value (can be any JSON type)')
    )
    default_value = models.JSONField(
        _('Default Value'),
        help_text=_('Default value if setting is reset')
    )

    # Metadata
    category = models.CharField(
        _('Category'),
        max_length=50,
        db_index=True,
        help_text=_('Category for grouping settings (e.g., "purchase", "inventory")')
    )
    data_type = models.CharField(
        _('Data Type'),
        max_length=20,
        choices=[
            ('string', _('String')),
            ('integer', _('Integer')),
            ('decimal', _('Decimal')),
            ('boolean', _('Boolean')),
            ('date', _('Date')),
            ('json', _('JSON Object')),
            ('list', _('List')),
        ],
        default='string',
        help_text=_('Expected data type for validation')
    )

    # Constraints
    is_required = models.BooleanField(
        _('Is Required'),
        default=False,
        help_text=_('Whether this setting must have a value')
    )
    is_user_editable = models.BooleanField(
        _('User Editable'),
        default=True,
        help_text=_('Whether users can modify this setting')
    )
    is_system_setting = models.BooleanField(
        _('System Setting'),
        default=False,
        help_text=_('Whether this is a core system setting')
    )

    class Meta:
        abstract = True
        ordering = ['category', 'display_name']

    def __str__(self):
        return f"{self.display_name} = {self.value}"

    def clean(self):
        """Validate setting value against data type"""
        super().clean()

        if self.is_required and (self.value is None or self.value == ''):
            raise ValidationError({
                'value': _('This setting is required and cannot be empty')
            })

        # Validate data type
        if not self._validate_data_type():
            raise ValidationError({
                'value': _(f'Value must be of type {self.data_type}')
            })

    def _validate_data_type(self):
        """Validate value matches expected data type"""
        if self.value is None:
            return not self.is_required

        try:
            if self.data_type == 'string':
                return isinstance(self.value, str)
            elif self.data_type == 'integer':
                return isinstance(self.value, int)
            elif self.data_type == 'decimal':
                return isinstance(self.value, (int, float, Decimal))
            elif self.data_type == 'boolean':
                return isinstance(self.value, bool)
            elif self.data_type == 'date':
                from datetime import date
                return isinstance(self.value, (str, date))
            elif self.data_type in ['json', 'list']:
                return True  # JSON field can store any type
            else:
                return True
        except Exception:
            return False

    def get_typed_value(self):
        """Return value converted to appropriate Python type"""
        if self.value is None:
            return self.default_value

        try:
            if self.data_type == 'decimal':
                return Decimal(str(self.value))
            elif self.data_type == 'date':
                if isinstance(self.value, str):
                    from datetime import datetime
                    return datetime.strptime(self.value, '%Y-%m-%d').date()
                return self.value
            else:
                return self.value
        except Exception:
            return self.default_value


class BaseSequence(UserTrackingModel):
    """
    Abstract base for sequence/numbering models
    Provides consistent document numbering across apps
    """

    prefix = models.CharField(
        _('Prefix'),
        max_length=10,
        db_index=True,
        help_text=_('Document prefix (e.g., REQ, ORD, INV)')
    )
    description = models.CharField(
        _('Description'),
        max_length=200,
        help_text=_('Description of what this sequence is for')
    )

    # Current state
    current_year = models.IntegerField(
        _('Current Year'),
        default=timezone.now().year,
        db_index=True
    )
    last_number = models.IntegerField(
        _('Last Number'),
        default=0,
        help_text=_('Last number issued for current year')
    )

    # Format configuration
    format_template = models.CharField(
        _('Format Template'),
        max_length=100,
        default='{prefix}-{year}-{number:04d}',
        help_text=_('Template for generating numbers: {prefix}-{year}-{number:04d}')
    )

    # Settings
    reset_yearly = models.BooleanField(
        _('Reset Yearly'),
        default=True,
        help_text=_('Whether to reset numbering each year')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this sequence is currently active')
    )

    class Meta:
        abstract = True
        unique_together = ('prefix', 'current_year')
        ordering = ['prefix', 'current_year']

    def __str__(self):
        return f"{self.prefix} ({self.current_year}): {self.last_number}"

    def get_next_number(self):
        """
        Get next number in sequence
        Returns the formatted number string
        """
        current_year = timezone.now().year

        # Check if we need to reset for new year
        if self.reset_yearly and current_year != self.current_year:
            self.current_year = current_year
            self.last_number = 0

        # Increment counter
        self.last_number += 1
        self.save()

        # Format and return
        return self.format_template.format(
            prefix=self.prefix,
            year=self.current_year,
            number=self.last_number
        )

    def preview_next_number(self):
        """Preview what the next number would be without incrementing"""
        current_year = timezone.now().year

        # Determine what the next number would be
        if self.reset_yearly and current_year != self.current_year:
            next_number = 1
            year = current_year
        else:
            next_number = self.last_number + 1
            year = self.current_year

        return self.format_template.format(
            prefix=self.prefix,
            year=year,
            number=next_number
        )


class BaseApprovalModel(UserTrackingModel):
    """
    Abstract base for models that require approval workflow
    Provides consistent approval tracking
    """

    APPROVAL_STATUS_CHOICES = [
        ('pending', _('Pending Approval')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('cancelled', _('Cancelled')),
    ]

    approval_status = models.CharField(
        _('Approval Status'),
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        db_index=True
    )

    # Approval tracking
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_%(app_label)s_%(class)s',
        verbose_name=_('Approved By')
    )
    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True
    )
    approval_notes = models.TextField(
        _('Approval Notes'),
        blank=True,
        help_text=_('Notes from approver')
    )

    # Rejection tracking
    rejected_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='rejected_%(app_label)s_%(class)s',
        verbose_name=_('Rejected By')
    )
    rejected_at = models.DateTimeField(
        _('Rejected At'),
        null=True,
        blank=True
    )
    rejection_reason = models.TextField(
        _('Rejection Reason'),
        blank=True,
        help_text=_('Reason for rejection')
    )

    class Meta:
        abstract = True

    def approve(self, user, notes=''):
        """Approve this item"""
        self.approval_status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.approval_notes = notes
        self.save()

    def reject(self, user, reason=''):
        """Reject this item"""
        self.approval_status = 'rejected'
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def cancel_approval(self, user):
        """Cancel approval process"""
        self.approval_status = 'cancelled'
        self.updated_by = user
        self.save()

    @property
    def is_approved(self):
        return self.approval_status == 'approved'

    @property
    def is_pending(self):
        return self.approval_status == 'pending'

    @property
    def is_rejected(self):
        return self.approval_status == 'rejected'