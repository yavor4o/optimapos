# nomenclatures/models/approvals.py
import decimal

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

User = get_user_model()


class ApprovalRuleManager(models.Manager):
    """Manager for ApprovalRule with specialized queries"""

    def for_document(self, document):
        """Get rules applicable for specific document"""
        return self.filter(
            models.Q(document_type=document.document_type) |
            models.Q(content_type=ContentType.objects.get_for_model(document.__class__))
        ).filter(is_active=True)

    def for_user_and_amount(self, user, amount, document_type=None):
        """Get rules user can execute for given amount"""
        rules = self.filter(is_active=True)

        if document_type:
            rules = rules.filter(document_type=document_type)

        if amount is not None:
            rules = rules.filter(
                models.Q(min_amount__lte=amount) &
                models.Q(max_amount__gte=amount)
            )

        # Filter by user permissions
        return rules.filter(
            models.Q(approver_user=user) |
            models.Q(approver_role__in=user.groups.all()) |
            models.Q(approver_permission__in=user.user_permissions.all())
        )

    def get_workflow_chain(self, document):
        """Get complete approval chain for document"""
        amount = getattr(document, 'get_estimated_total', lambda: Decimal('0'))()

        return self.for_document(document).filter(
            min_amount__lte=amount,
            max_amount__gte=amount
        ).order_by('approval_level', 'sort_order')


