# inventory/services/movement_service.py

from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from ..models import InventoryLocation, InventoryMovement, InventoryItem, InventoryBatch


class MovementService:
    """
    Service for creating and managing inventory movements
    Handles the complex logic of FIFO, batch tracking, and cache updates
    """

    @staticmethod
    @transaction.atomic
    def create_incoming_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            cost_price: Decimal,
            source_document_type: str = 'PURCHASE',
            source_document_number: str = '',
            movement_date=None,
            batch_number: str = None,
            expiry_date=None,
            reason: str = '',
            created_by=None
    ) -> InventoryMovement:
        """
        Create incoming inventory movement (purchases, receipts, production)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Auto-generate batch for batch-tracked products
        if product.track_batches and not batch_number:
            batch_number = f"AUTO_{product.code}_{movement_date.strftime('%y%m%d')}_{location.code}"

        movement = InventoryMovement.objects.create(
            location=location,
            product=product,
            movement_type=InventoryMovement.IN,
            quantity=quantity,
            cost_price=cost_price,
            batch_number=batch_number,
            expiry_date=expiry_date,
            source_document_type=source_document_type,
            source_document_number=source_document_number,
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        # Update product's moving average cost
        MovementService._update_product_moving_average(product, quantity, cost_price)

        return movement

    @staticmethod
    @transaction.atomic
    def create_outgoing_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_type: str = 'SALE',
            source_document_number: str = '',
            movement_date=None,
            reason: str = '',
            created_by=None,
            use_fifo: bool = True
    ) -> List[InventoryMovement]:
        """
        Create outgoing inventory movement (sales, issues, consumption)
        Handles FIFO logic for batch-tracked products
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        movements = []

        if product.track_batches and use_fifo:
            # FIFO consumption from batches
            remaining_to_consume = quantity

            # Get batches in FIFO order (oldest first, expiring first)
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('received_date', 'expiry_date')

            for batch in batches:
                if remaining_to_consume <= 0:
                    break

                # How much to consume from this batch
                consume_qty = min(remaining_to_consume, batch.remaining_qty)

                # Create movement for this batch
                movement = InventoryMovement.objects.create(
                    location=location,
                    product=product,
                    movement_type=InventoryMovement.OUT,
                    quantity=consume_qty,
                    cost_price=batch.cost_price,  # Use batch-specific cost
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    source_document_type=source_document_type,
                    source_document_number=source_document_number,
                    movement_date=movement_date,
                    reason=reason,
                    created_by=created_by
                )

                movements.append(movement)
                remaining_to_consume -= consume_qty

            # Check if we consumed everything
            if remaining_to_consume > 0:
                raise ValueError(
                    f"Insufficient stock: {remaining_to_consume} units could not be fulfilled"
                )

        else:
            # Simple movement without FIFO (non-batch products or override)
            # Get average cost for non-batch products
            try:
                item = InventoryItem.objects.get(location=location, product=product)
                cost_price = item.avg_cost
            except InventoryItem.DoesNotExist:
                cost_price = product.current_avg_cost

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=quantity,
                cost_price=cost_price,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )

            movements.append(movement)

        return movements

    @staticmethod
    @transaction.atomic
    def create_transfer_movement(
            from_location: InventoryLocation,
            to_location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_number: str = '',
            movement_date=None,
            reason: str = '',
            created_by=None
    ) -> Tuple[List[InventoryMovement], List[InventoryMovement]]:
        """
        Create transfer movements between locations
        Returns (outbound_movements, inbound_movements)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Create outbound movements (FIFO from source location)
        outbound_movements = MovementService.create_outgoing_movement(
            location=from_location,
            product=product,
            quantity=quantity,
            source_document_type='TRANSFER',
            source_document_number=source_document_number,
            movement_date=movement_date,
            reason=f"Transfer to {to_location.code}: {reason}",
            created_by=created_by,
            use_fifo=True
        )

        # Create corresponding inbound movements
        inbound_movements = []

        for out_movement in outbound_movements:
            in_movement = InventoryMovement.objects.create(
                location=to_location,
                product=product,
                movement_type=InventoryMovement.IN,
                quantity=out_movement.quantity,
                cost_price=out_movement.cost_price,  # Preserve cost
                batch_number=out_movement.batch_number,
                expiry_date=out_movement.expiry_date,
                source_document_type='TRANSFER',
                source_document_number=source_document_number,
                movement_date=movement_date,
                from_location=from_location,
                to_location=to_location,
                reason=f"Transfer from {from_location.code}: {reason}",
                created_by=created_by
            )
            inbound_movements.append(in_movement)

        return outbound_movements, inbound_movements

    @staticmethod
    @transaction.atomic
    def create_adjustment_movement(
            location: InventoryLocation,
            product,
            adjustment_qty: Decimal,
            reason: str,
            movement_date=None,
            created_by=None
    ) -> InventoryMovement:
        """
        Create inventory adjustment movement (positive or negative)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Determine movement type and actual quantity
        if adjustment_qty > 0:
            movement_type = InventoryMovement.IN
            quantity = adjustment_qty
        else:
            movement_type = InventoryMovement.OUT
            quantity = abs(adjustment_qty)

        # Get current average cost
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            cost_price = item.avg_cost
        except InventoryItem.DoesNotExist:
            cost_price = product.current_avg_cost

        movement = InventoryMovement.objects.create(
            location=location,
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            cost_price=cost_price,
            source_document_type='ADJUSTMENT',
            source_document_number='ADJ-' + timezone.now().strftime('%Y%m%d-%H%M%S'),
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        return movement

    @staticmethod
    def _update_product_moving_average(product, new_qty: Decimal, new_cost: Decimal):
        """
        Update product's moving average cost
        """
        old_qty = product.current_stock_qty
        old_cost = product.current_avg_cost
        old_total_value = old_qty * old_cost

        new_total_value = new_qty * new_cost
        new_total_qty = old_qty + new_qty

        if new_total_qty > 0:
            new_avg_cost = (old_total_value + new_total_value) / new_total_qty
        else:
            new_avg_cost = new_cost

        # Update product fields
        product.current_avg_cost = new_avg_cost
        product.current_stock_qty = new_total_qty
        product.last_purchase_cost = new_cost
        product.last_purchase_date = timezone.now().date()

        product.save(update_fields=[
            'current_avg_cost', 'current_stock_qty',
            'last_purchase_cost', 'last_purchase_date'
        ])

    @staticmethod
    def get_movement_history(
            location: InventoryLocation = None,
            product=None,
            movement_type: str = None,
            date_from=None,
            date_to=None,
            limit: int = 100
    ) -> List[Dict]:
        """
        Get movement history with filters
        """
        queryset = InventoryMovement.objects.select_related(
            'location', 'product', 'created_by'
        )

        # Apply filters
        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if date_from:
            queryset = queryset.filter(movement_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(movement_date__lte=date_to)

        queryset = queryset.order_by('-created_at')[:limit]

        movements = []
        for movement in queryset:
            movements.append({
                'id': movement.id,
                'location_code': movement.location.code,
                'product_code': movement.product.code,
                'product_name': movement.product.name,
                'movement_type': movement.movement_type,
                'movement_type_display': movement.get_movement_type_display(),
                'quantity': movement.quantity,
                'cost_price': movement.cost_price,
                'batch_number': movement.batch_number,
                'expiry_date': movement.expiry_date,
                'source_document_type': movement.source_document_type,
                'source_document_number': movement.source_document_number,
                'movement_date': movement.movement_date,
                'reason': movement.reason,
                'created_at': movement.created_at,
                'created_by': movement.created_by.username if movement.created_by else None
            })

        return movements

    @staticmethod
    def reconcile_inventory(location: InventoryLocation, product) -> Dict:
        """
        Reconcile inventory by recalculating from movements
        """
        # Refresh cached data
        InventoryItem.refresh_for_combination(location, product)

        # Refresh all batches for this product
        if product.track_batches:
            batch_numbers = InventoryMovement.objects.filter(
                location=location,
                product=product,
                batch_number__isnull=False
            ).values_list('batch_number', flat=True).distinct()

            for batch_number in batch_numbers:
                InventoryBatch.refresh_for_combination(
                    location=location,
                    product=product,
                    batch_number=batch_number
                )

        # Get updated data
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            return {
                'success': True,
                'current_qty': item.current_qty,
                'avg_cost': item.avg_cost,
                'last_movement': item.last_movement_date
            }
        except InventoryItem.DoesNotExist:
            return {
                'success': True,
                'current_qty': Decimal('0'),
                'avg_cost': Decimal('0'),
                'last_movement': None
            }

    @staticmethod
    def validate_movement_data(
            location: InventoryLocation,
            product,
            movement_type: str,
            quantity: Decimal,
            cost_price: Decimal = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate movement data before creation
        """
        errors = []

        # Basic validations
        if quantity <= 0:
            errors.append("Quantity must be positive")

        if cost_price is not None and cost_price < 0:
            errors.append("Cost price cannot be negative")

        # Stock availability for outgoing movements
        if movement_type == InventoryMovement.OUT:
            from .inventory_service import InventoryService
            availability = InventoryService.check_availability(location, product, quantity)

            if not availability['can_fulfill']:
                errors.append(
                    f"Insufficient stock. Available: {availability['available_qty']}, "
                    f"Required: {quantity}"
                )

        return len(errors) == 0, errors