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

    Използва се главно от DeliveryReceipt и понякога от PurchaseOrder.
    НЕ се използва от PurchaseRequest.
    """

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

    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        blank=True,
        help_text=_('How payment was made')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Payment validation enhanced with DocumentType"""
        super().clean()

        # Payment validation
        if self.payment_date and not self.is_paid:
            raise ValidationError({
                'payment_date': _('Payment date can only be set if document is marked as paid')
            })

        if self.is_paid and not self.payment_date:
            self.payment_date = timezone.now().date()