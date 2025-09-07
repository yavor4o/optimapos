# inventory/models/movements.py - REFACTORED

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

    def sales(self):
        """NEW: Filter movements from sales"""
        return self.filter(
            movement_type='OUT',
            source_document_type='SALE'
        )

    def purchases(self):
        """NEW: Filter movements from purchases"""
        return self.filter(
            movement_type='IN',
            source_document_type='PURCHASES'
        )

    def for_product(self, product):
        return self.filter(product=product)

    def for_location(self, location):
        return self.filter(location=location)

    def recent(self, days=30):
        from datetime import timedelta
        cutoff = timezone.now().date() - timedelta(days=days)
        return self.filter(movement_date__gte=cutoff)

    def with_profit_data(self):
        """NEW: Filter movements that have profit tracking"""
        return self.filter(sale_price__isnull=False)


class InventoryMovement(models.Model):
    """
    Source of truth - ALL inventory movements
    REFACTORED: Added sale price tracking for profit analysis
    """

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

    # === CORE DATA ===
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

    # === MOVEMENT DETAILS ===
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
    # FIXED: Standardized to CostPriceField for consistency
    cost_price = models.DecimalField(
        _('Cost Price'),
        max_digits=12,  # FIXED: Increased from 10 to 12 for consistency
        decimal_places=4,  # Keep 4 for calculation precision
        help_text=_('Actual unit cost price for this specific movement (4 decimal precision)')
    )

    # === NEW: Sale price tracking for profit analysis ===
    # FIXED: Standardized to CurrencyField for consistency
    sale_price = models.DecimalField(
        _('Sale Price'),
        max_digits=12,  # FIXED: Increased from 10 to 12 for consistency
        decimal_places=2,  # Keep 2 for currency display
        null=True,
        blank=True,
        help_text=_('Sale price per unit (for OUT movements from sales, currency precision)')
    )
    # FIXED: Standardized to CurrencyField for consistency
    profit_amount = models.DecimalField(
        _('Profit Amount'),
        max_digits=12,  # FIXED: Increased from 10 to 12 for consistency
        decimal_places=2,  # Keep 2 for currency display
        null=True,
        blank=True,
        help_text=_('Calculated profit per unit (sale_price - cost_price)')
    )

    # === BATCH/LOT TRACKING ===
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

    # === TRANSFER SPECIFIC ===
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

    # === DOCUMENT REFERENCE ===
    source_document_type = models.CharField(
        _('Source Document Type'),
        max_length=30,
        blank=True,
        db_index=True,
        help_text=_('Automatically set by system services')
    )
    source_document_number = models.CharField(
        _('Source Document Number'),
        max_length=50,
        blank=True
    )
    source_document_line_id = models.PositiveIntegerField(
        _('Source Document Line ID'),
        null=True,
        blank=True,
        help_text=_('Reference to specific line in source document')
    )

    # === DATES ===
    movement_date = models.DateField(
        _('Movement Date'),
        default=timezone.now,
        help_text=_('Business date of the movement')
    )

    # === ADDITIONAL INFO ===
    reason = models.CharField(
        _('Reason'),
        max_length=200,
        blank=True,
        help_text=_('Reason for this movement')
    )

    # === AUDIT ===
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
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
            models.Index(fields=['location', 'product', 'movement_date']),
            models.Index(fields=['movement_type', 'movement_date']),
            models.Index(fields=['source_document_type', 'source_document_number']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['movement_date']),
            models.Index(fields=['created_at']),
            # NEW: Index for profit analysis
            models.Index(fields=['sale_price', 'movement_date']),
        ]

    def __str__(self):
        direction = "→" if self.is_incoming else "←"
        batch_info = f" [{self.batch_number}]" if self.batch_number else ""
        return f"{direction} {self.quantity} × {self.product.code} @ {self.location.code}{batch_info}"

    def clean(self):
        """Enhanced validation"""
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

        # Sale price validation (NEW)
        if self.sale_price is not None and self.sale_price < 0:
            raise ValidationError({
                'sale_price': _('Sale price cannot be negative')
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

        # Sale price logic validation (NEW)
        if self.sale_price and self.movement_type != self.OUT:
            raise ValidationError({
                'sale_price': _('Sale price can only be set for outgoing movements')
            })

    def generate_auto_batch(self):
        """Generate automatic batch number for batch-tracked products"""
        today = timezone.now().date()
        return f"AUTO_{self.product.code}_{today.strftime('%y%m%d')}_{self.location.code}"

    def save(self, *args, **kwargs):
        # Calculate profit if both prices are available (NEW)
        if self.sale_price is not None and self.cost_price is not None:
            self.profit_amount = self.sale_price - self.cost_price
        else:
            self.profit_amount = None

        self.full_clean()
        super().save(*args, **kwargs)



    # def refresh_inventory_cache(self):
    #     """
    #     Refresh InventoryItem and InventoryBatch caches
    #     ENHANCED: Better error handling
    #     """
    #     try:
    #         from .items import InventoryItem, InventoryBatch
    #
    #         # Refresh aggregate inventory
    #         InventoryItem.refresh_for_combination(
    #             location=self.location,
    #             product=self.product
    #         )
    #
    #         # Refresh batch inventory if applicable
    #         if self.batch_number:
    #             InventoryBatch.refresh_for_combination(
    #                 location=self.location,
    #                 product=self.product,
    #                 batch_number=self.batch_number,
    #                 expiry_date=self.expiry_date
    #             )
    #
    #     except Exception as e:
    #         # Log error but don't break the movement creation
    #         import logging
    #         logger = logging.getLogger(__name__)
    #         logger.error(f"Error refreshing cache for movement {self.id}: {e}")

    # === PROPERTIES ===

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

    @property
    def total_cost_value(self):
        """Total cost value of this movement"""
        return self.quantity * self.cost_price

    @property
    def total_sale_value(self):
        """NEW: Total sale value of this movement"""
        if self.sale_price:
            return self.quantity * self.sale_price
        return None

    @property
    def total_profit(self):
        """NEW: Total profit from this movement"""
        if self.profit_amount:
            return self.quantity * self.profit_amount
        return None

    @property
    def profit_margin_percentage(self):
        """NEW: Profit margin as percentage"""
        if self.sale_price and self.sale_price > 0:
            from core.utils.decimal_utils import round_percentage
            margin = (self.profit_amount or Decimal('0')) / self.sale_price * 100
            return round_percentage(margin)
        return None

    # === BUSINESS METHODS ===

    def get_movement_analysis(self) -> dict:
        """
        NEW: Get comprehensive movement analysis
        """
        analysis = {
            'movement_type': self.movement_type,
            'quantity': self.quantity,
            'cost_price': self.cost_price,
            'total_cost_value': self.total_cost_value,
            'is_sale': self.movement_type == self.OUT and self.source_document_type == 'SALE',
            'has_batch': bool(self.batch_number),
            'movement_date': self.movement_date,
            'created_at': self.created_at,
        }

        # Add sale/profit data if available
        if self.sale_price:
            analysis.update({
                'sale_price': self.sale_price,
                'total_sale_value': self.total_sale_value,
                'profit_amount': self.profit_amount,
                'total_profit': self.total_profit,
                'profit_margin_percentage': self.profit_margin_percentage,
            })

        # Add batch info if available
        if self.batch_number:
            analysis.update({
                'batch_number': self.batch_number,
                'expiry_date': self.expiry_date,
                'is_auto_batch': self.batch_number.startswith('AUTO_'),
            })

        # Add transfer info if applicable
        if self.movement_type == self.TRANSFER:
            analysis.update({
                'from_location': self.from_location.code if self.from_location else None,
                'to_location': self.to_location.code if self.to_location else None,
            })

        return analysis


    @staticmethod
    def _validate_decimal_limits(quantity, cost_price, profit_amount=None):
        '''Validate decimal values don't exceed model field limits'''

        # Check quantity: max_digits=12, decimal_places=3
        if quantity and (quantity >= Decimal('10') ** 9 or quantity < Decimal('0.001')):
            raise ValidationError(f"Quantity {quantity} exceeds valid range")

        # Check cost_price: max_digits=10, decimal_places=4
        if cost_price and (cost_price >= Decimal('10') ** 6 or cost_price < Decimal('0.0001')):
            raise ValidationError(f"Cost price {cost_price} exceeds valid range")

        # Check profit_amount: max_digits=10, decimal_places=2
        if profit_amount and (profit_amount >= Decimal('10') ** 8 or profit_amount < Decimal('0.01')):
            raise ValidationError(f"Profit amount {profit_amount} exceeds valid range")

        return True

    @classmethod
    def get_profit_summary(cls, location=None, product=None, date_from=None, date_to=None) -> dict:
        """
        NEW: Get profit summary for sales movements
        """
        queryset = cls.objects.sales().filter(
            sale_price__isnull=False,
            profit_amount__isnull=False
        )

        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if date_from:
            queryset = queryset.filter(movement_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(movement_date__lte=date_to)

        from django.db.models import Sum, Count, Avg

        summary = queryset.aggregate(
            total_movements=Count('id'),
            total_quantity=Sum('quantity'),
            total_revenue=Sum(models.F('quantity') * models.F('sale_price')),
            total_cost=Sum(models.F('quantity') * models.F('cost_price')),
            total_profit=Sum(models.F('quantity') * models.F('profit_amount')),
            avg_profit_margin=Avg('profit_amount'),
        )

        # Calculate derived metrics
        total_revenue = summary['total_revenue'] or Decimal('0')
        total_profit = summary['total_profit'] or Decimal('0')

        if total_revenue > 0:
            from core.utils.decimal_utils import round_percentage
            summary['profit_margin_percentage'] = round_percentage(total_profit / total_revenue * 100)
        else:
            summary['profit_margin_percentage'] = Decimal('0')

        return summary

    def __repr__(self):
        return f"<InventoryMovement: {self.movement_type} {self.quantity} {self.product.code} @ {self.location.code}>"