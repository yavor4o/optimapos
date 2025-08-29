# nomenclatures/models/approvals.py - FIXED CLEAN VERSION
"""
Approval System - CLEANED & MODERNIZED

ФИКСИРАНО:
- Премахнати deprecated from_status/to_status string полета
- Използват се САМО from_status_obj/to_status_obj ForeignKey полета
- Backward compatibility чрез properties
- Cleanup на unused imports и код

ЗАПАЗЕНО:
- Multi-level approvals
- Financial limits (min/max amounts)
- User/Role/Permission approvers
- Audit trail (ApprovalLog)
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

User = get_user_model()


# =================================================================
# APPROVAL RULE MANAGER - FIXED
# =================================================================

class ApprovalRuleManager(models.Manager):
    """FIXED: Modern manager for ApprovalRule using ForeignKey fields"""

    def for_document_type(self, document_type):
        """Get rules for specific document type"""
        return self.filter(document_type=document_type, is_active=True)

    def for_transition(self, document_type, from_status_code, to_status_code):
        """
        FIXED: Get rules for specific status transition using codes

        Args:
            document_type: DocumentType instance
            from_status_code: Status code string (e.g., 'draft')
            to_status_code: Status code string (e.g., 'submitted')
        """
        return self.filter(
            document_type=document_type,
            from_status_obj__code=from_status_code,
            to_status_obj__code=to_status_code,
            is_active=True
        ).order_by('approval_level', 'sort_order')

    def for_amount_range(self, min_amount, max_amount=None):
        """Get rules applicable for amount range"""
        queryset = self.filter(min_amount__lte=min_amount, is_active=True)
        if max_amount:
            queryset = queryset.filter(
                models.Q(max_amount__gte=max_amount) | models.Q(max_amount__isnull=True)
            )
        return queryset

    def for_user(self, user):
        """Get rules that user can execute"""
        return self.filter(
            models.Q(approver_user=user) |
            models.Q(approver_role__in=user.groups.all()) |
            models.Q(approver_permission__in=user.user_permissions.all()),
            is_active=True
        )

    def by_level(self, level):
        """Get rules for specific approval level"""
        return self.filter(approval_level=level, is_active=True)


# =================================================================
# APPROVAL RULE - FIXED & MODERNIZED
# =================================================================

class ApprovalRule(models.Model):
    """
    FIXED: Approval Rule using only ForeignKey status references

    Дефинира кой може да одобрява какво при какви условия.
    FIXED VERSION използва само ForeignKey полета за статуси.
    """

    # =====================
    # BASIC INFO
    # =====================

    name = models.CharField(
        _('Rule Name'),
        max_length=100,
        help_text=_('Descriptive name: "Manager approval for orders over 1000 BGN"')
    )

    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of when this rule applies')
    )

    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this rule is currently active')
    )

    sort_order = models.PositiveIntegerField(
        _('Sort Order'),
        default=10,
        help_text=_('Order for applying rules (lower = higher priority)')
    )

    # =====================
    # DOCUMENT SCOPE
    # =====================

    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.CASCADE,
        verbose_name=_('Document Type'),
        help_text=_('Which document type this rule applies to')
    )

    # =====================
    # STATUS TRANSITION - FIXED: ONLY ForeignKey fields
    # =====================

    from_status_obj = models.ForeignKey(
        'nomenclatures.DocumentStatus',
        on_delete=models.PROTECT,
        related_name='approval_rules_from',
        verbose_name=_('From Status'),
        help_text=_('Starting status for this transition')
    )

    to_status_obj = models.ForeignKey(
        'nomenclatures.DocumentStatus',
        on_delete=models.PROTECT,
        related_name='approval_rules_to',
        verbose_name=_('To Status'),
        help_text=_('Target status for this transition')
    )

    # =====================
    # BACKWARD COMPATIBILITY PROPERTIES - FIXED
    # =====================

    @property
    def from_status(self):
        """FIXED: Backward compatibility for from_status"""
        return self.from_status_obj.code if self.from_status_obj else None

    @property
    def to_status(self):
        """FIXED: Backward compatibility for to_status"""
        return self.to_status_obj.code if self.to_status_obj else None

    # =====================
    # APPROVAL HIERARCHY
    # =====================

    approval_level = models.PositiveIntegerField(
        _('Approval Level'),
        default=1,
        help_text=_('Approval level: 1=first level, 2=second level, etc.')
    )

    requires_previous_level = models.BooleanField(
        _('Requires Previous Level'),
        default=True,
        help_text=_('Must previous approval levels be completed first?')
    )

    # =====================
    # APPROVER CONFIGURATION
    # =====================

    APPROVER_TYPE_CHOICES = [
        ('user', _('Specific User')),
        ('role', _('User Group/Role')),
        ('permission', _('Permission-based')),
        ('dynamic', _('Dynamic (determined at runtime)')),
    ]

    approver_type = models.CharField(
        _('Approver Type'),
        max_length=20,
        choices=APPROVER_TYPE_CHOICES,
        default='role',
        help_text=_('How to determine who can approve')
    )

    approver_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules',
        verbose_name=_('Approver User'),
        help_text=_('Specific user who can approve (if type=user)')
    )

    approver_role = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules',
        verbose_name=_('Approver Role'),
        help_text=_('Group/role that can approve (if type=role)')
    )

    approver_permission = models.ForeignKey(
        'auth.Permission',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules',
        verbose_name=_('Required Permission'),
        help_text=_('Permission required to approve (if type=permission)')
    )

    # =====================
    # FINANCIAL LIMITS
    # =====================

    min_amount = models.DecimalField(
        _('Minimum Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Minimum document amount for this rule to apply')
    )

    max_amount = models.DecimalField(
        _('Maximum Amount'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Maximum document amount (leave empty for unlimited)')
    )

    currency = models.CharField(
        _('Currency'),
        max_length=3,
        default='BGN',
        help_text=_('Currency for amount limits (ISO code)')
    )

    # =====================
    # WORKFLOW BEHAVIOR
    # =====================

    requires_reason = models.BooleanField(
        _('Requires Reason'),
        default=False,
        help_text=_('Must user provide a reason/comment when using this rule?')
    )

    rejection_allowed = models.BooleanField(
        _('Rejection Allowed'),
        default=True,
        help_text=_('Can user reject at this level?')
    )

    # =====================
    # METADATA
    # =====================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # =====================
    # MANAGERS
    # =====================

    objects = ApprovalRuleManager()

    class Meta:
        verbose_name = _('Approval Rule')
        verbose_name_plural = _('Approval Rules')
        ordering = ['document_type', 'approval_level', 'sort_order']

        # FIXED: Updated indexes to use ForeignKey fields
        indexes = [
            models.Index(fields=['document_type', 'from_status_obj', 'to_status_obj']),
            models.Index(fields=['document_type', 'is_active']),
            models.Index(fields=['approval_level']),
            models.Index(fields=['approver_type', 'is_active']),
            models.Index(fields=['min_amount', 'max_amount']),
        ]

        # FIXED: Updated constraint to use ForeignKey fields
        constraints = [
            models.UniqueConstraint(
                fields=['document_type', 'from_status_obj', 'to_status_obj', 'approval_level'],
                name='unique_approval_rule_per_level'
            )
        ]

    def __str__(self):
        """FIXED: Updated string representation using properties"""
        amount_range = f"{self.min_amount}"
        if self.max_amount:
            amount_range += f"-{self.max_amount}"
        else:
            amount_range += "+"

        return f"{self.name} (L{self.approval_level}): {self.from_status}→{self.to_status} ({amount_range} {self.currency})"

    def clean(self):
        """FIXED: Updated validation"""
        super().clean()

        # Amount validation
        if self.max_amount and self.min_amount > self.max_amount:
            raise ValidationError({
                'max_amount': _('Maximum amount must be greater than minimum amount')
            })

        # FIXED: Status validation using ForeignKey fields
        if self.from_status_obj and self.to_status_obj:
            if self.from_status_obj == self.to_status_obj:
                raise ValidationError({
                    'to_status_obj': _('Cannot transition to the same status')
                })

        # Approver validation
        if self.approver_type == 'user' and not self.approver_user:
            raise ValidationError({
                'approver_user': _('Approver user is required when type is "user"')
            })

        if self.approver_type == 'role' and not self.approver_role:
            raise ValidationError({
                'approver_role': _('Approver role is required when type is "role"')
            })

        if self.approver_type == 'permission' and not self.approver_permission:
            raise ValidationError({
                'approver_permission': _('Approver permission is required when type is "permission"')
            })

    # =====================
    # BUSINESS METHODS - FIXED
    # =====================

    def can_user_approve(self, user, document=None):
        """FIXED: Check if user can approve using this rule"""
        if not self.is_active:
            return False

        if self.approver_type == 'user':
            return self.approver_user == user

        elif self.approver_type == 'role':
            return user.groups.filter(id=self.approver_role.id).exists()

        elif self.approver_type == 'permission':
            return user.has_perm(
                f'{self.approver_permission.content_type.app_label}.{self.approver_permission.codename}'
            )

        elif self.approver_type == 'dynamic':
            # Dynamic approval - extend as needed
            return user.is_staff

        return False

    def get_approver_display(self):
        """Get human-readable approver info"""
        if self.approver_type == 'user' and self.approver_user:
            return f"User: {self.approver_user.get_full_name() or self.approver_user.username}"
        elif self.approver_type == 'role' and self.approver_role:
            return f"Role: {self.approver_role.name}"
        elif self.approver_type == 'permission' and self.approver_permission:
            return f"Permission: {self.approver_permission.name}"
        else:
            return f"Type: {self.get_approver_type_display()}"

    def is_amount_in_range(self, amount):
        """Check if amount falls within this rule's range"""
        if amount < self.min_amount:
            return False
        if self.max_amount and amount > self.max_amount:
            return False
        return True


