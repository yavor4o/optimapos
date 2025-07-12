# inventory/models/items.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal


class InventoryItemManager(models.Manager):
    """Manager for inventory items (cached quantities)"""

    def with_stock(self):
        return self.filter(current_qty__gt=0)

    def for_location(self, location):
        return self.filter(location=location)

    def for_product(self, product):
        return self.filter(product=product)

    def low_stock(self, threshold=10):
        return self.filter(
            current_qty__lte=threshold,
            current_qty__gt=0
        )


class InventoryBatchManager(models.Manager):
    """Manager for inventory batches"""

    def with_stock(self):
        return self.filter(remaining_qty__gt=0)

    def expired(self):
        from django.utils import timezone
        return self.filter(
            expiry_date__lt=timezone.now().date(),
            remaining_qty__gt=0
        )

    def expiring_soon(self, days=30):
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff,
            expiry_date__gte=timezone.now().date(),
            remaining_qty__gt=0
        )

    def fifo_order(self):
        """Order batches for FIFO consumption"""
        return self.filter(remaining_qty__gt=0).order_by('received_date', 'expiry_date')


class InventoryItem(models.Model):
    """Cached aggregate quantities per location+product for POS speed"""

    # Unique combination
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='inventory_items',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='inventory_items',
        verbose_name=_('Product')
    )

    # Cached quantities (calculated from movements)
    current_qty = models.DecimalField(
        _('Current Quantity'),
        max_digits=12,
        decimal_places=3,
        default=0
    )
    reserved_qty = models.DecimalField(
        _('Reserved Quantity'),
        max_digits=12,
        decimal_places=3,
        default=0
    )

    # Cached cost data (for moving average)
    avg_cost = models.DecimalField(
        _('Average Cost'),
        max_digits=10,
        decimal_places=4,
        default=0
    )

    # Reorder settings
    min_stock_level = models.DecimalField(
        _('Minimum Stock Level'),
        max_digits=12,
        decimal_places=3,
        default=0
    )
    max_stock_level = models.DecimalField(
        _('Maximum Stock Level'),
        max_digits=12,
        decimal_places=3,
        default=0
    )

    # Cache metadata
    last_movement_date = models.DateTimeField(
        _('Last Movement'),
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = InventoryItemManager()

    class Meta:
        unique_together = ('location', 'product')
        verbose_name = _('Inventory Item')
        verbose_name_plural = _('Inventory Items')
        indexes = [
            models.Index(fields=['location', 'current_qty']),
            models.Index(fields=['product', 'current_qty']),
        ]

    def __str__(self):
        return f"{self.product.code} @ {self.location.code}: {self.available_qty}"

    @property
    def available_qty(self):
        """Available quantity (current - reserved)"""
        return self.current_qty - self.reserved_qty

    @property
    def needs_reorder(self):
        """Check if stock is below minimum level"""
        return self.available_qty <= self.min_stock_level

    @property
    def is_overstocked(self):
        """Check if stock is above maximum level"""
        return self.max_stock_level > 0 and self.current_qty > self.max_stock_level

    @classmethod
    def refresh_for_combination(cls, location, product):
        """Recalculate cached data from movements"""
        from .movements import InventoryMovement

        movements = InventoryMovement.objects.filter(
            location=location,
            product=product
        )

        if not movements.exists():
            # No movements - delete the cache record
            cls.objects.filter(location=location, product=product).delete()
            return None

        # Calculate totals
        total_in = movements.filter(
            movement_type__in=['IN', 'PRODUCTION']
        ).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        total_out = movements.filter(
            movement_type__in=['OUT']
        ).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        current_qty = total_in - total_out

        # Calculate weighted average cost
        in_movements = movements.filter(movement_type__in=['IN', 'PRODUCTION'])
        if in_movements.exists():
            total_cost = sum(
                m.quantity * m.cost_price for m in in_movements
            )
            total_qty = sum(m.quantity for m in in_movements)
            avg_cost = total_cost / total_qty if total_qty > 0 else Decimal('0')
        else:
            avg_cost = Decimal('0')

        # Get last movement
        last_movement = movements.order_by('-created_at').first()

        # Update or create
        if current_qty > 0:
            item, created = cls.objects.update_or_create(
                location=location,
                product=product,
                defaults={
                    'current_qty': current_qty,
                    'avg_cost': avg_cost,
                    'last_movement_date': last_movement.created_at if last_movement else None,
                }
            )
            return item
        else:
            # Zero or negative stock - delete the record
            cls.objects.filter(location=location, product=product).delete()
            return None


class InventoryBatch(models.Model):
    """Detailed batch/lot tracking for FIFO management"""

    # Unique combination
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.CASCADE,
        related_name='inventory_batches',
        verbose_name=_('Location')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='inventory_batches',
        verbose_name=_('Product')
    )

    # Batch identification
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True
    )

    # Batch quantities
    received_qty = models.DecimalField(
        _('Received Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Original quantity received')
    )
    remaining_qty = models.DecimalField(
        _('Remaining Quantity'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Current remaining quantity')
    )

    # Batch cost (for this specific batch)
    cost_price = models.DecimalField(
        _('Cost Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Cost price for this batch')
    )

    # FIFO data
    received_date = models.DateTimeField(
        _('Received Date'),
        help_text=_('When this batch was received')
    )

    # Flags
    is_unknown_batch = models.BooleanField(
        _('Is Unknown Batch'),
        default=False,
        help_text=_('Auto-generated batch for products without explicit batch info')
    )

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = InventoryBatchManager()

    class Meta:
        unique_together = ('location', 'product', 'batch_number', 'expiry_date')
        verbose_name = _('Inventory Batch')
        verbose_name_plural = _('Inventory Batches')
        ordering = ['received_date', 'expiry_date']
        indexes = [
            models.Index(fields=['location', 'product', 'remaining_qty']),
            models.Index(fields=['expiry_date', 'remaining_qty']),
            models.Index(fields=['batch_number']),
        ]

    def __str__(self):
        expiry_info = f" (expires {self.expiry_date})" if self.expiry_date else ""
        unknown_info = " [AUTO]" if self.is_unknown_batch else ""
        return f"{self.product.code} - {self.batch_number}{expiry_info}: {self.remaining_qty}{unknown_info}"

    @property
    def is_expired(self):
        """Check if batch is expired"""
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.now().date()

    @property
    def days_until_expiry(self):
        """Days until expiry (negative if expired)"""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - timezone.now().date()
        return delta.days

    @property
    def consumed_qty(self):
        """Quantity consumed from this batch"""
        return self.received_qty - self.remaining_qty

    @classmethod
    def refresh_for_combination(cls, location, product, batch_number, expiry_date=None):
        """Recalculate batch data from movements"""
        from .movements import InventoryMovement

        movements = InventoryMovement.objects.filter(
            location=location,
            product=product,
            batch_number=batch_number
        )

        if expiry_date:
            movements = movements.filter(expiry_date=expiry_date)

        if not movements.exists():
            # No movements for this batch - delete it
            cls.objects.filter(
                location=location,
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date
            ).delete()
            return None

        # Calculate batch totals
        batch_in = movements.filter(
            movement_type__in=['IN', 'PRODUCTION']
        ).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        batch_out = movements.filter(
            movement_type__in=['OUT']
        ).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        remaining_qty = batch_in - batch_out

        if remaining_qty <= 0:
            # Batch fully consumed - delete it
            cls.objects.filter(
                location=location,
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date
            ).delete()
            return None

        # Get batch cost and received date from first IN movement
        first_in_movement = movements.filter(
            movement_type__in=['IN', 'PRODUCTION']
        ).order_by('created_at').first()

        if first_in_movement:
            cost_price = first_in_movement.cost_price
            received_date = first_in_movement.created_at
            is_unknown = batch_number.startswith('AUTO_')
        else:
            # Fallback values
            cost_price = Decimal('0')
            received_date = timezone.now()
            is_unknown = True

        # Update or create batch record
        batch, created = cls.objects.update_or_create(
            location=location,
            product=product,
            batch_number=batch_number,
            expiry_date=expiry_date,
            defaults={
                'received_qty': batch_in,
                'remaining_qty': remaining_qty,
                'cost_price': cost_price,
                'received_date': received_date,
                'is_unknown_batch': is_unknown,
            }
        )

        return batch