# inventory/services/movement_service.py
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from ..models import InventoryLocation, InventoryMovement, InventoryItem, InventoryBatch

logger = logging.getLogger(__name__)


class MovementService:
    """
    REFACTORED MovementService - eliminates Product dependencies

    Core responsibility: Create and manage inventory movements
    - Integrates with ProductValidationService for business rules
    - Uses InventoryItem as single source of truth for costs/quantities
    - Supports sale_price tracking for profit analysis
    - Thread-safe operations with proper error handling
    """

    # =====================================================
    # CORE MOVEMENT CREATION METHODS
    # =====================================================

    @staticmethod
    @transaction.atomic
    def create_incoming_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            cost_price: Decimal,
            source_document_type: str = 'PURCHASE',
            source_document_number: str = '',
            source_document_line_id: Optional[int] = None,
            movement_date=None,
            batch_number: str = None,
            expiry_date=None,
            reason: str = '',
            created_by=None
    ) -> InventoryMovement:
        """
        Create incoming inventory movement (purchases, receipts, production)

        INTEGRATION POINTS:
        - ProductValidationService.can_purchase_product() validation
        - InventoryItem.refresh_for_combination() cache update
        - Batch tracking support via location settings
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # ✅ VALIDATION INTEGRATION
        from products.services import ProductValidationService
        can_purchase, message, details = ProductValidationService.can_purchase_product(
            product=product,
            quantity=quantity,
            supplier=None  # Could be enhanced to pass supplier
        )

        if not can_purchase:
            raise ValidationError(f"Cannot receive {product.code}: {message}")

        # ✅ BATCH TRACKING LOGIC
        should_track_batches = location.should_track_batches(product)

        if should_track_batches and not batch_number:
            # Auto-generate batch for batch-tracked products
            batch_number = f"AUTO_{product.code}_{movement_date.strftime('%Y%m%d')}_{location.code}"

        # ✅ CREATE MOVEMENT
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
            source_document_line_id=source_document_line_id,
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        # ✅ CACHE REFRESH (eliminates Product update)
        try:
            InventoryItem.refresh_for_combination(location, product)

            if batch_number and should_track_batches:
                InventoryBatch.refresh_for_combination(location, product, batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after incoming movement: {e}")
            # Don't fail the movement creation due to cache issues

        logger.info(f"✅ Created incoming movement: {product.code} +{quantity} at {location.code}")
        return movement

    @staticmethod
    @transaction.atomic
    def create_outgoing_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_type: str = 'SALE',
            source_document_number: str = '',
            source_document_line_id: Optional[int] = None,
            movement_date=None,
            reason: str = '',
            created_by=None,
            use_fifo: bool = True,
            allow_negative_stock: Optional[bool] = None,
            manual_cost_price: Optional[Decimal] = None,
            manual_batch_number: Optional[str] = None,
            sale_price: Optional[Decimal] = None  # ← NEW: For profit tracking
    ) -> List[InventoryMovement]:
        """
        Create outgoing inventory movements with enhanced features

        NEW FEATURES:
        - sale_price parameter for profit tracking
        - Integration with ProductValidationService
        - Smart cost price calculation hierarchy
        - Enhanced FIFO with thread safety
        - Proper error handling and logging
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # ✅ DETERMINE NEGATIVE STOCK POLICY
        if allow_negative_stock is None:
            allow_negative_stock = location.allow_negative_stock

        # ✅ VALIDATION INTEGRATION
        from products.services import ProductValidationService
        can_sell, message, details = ProductValidationService.can_sell_product(
            product=product,
            quantity=quantity,
            location=location
        )

        if not can_sell and not allow_negative_stock:
            raise ValidationError(f"Cannot sell {product.code}: {message}")

        movements = []

        # =====================================================
        # BATCH TRACKING vs SIMPLE STOCK
        # =====================================================
        should_track_batches = location.should_track_batches(product)

        if should_track_batches and use_fifo and not manual_cost_price and not manual_batch_number:
            # ✅ FIFO BATCH MOVEMENTS
            movements = MovementService._create_fifo_outgoing_movements(
                location=location,
                product=product,
                quantity=quantity,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by,
                sale_price=sale_price
            )

        else:
            # ✅ SIMPLE STOCK MOVEMENT
            cost_price = MovementService._get_smart_cost_price(
                location=location,
                product=product,
                manual_price=manual_cost_price,
                batch_number=manual_batch_number,
                movement_type='OUT'
            )

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=quantity,
                cost_price=cost_price,
                sale_price=sale_price,  # ← NEW: For profit tracking
                batch_number=manual_batch_number,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
                # profit_amount will be auto-calculated in save()
            )
            movements.append(movement)

        # ✅ CACHE REFRESH
        try:
            InventoryItem.refresh_for_combination(location, product)

            # Refresh affected batches
            for movement in movements:
                if movement.batch_number and should_track_batches:
                    InventoryBatch.refresh_for_combination(location, product, movement.batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after outgoing movement: {e}")

        total_quantity = sum(m.quantity for m in movements)
        logger.info(
            f"✅ Created {len(movements)} outgoing movement(s): {product.code} -{total_quantity} at {location.code}")

        return movements

    @staticmethod
    @transaction.atomic
    def create_transfer_movement(
            from_location: InventoryLocation,
            to_location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_type: str = 'TRANSFER',
            source_document_number: str = '',
            source_document_line_id: Optional[int] = None,
            movement_date=None,
            reason: str = '',
            created_by=None
    ) -> Tuple[List[InventoryMovement], List[InventoryMovement]]:
        """
        Create transfer movements between locations with enhanced safety

        IMPROVEMENTS:
        - Thread-safe operations
        - Proper error handling and rollback
        - Cost preservation across locations
        - Batch tracking support
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        try:
            # ✅ CREATE OUTBOUND MOVEMENTS (from source location)
            outbound_movements = MovementService.create_outgoing_movement(
                location=from_location,
                product=product,
                quantity=quantity,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=f"Transfer to {to_location.code}: {reason}",
                created_by=created_by,
                use_fifo=True  # Always use FIFO for transfers
            )

            # ✅ CREATE CORRESPONDING INBOUND MOVEMENTS
            inbound_movements = []

            for out_movement in outbound_movements:
                in_movement = MovementService.create_incoming_movement(
                    location=to_location,
                    product=product,
                    quantity=out_movement.quantity,
                    cost_price=out_movement.cost_price,  # ← Preserve cost
                    batch_number=out_movement.batch_number,  # ← Preserve batch
                    expiry_date=out_movement.expiry_date,  # ← Preserve expiry
                    source_document_type=source_document_type,
                    source_document_number=source_document_number,
                    source_document_line_id=source_document_line_id,
                    movement_date=movement_date,
                    reason=f"Transfer from {from_location.code}: {reason}",
                    created_by=created_by
                )
                inbound_movements.append(in_movement)

            logger.info(
                f"✅ Transfer completed: {product.code} {quantity} from {from_location.code} to {to_location.code}")
            return outbound_movements, inbound_movements

        except Exception as e:
            logger.error(f"Error in transfer operation: {e}")
            raise  # Re-raise to trigger transaction rollback

    @staticmethod
    @transaction.atomic
    def create_adjustment_movement(
            location: InventoryLocation,
            product,
            adjustment_qty: Decimal,
            reason: str,
            movement_date=None,
            created_by=None,
            manual_cost_price: Optional[Decimal] = None,
            batch_number: Optional[str] = None
    ) -> InventoryMovement:
        """
        Create inventory adjustment movement with smart cost calculation

        IMPROVEMENTS:
        - Smart cost price determination
        - Support for batch adjustments
        - Better error handling
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # ✅ DETERMINE MOVEMENT TYPE AND QUANTITY
        if adjustment_qty > 0:
            movement_type = InventoryMovement.IN
            quantity = adjustment_qty
        else:
            movement_type = InventoryMovement.OUT
            quantity = abs(adjustment_qty)

        # ✅ SMART COST PRICE
        cost_price = manual_cost_price or MovementService._get_smart_cost_price(
            location=location,
            product=product,
            batch_number=batch_number,
            movement_type='ADJUSTMENT'
        )

        # ✅ CREATE MOVEMENT
        movement = InventoryMovement.objects.create(
            location=location,
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            cost_price=cost_price,
            batch_number=batch_number,
            source_document_type='ADJUSTMENT',
            source_document_number=f'ADJ-{timezone.now().strftime("%Y%m%d-%H%M%S")}',
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        # ✅ CACHE REFRESH
        try:
            InventoryItem.refresh_for_combination(location, product)

            if batch_number and location.should_track_batches(product):
                InventoryBatch.refresh_for_combination(location, product, batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after adjustment: {e}")

        logger.info(f"✅ Created adjustment: {product.code} {adjustment_qty:+} at {location.code}")
        return movement

    # =====================================================
    # SMART COST CALCULATION
    # =====================================================

    @staticmethod
    def _get_smart_cost_price(
            location: InventoryLocation,
            product,
            manual_price: Optional[Decimal] = None,
            batch_number: Optional[str] = None,
            movement_type: str = 'OUT'
    ) -> Decimal:
        """
        Smart cost price calculation hierarchy

        PRIORITY ORDER:
        1. Manual price (if provided)
        2. Batch-specific cost (if batch movement)
        3. InventoryItem.avg_cost (current average for location)
        4. Fallback: 0.00 (NO Product fallback!)
        """

        # 1. ✅ MANUAL PRICE (highest priority)
        if manual_price is not None:
            return manual_price

        # 2. ✅ BATCH-SPECIFIC COST
        if batch_number:
            try:
                batch = InventoryBatch.objects.get(
                    location=location,
                    product=product,
                    batch_number=batch_number
                )
                if batch.cost_price > 0:
                    return batch.cost_price
            except InventoryBatch.DoesNotExist:
                pass

        # 3. ✅ INVENTORY ITEM AVERAGE COST
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            if item.avg_cost > 0:
                return item.avg_cost
        except InventoryItem.DoesNotExist:
            pass

        # 4. ✅ FALLBACK (NO Product dependency!)
        logger.warning(f"No cost price found for {product.code} at {location.code}, using 0.00")
        return Decimal('0.00')

    # =====================================================
    # FIFO BATCH HANDLING
    # =====================================================

    @staticmethod
    def _create_fifo_outgoing_movements(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_type: str,
            source_document_number: str,
            source_document_line_id: Optional[int],
            movement_date,
            reason: str,
            created_by,
            sale_price: Optional[Decimal] = None
    ) -> List[InventoryMovement]:
        """
        Create FIFO outgoing movements for batch-tracked products

        IMPROVEMENTS:
        - Thread-safe with select_for_update()
        - Expiry date prioritization
        - Proper error handling for insufficient stock
        - Sale price distribution across batches
        """
        movements = []
        remaining_qty = quantity

        try:
            # ✅ THREAD-SAFE FIFO BATCH SELECTION
            available_batches = InventoryBatch.objects.select_for_update().filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('expiry_date', 'received_date', 'batch_number')

            if not available_batches.exists():
                raise ValidationError(f"No available batches for {product.code} at {location.code}")

            for batch in available_batches:
                if remaining_qty <= 0:
                    break

                # Determine quantity to take from this batch
                batch_qty = min(remaining_qty, batch.remaining_qty)

                # Calculate proportional sale price for this batch
                batch_sale_price = None
                if sale_price is not None:
                    batch_sale_price = sale_price  # Same sale price per unit

                # Create movement for this batch
                movement = InventoryMovement.objects.create(
                    location=location,
                    product=product,
                    movement_type=InventoryMovement.OUT,
                    quantity=batch_qty,
                    cost_price=batch.cost_price,
                    sale_price=batch_sale_price,
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    source_document_type=source_document_type,
                    source_document_number=source_document_number,
                    source_document_line_id=source_document_line_id,
                    movement_date=movement_date,
                    reason=f"{reason} (FIFO batch: {batch.batch_number})",
                    created_by=created_by
                )
                movements.append(movement)
                remaining_qty -= batch_qty

                logger.debug(f"FIFO: Allocated {batch_qty} from batch {batch.batch_number}")

            # ✅ CHECK IF FULLY FULFILLED
            if remaining_qty > 0:
                raise ValidationError(
                    f"Insufficient batch stock for {product.code} at {location.code}. "
                    f"Requested: {quantity}, Available: {quantity - remaining_qty}"
                )

        except Exception as e:
            logger.error(f"Error in FIFO batch processing: {e}")
            raise

        return movements

    # =====================================================
    # DOCUMENT AUTOMATION (cleaned up)
    # =====================================================

    @staticmethod
    @transaction.atomic
    def create_from_document(document) -> List[InventoryMovement]:
        """
        AUTOMATION LAYER - creates movements from complete documents
        Used for workflow automation, NOT for real-time operations

        CLEANED UP:
        - Eliminates Product dependencies
        - Uses core movement methods
        - Proper error handling
        """
        movements = []
        model_name = document._meta.model_name.lower()

        try:
            # ✅ DISPATCH TO DOCUMENT-SPECIFIC HANDLERS
            if model_name == 'deliveryreceipt':
                movements = MovementService._create_from_delivery(document)
            elif model_name == 'purchaseorder':
                movements = MovementService._create_from_purchase_order(document)
            elif model_name == 'stocktransfer':
                movements = MovementService._create_from_stock_transfer(document)
            elif model_name == 'stockadjustment':
                movements = MovementService._create_from_stock_adjustment(document)
            else:
                logger.warning(f"No automation handler for document type: {model_name}")

            if movements:
                logger.info(f"✅ Document automation: Created {len(movements)} movements for {document.document_number}")

        except Exception as e:
            logger.error(f"Error in document automation for {document.document_number}: {e}")
            raise  # Re-raise for transaction rollback

        return movements

    @staticmethod
    def _create_from_delivery(delivery) -> List[InventoryMovement]:
        """
        Create movements from delivery document using core methods

        CLEANED UP:
        - Uses create_incoming_movement()
        - Eliminates Product dependencies
        - Proper error handling per line
        """
        movements = []

        if not hasattr(delivery, 'lines'):
            logger.error(f"Delivery {delivery.document_number} has no lines")
            return movements

        # Get inventory direction from DocumentType
        direction = getattr(delivery.document_type, 'inventory_direction', 'in')

        for line in delivery.lines.all():
            if not line.received_quantity or line.received_quantity == 0:
                continue

            try:
                if direction == 'in' and line.received_quantity > 0:
                    # ✅ INCOMING DELIVERY
                    movement = MovementService.create_incoming_movement(
                        location=delivery.location,
                        product=line.product,
                        quantity=abs(line.received_quantity),
                        cost_price=line.unit_price or Decimal('0.00'),
                        source_document_type='DELIVERY',
                        source_document_number=delivery.document_number,
                        source_document_line_id=getattr(line, 'line_number', None),
                        movement_date=getattr(delivery, 'delivery_date', None) or delivery.document_date,
                        batch_number=getattr(line, 'batch_number', None),
                        expiry_date=getattr(line, 'expiry_date', None),
                        reason=f"Delivery receipt (line {getattr(line, 'line_number', '?')})",
                        created_by=getattr(delivery, 'updated_by', None) or getattr(delivery, 'created_by', None)
                    )
                    movements.append(movement)

                elif direction == 'out' and line.received_quantity > 0:
                    # ✅ OUTGOING DELIVERY (returns, etc.)
                    outgoing_movements = MovementService.create_outgoing_movement(
                        location=delivery.location,
                        product=line.product,
                        quantity=abs(line.received_quantity),
                        source_document_type='DELIVERY_OUT',
                        source_document_number=delivery.document_number,
                        source_document_line_id=getattr(line, 'line_number', None),
                        movement_date=getattr(delivery, 'delivery_date', None) or delivery.document_date,
                        reason=f"Delivery dispatch (line {getattr(line, 'line_number', '?')})",
                        created_by=getattr(delivery, 'updated_by', None) or getattr(delivery, 'created_by', None),
                        allow_negative_stock=True
                    )
                    movements.extend(outgoing_movements)

                elif direction == 'both':
                    if line.received_quantity > 0:
                        # Positive = incoming
                        movement = MovementService.create_incoming_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            cost_price=line.unit_price or Decimal('0.00'),
                            source_document_type='DELIVERY',
                            source_document_number=delivery.document_number,
                            source_document_line_id=getattr(line, 'line_number', None),
                            movement_date=getattr(delivery, 'delivery_date', None) or delivery.document_date,
                            batch_number=getattr(line, 'batch_number', None),
                            expiry_date=getattr(line, 'expiry_date', None),
                            reason=f"Delivery receipt (line {getattr(line, 'line_number', '?')})",
                            created_by=getattr(delivery, 'updated_by', None) or getattr(delivery, 'created_by', None)
                        )
                        movements.append(movement)

                    elif line.received_quantity < 0:
                        # Negative = outgoing/return
                        outgoing_movements = MovementService.create_outgoing_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            source_document_type='DELIVERY_RETURN',
                            source_document_number=delivery.document_number,
                            source_document_line_id=getattr(line, 'line_number', None),
                            movement_date=getattr(delivery, 'delivery_date', None) or delivery.document_date,
                            reason=f"Delivery return/correction (line {getattr(line, 'line_number', '?')})",
                            created_by=getattr(delivery, 'updated_by', None) or getattr(delivery, 'created_by', None),
                            allow_negative_stock=True
                        )
                        movements.extend(outgoing_movements)

            except Exception as e:
                logger.error(f"Error processing delivery line {getattr(line, 'line_number', '?')}: {e}")
                continue  # Continue with other lines

        return movements

    @staticmethod
    def _create_from_purchase_order(order) -> List[InventoryMovement]:
        """
        Create movements from purchase order (auto-receive scenario)
        """
        movements = []

        # Check if auto-receive is enabled
        if not getattr(order.document_type, 'auto_receive', False):
            logger.debug(f"Order {order.document_number} does not have auto-receive enabled")
            return movements

        for line in order.lines.all():
            if not line.ordered_quantity or line.ordered_quantity <= 0:
                continue

            try:
                movement = MovementService.create_incoming_movement(
                    location=order.location,
                    product=line.product,
                    quantity=line.ordered_quantity,
                    cost_price=line.unit_price or Decimal('0.00'),
                    source_document_type='PURCHASE_AUTO',
                    source_document_number=order.document_number,
                    source_document_line_id=getattr(line, 'line_number', None),
                    movement_date=order.document_date,
                    reason=f"Auto-receive from PO (line {getattr(line, 'line_number', '?')})",
                    created_by=getattr(order, 'created_by', None)
                )
                movements.append(movement)

            except Exception as e:
                logger.error(f"Error in auto-receive for PO line {getattr(line, 'line_number', '?')}: {e}")
                continue

        return movements

    @staticmethod
    def _create_from_stock_transfer(transfer) -> List[InventoryMovement]:
        """
        Create movements from stock transfer document
        """
        movements = []

        for line in transfer.lines.all():
            if not line.quantity or line.quantity <= 0:
                continue

            try:
                # Use the transfer method which handles both directions
                outbound, inbound = MovementService.create_transfer_movement(
                    from_location=transfer.from_location,
                    to_location=transfer.to_location,
                    product=line.product,
                    quantity=line.quantity,
                    source_document_type='TRANSFER',
                    source_document_number=transfer.document_number,
                    source_document_line_id=getattr(line, 'line_number', None),
                    movement_date=transfer.document_date,
                    reason=f"Stock transfer (line {getattr(line, 'line_number', '?')})",
                    created_by=getattr(transfer, 'created_by', None)
                )
                movements.extend(outbound)
                movements.extend(inbound)

            except Exception as e:
                logger.error(f"Error in transfer for line {getattr(line, 'line_number', '?')}: {e}")
                continue

        return movements

    @staticmethod
    def _create_from_stock_adjustment(adjustment) -> List[InventoryMovement]:
        """
        Create movements from stock adjustment document
        """
        movements = []

        for line in adjustment.lines.all():
            if not line.adjustment_quantity or line.adjustment_quantity == 0:
                continue

            try:
                movement = MovementService.create_adjustment_movement(
                    location=adjustment.location,
                    product=line.product,
                    adjustment_qty=line.adjustment_quantity,
                    reason=f"Stock adjustment: {adjustment.reason} (line {getattr(line, 'line_number', '?')})",
                    movement_date=adjustment.document_date,
                    created_by=getattr(adjustment, 'created_by', None),
                    manual_cost_price=getattr(line, 'cost_price', None),
                    batch_number=getattr(line, 'batch_number', None)
                )
                movements.append(movement)

            except Exception as e:
                logger.error(f"Error in adjustment for line {getattr(line, 'line_number', '?')}: {e}")
                continue

        return movements

    # =====================================================
    # UTILITY METHODS
    # =====================================================

    @staticmethod
    def get_movement_statistics(location=None, product=None, date_from=None, date_to=None) -> Dict:
        """
        Get movement statistics for reporting
        """
        queryset = InventoryMovement.objects.all()

        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if date_from:
            queryset = queryset.filter(movement_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(movement_date__lte=date_to)

        # Aggregate statistics
        from django.db.models import Count, Sum, Avg, F, Q

        stats = queryset.aggregate(
            total_movements=Count('id'),
            total_in_qty=Sum('quantity', filter=Q(movement_type='IN')),
            total_out_qty=Sum('quantity', filter=Q(movement_type='OUT')),
            total_in_value=Sum(F('quantity') * F('cost_price'), filter=Q(movement_type='IN')),
            total_out_value=Sum(F('quantity') * F('cost_price'), filter=Q(movement_type='OUT')),
            avg_cost_price=Avg('cost_price')
        )

        # Calculate profit if sale_price data is available
        profit_stats = queryset.filter(
            sale_price__isnull=False,
            movement_type='OUT'
        ).aggregate(
            total_revenue=Sum(F('quantity') * F('sale_price')),
            total_profit=Sum(F('quantity') * (F('sale_price') - F('cost_price')))
        )

        return {
            **stats,
            **profit_stats,
            'net_quantity': (stats['total_in_qty'] or Decimal('0')) - (stats['total_out_qty'] or Decimal('0')),
            'net_value': (stats['total_in_value'] or Decimal('0')) - (stats['total_out_value'] or Decimal('0'))
        }

    @staticmethod
    def reverse_movement(original_movement: InventoryMovement, reason: str = '', created_by=None) -> InventoryMovement:
        """
        Create a reverse movement to correct errors
        """
        reverse_type = InventoryMovement.OUT if original_movement.movement_type == InventoryMovement.IN else InventoryMovement.IN

        return MovementService.create_adjustment_movement(
            location=original_movement.location,
            product=original_movement.product,
            adjustment_qty=-original_movement.quantity if original_movement.movement_type == InventoryMovement.IN else original_movement.quantity,
            reason=f"Reverse of movement #{original_movement.id}: {reason}",
            movement_date=timezone.now().date(),
            created_by=created_by,
            manual_cost_price=original_movement.cost_price,
            batch_number=original_movement.batch_number
        )