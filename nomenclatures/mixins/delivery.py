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
    """

    # =====================
    # DELIVERY TIMING
    # =====================
    delivery_date = models.DateField(
        _('Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When delivery was made')
    )

    expected_delivery_date = models.DateField(
        _('Expected Delivery Date'),
        null=True,
        blank=True,
        help_text=_('When delivery is expected')
    )

    # =====================
    # DELIVERY ADDRESS
    # =====================
    delivery_address = models.TextField(
        _('Delivery Address'),
        blank=True,
        help_text=_('Full delivery address')
    )

    delivery_contact = models.CharField(
        _('Delivery Contact'),
        max_length=100,
        blank=True,
        help_text=_('Contact person for delivery')
    )

    delivery_phone = models.CharField(
        _('Delivery Phone'),
        max_length=20,
        blank=True,
        help_text=_('Phone number for delivery contact')
    )

    # =====================
    # DELIVERY TRACKING
    # =====================
    tracking_number = models.CharField(
        _('Tracking Number'),
        max_length=100,
        blank=True,
        help_text=_('Courier tracking number')
    )

    carrier = models.CharField(
        _('Carrier'),
        max_length=100,
        blank=True,
        help_text=_('Delivery company/carrier')
    )

    # =====================
    # DELIVERY STATUS
    # =====================
    delivery_notes = models.TextField(
        _('Delivery Notes'),
        blank=True,
        help_text=_('Notes about the delivery')
    )

    received_by = models.CharField(
        _('Received By'),
        max_length=100,
        blank=True,
        help_text=_('Who received the delivery')
    )

    class Meta:
        abstract = True

    def clean(self):
        """Delivery validation"""
        super().clean()

        # Date validation
        if self.delivery_date and self.expected_delivery_date:
            if self.delivery_date < self.expected_delivery_date:
                # Early delivery is usually OK, just log
                pass

    @property
    def is_delivered(self):
        """Check if delivery has been made"""
        return bool(self.delivery_date)

    @property
    def is_late(self):
        """Check if delivery is late"""
        if not self.expected_delivery_date:
            return False

        compare_date = self.delivery_date or timezone.now().date()
        return compare_date > self.expected_delivery_date

    @property
    def delivery_delay_days(self):
        """Calculate delivery delay in days"""
        if not self.expected_delivery_date:
            return None

        compare_date = self.delivery_date or timezone.now().date()
        if compare_date <= self.expected_delivery_date:
            return 0

        delta = compare_date - self.expected_delivery_date
        return delta.days