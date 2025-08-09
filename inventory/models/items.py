# inventory/models/items.py - REFACTORED

from django.db import models, transaction
from django.db.models import ExpressionWrapper, F, DecimalField, Sum
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

    def negative_stock(self):
        return self.filter(current_qty__lt=0)


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
    """
    Cached aggregate quantities per location+product for POS speed
    REFACTORED: Added thread safety with select_for_update
    """

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

    # === CACHED QUANTITIES ===
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
        default=0,
        help_text=_('Quantity reserved for orders/transfers')
    )

    # === CACHED COSTS ===
    avg_cost = models.DecimalField(
        _('Average Cost'),
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text=_('Weighted average cost price')
    )

    # === NEW: Additional cost tracking from Products refactoring ===
    last_purchase_cost = models.DecimalField(
        _('Last Purchase Cost'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Last purchase cost for this location')
    )
    last_purchase_date = models.DateField(
        _('Last Purchase Date'),
        null=True,
        blank=True
    )
    last_sale_price = models.DecimalField(
        _('Last Sale Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Last sale price for this location')
    )
    last_sale_date = models.DateField(
        _('Last Sale Date'),
        null=True,
        blank=True
    )

    # === STOCK MANAGEMENT ===
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

    # === AUDIT ===
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
        ordering = ['location', 'product']
        indexes = [
            models.Index(fields=['location', 'current_qty']),
            models.Index(fields=['product', 'current_qty']),
            models.Index(fields=['current_qty']),
        ]

    def __str__(self):
        return f"{self.product.code} @ {self.location.code}: {self.current_qty}"

    @property
    def available_qty(self):
        """Quantity available for sale (current - reserved)"""
        return self.current_qty - self.reserved_qty

    @property
    def needs_reorder(self):
        """Check if stock level is below minimum"""
        return self.min_stock_level > 0 and self.current_qty <= self.min_stock_level

    @property
    def is_overstocked(self):
        """Check if stock level is above maximum"""
        return self.max_stock_level > 0 and self.current_qty > self.max_stock_level

    @classmethod
    @transaction.atomic
    def refresh_for_combination(cls, location, product):
        """
        REFACTORED: Thread-safe recalculation of cached data from movements
        Added select_for_update to prevent race conditions
        """
        from .movements import InventoryMovement

        try:
            # CRITICAL: Lock the record to prevent concurrent updates
            existing_item = cls.objects.select_for_update().filter(
                location=location,
                product=product
            ).first()

            movements = InventoryMovement.objects.filter(
                location=location,
                product=product
            )

            if not movements.exists():
                # No movements - delete the cache record
                if existing_item:
                    existing_item.delete()
                return None

            # === CALCULATE TOTALS ===
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

            # === CALCULATE WEIGHTED AVERAGE COST ===
            in_movements = movements.filter(movement_type__in=['IN', 'PRODUCTION'])

            annotated = in_movements.annotate(
                line_total=ExpressionWrapper(
                    F('quantity') * F('cost_price'),
                    output_field=DecimalField()
                )
            )

            aggregated = annotated.aggregate(
                total_cost=Sum('line_total'),
                total_qty=Sum('quantity')
            )

            total_cost = aggregated['total_cost'] or Decimal('0')
            total_qty = aggregated['total_qty'] or Decimal('0')
            avg_cost = total_cost / total_qty if total_qty > 0 else Decimal('0')

            # === GET LAST PURCHASE DATA ===
            last_purchase = in_movements.order_by('-created_at').first()
            last_purchase_cost = last_purchase.cost_price if last_purchase else None
            last_purchase_date = last_purchase.movement_date if last_purchase else None

            # === GET LAST SALE DATA ===
            last_sale = movements.filter(
                movement_type='OUT',
                source_document_type='SALE'
            ).order_by('-created_at').first()

            # For last sale price, we need to integrate with Sales module
            # For now, we'll leave it as None and update when Sales module is ready
            last_sale_price = None
            last_sale_date = last_sale.movement_date if last_sale else None

            # === GET LAST MOVEMENT ===
            last_movement = movements.order_by('-created_at').first()

            # === UPDATE OR CREATE RECORD ===
            if current_qty != 0 or existing_item:  # Keep record even for zero qty if it existed
                defaults = {
                    'current_qty': current_qty,
                    'avg_cost': avg_cost,
                    'last_purchase_cost': last_purchase_cost,
                    'last_purchase_date': last_purchase_date,
                    'last_sale_price': last_sale_price,
                    'last_sale_date': last_sale_date,
                    'last_movement_date': last_movement.created_at if last_movement else None,
                }

                # Preserve existing min/max levels and reserved_qty
                if existing_item:
                    defaults.update({
                        'min_stock_level': existing_item.min_stock_level,
                        'max_stock_level': existing_item.max_stock_level,
                        'reserved_qty': existing_item.reserved_qty,
                    })

                item, created = cls.objects.update_or_create(
                    location=location,
                    product=product,
                    defaults=defaults
                )
                return item
            else:
                # No quantity and no existing record - don't create
                return None

        except Exception as e:
            # Log error but don't break the system
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing InventoryItem for {product.code}@{location.code}: {e}")
            return None

    def reserve_quantity(self, quantity: Decimal, reason: str = '') -> bool:
        """
        ENHANCED: Reserve quantity for orders/transfers
        Thread-safe with select_for_update
        """
        if quantity <= 0:
            return False

        with transaction.atomic():
            # Lock this record
            item = InventoryItem.objects.select_for_update().get(pk=self.pk)

            if item.available_qty >= quantity:
                item.reserved_qty += quantity
                item.save(update_fields=['reserved_qty'])
                return True
            else:
                return False

    def release_reservation(self, quantity: Decimal, reason: str = '') -> bool:
        """
        ENHANCED: Release reserved quantity
        Thread-safe with select_for_update
        """
        if quantity <= 0:
            return False

        with transaction.atomic():
            # Lock this record
            item = InventoryItem.objects.select_for_update().get(pk=self.pk)

            if item.reserved_qty >= quantity:
                item.reserved_qty -= quantity
                item.save(update_fields=['reserved_qty'])
                return True
            else:
                return False

    def get_stock_analysis(self) -> dict:
        """
        NEW: Get comprehensive stock analysis for this item
        """
        return {
            'current_qty': self.current_qty,
            'available_qty': self.available_qty,
            'reserved_qty': self.reserved_qty,
            'needs_reorder': self.needs_reorder,
            'is_overstocked': self.is_overstocked,
            'min_stock_level': self.min_stock_level,
            'max_stock_level': self.max_stock_level,
            'avg_cost': self.avg_cost,
            'last_purchase_cost': self.last_purchase_cost,
            'last_sale_price': self.last_sale_price,
            'stock_value': self.current_qty * self.avg_cost,
            'last_movement_date': self.last_movement_date,
            'days_since_last_movement': (
                timezone.now().date() - self.last_movement_date.date()
            ).days if self.last_movement_date else None
        }


class InventoryBatch(models.Model):
    """
    ENHANCED: Detailed batch/lot tracking for FIFO management
    Added conversion tracking for UNKNOWN batches
    """

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

    # === NEW: Batch conversion tracking ===
    is_unknown_batch = models.BooleanField(
        _('Is Unknown Batch'),
        default=False,
        help_text=_('Auto-generated batch for products without explicit batch info')
    )
    conversion_date = models.DateTimeField(
        _('Conversion Date'),
        null=True,
        blank=True,
        help_text=_('When product was converted to batch tracking')
    )
    original_source = models.CharField(
        _('Original Source'),
        max_length=100,
        blank=True,
        help_text=_('Source of this batch (for unknown batches)')
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
            models.Index(fields=['is_unknown_batch']),
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

    @property
    def consumption_percentage(self):
        """Percentage of batch consumed"""
        if self.received_qty == 0:
            return 0
        return (self.consumed_qty / self.received_qty) * 100

    @classmethod
    @transaction.atomic
    def refresh_for_combination(cls, location, product, batch_number, expiry_date=None):
        """
        REFACTORED: Thread-safe recalculation of batch data from movements
        """
        from .movements import InventoryMovement

        try:
            # CRITICAL: Lock any existing batch record
            existing_batch = cls.objects.select_for_update().filter(
                location=location,
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date
            ).first()

            movements = InventoryMovement.objects.filter(
                location=location,
                product=product,
                batch_number=batch_number
            )

            if expiry_date:
                movements = movements.filter(expiry_date=expiry_date)

            if not movements.exists():
                # No movements for this batch - delete it
                if existing_batch:
                    existing_batch.delete()
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
                if existing_batch:
                    existing_batch.delete()
                return None

            # Get batch cost and received date from first IN movement
            first_in_movement = movements.filter(
                movement_type__in=['IN', 'PRODUCTION']
            ).order_by('created_at').first()

            if first_in_movement:
                cost_price = first_in_movement.cost_price
                received_date = first_in_movement.created_at
                is_unknown = batch_number.startswith('AUTO_') or batch_number.startswith('UNKNOWN_')
            else:
                # Fallback values
                cost_price = Decimal('0')
                received_date = timezone.now()
                is_unknown = True

            # Update or create batch record
            defaults = {
                'received_qty': batch_in,
                'remaining_qty': remaining_qty,
                'cost_price': cost_price,
                'received_date': received_date,
                'is_unknown_batch': is_unknown,
            }

            # Preserve existing conversion data
            if existing_batch and existing_batch.conversion_date:
                defaults.update({
                    'conversion_date': existing_batch.conversion_date,
                    'original_source': existing_batch.original_source,
                })

            batch, created = cls.objects.update_or_create(
                location=location,
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date,
                defaults=defaults
            )

            return batch

        except Exception as e:
            # Log error but don't break the system
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing InventoryBatch {batch_number} for {product.code}@{location.code}: {e}")
            return None

    def consume_quantity(self, quantity: Decimal) -> bool:
        """
        ENHANCED: Consume quantity from this batch (thread-safe)
        """
        if quantity <= 0:
            return False

        with transaction.atomic():
            # Lock this batch
            batch = InventoryBatch.objects.select_for_update().get(pk=self.pk)

            if batch.remaining_qty >= quantity:
                batch.remaining_qty -= quantity
                batch.save(update_fields=['remaining_qty'])
                return True
            else:
                return False

    @classmethod
    def create_unknown_batch_for_conversion(cls, location, product, current_qty, avg_cost):
        """
        NEW: Create UNKNOWN batch when converting product to batch tracking
        """
        if current_qty <= 0:
            return None

        today = timezone.now()
        batch_number = f"UNKNOWN_{product.code}_{today.strftime('%Y%m%d')}"

        batch = cls.objects.create(
            location=location,
            product=product,
            batch_number=batch_number,
            received_qty=current_qty,
            remaining_qty=current_qty,
            cost_price=avg_cost,
            received_date=today,
            is_unknown_batch=True,
            conversion_date=today,
            original_source='Batch tracking conversion'
        )

        return batch

    def get_batch_analysis(self) -> dict:
        """
        NEW: Get comprehensive batch analysis
        """
        return {
            'batch_number': self.batch_number,
            'received_qty': self.received_qty,
            'remaining_qty': self.remaining_qty,
            'consumed_qty': self.consumed_qty,
            'consumption_percentage': self.consumption_percentage,
            'cost_price': self.cost_price,
            'total_value': self.remaining_qty * self.cost_price,
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
            'is_unknown_batch': self.is_unknown_batch,
            'received_date': self.received_date,
            'expiry_date': self.expiry_date,
        }