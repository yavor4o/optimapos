# nomenclatures/mixins/delivery.py
"""
Delivery Mixin - EXTRACTED FROM purchases.models.base
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone


class DeliveryMixin(models.Model):
    """
    Mixin за документи с delivery информация

    Използва се от DeliveryReceipt.
    НЕ се използва от PurchaseRequest или PurchaseOrder.
    """

    delivery_date = models.DateField(
        _('Delivery Date'),
        help_text=_('When goods were delivered')
    )

    delivery_instructions = models.TextField(
        _('Delivery Instructions'),
        blank=True,
        help_text=_('Special instructions for delivery')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Delivery validation"""
        super().clean()
        # Delivery date може да е във всякакво време - това е реалната дата