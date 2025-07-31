# inventory/models/movements.py

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal


class InventoryMovementManager(models.Manager):
    """Manager for inventory movements (source of truth)"""

    def incoming(self):
        return self.filter(movement_type='IN')

    def outgoing(self):
        return self.filter(movement_type='OUT')

    def transfers(self):
        return self.filter(movement_type='TRANSFER')

    def adjustments(self):
        return self.filter(movement_type='ADJUSTMENT')

    def for_product(self, product):
        return self.filter(product=product)

    def for_location(self, location):
        return self.filter(location=location)

    def recent(self, days=30):
        from datetime import timedelta
        cutoff = timezone.now().date() - timedelta(days=days)
        return self.filter(movement_date__gte=cutoff)


class InventoryMovement(models.Model):
    """Source of truth - ALL inventory movements"""

    # Movement types
    IN = 'IN'
    OUT = 'OUT'
    TRANSFER = 'TRANSFER'
    ADJUSTMENT = 'ADJUSTMENT'
    PRODUCTION = 'PRODUCTION'
    CYCLE_COUNT = 'CYCLE_COUNT'

    MOVEMENT_TYPE_CHOICES = [
        (IN, _('Incoming (Purchase/Receipt)')),
        (OUT, _('Outgoing (Sale/Issue)')),
        (TRANSFER, _('Transfer Between Locations')),
        (ADJUSTMENT, _('Inventory Adjustment')),
        (PRODUCTION, _('Production/Assembly')),
        (CYCLE_COUNT, _('Cycle Count Correction')),
    ]

    # Core data
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='movements',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='inventory_movements',
        verbose_name=_('Product')
    )

    # Movement details
    movement_type = models.CharField(
        _('Movement Type'),
        max_length=15,
        choices=MOVEMENT_TYPE_CHOICES
    )
    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Always positive - type determines direction')
    )
    cost_price = models.DecimalField(
        _('Cost Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Actual unit cost price for this specific movement')
    )

    # Optional batch/lot tracking
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        null=True,
        blank=True
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True
    )
    serial_number = models.CharField(
        _('Serial Number'),
        max_length=50,
        null=True,
        blank=True
    )

    # Transfer specific (when movement_type='TRANSFER')
    from_location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='outbound_transfers',
        verbose_name=_('From Location')
    )
    to_location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='inbound_transfers',
        verbose_name=_('To Location')
    )

    # Document reference
    source_document_type = models.CharField(
        _('Source Document Type'),
        max_length=20,
        choices=[
            ('PURCHASES', _('Purchase Order')),
            ('SALE', _('Sale')),
            ('TRANSFER', _('Transfer Order')),
            ('ADJUSTMENT', _('Adjustment')),
            ('PRODUCTION', _('Production Order')),
            ('CYCLE_COUNT', _('Cycle Count')),
        ],
        blank=True
    )
    source_document_number = models.CharField(
        _('Source Document Number'),
        max_length=50,
        blank=True
    )
    movement_date = models.DateField(_('Movement Date'))



    # Additional info
    reason = models.CharField(_('Reason'), max_length=100, blank=True)
    notes = models.TextField(_('Notes'), blank=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Created By')
    )

    objects = InventoryMovementManager()

    class Meta:
        verbose_name = _('Inventory Movement')
        verbose_name_plural = _('Inventory Movements')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['location', 'product', '-created_at']),
            models.Index(fields=['movement_type', '-created_at']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['movement_date']),
            models.Index(fields=['source_document_number']),
        ]

    def __str__(self):
        direction = "+" if self.movement_type == self.IN else "-"
        batch_info = f" ({self.batch_number})" if self.batch_number else ""
        return f"{direction}{self.quantity} {self.product.code}{batch_info} @ {self.location.code}"

    def clean(self):
        # Quantity validation
        if self.quantity <= 0:
            raise ValidationError({
                'quantity': _('Quantity must be positive')
            })

        # Cost price validation
        if self.cost_price < 0:
            raise ValidationError({
                'cost_price': _('Cost price cannot be negative')
            })

        # Transfer validation
        if self.movement_type == self.TRANSFER:
            if not self.from_location or not self.to_location:
                raise ValidationError({
                    'movement_type': _('Transfer movements require both from_location and to_location')
                })
            if self.from_location == self.to_location:
                raise ValidationError({
                    'to_location': _('Cannot transfer to the same location')
                })

        # Batch tracking validation
        if (self.product and self.product.track_batches and
                self.movement_type == self.IN and not self.batch_number):
            # Auto-generate batch number for batch-tracked products
            self.batch_number = self.generate_auto_batch()

    def generate_auto_batch(self):
        """Generate automatic batch number for batch-tracked products"""
        today = timezone.now().date()
        return f"AUTO_{self.product.code}_{today.strftime('%y%m%d')}_{self.location.code}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        # Update cached inventory data after saving
        self.refresh_inventory_cache()

    def refresh_inventory_cache(self):
        """Refresh InventoryItem and InventoryBatch caches"""
        from .items import InventoryItem, InventoryBatch

        # Refresh aggregate inventory
        InventoryItem.refresh_for_combination(
            location=self.location,
            product=self.product
        )

        # Refresh batch inventory if applicable
        if self.batch_number:
            InventoryBatch.refresh_for_combination(
                location=self.location,
                product=self.product,
                batch_number=self.batch_number,
                expiry_date=self.expiry_date
            )

    @property
    def is_incoming(self):
        """Check if this is an incoming movement"""
        return self.movement_type in [self.IN, self.PRODUCTION]

    @property
    def is_outgoing(self):
        """Check if this is an outgoing movement"""
        return self.movement_type in [self.OUT]

    @property
    def effective_quantity(self):
        """Get signed quantity based on movement type"""
        if self.is_incoming:
            return self.quantity
        elif self.is_outgoing:
            return -self.quantity
        else:
            return Decimal('0')  # Transfers, adjustments handled separately