# =================================================================
# APPROVAL LOG - UNCHANGED BUT FIXED IMPORTS
# =================================================================

class ApprovalLog(models.Model):
    """
    Approval Log - Audit trail for approval actions

    UNCHANGED но с FIXED imports и relationships
    """

    # =====================
    # DOCUMENT REFERENCE
    # =====================

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_('Content Type')
    )

    object_id = models.PositiveIntegerField(
        _('Object ID')
    )

    # =====================
    # APPROVAL ACTION
    # =====================

    ACTION_CHOICES = [
        ('submitted', _('Submitted for Approval')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('escalated', _('Escalated')),
        ('cancelled', _('Cancelled')),
    ]

    action = models.CharField(
        _('Action'),
        max_length=20,
        choices=ACTION_CHOICES
    )

    from_status = models.CharField(
        _('From Status'),
        max_length=30
    )

    to_status = models.CharField(
        _('To Status'),
        max_length=30
    )

    # =====================
    # RULE REFERENCE
    # =====================

    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Applied Rule')
    )

    # =====================
    # ACTOR & CONTEXT
    # =====================

    actor = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name=_('Actor'),
        help_text=_('User who performed the action')
    )

    comments = models.TextField(
        _('Comments'),
        blank=True,
        help_text=_('Additional comments or reasons')
    )

    # =====================
    # AUDIT METADATA
    # =====================

    timestamp = models.DateTimeField(
        _('Timestamp'),
        auto_now_add=True
    )

    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        null=True,
        blank=True
    )

    user_agent = models.TextField(
        _('User Agent'),
        blank=True,
        help_text=_('Browser/client user agent')
    )

    class Meta:
        verbose_name = _('Approval Log')
        verbose_name_plural = _('Approval Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['actor']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} by {self.actor.username} at {self.timestamp}"

    @property
    def document(self):
        """Get the related document object"""
        try:
            return self.content_type.get_object_for_this_type(pk=self.object_id)
        except:
            return None

    def get_actor_display(self):
        """Get formatted actor name"""
        return self.actor.get_full_name() or self.actor.username