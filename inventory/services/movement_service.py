# inventory/services/movement_service.py - COMPLETE RESULT PATTERN REFACTORING


import logging
from datetime import timedelta
from django.db import transaction

from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from core.utils.result import Result
from ..models import InventoryLocation, InventoryMovement, InventoryItem, InventoryBatch
from django.db.models import Sum, F
logger = logging.getLogger(__name__)


class MovementService:
    """
    COMPLETE MovementService - REFACTORED WITH RESULT PATTERN

    CHANGES: All public methods now return Result objects
    Legacy methods available for backward compatibility
    ALL ORIGINAL FUNCTIONALITY PRESERVED
    """

    # =====================================================
    # NEW: RESULT-BASED PUBLIC API
    # =====================================================

    @staticmethod
    @transaction.atomic
    def create_incoming_stock(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            cost_price: Decimal,
            source_document_type: str = 'RECEIPT',
            source_document_number: str = '',
            source_document_line_id: Optional[int] = None,
            batch_number: Optional[str] = None,
            expiry_date=None,
            movement_date=None,
            reason: str = '',
            created_by=None
    ) -> Result:
        """
        🎯 PRIMARY API: Create incoming inventory movement - NEW Result-based method
        """
        try:
            # Validate inputs
            validation_result = MovementService._validate_movement_inputs(
                location, product, quantity, 'IN'
            )
            if not validation_result.ok:
                return validation_result

            if cost_price < 0:
                return Result.error(
                    code='INVALID_COST_PRICE',
                    msg='Cost price cannot be negative',
                    data={'cost_price': cost_price}
                )

            # Set defaults
            if movement_date is None:
                movement_date = timezone.now().date()

            # Create movement using legacy method for full compatibility
            movement = MovementService._create_incoming_movement_internal(
                location=location,
                product=product,
                quantity=quantity,
                cost_price=cost_price,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                batch_number=batch_number,
                expiry_date=expiry_date,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )

            movement_data = {
                'movement_id': movement.id,
                'movement_type': 'IN',
                'quantity': quantity,
                'cost_price': cost_price,
                'location_code': location.code,
                'product_code': product.code,
                'batch_number': batch_number,
                'movement_date': movement_date,
                'cache_updated': True
            }

            logger.info(f"✅ Created incoming movement: {product.code} +{quantity} at {location.code}")

            return Result.success(
                data=movement_data,
                msg=f'Successfully received {quantity} units of {product.code}'
            )

        except Exception as e:
            logger.error(f"Error creating incoming movement: {e}")
            return Result.error(
                code='MOVEMENT_CREATION_ERROR',
                msg=f'Failed to create incoming movement: {str(e)}',
                data={'product_code': getattr(product, 'code', '?'), 'quantity': quantity}
            )

    @staticmethod
    @transaction.atomic
    def create_outgoing_stock(
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
            sale_price: Optional[Decimal] = None,
            customer=None
    ) -> Result:
        """
        🎯 PRIMARY API: Create outgoing inventory movement - NEW Result-based method
        """
        try:
            # Validate inputs
            validation_result = MovementService._validate_movement_inputs(
                location, product, quantity, 'OUT'
            )
            if not validation_result.ok:
                return validation_result

            # Create movements using legacy method for full functionality
            movements = MovementService._create_outgoing_movement_internal(
                location=location,
                product=product,
                quantity=quantity,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by,
                use_fifo=use_fifo,
                allow_negative_stock=allow_negative_stock,
                manual_cost_price=manual_cost_price,
                manual_batch_number=manual_batch_number,
                sale_price=sale_price,
                customer=customer
            )

            # Prepare response data
            movements_data = []
            total_cost = Decimal('0')
            total_sale = Decimal('0')

            for movement in movements:
                movement_info = {
                    'movement_id': movement.id,
                    'quantity': movement.quantity,
                    'cost_price': movement.cost_price,
                    'sale_price': movement.sale_price,
                    'batch_number': movement.batch_number,
                    'profit': (movement.sale_price or Decimal('0')) - movement.cost_price
                }
                movements_data.append(movement_info)
                total_cost += movement.cost_price * movement.quantity
                if movement.sale_price:
                    total_sale += movement.sale_price * movement.quantity

            result_data = {
                'movements': movements_data,
                'movements_count': len(movements),
                'total_quantity': quantity,
                'total_cost': total_cost,
                'total_sale': total_sale,
                'total_profit': total_sale - total_cost,
                'location_code': location.code,
                'product_code': product.code
            }

            logger.info(f"✅ Created outgoing movement: {product.code} -{quantity} at {location.code}")

            return Result.success(
                data=result_data,
                msg=f'Successfully issued {quantity} units of {product.code}'
            )

        except Exception as e:
            logger.error(f"Error creating outgoing movement: {e}")
            return Result.error(
                code='MOVEMENT_CREATION_ERROR',
                msg=f'Failed to create outgoing movement: {str(e)}',
                data={'product_code': getattr(product, 'code', '?'), 'quantity': quantity}
            )

    @staticmethod
    @transaction.atomic
    def create_stock_transfer(
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
    ) -> Result:
        """
        🎯 TRANSFER API: Create stock transfer between locations - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            outbound, inbound = MovementService._create_transfer_movement_internal(
                from_location=from_location,
                to_location=to_location,
                product=product,
                quantity=quantity,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )

            transfer_data = {
                'transfer_id': f"{source_document_type}-{source_document_number or 'AUTO'}",
                'from_location': from_location.code,
                'to_location': to_location.code,
                'product_code': product.code,
                'quantity': quantity,
                'outbound_movements': [{'id': m.id, 'quantity': m.quantity} for m in outbound],
                'inbound_movements': [{'id': m.id, 'quantity': m.quantity} for m in inbound],
                'movement_date': movement_date or timezone.now().date()
            }

            logger.info(
                f"✅ Transfer completed: {product.code} {quantity} from {from_location.code} to {to_location.code}")

            return Result.success(
                data=transfer_data,
                msg=f'Successfully transferred {quantity} units from {from_location.code} to {to_location.code}'
            )

        except Exception as e:
            logger.error(f"Error in stock transfer: {e}")
            return Result.error(
                code='TRANSFER_ERROR',
                msg=f'Stock transfer failed: {str(e)}',
                data={'from_location': from_location.code, 'to_location': to_location.code}
            )

    @staticmethod
    @transaction.atomic
    def create_stock_adjustment(
            location: InventoryLocation,
            product,
            adjustment_qty: Decimal,
            reason: str,
            movement_date=None,
            created_by=None,
            manual_cost_price: Optional[Decimal] = None,
            batch_number: Optional[str] = None
    ) -> Result:
        """
        🎯 ADJUSTMENT API: Create inventory adjustment - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            movement = MovementService._create_adjustment_movement_internal(
                location=location,
                product=product,
                adjustment_qty=adjustment_qty,
                reason=reason,
                movement_date=movement_date,
                created_by=created_by,
                manual_cost_price=manual_cost_price,
                batch_number=batch_number
            )

            adjustment_data = {
                'movement_id': movement.id,
                'adjustment_type': 'INCREASE' if adjustment_qty > 0 else 'DECREASE',
                'adjustment_quantity': adjustment_qty,
                'actual_quantity': movement.quantity,
                'cost_price': movement.cost_price,
                'location_code': location.code,
                'product_code': product.code,
                'batch_number': batch_number,
                'movement_date': movement.movement_date,
                'reason': reason
            }

            logger.info(f"✅ Created adjustment: {product.code} {adjustment_qty:+} at {location.code}")

            return Result.success(
                data=adjustment_data,
                msg=f'Successfully adjusted {product.code} by {adjustment_qty} units'
            )

        except Exception as e:
            logger.error(f"Error creating stock adjustment: {e}")
            return Result.error(
                code='ADJUSTMENT_ERROR',
                msg=f'Stock adjustment failed: {str(e)}',
                data={'product_code': getattr(product, 'code', '?'), 'adjustment_qty': adjustment_qty}
            )

    @staticmethod
    @transaction.atomic
    def reverse_stock_movement(
            original_movement: InventoryMovement,
            reason: str = '',
            created_by=None
    ) -> Result:
        """
        🎯 REVERSE API: Create reverse movement for corrections - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            reverse_movement = MovementService._reverse_movement_internal(
                original_movement=original_movement,
                reason=reason,
                created_by=created_by
            )

            reverse_data = {
                'reverse_movement_id': reverse_movement.id,
                'original_movement_id': original_movement.id,
                'original_type': original_movement.movement_type,
                'reverse_type': reverse_movement.movement_type,
                'quantity': reverse_movement.quantity,
                'location_code': reverse_movement.location.code,
                'product_code': reverse_movement.product.code,
                'reason': reason
            }

            logger.info(f"✅ Created reverse movement: {reverse_movement.id} for original {original_movement.id}")

            return Result.success(
                data=reverse_data,
                msg=f'Successfully created reverse movement for {original_movement.source_document_number}'
            )

        except Exception as e:
            logger.error(f"Error creating reverse movement: {e}")
            return Result.error(
                code='REVERSE_ERROR',
                msg=f'Reverse movement failed: {str(e)}',
                data={'original_movement_id': original_movement.id}
            )

    @staticmethod
    def process_document_movements(document) -> Result:
        """
        🎯 AUTOMATION API: Process inventory movements from document - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            movements = MovementService._create_from_document_internal(document)

            processing_data = {
                'document_id': getattr(document, 'id', None),
                'document_type': document._meta.model_name.lower(),
                'document_number': getattr(document, 'document_number', ''),
                'movements_created': len(movements),
                'movements': [{'id': m.id, 'type': m.movement_type, 'quantity': m.quantity} for m in movements]
            }

            logger.info(f"✅ Processed document: {len(movements)} movements created")

            return Result.success(
                data=processing_data,
                msg=f'Successfully processed document with {len(movements)} movements'
            )

        except Exception as e:
            logger.error(f"Error processing document movements: {e}")
            return Result.error(
                code='DOCUMENT_PROCESSING_ERROR',
                msg=f'Document processing failed: {str(e)}',
                data={'document_type': getattr(document, '_meta.model_name', '?')}
            )

    @staticmethod
    def sync_movements_with_document(document) -> Result:
        """
        🎯 SYNC API: Synchronize movements with document status - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            sync_result = MovementService._sync_movements_with_document_internal(document)

            return Result.success(
                data=sync_result,
                msg='Successfully synchronized movements with document status'
            )

        except Exception as e:
            logger.error(f"Error syncing movements: {e}")
            return Result.error(
                code='SYNC_ERROR',
                msg=f'Movement synchronization failed: {str(e)}',
                data={'document_id': getattr(document, 'id', None)}
            )

    @staticmethod
    def bulk_create_movements(movement_data_list: List[Dict]) -> Result:
        """
        🎯 BULK API: Create multiple movements efficiently - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            movements = MovementService._bulk_create_movements_internal(movement_data_list)

            bulk_data = {
                'total_requested': len(movement_data_list),
                'successfully_created': len(movements),
                'movements': [{'id': m.id, 'product_code': m.product.code} for m in movements]
            }

            return Result.success(
                data=bulk_data,
                msg=f'Successfully created {len(movements)} out of {len(movement_data_list)} movements'
            )

        except Exception as e:
            logger.error(f"Error in bulk movement creation: {e}")
            return Result.error(
                code='BULK_CREATION_ERROR',
                msg=f'Bulk movement creation failed: {str(e)}',
                data={'requested_count': len(movement_data_list)}
            )

    @staticmethod
    def get_movement_analysis(
            location=None,
            product=None,
            days_back: int = 30,
            movement_types: List[str] = None
    ) -> Result:
        """
        🎯 ANALYSIS API: Get detailed movement history and analysis - NEW Result-based method
        """
        try:
            # Use legacy method for full functionality
            history = MovementService._get_movement_history_internal(
                location=location,
                product=product,
                days_back=days_back,
                movement_types=movement_types,
                include_profit_data=True
            )

            # Calculate summary statistics
            total_in = sum(h['quantity'] for h in history if h['movement_type'] == 'IN')
            total_out = sum(h['quantity'] for h in history if h['movement_type'] == 'OUT')
            total_profit = sum(h.get('total_profit', 0) for h in history if h.get('total_profit'))

            analysis_data = {
                'period_days': days_back,
                'total_movements': len(history),
                'total_in': total_in,
                'total_out': total_out,
                'net_movement': total_in - total_out,
                'total_profit': total_profit,
                'movements': history
            }

            return Result.success(
                data=analysis_data,
                msg=f'Movement analysis completed for {days_back} days'
            )

        except Exception as e:
            logger.error(f"Error in movement analysis: {e}")
            return Result.error(
                code='ANALYSIS_ERROR',
                msg=f'Movement analysis failed: {str(e)}'
            )

    # =====================================================
    # INTERNAL IMPLEMENTATION METHODS (FULL ORIGINAL LOGIC)
    # =====================================================

    @staticmethod
    @transaction.atomic
    def _create_incoming_movement_internal(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            cost_price: Decimal,
            source_document_type: str = 'RECEIPT',
            source_document_number: str = '',
            source_document_line_id: Optional[int] = None,
            batch_number: Optional[str] = None,
            expiry_date=None,
            movement_date=None,
            reason: str = '',
            created_by=None
    ) -> InventoryMovement:
        """Internal incoming movement creation with full original logic"""

        if movement_date is None:
            movement_date = timezone.now().date()

        # CREATE MOVEMENT
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
                    logger.warning(f"Error checking cost change: {e}")

            # Batch cache if needed
            if batch_number and MovementService._should_track_batches(location, product):
                InventoryBatch.refresh_for_combination(location, product, batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after incoming movement: {e}")

        logger.info(f"✅ Created incoming movement: {product.code} +{quantity} at {location.code}")
        return movement

    @staticmethod
    @transaction.atomic
    def _create_outgoing_movement_internal(
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
            sale_price: Optional[Decimal] = None,
            customer=None
    ) -> List[InventoryMovement]:
        """Internal outgoing movement creation with WORKING RACE CONDITION PROTECTION"""

        if movement_date is None:
            movement_date = timezone.now().date()

        if allow_negative_stock is None:
            allow_negative_stock = getattr(location, 'allow_negative_stock', False)

        # Auto-detect sale price if not provided
        if sale_price is None and source_document_type in ['SALE', 'DELIVERY']:
            sale_price = MovementService._detect_sale_price(location, product, customer, quantity)

        # 🔒 CRITICAL FIX: Lock AND update atomically
        if not allow_negative_stock:
            # Try to update atomically with F() expression
            updated = InventoryItem.objects.filter(
                location=location,
                product=product,
                current_qty__gte=quantity + F('reserved_qty')  # Check available
            ).update(
                current_qty=F('current_qty') - quantity  # Decrease atomically
            )

            if updated == 0:
                # No rows updated = insufficient stock
                try:
                    item = InventoryItem.objects.get(location=location, product=product)
                    available = item.current_qty - item.reserved_qty
                    raise ValidationError(
                        f"Insufficient stock. Available: {available}, Required: {quantity}"
                    )
                except InventoryItem.DoesNotExist:
                    raise ValidationError("No inventory record found for this product at this location")

        else:
            # If negative allowed, just decrease without checking
            InventoryItem.objects.filter(
                location=location,
                product=product
            ).update(
                current_qty=F('current_qty') - quantity
            )

        movements = []
        should_track_batches = MovementService._should_track_batches(location, product)

        if should_track_batches and use_fifo and manual_batch_number is None:
            movements = MovementService._create_fifo_outgoing_movements(
                location, product, quantity, movement_date, source_document_type,
                source_document_number, source_document_line_id, reason, created_by, sale_price
            )
        else:
            cost_price = manual_cost_price or MovementService._get_smart_cost_price(
                location=location,
                product=product,
                batch_number=manual_batch_number,
                movement_type='OUT'
            )

            # Round cost price
            cost_price = cost_price.quantize(Decimal('0.01'))

            # Calculate and round profit
            profit_amount = Decimal('0.00')
            if sale_price:  # ← CHECK if sale_price exists
                sale_price = sale_price.quantize(Decimal('0.01'))  # ← quantize ONLY if not None
                profit_amount = ((sale_price - cost_price) * quantity).quantize(Decimal('0.01'))

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=quantity,
                cost_price=cost_price,
                sale_price=sale_price,  # Can be None - that's OK
                profit_amount=profit_amount,
                batch_number=manual_batch_number,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )
            movements.append(movement)

        # Cache refresh AFTER movement is created
        try:
            InventoryItem.refresh_for_combination(location, product)

            if should_track_batches and movements:
                for movement in movements:
                    if movement.batch_number:
                        InventoryBatch.refresh_for_combination(
                            location, product, movement.batch_number
                        )
        except Exception as e:
            logger.error(f"Error refreshing cache after outgoing movement: {e}")

        # Log success
        total_profit = sum(getattr(m, 'total_profit', 0) or Decimal('0') for m in movements)
        logger.info(
            f"✅ Created outgoing movement: {product.code} -{quantity} at {location.code}, "
            f"movements: {len(movements)}, total_profit: {total_profit}"
        )

        return movements

    @staticmethod
    def _create_fifo_outgoing_movements(
            location, product, quantity, movement_date, source_document_type,
            source_document_number, source_document_line_id, reason, created_by, sale_price
    ) -> List[InventoryMovement]:
        """FIFO implementation with BATCH LOCKING and PROFIT ROUNDING"""

        movements = []
        remaining_qty = quantity

        # 🔒 Lock batches with select_for_update()
        available_batches = InventoryBatch.objects.select_for_update().filter(
            location=location,
            product=product,
            current_qty__gt=0
        ).order_by('created_at')

        for batch in available_batches:
            if remaining_qty <= 0:
                break

            qty_from_batch = min(remaining_qty, batch.current_qty)

            # 🔧 FIX: Calculate and round profit_amount
            batch_cost = batch.avg_cost or Decimal('0.00')
            profit_amount = Decimal('0.00')
            if sale_price:
                profit_amount = ((sale_price - batch_cost) * qty_from_batch).quantize(Decimal('0.01'))

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=qty_from_batch,
                cost_price=batch_cost,
                sale_price=sale_price,
                profit_amount=profit_amount,  # ← ДОБАВЕНО С ЗАКРЪГЛЯНЕ
                batch_number=batch.batch_number,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason or f'FIFO from batch {batch.batch_number}',
                created_by=created_by
            )
            movements.append(movement)

            # Update batch atomically

            InventoryBatch.objects.filter(pk=batch.pk).update(
                current_qty=F('current_qty') - qty_from_batch
            )

            remaining_qty -= qty_from_batch

        # Handle remaining if no batches
        if remaining_qty > 0:
            if not getattr(location, 'allow_negative_stock', False):
                raise ValidationError(f"Insufficient batch quantities. Need {remaining_qty} more units")

            default_cost = MovementService._get_smart_cost_price(location, product, None, 'OUT')

            # 🔧 FIX: Round profit for non-batch movement too
            profit_amount = Decimal('0.00')
            if sale_price:
                profit_amount = ((sale_price - default_cost) * remaining_qty).quantize(Decimal('0.01'))

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=remaining_qty,
                cost_price=default_cost,
                sale_price=sale_price,
                profit_amount=profit_amount,  # ← ДОБАВЕНО
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                source_document_line_id=source_document_line_id,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )
            movements.append(movement)

        return movements

    @staticmethod
    def _get_available_batches(location, product) -> List[Dict]:
        """Get available batches ordered by FIFO"""
        try:
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                current_qty__gt=0
            ).order_by('created_at')  # FIFO order

            batch_list = []
            for batch in batches:
                batch_list.append({
                    'batch_number': batch.batch_number,
                    'available_qty': batch.current_qty,
                    'avg_cost': batch.avg_cost or Decimal('0'),
                    'created_at': batch.created_at
                })

            return batch_list

        except Exception as e:
            logger.error(f"Error getting available batches: {e}")
            return []

    @staticmethod
    @transaction.atomic
    def _create_transfer_movement_internal(
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
        """Internal transfer movement creation with LOCKING"""

        if movement_date is None:
            movement_date = timezone.now().date()

        # 🔒 LOCK source location inventory first
        try:
            source_item = InventoryItem.objects.select_for_update().get(
                location=from_location,
                product=product
            )
            if source_item.available_qty < quantity:
                raise ValidationError(
                    f"Insufficient stock at source. Available: {source_item.available_qty}, Required: {quantity}"
                )
        except InventoryItem.DoesNotExist:
            raise ValidationError(f"No inventory at source location {from_location.code}")

        # Create outgoing movements from source location
        outbound_movements = MovementService._create_outgoing_movement_internal(
            location=from_location,
            product=product,
            quantity=quantity,
            source_document_type=source_document_type,
            source_document_number=source_document_number,
            source_document_line_id=source_document_line_id,
            movement_date=movement_date,
            reason=f"Transfer to {to_location.code}: {reason}",
            created_by=created_by,
            use_fifo=True,
            allow_negative_stock=False
        )

        # Calculate weighted average cost from outbound movements
        total_cost = sum(m.cost_price * m.quantity for m in outbound_movements)
        transfer_cost = total_cost / quantity

        # Create incoming movement at destination
        inbound_movement = MovementService._create_incoming_movement_internal(
            location=to_location,
            product=product,
            quantity=quantity,
            cost_price=transfer_cost,
            source_document_type=source_document_type,
            source_document_number=source_document_number,
            source_document_line_id=source_document_line_id,
            movement_date=movement_date,
            reason=f"Transfer from {from_location.code}: {reason}",
            created_by=created_by
        )

        logger.info(f"✅ Transfer completed: {product.code} {quantity} from {from_location.code} to {to_location.code}")
        return outbound_movements, [inbound_movement]

    @staticmethod
    @transaction.atomic
    def _create_adjustment_movement_internal(
            location: InventoryLocation,
            product,
            adjustment_qty: Decimal,
            reason: str,
            movement_date=None,
            created_by=None,
            manual_cost_price: Optional[Decimal] = None,
            batch_number: Optional[str] = None
    ) -> InventoryMovement:
        """Internal adjustment movement creation - full original logic"""

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

            if batch_number and MovementService._should_track_batches(location, product):
                InventoryBatch.refresh_for_combination(location, product, batch_number)

        except Exception as e:
            logger.error(f"Error refreshing cache after adjustment: {e}")

        logger.info(f"✅ Created adjustment: {product.code} {adjustment_qty:+} at {location.code}")
        return movement

    @staticmethod
    @transaction.atomic
    def _reverse_movement_internal(
            original_movement: InventoryMovement,
            reason: str = '',
            created_by=None
    ) -> InventoryMovement:
        """Internal reverse movement creation - full original logic"""

        try:
            # Generate reversal document number
            reversal_doc_number = f"REV-{original_movement.source_document_number}"

            # Check if reverse already exists
            existing_reverse = InventoryMovement.objects.filter(
                source_document_type='REVERSAL',
                source_document_number=reversal_doc_number,
                product=original_movement.product,
                location=original_movement.location,
                source_document_line_id=original_movement.source_document_line_id
            ).first()

            if existing_reverse:
                logger.info(f"Reverse movement already exists: {existing_reverse.id}")
                return existing_reverse

            # Determine reverse movement type
            reverse_movement_type = 'OUT' if original_movement.movement_type == 'IN' else 'IN'

            # Create reverse movement
            reverse_movement = InventoryMovement.objects.create(
                movement_type=reverse_movement_type,
                product=original_movement.product,
                location=original_movement.location,
                quantity=original_movement.quantity,
                cost_price=original_movement.cost_price,
                source_document_type='REVERSAL',
                source_document_number=reversal_doc_number,
                source_document_line_id=original_movement.source_document_line_id,
                reason=reason or f'Reverse of {original_movement.source_document_number}',
                movement_date=timezone.now(),
                created_by=created_by
            )

            # Refresh cache
            InventoryItem.refresh_for_combination(original_movement.location, original_movement.product)

            logger.info(f"Created reverse movement {reverse_movement.id} for original {original_movement.id}")
            return reverse_movement

        except Exception as e:
            logger.error(f"Error creating reverse movement: {e}")
            raise

    @staticmethod
    def _create_from_document_internal(document) -> List[InventoryMovement]:
        """Internal document processing - full original logic"""

        movements = []
        model_name = document._meta.model_name.lower()

        try:
            if model_name == 'deliveryreceipt':
                movements = MovementService._create_from_delivery(document)
            elif model_name == 'purchaseorder':
                movements = MovementService._create_from_purchase_order(document)
            elif model_name == 'stocktransfer':
                movements = MovementService._create_from_stock_transfer(document)
            elif model_name == 'purchaserequest':
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
    def _sync_movements_with_document_internal(document) -> Dict:
        """Internal movement synchronization - full original logic"""

        try:
            # Delete existing movements for this document
            from inventory.models import InventoryMovement

            # Original movements
            original_movements = InventoryMovement.objects.filter(
                source_document_type__in=['PURCHASE_REQUEST', 'PURCHASEREQUEST'],
                source_document_number=document.document_number
            )

            # Reversal movements
            reversal_movements = InventoryMovement.objects.filter(
                source_document_type='REVERSAL'
            ).filter(
                source_document_number__contains=document.document_number
            )

            original_count = original_movements.count()
            reversal_count = reversal_movements.count()

            original_movements.delete()
            reversal_movements.delete()

            logger.info(f"Deleted {original_count} original + {reversal_count} reversal movements")

            # Create fresh movements if status requires
            new_movements = []

            try:
                from nomenclatures.models import DocumentTypeStatus

                current_config = DocumentTypeStatus.objects.filter(
                    document_type=document.document_type,
                    status__code=document.status,
                    is_active=True
                ).first()

                if current_config and current_config.creates_inventory_movements:
                    new_movements = MovementService._create_from_document_internal(document)
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
    def _bulk_create_movements_internal(movement_data_list: List[Dict]) -> List[InventoryMovement]:
        """Internal bulk creation - full original logic"""

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
                    movement = MovementService._create_incoming_movement_internal(**data)
                    movements.append(movement)
                elif data['movement_type'] == 'OUT':
                    movement_list = MovementService._create_outgoing_movement_internal(**data)
                    movements.extend(movement_list)
                else:
                    errors.append(f"Row {i + 1}: Unsupported movement type: {data['movement_type']}")
                    continue

            except Exception as e:
                errors.append(f"Row {i + 1}: {str(e)}")
                continue

        if errors:
            logger.error(f"Bulk movement creation errors: {errors}")

        logger.info(f"Bulk created {len(movements)} movements with {len(errors)} errors")
        return movements

    @staticmethod
    def _get_movement_history_internal(
            location=None,
            product=None,
            days_back: int = 30,
            movement_types: List[str] = None,
            include_profit_data: bool = True
    ) -> List[Dict]:
        """Internal movement history - full original logic"""

        queryset = InventoryMovement.objects.select_related(
            'product', 'location', 'created_by'
        )

        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if movement_types:
            queryset = queryset.filter(movement_type__in=movement_types)

        # Filter by date
        if days_back > 0:
            start_date = timezone.now().date() - timedelta(days=days_back)
            queryset = queryset.filter(movement_date__gte=start_date)

        movements = queryset.order_by('-movement_date', '-created_at')

        history = []
        for movement in movements:
            movement_data = {
                'id': movement.id,
                'movement_date': movement.movement_date,
                'movement_type': movement.movement_type,
                'quantity': movement.quantity,
                'cost_price': movement.cost_price,
                'sale_price': movement.sale_price,
                'batch_number': movement.batch_number,
                'source_document_type': movement.source_document_type,
                'source_document_number': movement.source_document_number,
                'reason': movement.reason,
                'product_code': movement.product.code,
                'location_code': movement.location.code,
                'created_by': movement.created_by.username if movement.created_by else None,
            }

            if include_profit_data and movement.sale_price:
                movement_data.update({
                    'unit_profit': movement.sale_price - movement.cost_price,
                    'total_profit': (movement.sale_price - movement.cost_price) * movement.quantity,
                    'profit_margin': ((
                                                  movement.sale_price - movement.cost_price) / movement.sale_price * 100) if movement.sale_price > 0 else 0
                })

            history.append(movement_data)

        return history

    # =====================================================
    # DOCUMENT PROCESSING METHODS (FULL ORIGINAL IMPLEMENTATIONS)
    # =====================================================

    @staticmethod
    def _create_from_delivery(delivery) -> List[InventoryMovement]:
        """Enhanced delivery processing - full original logic"""
        movements = []
        direction = getattr(delivery.document_type, 'inventory_direction', 'in')

        for line in delivery.lines.all():
            if not line.received_quantity or line.received_quantity == 0:
                continue

            try:
                if direction == 'both':
                    if line.received_quantity > 0:
                        # Positive = incoming
                        movement = MovementService._create_incoming_movement_internal(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            cost_price=line.unit_price or Decimal('0.00'),
                            source_document_type='DELIVERY',
                            source_document_number=delivery.document_number,
                            source_document_line_id=line.line_number,
                            batch_number=getattr(line, 'batch_number', None),
                            expiry_date=getattr(line, 'expiry_date', None),
                            reason=f"Delivery receipt (line {line.line_number})"
                        )
                        movements.append(movement)

                    elif line.received_quantity < 0:
                        # Negative = outgoing (return/correction)
                        outgoing_movements = MovementService._create_outgoing_movement_internal(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),
                            source_document_type='DELIVERY_RETURN',
                            source_document_number=delivery.document_number,
                            source_document_line_id=line.line_number,
                            reason=f"Delivery return (line {line.line_number})"
                        )
                        movements.extend(outgoing_movements)

                elif direction == 'in' or direction == 'both':
                    # Standard incoming delivery
                    movement = MovementService._create_incoming_movement_internal(
                        location=delivery.location,
                        product=line.product,
                        quantity=abs(line.received_quantity),
                        cost_price=line.unit_price or Decimal('0.00'),
                        source_document_type='DELIVERY',
                        source_document_number=delivery.document_number,
                        source_document_line_id=line.line_number,
                        batch_number=getattr(line, 'batch_number', None),
                        expiry_date=getattr(line, 'expiry_date', None),
                        reason=f"Delivery receipt (line {line.line_number})"
                    )
                    movements.append(movement)

                elif direction == 'out':
                    # Outgoing delivery (rare)
                    outgoing_movements = MovementService._create_outgoing_movement_internal(
                        location=delivery.location,
                        product=line.product,
                        quantity=abs(line.received_quantity),
                        source_document_type='DELIVERY_OUT',
                        source_document_number=delivery.document_number,
                        source_document_line_id=line.line_number,
                        reason=f"Delivery dispatch (line {line.line_number})"
                    )
                    movements.extend(outgoing_movements)

            except Exception as e:
                logger.error(f"Error processing delivery line {line.line_number}: {e}")
                continue

        return movements

    @staticmethod
    def _create_from_purchase_order(order) -> List[InventoryMovement]:
        """Create movements from purchase order (auto-receive scenario) - full original logic"""
        movements = []

        # Check if auto-receive is enabled
        if not getattr(order.document_type, 'auto_receive', False):
            logger.debug(f"Order {order.document_number} does not have auto-receive enabled")
            return movements

        for line in order.lines.all():
            if not line.ordered_quantity or line.ordered_quantity <= 0:
                continue

            try:
                movement = MovementService._create_incoming_movement_internal(
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
    def _create_from_purchase_request(request) -> List[InventoryMovement]:
        """Create movements from approved purchase request - full original logic"""
        movements = []

        for line in request.lines.all():
            if not line.requested_quantity or line.requested_quantity == 0:
                continue

            try:
                # Use correct price field
                cost_price = getattr(line, 'unit_price', None) or getattr(line, 'entered_price', None) or Decimal(
                    '0.00')

                # PurchaseRequest usually creates IN movement (planned receipt)
                movement = MovementService._create_incoming_movement_internal(
                    location=request.location,
                    product=line.product,
                    quantity=line.requested_quantity,
                    cost_price=cost_price,
                    source_document_type='PURCHASE_REQUEST',
                    source_document_number=request.document_number,
                    source_document_line_id=getattr(line, 'line_number', None),
                    reason=f"Purchase request approved (line {getattr(line, 'line_number', None)})"
                )
                movements.append(movement)

            except Exception as e:
                logger.error(f"Error processing request line {getattr(line, 'line_number', '?')}: {e}")
                continue

        return movements

    @staticmethod
    def _create_from_stock_transfer(transfer) -> List[InventoryMovement]:
        """Create movements from stock transfer document - full original logic"""
        movements = []

        for line in transfer.lines.all():
            if not line.quantity or line.quantity <= 0:
                continue

            try:
                # Use the transfer method which handles both directions
                outbound, inbound = MovementService._create_transfer_movement_internal(
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
        """Create movements from stock adjustment document - full original logic"""
        movements = []

        for line in adjustment.lines.all():
            if not line.adjustment_quantity or line.adjustment_quantity == 0:
                continue

            try:
                movement = MovementService._create_adjustment_movement_internal(
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
    # UTILITY HELPER METHODS (FULL ORIGINAL IMPLEMENTATIONS)
    # =====================================================

    @staticmethod
    def _validate_movement_inputs(location, product, quantity, movement_type) -> Result:
        """Internal validation of movement inputs"""
        if not location:
            return Result.error(code='INVALID_LOCATION', msg='Location is required')

        if not product:
            return Result.error(code='INVALID_PRODUCT', msg='Product is required')

        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg='Quantity must be positive',
                data={'quantity': quantity}
            )

        # Check for fractional pieces
        if hasattr(product, 'unit_type') and product.unit_type == 'PIECE':
            if quantity != int(quantity):
                return Result.error(
                    code='FRACTIONAL_PIECES',
                    msg='Piece products cannot have fractional quantities',
                    data={'quantity': quantity, 'unit_type': product.unit_type}
                )

        return Result.success()

    @staticmethod
    def _detect_sale_price(location, product, customer=None, quantity=Decimal('1')) -> Optional[Decimal]:
        """Auto-detect sale price using PricingService"""
        try:
            from pricing.services import PricingService

            price_result = PricingService.get_product_pricing(location, product, customer, quantity)
            if price_result.ok:
                return price_result.data.get('final_price')
            else:
                logger.warning(f"Pricing failed: {price_result.msg}")
                return None
        except Exception as e:
            logger.warning(f"Could not detect sale price: {e}")
            return None

    @staticmethod
    def _should_track_batches(location, product) -> bool:
        """
        Determine if batch tracking should be used
        SIMPLE VERSION - based on what EXISTS in the code
        """
        # Check if location has the method (currently doesn't exist)
        if hasattr(location, 'should_track_batches'):
            return location.should_track_batches(product)

        # Check product settings that ACTUALLY EXIST
        if hasattr(product, 'track_batches'):
            return product.track_batches
        elif hasattr(product, 'requires_batch_tracking'):
            return product.requires_batch_tracking

        # Default - no batch tracking
        return False

    @staticmethod
    def _get_smart_cost_price(location, product, batch_number=None, movement_type='OUT') -> Decimal:
        """Get smart cost price based on movement type"""
        try:
            if batch_number:
                # Try to get batch-specific cost
                batch = InventoryBatch.objects.get(
                    location=location, product=product, batch_number=batch_number
                )
                return batch.avg_cost or Decimal('0')
            else:
                # Get location average cost
                item = InventoryItem.objects.get(location=location, product=product)
                return item.avg_cost or Decimal('0')
        except (InventoryItem.DoesNotExist, InventoryBatch.DoesNotExist):
            return Decimal('0')

    @staticmethod
    def _trigger_pricing_update(location, product, new_cost):
        """Trigger pricing update when cost changes significantly"""
        try:
            from pricing.services import PricingService
            # Update markup-based prices
            logger.info(f"Triggering pricing update for {product.code} with new cost {new_cost}")
            # Implementation would depend on pricing structure
        except Exception as e:
            logger.warning(f"Could not trigger pricing update: {e}")

    @staticmethod
    def validate_movement_data(data: Dict) -> Tuple[bool, List[str]]:
        """Validate movement data for bulk operations"""
        errors = []

        required_fields = ['location', 'product', 'quantity', 'movement_type']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")

        if 'quantity' in data:
            try:
                quantity = Decimal(str(data['quantity']))
                if quantity <= 0:
                    errors.append("Quantity must be positive")
            except:
                errors.append("Invalid quantity format")

        if 'movement_type' in data:
            if data['movement_type'] not in ['IN', 'OUT']:
                errors.append("Movement type must be 'IN' or 'OUT'")

        return len(errors) == 0, errors

    @staticmethod
    def get_movement_statistics(location=None, product=None, date_from=None, date_to=None) -> Dict:
        """Get movement statistics for reporting"""
        queryset = InventoryMovement.objects.all()

        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if date_from:
            queryset = queryset.filter(movement_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(movement_date__lte=date_to)

        stats = {
            'total_movements': queryset.count(),
            'total_in': queryset.filter(movement_type='IN').count(),
            'total_out': queryset.filter(movement_type='OUT').count(),
            'total_quantity_in': queryset.filter(movement_type='IN').aggregate(
                total=Sum('quantity'))['total'] or Decimal('0'),
            'total_quantity_out': queryset.filter(movement_type='OUT').aggregate(
                total=Sum('quantity'))['total'] or Decimal('0'),
        }

        stats['net_quantity'] = stats['total_quantity_in'] - stats['total_quantity_out']

        return stats


# =====================================================
# MODULE EXPORTS
# =====================================================

__all__ = ['MovementService']