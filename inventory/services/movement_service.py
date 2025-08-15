# inventory/services/movement_service.py - ENHANCED WITH PRICING INTEGRATION

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from ..models import InventoryLocation, InventoryMovement, InventoryItem, InventoryBatch

logger = logging.getLogger(__name__)


class MovementService:
    """
    ENHANCED MovementService with automatic pricing integration

    NEW FEATURES:
    - Automatic sale_price detection for sales movements
    - Smart pricing integration with PricingService
    - Enhanced profit tracking with customer context
    """

    # =====================================================
    # ENHANCED OUTGOING MOVEMENT WITH PRICING
    # =====================================================

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
            sale_price: Optional[Decimal] = None,  # ← Can be manual or auto-detected
            customer=None  # ← NEW: For pricing context
    ) -> List[InventoryMovement]:
        """
        Create outgoing inventory movements with AUTOMATIC PRICING

        NEW FEATURES:
        - Automatic sale_price detection for sales
        - Customer-aware pricing
        - Enhanced profit tracking
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

        # ✅ AUTOMATIC SALE PRICE DETECTION
        if sale_price is None and source_document_type in ['SALE', 'POS_SALE']:
            sale_price = MovementService._get_automatic_sale_price(
                location=location,
                product=product,
                customer=customer,
                quantity=quantity
            )

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
                sale_price=sale_price,  # ← Auto-detected or manual
                batch_number=manual_batch_number,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )
            movements.append(movement)

        # ✅ CACHE REFRESH (eliminates Product update)
        try:
            InventoryItem.refresh_for_combination(location, product)

            if should_track_batches and movements:
                for movement in movements:
                    if movement.batch_number:
                        InventoryBatch.refresh_for_combination(
                            location, product, movement.batch_number, movement.expiry_date
                        )

        except Exception as e:
            logger.error(f"Error refreshing cache after outgoing movement: {e}")

        # ✅ LOG SUCCESS WITH PROFIT INFO
        total_profit = sum(m.total_profit or Decimal('0') for m in movements)
        logger.info(
            f"✅ Created outgoing movement: {product.code} -{quantity} at {location.code}, "
            f"movements: {len(movements)}, total_profit: {total_profit}"
        )

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
    # AUTOMATIC PRICING METHODS
    # =====================================================

    @staticmethod
    def _get_automatic_sale_price(
            location: InventoryLocation,
            product,
            customer=None,
            quantity: Decimal = Decimal('1')
    ) -> Optional[Decimal]:
        """
        ✅ NEW: Automatic sale price detection using PricingService

        Returns None if pricing fails (let the movement proceed without sale_price)
        """
        try:
            from pricing.services import PricingService

            sale_price = PricingService.get_sale_price(
                location=location,
                product=product,
                customer=customer,
                quantity=quantity
            )

            if sale_price > 0:
                logger.debug(
                    f"Auto-detected sale price: {product.code} = {sale_price} "
                    f"(customer: {customer}, qty: {quantity})"
                )
                return sale_price
            else:
                logger.warning(f"Zero sale price detected for {product.code}")
                return None

        except Exception as e:
            logger.error(f"Error getting automatic sale price for {product.code}: {e}")
            return None

    # =====================================================
    # ENHANCED FIFO WITH PRICING
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
        ✅ ENHANCED: Proper sale_price distribution across batches
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

                # ✅ SAME SALE PRICE PER UNIT across all batches
                batch_sale_price = sale_price  # Same price per unit

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
    # ENHANCED INCOMING MOVEMENT
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
        Create incoming inventory movement
        ✅ ENHANCED: Triggers pricing updates when needed
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # ✅ VALIDATION INTEGRATION
        from products.services import ProductValidationService
        can_purchase, message, details = ProductValidationService.can_purchase_product(
            product=product,
            quantity=quantity,
            supplier=None
        )

        if not can_purchase:
            raise ValidationError(f"Cannot receive {product.code}: {message}")

        # ✅ BATCH TRACKING LOGIC
        should_track_batches = location.should_track_batches(product)

        if should_track_batches and not batch_number:
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

        # ✅ CACHE REFRESH & PRICING UPDATE
        try:
            # Get old avg cost for pricing update check
            old_avg_cost = None
            try:
                old_item = InventoryItem.objects.get(location=location, product=product)
                old_avg_cost = old_item.avg_cost
            except InventoryItem.DoesNotExist:
                pass

            # Refresh inventory cache
            InventoryItem.refresh_for_combination(location, product)

            # Check if avg cost changed significantly and update pricing
            if old_avg_cost is not None:
                try:
                    new_item = InventoryItem.objects.get(location=location, product=product)
                    new_avg_cost = new_item.avg_cost

                    # If cost changed by more than 5%, update markup prices
                    if old_avg_cost > 0:
                        cost_change_percentage = abs(new_avg_cost - old_avg_cost) / old_avg_cost * 100
                        if cost_change_percentage > 5:  # 5% threshold
                            MovementService._trigger_pricing_update(location, product, new_avg_cost)

                except Exception as e:
                    logger.error(f"Error checking cost change: {e}")

            # Refresh batch cache
            if batch_number and should_track_batches:
                InventoryBatch.refresh_for_combination(location, product, batch_number, expiry_date)

        except Exception as e:
            logger.error(f"Error refreshing cache after incoming movement: {e}")

        logger.info(f"✅ Created incoming movement: {product.code} +{quantity} at {location.code}")
        return movement

    @staticmethod
    def _trigger_pricing_update(location, product, new_avg_cost: Decimal):
        """
        ✅ NEW: Trigger pricing updates when cost changes significantly
        """
        try:
            from pricing.services import PricingService

            updated_count = PricingService.update_pricing_after_inventory_change(
                location=location,
                product=product,
                new_avg_cost=new_avg_cost
            )

            if updated_count > 0:
                logger.info(
                    f"Auto-updated {updated_count} markup prices for {product.code} "
                    f"at {location.code} (new avg cost: {new_avg_cost})"
                )

        except Exception as e:
            logger.error(f"Error triggering pricing update: {e}")

    # =====================================================
    # SMART COST CALCULATION (unchanged)
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
        """
        # 1. Manual price (highest priority)
        if manual_price is not None:
            return manual_price

        # 2. Batch-specific cost (if batch movement)
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

        # 3. InventoryItem.avg_cost (current average for location)
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            if item.avg_cost > 0:
                return item.avg_cost
        except InventoryItem.DoesNotExist:
            pass

        # 4. Fallback: 0.00 (NO Product fallback!)
        logger.warning(f"No cost data available for {product.code} at {location.code}")
        return Decimal('0.00')

    # =====================================================
    # TRANSFER AND ADJUSTMENT (unchanged but documented)
    # =====================================================

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
        Create transfer between locations (unchanged logic)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        try:
            # Create outbound movements (with FIFO if applicable)
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
                use_fifo=True
            )

            # Create corresponding inbound movements
            inbound_movements = []

            for out_movement in outbound_movements:
                in_movement = MovementService.create_incoming_movement(
                    location=to_location,
                    product=product,
                    quantity=out_movement.quantity,
                    cost_price=out_movement.cost_price,
                    batch_number=out_movement.batch_number,
                    expiry_date=out_movement.expiry_date,
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
            raise

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
        Create inventory adjustment movement (unchanged logic)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Determine movement type and quantity
        if adjustment_qty > 0:
            movement_type = InventoryMovement.IN
            quantity = adjustment_qty
        else:
            movement_type = InventoryMovement.OUT
            quantity = abs(adjustment_qty)

        # Smart cost price
        cost_price = manual_cost_price or MovementService._get_smart_cost_price(
            location=location,
            product=product,
            batch_number=batch_number,
            movement_type='ADJUSTMENT'
        )

        # Create movement
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

        # Cache refresh
        try:
            InventoryItem.refresh_for_combination(location, product)

            if batch_number and location.should_track_batches(product):
                InventoryBatch.refresh_for_combination(location, product, batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after adjustment: {e}")

        logger.info(f"✅ Created adjustment: {product.code} {adjustment_qty:+} at {location.code}")
        return movement

    # =====================================================
    # UTILITY AND REPORTING METHODS
    # =====================================================

    @staticmethod
    def get_movement_statistics(location=None, product=None, date_from=None, date_to=None) -> Dict:
        """
        Get comprehensive movement statistics for reporting
        ✅ ENHANCED: Includes profit tracking statistics
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

        # ✅ NEW: Calculate profit if sale_price data is available
        profit_stats = queryset.filter(
            sale_price__isnull=False,
            movement_type='OUT'
        ).aggregate(
            total_revenue=Sum(F('quantity') * F('sale_price')),
            total_profit=Sum(F('quantity') * (F('sale_price') - F('cost_price'))),
            avg_sale_price=Avg('sale_price'),
            profit_movements_count=Count('id')
        )

        return {
            **stats,
            **profit_stats,
            'net_quantity': (stats['total_in_qty'] or Decimal('0')) - (stats['total_out_qty'] or Decimal('0')),
            'net_value': (stats['total_in_value'] or Decimal('0')) - (stats['total_out_value'] or Decimal('0')),
            'profit_margin': (profit_stats['total_profit'] / profit_stats['total_revenue'] * 100)
            if profit_stats['total_revenue'] else None
        }

    @staticmethod
    def reverse_movement(original_movement, reason: str = '', created_by=None):
        """
        Create a reverse movement for the given original movement
        ✅ FIXED: Use document number instead of movement ID
        """
        try:
            # ✅ ИЗПОЛЗВАЙ НОМЕРА НА ДОКУМЕНТА вместо ID на движението
            reversal_doc_number = f'REV-{original_movement.source_document_number}'

            # ✅ ПРОВЕРИ ДАЛИ ВЕЧЕ СЪЩЕСТВУВА reverse ЗА ТОЗИ ДОКУМЕНТ + ПРОДУКТ + LOCATION
            existing_reverse = InventoryMovement.objects.filter(
                source_document_type='REVERSAL',
                source_document_number=reversal_doc_number,
                product=original_movement.product,
                location=original_movement.location,
                source_document_line_id=original_movement.source_document_line_id  # ← За различни линии
            ).first()

            if existing_reverse:
                logger.info(
                    f"Reverse movement for {original_movement.source_document_number} line {original_movement.source_document_line_id} already exists: {existing_reverse.id}")
                return existing_reverse

            # Определи обратния тип движение
            reverse_movement_type = 'OUT' if original_movement.movement_type == 'IN' else 'IN'

            # Създай reverse движението
            reverse_movement = InventoryMovement.objects.create(
                movement_type=reverse_movement_type,
                product=original_movement.product,
                location=original_movement.location,
                quantity=original_movement.quantity,  # Същото количество
                cost_price=original_movement.cost_price,
                source_document_type='REVERSAL',
                source_document_number=reversal_doc_number,  # ← REV-0000000010
                source_document_line_id=original_movement.source_document_line_id,
                reason=reason or f'Reverse of {original_movement.source_document_number} line {original_movement.source_document_line_id}',
                movement_date=timezone.now(),
                created_by=created_by
            )

            logger.info(
                f"Created reverse movement {reverse_movement.id} for document {original_movement.source_document_number}")
            return reverse_movement

        except Exception as e:
            logger.error(
                f"Error creating reverse movement for document {original_movement.source_document_number}: {e}")
            raise

    @staticmethod
    def get_movement_history(
            location=None,
            product=None,
            days_back: int = 30,
            movement_types: List[str] = None,
            include_profit_data: bool = True
    ) -> List[Dict]:
        """
        Get detailed movement history for analysis
        ✅ NEW: Enhanced with profit tracking
        """
        queryset = InventoryMovement.objects.select_related(
            'product', 'location', 'created_by'
        )

        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if movement_types:
            queryset = queryset.filter(movement_type__in=movement_types)

        # Date filter
        if days_back:
            cutoff_date = timezone.now().date() - timedelta(days=days_back)
            queryset = queryset.filter(movement_date__gte=cutoff_date)

        movements = queryset.order_by('-movement_date', '-created_at')[:100]  # Limit for performance

        history = []
        for movement in movements:
            entry = {
                'id': movement.id,
                'movement_date': movement.movement_date,
                'movement_type': movement.movement_type,
                'movement_type_display': movement.get_movement_type_display(),
                'product_code': movement.product.code,
                'product_name': movement.product.name,
                'location_code': movement.location.code,
                'quantity': movement.quantity,
                'cost_price': movement.cost_price,
                'total_cost_value': movement.total_cost_value,
                'batch_number': movement.batch_number,
                'source_document': f"{movement.source_document_type}: {movement.source_document_number}",
                'reason': movement.reason,
                'created_by': str(movement.created_by) if movement.created_by else None,
                'created_at': movement.created_at
            }

            # Add profit data if available and requested
            if include_profit_data and movement.sale_price:
                entry.update({
                    'sale_price': movement.sale_price,
                    'total_sale_value': movement.total_sale_value,
                    'profit_amount': movement.profit_amount,
                    'total_profit': movement.total_profit,
                    'profit_margin_percentage': movement.profit_margin_percentage
                })

            history.append(entry)

        return history

    @staticmethod
    def validate_movement_data(movement_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate movement data before creation
        ✅ ENHANCED: Includes sale_price validation
        """
        errors = []

        # Required fields
        if not movement_data.get('quantity'):
            errors.append('Quantity is required')
        elif movement_data['quantity'] <= 0:
            errors.append('Quantity must be positive')

        if not movement_data.get('cost_price') and movement_data['cost_price'] != 0:
            errors.append('Cost price is required')
        elif movement_data.get('cost_price', 0) < 0:
            errors.append('Cost price cannot be negative')

        # Sale price validation
        if movement_data.get('sale_price') is not None:
            if movement_data['sale_price'] < 0:
                errors.append('Sale price cannot be negative')

            cost_price = movement_data.get('cost_price', 0)
            if cost_price > 0 and movement_data['sale_price'] < cost_price:
                errors.append('Sale price is below cost price - check for errors')

        # Batch validation
        if movement_data.get('batch_number'):
            if len(movement_data['batch_number']) > 50:
                errors.append('Batch number too long (max 50 characters)')

        # Date validation
        if movement_data.get('movement_date'):
            from datetime import date
            if movement_data['movement_date'] > date.today():
                errors.append('Movement date cannot be in the future')

        return len(errors) == 0, errors

    @staticmethod
    def can_create_movement(location, product, movement_type: str, quantity: Decimal) -> Tuple[bool, str]:
        """
        Check if movement can be created (business rules validation)
        """
        # Product validation
        if movement_type == 'OUT':
            from products.services import ProductValidationService
            can_sell, message, details = ProductValidationService.can_sell_product(
                product=product,
                quantity=quantity,
                location=location
            )
            if not can_sell and not location.allow_negative_stock:
                return False, message

        elif movement_type == 'IN':
            from products.services import ProductValidationService
            can_purchase, message, details = ProductValidationService.can_purchase_product(
                product=product,
                quantity=quantity
            )
            if not can_purchase:
                return False, message

        # Location validation
        if not location.is_active:
            return False, f"Location {location.code} is not active"

        return True, "OK"

    # =====================================================
    # BULK OPERATIONS
    # =====================================================

    @staticmethod
    @transaction.atomic
    def bulk_create_movements(movement_data_list: List[Dict]) -> List[InventoryMovement]:
        """
        Bulk create multiple movements efficiently
        ✅ NEW: Batch processing with proper error handling
        """
        movements = []
        errors = []

        for i, data in enumerate(movement_data_list):
            try:
                # Validate data
                is_valid, validation_errors = MovementService.validate_movement_data(data)
                if not is_valid:
                    errors.append(f"Row {i + 1}: {', '.join(validation_errors)}")
                    continue

                # Create movement based on type
                if data['movement_type'] == 'IN':
                    movement = MovementService.create_incoming_movement(**data)
                elif data['movement_type'] == 'OUT':
                    movement_list = MovementService.create_outgoing_movement(**data)
                    movements.extend(movement_list)
                    continue
                else:
                    errors.append(f"Row {i + 1}: Unsupported movement type: {data['movement_type']}")
                    continue

                movements.append(movement)

            except Exception as e:
                errors.append(f"Row {i + 1}: {str(e)}")
                continue

        if errors:
            # Log errors but don't fail the entire batch
            logger.error(f"Bulk movement creation errors: {errors}")

        logger.info(f"Bulk created {len(movements)} movements with {len(errors)} errors")
        return movements

    @staticmethod
    def bulk_reverse_movements(movement_ids: List[int], reason: str = '', created_by=None) -> Tuple[int, List[str]]:
        """
        Bulk reverse multiple movements
        """
        success_count = 0
        errors = []

        movements = InventoryMovement.objects.filter(id__in=movement_ids)

        for movement in movements:
            try:
                MovementService.reverse_movement(movement, reason, created_by)
                success_count += 1
            except Exception as e:
                errors.append(f"Movement {movement.id}: {str(e)}")

        return success_count, errors

    # =====================================================
    # DOCUMENT AUTOMATION (unchanged)
    # =====================================================

    @staticmethod
    @transaction.atomic
    def create_from_document(document) -> List[InventoryMovement]:
        """
        AUTOMATION LAYER - създава движения от цели документи
        """
        movements = []
        model_name = document._meta.model_name.lower()

        try:
            if model_name == 'deliveryreceipt':
                movements = MovementService._create_from_delivery(document)
            elif model_name == 'purchaseorder':
                movements = MovementService._create_from_purchase_order(document)
            elif model_name == 'stocktransfer':
                movements = MovementService._create_from_stock_transfer(document)

            elif model_name == 'purchaserequest':  # ← ДОБАВИ ТОВА
                movements = MovementService._create_from_purchase_request(document)

            elif model_name == 'stockadjustment':
                movements = MovementService._create_from_stock_adjustment(document)
            else:
                logger.warning(f"No automation handler for: {model_name}")

        except Exception as e:
            logger.error(f"Error in document automation: {e}")
            raise

        return movements

    @staticmethod
    def _create_from_delivery(delivery) -> List[InventoryMovement]:
        """Enhanced delivery processing"""
        movements = []
        direction = getattr(delivery.document_type, 'inventory_direction', 'in')

        for line in delivery.lines.all():
            if not line.received_quantity or line.received_quantity == 0:
                continue

            try:
                if direction == 'both':
                    if line.received_quantity > 0:
                        # Positive = incoming
                        movement = MovementService.create_incoming_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            cost_price=line.unit_price or Decimal('0.00'),
                            source_document_type='DELIVERY',
                            source_document_number=delivery.document_number,
                            source_document_line_id=line.line_number,
                            batch_number=line.batch_number,
                            expiry_date=line.expiry_date,
                            reason=f"Delivery receipt (line {line.line_number})"
                        )
                        movements.append(movement)

                    elif line.received_quantity < 0:
                        # Negative = outgoing (return/correction)
                        outgoing_movements = MovementService.create_outgoing_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            source_document_type='DELIVERY_RETURN',
                            source_document_number=delivery.document_number,
                            source_document_line_id=line.line_number,
                            reason=f"Delivery return/correction (line {line.line_number})",
                            allow_negative_stock=True
                        )
                        movements.extend(outgoing_movements)

            except Exception as e:
                logger.error(f"Error processing delivery line {line.line_number}: {e}")
                continue

        return movements

    @staticmethod
    def reverse_document_movements(document, reason: str = '') -> int:
        """
        Reverse all inventory movements for a document
        Returns count of reversed movements
        ✅ FIXED: Handle different source_document_type naming conventions
        """
        try:
            # ✅ FIXED: Опитай различни naming conventions
            possible_types = [
                document._meta.model_name.upper(),  # PURCHASEREQUEST
                document.__class__.__name__.upper(),  # PURCHASEREQUEST
                'PURCHASE_REQUEST',  # Manual mapping
                document._meta.model_name.upper().replace('REQUEST', '_REQUEST'),  # PURCHASE_REQUEST
            ]

            # Намери движенията с всички възможни типове
            movements = InventoryMovement.objects.filter(
                source_document_type__in=possible_types,
                source_document_number=document.document_number
            )

            logger.info(f"Found {movements.count()} movements to reverse for {document.document_number}")

            reversed_count = 0
            for movement in movements:
                try:
                    MovementService.reverse_movement(
                        original_movement=movement,
                        reason=reason or f"Document {document.document_number} status change",
                        created_by=getattr(document, 'updated_by', None)
                    )
                    reversed_count += 1
                except Exception as e:
                    logger.error(f"Error reversing movement {movement.id}: {e}")
                    continue

            logger.info(f"Successfully reversed {reversed_count} movements")
            return reversed_count

        except Exception as e:
            logger.error(f"Error reversing document movements: {e}")
            return 0

    @staticmethod
    def sync_movements_with_document(document, user=None, reason: str = '') -> dict:
        """
        Synchronize movements with current document state
        ✅ FIXED: More aggressive cleanup
        """
        try:
            # 1. ✅ НАМЕРИ И ИЗТРИЙ ВСИЧКИ СВЪРЗАНИ ДВИЖЕНИЯ (INCLUDING REVERSALS)
            from inventory.models import InventoryMovement

            # Оригинални движения
            original_movements = InventoryMovement.objects.filter(
                source_document_type__in=['PURCHASE_REQUEST', 'PURCHASEREQUEST'],
                source_document_number=document.document_number
            )

            # Reversal движения (може да са с различни source_document_number)
            reversal_movements = InventoryMovement.objects.filter(
                source_document_type='REVERSAL'
            ).filter(
                source_document_number__contains=document.document_number
            )

            original_count = original_movements.count()
            reversal_count = reversal_movements.count()

            # DELETE ALL
            original_movements.delete()
            reversal_movements.delete()

            logger.info(f"Deleted {original_count} original + {reversal_count} reversal movements")

            # 2. ✅ СЪЗДАЙ FRESH MOVEMENTS ако статусът изисква
            new_movements = []

            try:
                from nomenclatures.models import DocumentTypeStatus

                current_config = DocumentTypeStatus.objects.filter(
                    document_type=document.document_type,
                    status__code=document.status,
                    is_active=True
                ).first()

                if current_config and current_config.creates_inventory_movements:
                    new_movements = MovementService.create_from_document(document)
                    logger.info(f"Created {len(new_movements)} fresh movements")

            except Exception as e:
                logger.warning(f"Could not check status config: {e}")

            return {
                'success': True,
                'deleted_original': original_count,
                'deleted_reversal': reversal_count,
                'created_movements': len(new_movements),
                'total_corrections': original_count + reversal_count + len(new_movements)
            }

        except Exception as e:
            logger.error(f"Error syncing movements with document: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def _create_from_purchase_request(request) -> List[InventoryMovement]:
        """Create movements from approved purchase request"""
        movements = []

        for line in request.lines.all():
            if not line.requested_quantity or line.requested_quantity == 0:
                continue

            try:
                # Използвай правилното price поле
                cost_price = line.unit_price or line.entered_price or Decimal('0.00')

                # PurchaseRequest обикновено е IN движение (планирано получаване)
                movement = MovementService.create_incoming_movement(
                    location=request.location,
                    product=line.product,
                    quantity=line.requested_quantity,
                    cost_price=cost_price,
                    source_document_type='PURCHASE_REQUEST',
                    source_document_number=request.document_number,
                    source_document_line_id=line.line_number,
                    reason=f"Purchase request approved (line {line.line_number})"
                )
                movements.append(movement)

            except Exception as e:
                logger.error(f"Error processing request line {line.line_number}: {e}")
                continue

        return movements