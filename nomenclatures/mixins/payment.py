# nomenclatures/mixins/payment.py
"""
Payment Mixin - EXTRACTED FROM purchases.models.base
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone


class PaymentMixin(models.Model):
    """
    Mixin за документи с плащания
    """

    # =====================
    # PAYMENT STATUS
    # =====================
    is_paid = models.BooleanField(
        _('Is Paid'),
        default=False,
        help_text=_('Whether this document has been paid')
    )

    payment_date = models.DateField(
        _('Payment Date'),
        null=True,
        blank=True,
        help_text=_('When payment was made')
    )

    # =====================
    # PAYMENT DETAILS
    # =====================
    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        blank=True,
        help_text=_('How payment was made')
    )

    payment_reference = models.CharField(
        _('Payment Reference'),
        max_length=100,
        blank=True,
        help_text=_('Bank reference, transaction ID, etc.')
    )

    # =====================
    # PAYMENT TERMS
    # =====================
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=100,
        blank=True,
        help_text=_('Payment terms and conditions')
    )

    due_date = models.DateField(
        _('Due Date'),
        null=True,
        blank=True,
        help_text=_('When payment is due')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Payment validation"""
        super().clean()

        # Payment validation
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()

    @property
    def is_overdue(self):
        """Check if payment is overdue"""
        if not self.due_date or self.is_paid:
            return False
        return timezone.now().date() > self.due_date

    @property
    def days_until_due(self):
        """Days until payment is due"""
        if not self.due_date or self.is_paid:
            return None

        delta = self.due_date - timezone.now().date()
        return delta.days