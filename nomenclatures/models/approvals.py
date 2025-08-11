# nomenclatures/models/approvals.py - SIMPLIFIED & CLEAN
"""
Approval System - SIMPLIFIED VERSION

ЦЕЛИ НА РЕФАКТОРИРАНЕ:
- Опростяване на ApprovalRule (премахване на complexity)
- Ясна интеграция с новия DocumentType
- Запазване на core функционалност
- По-лесна администрация

ПРЕМАХНАТО:
- auto_approve_conditions (твърде сложно за POS система)
- escalation_days (overkill)
- parallel approvals (ненужно)
- content_type fallback (DocumentType е достатъчен)

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
# APPROVAL RULE MANAGER
# =================================================================

class ApprovalRuleManager(models.Manager):
    """Simplified manager for ApprovalRule"""

    def for_document_type(self, document_type):
        """Get rules for specific document type"""
        return self.filter(document_type=document_type, is_active=True)

    def for_transition(self, document_type, from_status, to_status):
        """Get rules for specific status transition"""
        return self.filter(
            document_type=document_type,
            from_status=from_status,
            to_status=to_status,
            is_active=True
        ).order_by('approval_level', 'sort_order')

    def for_amount_range(self, min_amount, max_amount=None):
        """Get rules applicable for amount range"""
        queryset = self.filter(min_amount__lte=min_amount)
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


# =================================================================
# APPROVAL RULE - SIMPLIFIED
# =================================================================

class ApprovalRule(models.Model):
    """
    Approval Rule - SIMPLIFIED VERSION

    Дефинира кой може да одобрява какво при какви условия.
    Опростена версия без излишна complexity.
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
    # STATUS TRANSITION
    # =====================

    from_status = models.CharField(
        _('From Status'),
        max_length=30,
        help_text=_('Document status this rule applies from: "submitted", "draft"')
    )

    to_status = models.CharField(
        _('To Status'),
        max_length=30,
        help_text=_('Target status after approval: "approved", "rejected"')
    )

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
    # FINANCIAL LIMITS
    # =====================

    min_amount = models.DecimalField(
        _('Minimum Amount'),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Minimum document amount this rule applies to')
    )

    max_amount = models.DecimalField(
        _('Maximum Amount'),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Maximum document amount (null = no limit)')
    )

    currency = models.CharField(
        _('Currency'),
        max_length=3,
        default='BGN',
        help_text=_('Currency for amount limits')
    )

    # =====================
    # APPROVER CONFIGURATION
    # =====================

    APPROVER_TYPE_CHOICES = [
        ('user', _('Specific User')),
        ('role', _('User Role/Group')),
        ('permission', _('Permission')),
    ]

    approver_type = models.CharField(
        _('Approver Type'),
        max_length=20,
        choices=APPROVER_TYPE_CHOICES,
        help_text=_('How to determine who can approve')
    )

    approver_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules_as_user',
        verbose_name=_('Approver User'),
        help_text=_('Specific user who can approve (if type=user)')
    )

    approver_role = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules_as_role',
        verbose_name=_('Approver Role'),
        help_text=_('User group that can approve (if type=role)')
    )

    approver_permission = models.ForeignKey(
        'auth.Permission',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='approval_rules_as_permission',
        verbose_name=_('Approver Permission'),
        help_text=_('Permission required to approve (if type=permission)')
    )

    # =====================
    # BEHAVIOR SETTINGS
    # =====================

    rejection_allowed = models.BooleanField(
        _('Rejection Allowed'),
        default=True,
        help_text=_('Can approver reject at this level?')
    )

    requires_reason = models.BooleanField(
        _('Requires Reason'),
        default=False,
        help_text=_('Must provide reason/comment for approval/rejection?')
    )

    # =====================
    # NOTIFICATIONS (simplified)
    # =====================

    notify_on_trigger = models.BooleanField(
        _('Notify on Trigger'),
        default=True,
        help_text=_('Send notification when this rule is triggered')
    )

    notify_on_complete = models.BooleanField(
        _('Notify on Complete'),
        default=True,
        help_text=_('Send notification when approval/rejection is completed')
    )

    # =====================
    # AUDIT FIELDS
    # =====================

    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_approval_rules',
        verbose_name=_('Created By')
    )

    # =====================
    # MANAGERS
    # =====================

    objects = ApprovalRuleManager()

    class Meta:
        verbose_name = _('Approval Rule')
        verbose_name_plural = _('Approval Rules')
        ordering = ['document_type', 'approval_level', 'sort_order']
        indexes = [
            models.Index(fields=['document_type', 'from_status', 'to_status']),
            models.Index(fields=['approval_level', 'sort_order']),
            models.Index(fields=['min_amount', 'max_amount']),
            models.Index(fields=['approver_type', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['document_type', 'from_status', 'to_status', 'approval_level'],
                name='unique_approval_rule_per_level'
            )
        ]

    def __str__(self):
        amount_range = f"{self.min_amount}"
        if self.max_amount:
            amount_range += f"-{self.max_amount}"
        else:
            amount_range += "+"

        return f"{self.name} (Level {self.approval_level}): {self.from_status}→{self.to_status} ({amount_range} {self.currency})"

    def clean(self):
        """Simplified validation"""
        super().clean()

        # Amount validation
        if self.max_amount and self.min_amount > self.max_amount:
            raise ValidationError({
                'max_amount': _('Maximum amount must be greater than minimum amount')
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

        # Clear conflicting approver fields
        if self.approver_type != 'user':
            self.approver_user = None
        if self.approver_type != 'role':
            self.approver_role = None
        if self.approver_type != 'permission':
            self.approver_permission = None

    # =====================
    # BUSINESS METHODS
    # =====================

    def can_user_approve(self, user, document=None):
        """Check if user can approve using this rule"""
        if not self.is_active:
            return False

        if self.approver_type == 'user':
            return self.approver_user == user

        elif self.approver_type == 'role':
            return user.groups.filter(id=self.approver_role.id).exists()

        elif self.approver_type == 'permission':
            return user.has_perm(
                f'{self.approver_permission.content_type.app_label}.{self.approver_permission.codename}')

        return False

    def applies_to_amount(self, amount):
        """Check if rule applies to given amount"""
        if amount < self.min_amount:
            return False

        if self.max_amount and amount > self.max_amount:
            return False

        return True

    def get_approver_display(self):
        """Get human-readable approver information"""
        if self.approver_type == 'user' and self.approver_user:
            return f"User: {self.approver_user.get_full_name() or self.approver_user.username}"
        elif self.approver_type == 'role' and self.approver_role:
            return f"Role: {self.approver_role.name}"
        elif self.approver_type == 'permission' and self.approver_permission:
            return f"Permission: {self.approver_permission.name}"
        else:
            return "Unknown"


# =================================================================
# APPROVAL LOG - UNCHANGED BUT SIMPLIFIED
# =================================================================

class ApprovalLog(models.Model):
    """
    Approval Log - Audit trail за approval actions

    Записва всички approval/rejection действия за audit purposes.
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
        blank=True
    )

    class Meta:
        verbose_name = _('Approval Log')
        verbose_name_plural = _('Approval Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['actor', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['rule', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.get_action_display()}: {self.from_status} → {self.to_status} by {self.actor.username}"

    @property
    def document(self):
        """Get referenced document object"""
        try:
            return self.content_type.get_object_for_this_type(id=self.object_id)
        except:
            return None


# =================================================================
# HELPER FUNCTIONS
# =================================================================

def get_approval_rules_for_transition(document_type, from_status, to_status, amount=None):
    """
    Get applicable approval rules for status transition

    Args:
        document_type: DocumentType instance
        from_status: Current status
        to_status: Target status
        amount: Document amount (optional)

    Returns:
        QuerySet of applicable ApprovalRule instances
    """
    rules = ApprovalRule.objects.for_transition(document_type, from_status, to_status)

    if amount is not None:
        rules = rules.filter(
            min_amount__lte=amount
        ).filter(
            models.Q(max_amount__gte=amount) | models.Q(max_amount__isnull=True)
        )

    return rules


def can_user_approve_transition(user, document_type, from_status, to_status, amount=None):
    """
    Check if user can approve specific transition

    Args:
        user: User instance
        document_type: DocumentType instance
        from_status: Current status
        to_status: Target status
        amount: Document amount (optional)

    Returns:
        bool: True if user can approve
    """
    rules = get_approval_rules_for_transition(document_type, from_status, to_status, amount)

    for rule in rules:
        if rule.can_user_approve(user):
            return True

    return False


def create_basic_approval_rules():
    """
    Create basic approval rules for standard POS system

    Usage:
        create_basic_approval_rules()  # Creates standard rules
    """
    from nomenclatures.models import DocumentType
    from django.contrib.auth.models import Group, Permission

    # Get or create manager group
    managers_group, _ = Group.objects.get_or_create(name='Managers')

    # Get document types
    try:
        request_type = DocumentType.objects.get(type_key='purchase_request')

        # Basic approval rule: Managers can approve purchase requests
        ApprovalRule.objects.get_or_create(
            document_type=request_type,
            from_status='submitted',
            to_status='approved',
            approval_level=1,
            defaults={
                'name': 'Manager approval for purchase requests',
                'approver_type': 'role',
                'approver_role': managers_group,
                'min_amount': Decimal('0.00'),
                'max_amount': None,  # No limit
                'rejection_allowed': True,
                'requires_reason': True
            }
        )

        print("✅ Basic approval rules created successfully")

    except DocumentType.DoesNotExist:
        print("❌ DocumentType 'purchase_request' not found. Create document types first.")
    except Exception as e:
        print(f"❌ Error creating approval rules: {e}")