class ApprovalRule(models.Model):
    """
    Approval Rule - Правило за одобрение

    Динамично дефинира кой може да одобрява какво, при какви условия
    """

    # =====================
    # BASIC INFO
    # =====================
    name = models.CharField(
        _('Rule Name'),
        max_length=100,
        help_text=_('Descriptive name for this approval rule')
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
        null=True,
        blank=True,
        verbose_name=_('Document Type'),
        help_text=_('Specific document type this rule applies to')
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Content Type'),
        help_text=_('Model class this rule applies to (fallback if no document type)')
    )

    # =====================
    # STATUS TRANSITIONS
    # =====================
    from_status = models.CharField(
        _('From Status'),
        max_length=30,
        help_text=_('Document status this rule can be applied from')
    )

    to_status = models.CharField(
        _('To Status'),
        max_length=30,
        help_text=_('Document status this rule transitions to')
    )

    # =====================
    # FINANCIAL LIMITS
    # =====================
    min_amount = models.DecimalField(
        _('Minimum Amount'),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Minimum document amount for this rule')
    )

    max_amount = models.DecimalField(
        _('Maximum Amount'),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Maximum document amount for this rule (null = no limit)')
    )

    currency = models.CharField(
        _('Currency'),
        max_length=3,
        default='BGN',
        help_text=_('Currency for amount limits')
    )

    # =====================
    # APPROVER DEFINITION
    # =====================
    APPROVER_TYPE_CHOICES = [
        ('user', _('Specific User')),
        ('role', _('User Role/Group')),
        ('permission', _('User Permission')),
        ('dynamic', _('Dynamic (calculated)')),
    ]

    approver_type = models.CharField(
        _('Approver Type'),
        max_length=20,
        choices=APPROVER_TYPE_CHOICES,
        default='role',
        help_text=_('How the approver is determined')
    )

    approver_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Approver User'),
        help_text=_('Specific user who can approve (if approver_type=user)')
    )

    approver_role = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Approver Role'),
        help_text=_('User group/role that can approve (if approver_type=role)')
    )

    approver_permission = models.ForeignKey(
        'auth.Permission',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Approver Permission'),
        help_text=_('Permission required to approve (if approver_type=permission)')
    )

    # =====================
    # WORKFLOW CONTROL
    # =====================
    approval_level = models.PositiveIntegerField(
        _('Approval Level'),
        default=1,
        help_text=_('Level in approval hierarchy (1=first, 2=second, etc.)')
    )

    is_parallel = models.BooleanField(
        _('Parallel Approval'),
        default=False,
        help_text=_('Can be approved in parallel with same-level rules')
    )

    requires_previous_level = models.BooleanField(
        _('Requires Previous Level'),
        default=True,
        help_text=_('Must previous approval levels be completed first?')
    )

    # =====================
    # BUSINESS RULES
    # =====================
    auto_approve_conditions = models.JSONField(
        _('Auto Approve Conditions'),
        default=dict,
        blank=True,
        help_text=_('Conditions for automatic approval (JSON)')
    )

    rejection_allowed = models.BooleanField(
        _('Rejection Allowed'),
        default=True,
        help_text=_('Can approver reject at this level?')
    )

    escalation_days = models.PositiveIntegerField(
        _('Escalation Days'),
        null=True,
        blank=True,
        help_text=_('Days before escalating to next level (null = no escalation)')
    )

    # =====================
    # NOTIFICATIONS
    # =====================
    notify_approver = models.BooleanField(
        _('Notify Approver'),
        default=True,
        help_text=_('Send notification to approver when rule is triggered')
    )

    notify_requester = models.BooleanField(
        _('Notify Requester'),
        default=True,
        help_text=_('Send notification to requester when approved/rejected')
    )

    # =====================
    # AUDIT
    # =====================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_approval_rules',
        null=True,
        blank=True
    )

    # =====================
    # MANAGERS
    # =====================
    objects = ApprovalRuleManager()

    class Meta:
        verbose_name = _('Approval Rule')
        verbose_name_plural = _('Approval Rules')
        ordering = ['approval_level', 'sort_order', 'name']
        indexes = [
            models.Index(fields=['document_type', 'from_status']),
            models.Index(fields=['content_type', 'from_status']),
            models.Index(fields=['approval_level', 'sort_order']),
            models.Index(fields=['min_amount', 'max_amount']),
            models.Index(fields=['approver_type', 'is_active']),
        ]
        unique_together = [
            ['document_type', 'from_status', 'to_status', 'approval_level', 'approver_user'],
            ['document_type', 'from_status', 'to_status', 'approval_level', 'approver_role'],
        ]

    def __str__(self):
        amount_str = f"{self.min_amount}"
        if self.max_amount:
            amount_str += f"-{self.max_amount}"
        else:
            amount_str += "+"

        return f"{self.name}: {self.from_status}→{self.to_status} ({amount_str} {self.currency})"

    # =====================
    # VALIDATION
    # =====================
    def clean(self):
        """Enhanced validation with DocumentType sync and conflict detection"""
        super().clean()

        # =====================
        # 1. BASIC CONFIGURATION VALIDATION
        # =====================

        # Must have either document_type or content_type
        if not self.document_type and not self.content_type:
            raise ValidationError({
                '__all__': _('Must specify either Document Type or Content Type')
            })

        # Amount validation
        if self.max_amount and self.min_amount > self.max_amount:
            raise ValidationError({
                'max_amount': _('Maximum amount must be greater than minimum amount')
            })

        # =====================
        # 2. APPROVER CONFIGURATION VALIDATION
        # =====================

        # Validate approver fields based on type
        if self.approver_type == 'user':
            if not self.approver_user:
                raise ValidationError({
                    'approver_user': _('Approver user is required when type is "user"')
                })
            # Clear conflicting fields
            if self.approver_role or self.approver_permission:
                raise ValidationError({
                    '__all__': _('Only approver_user should be set when type is "user"')
                })

        elif self.approver_type == 'role':
            if not self.approver_role:
                raise ValidationError({
                    'approver_role': _('Approver role is required when type is "role"')
                })
            # Clear conflicting fields
            if self.approver_user or self.approver_permission:
                raise ValidationError({
                    '__all__': _('Only approver_role should be set when type is "role"')
                })

        elif self.approver_type == 'permission':
            if not self.approver_permission:
                raise ValidationError({
                    'approver_permission': _('Approver permission is required when type is "permission"')
                })
            # Clear conflicting fields
            if self.approver_user or self.approver_role:
                raise ValidationError({
                    '__all__': _('Only approver_permission should be set when type is "permission"')
                })

        elif self.approver_type == 'dynamic':
            # Dynamic type shouldn't have any approver fields set
            if self.approver_user or self.approver_role or self.approver_permission:
                raise ValidationError({
                    '__all__': _('No approver fields should be set when type is "dynamic"')
                })

        # =====================
        # 3. DOCUMENTTYPE SYNCHRONIZATION VALIDATION
        # =====================

        if self.document_type:
            # Check if statuses exist in DocumentType
            allowed_statuses = self.document_type.allowed_statuses or []

            if self.from_status not in allowed_statuses:
                raise ValidationError({
                    'from_status': _(
                        f'Status "{self.from_status}" is not in DocumentType allowed statuses: {allowed_statuses}')
                })

            if self.to_status not in allowed_statuses:
                raise ValidationError({
                    'to_status': _(
                        f'Status "{self.to_status}" is not in DocumentType allowed statuses: {allowed_statuses}')
                })

            # Check if transition is allowed by DocumentType
            if not self.document_type.can_transition_to(self.from_status, self.to_status):
                next_statuses = self.document_type.get_next_statuses(self.from_status)
                raise ValidationError({
                    '__all__': _(
                        f'DocumentType "{self.document_type.name}" does not allow transition from "{self.from_status}" to "{self.to_status}". Allowed next statuses: {next_statuses}')
                })

        # =====================
        # 4. OVERLAPPING RULES DETECTION
        # =====================

        # Find potentially conflicting rules
        base_query = ApprovalRule.objects.filter(
            is_active=True
        ).exclude(pk=self.pk if self.pk else None)

        # Filter by document scope
        if self.document_type:
            base_query = base_query.filter(document_type=self.document_type)
        elif self.content_type:
            base_query = base_query.filter(content_type=self.content_type)

        # Filter by transition and level
        conflicting_rules = base_query.filter(
            from_status=self.from_status,
            to_status=self.to_status,
            approval_level=self.approval_level
        )

        # Check for approver conflicts
        approver_conflicts = []

        for rule in conflicting_rules:
            # Same approver type and same approver
            if (self.approver_type == rule.approver_type and
                    self.approver_user == rule.approver_user and
                    self.approver_role == rule.approver_role and
                    self.approver_permission == rule.approver_permission):

                # Check for amount range overlap
                if self._amount_ranges_overlap(rule):
                    approver_conflicts.append(rule)

        if approver_conflicts:
            conflict_details = []
            for rule in approver_conflicts:
                range_str = f"{rule.min_amount}-{rule.max_amount or '∞'} {rule.currency}"
                conflict_details.append(f"'{rule.name}' ({range_str})")

            raise ValidationError({
                '__all__': _(f'Conflicting rules with overlapping amount ranges: {", ".join(conflict_details)}')
            })

        # =====================
        # 5. BUSINESS LOGIC VALIDATION
        # =====================

        # Level sequence validation
        if self.approval_level > 1 and self.requires_previous_level:
            # Check if previous level exists
            previous_level_exists = ApprovalRule.objects.filter(
                document_type=self.document_type,
                from_status=self.from_status,
                approval_level=self.approval_level - 1,
                is_active=True
            ).exists()

            if not previous_level_exists:
                raise ValidationError({
                    'approval_level': _(f'No active rule exists for previous level {self.approval_level - 1}')
                })

        # Escalation validation
        if self.escalation_days is not None and self.escalation_days <= 0:
            raise ValidationError({
                'escalation_days': _('Escalation days must be positive if specified')
            })

    def _amount_ranges_overlap(self, other_rule):
        """Check if amount ranges overlap with another rule"""

        # Handle None values (unlimited max_amount)
        self_max = self.max_amount if self.max_amount is not None else float('inf')
        other_max = other_rule.max_amount if other_rule.max_amount is not None else float('inf')

        # Check for overlap: ranges overlap if one starts before the other ends
        return not (self_max < other_rule.min_amount or self.min_amount > other_max)

    # =====================
    # BUSINESS METHODS
    # =====================
    def can_approve(self, user, document=None):
        """Check if user can approve using this rule"""
        if not self.is_active:
            return False

        if self.approver_type == 'user':
            return user == self.approver_user
        elif self.approver_type == 'role':
            return user.groups.filter(id=self.approver_role.id).exists()
        elif self.approver_type == 'permission':
            return user.has_perm(
                f"{self.approver_permission.content_type.app_label}.{self.approver_permission.codename}")
        elif self.approver_type == 'dynamic':
            # Implement dynamic logic based on document
            return self._evaluate_dynamic_approval(user, document)

        return False

    def applies_to_document(self, document):
        """Check if this rule applies to given document"""

        # Document type check
        if self.document_type and document.document_type != self.document_type:
            return False

        # Content type check (fallback)
        if not self.document_type and self.content_type:
            if ContentType.objects.get_for_model(document) != self.content_type:
                return False

        # Status check
        if document.status != self.from_status:
            return False

        # Amount check - ENHANCED with safe handling
        if hasattr(document, 'get_estimated_total'):
            try:
                amount = document.get_estimated_total()
                # Only validate amount if we got a valid numeric value
                if amount is not None and amount >= 0:
                    if amount < self.min_amount:
                        return False
                    if self.max_amount and amount > self.max_amount:
                        return False
            except (AttributeError, TypeError, ValueError, decimal.InvalidOperation):
                # If amount calculation fails, skip amount validation
                # Rule applies based on other criteria (document_type, status, etc.)
                pass

        return True

    def _evaluate_dynamic_approval(self, user, document):
        """Evaluate dynamic approval logic"""
        if hasattr(document, 'location') and hasattr(user, 'managed_locations'):
            return document.location in user.managed_locations.all()

        return False

    # =====================
    # DISPLAY METHODS
    # =====================
    def get_approver_display(self):
        """Get human-readable approver information"""
        if self.approver_type == 'user' and self.approver_user:
            return f"User: {self.approver_user.get_full_name()}"
        elif self.approver_type == 'role' and self.approver_role:
            return f"Role: {self.approver_role.name}"
        elif self.approver_type == 'permission' and self.approver_permission:
            return f"Permission: {self.approver_permission.name}"
        elif self.approver_type == 'dynamic':
            return "Dynamic (calculated)"
        return "Not configured"

    def get_amount_range_display(self):
        """Get formatted amount range"""
        if self.max_amount:
            return f"{self.min_amount} - {self.max_amount} {self.currency}"
        else:
            return f"{self.min_amount}+ {self.currency}"


class ApprovalLog(models.Model):
    """
    Approval Log - История на одобренията

    Записва всяко действие в approval процеса
    """

    # =====================
    # DOCUMENT REFERENCE
    # =====================
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()

    # =====================
    # APPROVAL ACTION
    # =====================
    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.PROTECT,
        verbose_name=_('Applied Rule')
    )

    action = models.CharField(
        _('Action'),
        max_length=20,
        choices=[
            ('submitted', _('Submitted for Approval')),
            ('approved', _('Approved')),
            ('rejected', _('Rejected')),
            ('escalated', _('Escalated')),
            ('auto_approved', _('Auto Approved')),
        ]
    )

    from_status = models.CharField(_('From Status'), max_length=30)
    to_status = models.CharField(_('To Status'), max_length=30)

    # =====================
    # ACTOR INFO
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
    # METADATA
    # =====================
    timestamp = models.DateTimeField(auto_now_add=True)

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
        ]

    def __str__(self):
        return f"{self.actor.get_full_name()}: {self.get_action_display()} ({self.timestamp})"