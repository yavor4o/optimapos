# inventory/services/inventory_service.py - FULL REFACTORED WITH RESULT PATTERN

from django.db.models import Sum, Count, F, Q, Avg, Max, Min
from django.utils import timezone
from django.db import transaction
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import date, timedelta

from core.utils.result import Result
from ..models import InventoryLocation, InventoryItem, InventoryBatch, InventoryMovement


class InventoryService:
    """
    Enhanced InventoryService - FULLY REFACTORED to use Result pattern

    CHANGES: All methods now return Result objects for consistency
    Legacy methods available for backward compatibility
    """

    # =====================================================
    # NEW: RESULT-BASED METHODS
    # =====================================================

    @staticmethod
    def validate_availability(location: InventoryLocation, product, required_qty: Decimal) -> Result:
        """
        Primary availability check - NEW Result-based method

        Replaces check_availability() with better error handling
        """
        try:
            item = InventoryItem.objects.get(location=location, product=product)

            available = item.available_qty
            can_fulfill = available >= required_qty or location.allow_negative_stock

            availability_data = {
                'available': True,
                'current_qty': item.current_qty,
                'available_qty': available,
                'reserved_qty': item.reserved_qty,
                'can_fulfill': can_fulfill,
                'shortage': max(Decimal('0'), required_qty - available) if not can_fulfill else Decimal('0'),
                'avg_cost': item.avg_cost,
                'last_purchase_cost': getattr(item, 'last_purchase_cost', None),
                'last_sale_price': getattr(item, 'last_sale_price', None),
                'last_movement_date': item.updated_at,
                'product_code': product.code,
                'location_code': location.code,
                'allow_negative_stock': location.allow_negative_stock,
            }

            if not can_fulfill and not location.allow_negative_stock:
                return Result.error(
                    code='INSUFFICIENT_STOCK',
                    msg=f"Insufficient stock. Available: {available}, Required: {required_qty}",
                    data=availability_data
                )

            return Result.success(
                data=availability_data,
                msg=f"Stock available: {available} units"
            )

        except InventoryItem.DoesNotExist:
            return Result.error(
                code='ITEM_NOT_FOUND',
                msg=f"Product {product.code} not found at location {location.code}",
                data={
                    'product_code': product.code,
                    'location_code': location.code,
                    'current_qty': Decimal('0'),
                    'available_qty': Decimal('0'),
                    'can_fulfill': location.allow_negative_stock
                }
            )
        except Exception as e:
            return Result.error(
                code='AVAILABILITY_ERROR',
                msg=f"Error checking availability: {str(e)}",
                data={'product_code': product.code, 'location_code': location.code}
            )

    @staticmethod
    def validate_batch_availability(location: InventoryLocation, product, required_qty: Decimal) -> Result:
        """
        Enhanced batch availability check - NEW Result-based method
        """
        try:
            # Check if batches should be tracked
            should_track_batches = location.should_track_batches(product)

            if not should_track_batches:
                # Fallback to regular availability
                return InventoryService.validate_availability(location, product, required_qty)

            # Get FIFO ordered batches
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('received_date', 'id')

            batch_details = []
            total_available = Decimal('0')
            remaining_need = required_qty

            for batch in batches:
                is_expired = batch.expiry_date and batch.expiry_date < timezone.now().date()

                batch_info = {
                    'batch_number': batch.batch_number,
                    'expiry_date': batch.expiry_date,
                    'remaining_qty': batch.remaining_qty,
                    'cost_price': batch.cost_price,
                    'received_date': batch.received_date,
                    'is_expired': is_expired,
                    'batch_value': batch.remaining_qty * batch.cost_price,
                    'can_use_qty': min(batch.remaining_qty, remaining_need) if remaining_need > 0 else Decimal('0')
                }

                batch_details.append(batch_info)
                total_available += batch.remaining_qty

                if remaining_need > 0:
                    remaining_need -= min(batch.remaining_qty, remaining_need)

            can_fulfill = total_available >= required_qty or location.allow_negative_stock

            batch_data = {
                'should_track_batches': should_track_batches,
                'total_available': total_available,
                'required_qty': required_qty,
                'can_fulfill': can_fulfill,
                'shortage': max(Decimal('0'), required_qty - total_available) if not can_fulfill else Decimal('0'),
                'batch_count': len(batch_details),
                'batch_details': batch_details,
                'expired_batches': [b for b in batch_details if b['is_expired']],
                'location_code': location.code,
                'product_code': product.code
            }

            if not can_fulfill and not location.allow_negative_stock:
                return Result.error(
                    code='INSUFFICIENT_BATCH_STOCK',
                    msg=f"Insufficient batch stock. Available: {total_available}, Required: {required_qty}",
                    data=batch_data
                )

            return Result.success(
                data=batch_data,
                msg=f"Batch stock available: {total_available} units in {len(batch_details)} batches"
            )

        except Exception as e:
            return Result.error(
                code='BATCH_AVAILABILITY_ERROR',
                msg=f"Error checking batch availability: {str(e)}",
                data={'product_code': product.code, 'location_code': location.code}
            )

    @staticmethod
    def reserve_stock_qty(location: InventoryLocation, product, quantity: Decimal, reason: str = '') -> Result:
        """
        Reserve stock quantity - NEW Result-based method
        """
        try:
            # First check availability
            availability_result = InventoryService.validate_availability(location, product, quantity)
            if not availability_result.ok:
                return availability_result

            with transaction.atomic():
                item = InventoryItem.objects.select_for_update().get(
                    location=location, product=product
                )

                if item.available_qty < quantity and not location.allow_negative_stock:
                    return Result.error(
                        code='INSUFFICIENT_AVAILABLE',
                        msg=f"Cannot reserve {quantity}, only {item.available_qty} available",
                        data={
                            'requested_qty': quantity,
                            'available_qty': item.available_qty,
                            'current_qty': item.current_qty,
                            'reserved_qty': item.reserved_qty
                        }
                    )

                # Update reservation
                old_reserved = item.reserved_qty
                item.reserved_qty += quantity
                item.save(update_fields=['reserved_qty'])

                reservation_data = {
                    'product_code': product.code,
                    'location_code': location.code,
                    'reserved_quantity': quantity,
                    'total_reserved': item.reserved_qty,
                    'previous_reserved': old_reserved,
                    'available_after_reservation': item.available_qty,
                    'reason': reason,
                    'timestamp': timezone.now().isoformat()
                }

                return Result.success(
                    data=reservation_data,
                    msg=f"Reserved {quantity} units. Total reserved: {item.reserved_qty}"
                )

        except InventoryItem.DoesNotExist:
            return Result.error(
                code='ITEM_NOT_FOUND',
                msg=f"Cannot reserve: Product {product.code} not found at {location.code}",
                data={'product_code': product.code, 'location_code': location.code}
            )
        except Exception as e:
            return Result.error(
                code='RESERVATION_ERROR',
                msg=f"Error reserving stock: {str(e)}",
                data={'product_code': product.code, 'quantity': quantity}
            )

    @staticmethod
    def release_reservation(location: InventoryLocation, product, quantity: Decimal) -> Result:
        """
        Release stock reservation - NEW Result-based method
        """
        try:
            with transaction.atomic():
                item = InventoryItem.objects.select_for_update().get(
                    location=location, product=product
                )

                if item.reserved_qty < quantity:
                    return Result.error(
                        code='INSUFFICIENT_RESERVED',
                        msg=f"Cannot release {quantity}, only {item.reserved_qty} reserved",
                        data={
                            'requested_qty': quantity,
                            'reserved_qty': item.reserved_qty,
                            'available_qty': item.available_qty
                        }
                    )

                # Update reservation
                old_reserved = item.reserved_qty
                item.reserved_qty -= quantity
                item.save(update_fields=['reserved_qty'])

                release_data = {
                    'product_code': product.code,
                    'location_code': location.code,
                    'released_quantity': quantity,
                    'total_reserved': item.reserved_qty,
                    'previous_reserved': old_reserved,
                    'available_after_release': item.available_qty,
                    'timestamp': timezone.now().isoformat()
                }

                return Result.success(
                    data=release_data,
                    msg=f"Released {quantity} units. Total reserved: {item.reserved_qty}"
                )

        except InventoryItem.DoesNotExist:
            return Result.error(
                code='ITEM_NOT_FOUND',
                msg=f"Cannot release: Product {product.code} not found at {location.code}",
                data={'product_code': product.code, 'location_code': location.code}
            )
        except Exception as e:
            return Result.error(
                code='RELEASE_ERROR',
                msg=f"Error releasing reservation: {str(e)}",
                data={'product_code': product.code, 'quantity': quantity}
            )

    @staticmethod
    def get_stock_summary(location: InventoryLocation, product) -> Result:
        """
        Get comprehensive stock information - NEW Result-based method
        """
        try:
            item = InventoryItem.objects.get(location=location, product=product)

            # Get batch information if available
            batches = []
            batch_total_qty = Decimal('0')
            if product.track_batches and location.should_track_batches(product):
                batch_queryset = InventoryBatch.objects.filter(
                    location=location,
                    product=product,
                    remaining_qty__gt=0
                ).order_by('received_date')

                for batch in batch_queryset:
                    batch_info = {
                        'batch_number': batch.batch_number,
                        'remaining_qty': batch.remaining_qty,
                        'received_qty': batch.received_qty,
                        'expiry_date': batch.expiry_date,
                        'cost_price': batch.cost_price,
                        'received_date': batch.received_date,
                        'is_expired': batch.expiry_date and batch.expiry_date < timezone.now().date(),
                        'batch_value': batch.remaining_qty * batch.cost_price
                    }
                    batches.append(batch_info)
                    batch_total_qty += batch.remaining_qty

            stock_data = {
                'product_code': product.code,
                'product_name': product.name,
                'location_code': location.code,
                'location_name': location.name,
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'last_purchase_cost': getattr(item, 'last_purchase_cost', None),
                'last_purchase_date': getattr(item, 'last_purchase_date', None),
                'last_sale_date': getattr(item, 'last_sale_date', None),
                'last_sale_price': getattr(item, 'last_sale_price', None),
                'total_stock_value': item.current_qty * item.avg_cost,
                'available_stock_value': item.available_qty * item.avg_cost,
                'batches': batches,
                'batch_count': len(batches),
                'total_batch_qty': batch_total_qty,
                'tracks_batches': product.track_batches and location.should_track_batches(product),
                'stock_status': 'IN_STOCK' if item.current_qty > 0 else 'OUT_OF_STOCK',
                'last_updated': item.updated_at
            }

            return Result.success(
                data=stock_data,
                msg=f"Stock summary for {product.code}: {item.current_qty} units"
            )

        except InventoryItem.DoesNotExist:
            return Result.error(
                code='ITEM_NOT_FOUND',
                msg=f"No stock record for {product.code} at {location.code}",
                data={
                    'product_code': product.code,
                    'location_code': location.code,
                    'current_qty': Decimal('0'),
                    'stock_status': 'NOT_TRACKED'
                }
            )
        except Exception as e:
            return Result.error(
                code='STOCK_INFO_ERROR',
                msg=f"Error retrieving stock info: {str(e)}",
                data={'product_code': product.code, 'location_code': location.code}
            )

    @staticmethod
    def validate_stock_operation(location: InventoryLocation, product, quantity: Decimal,
                                 operation_type: str) -> Result:
        """
        Enhanced validation for stock operations - NEW Result-based method
        """
        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg="Quantity must be positive",
                data={'quantity': quantity, 'operation_type': operation_type}
            )

        if operation_type == 'OUT':
            availability_result = InventoryService.validate_availability(location, product, quantity)
            if not availability_result.ok:
                return availability_result

            operation_data = availability_result.data
            operation_data['operation_type'] = operation_type
            operation_data['validated_for'] = 'OUTGOING_MOVEMENT'

            return Result.success(
                data=operation_data,
                msg=f"Validated for outgoing movement: {quantity} units"
            )

        elif operation_type == 'IN':
            # Basic validation for incoming stock
            operation_data = {
                'operation_type': operation_type,
                'quantity': quantity,
                'product_code': product.code,
                'location_code': location.code,
                'validated_for': 'INCOMING_MOVEMENT'
            }

            return Result.success(
                data=operation_data,
                msg=f"Validated for incoming movement: {quantity} units"
            )

        elif operation_type == 'TRANSFER':
            # Validate source location has stock
            availability_result = InventoryService.validate_availability(location, product, quantity)
            if not availability_result.ok:
                return availability_result

            operation_data = availability_result.data
            operation_data['operation_type'] = operation_type
            operation_data['validated_for'] = 'TRANSFER_OUT'

            return Result.success(
                data=operation_data,
                msg=f"Validated for transfer out: {quantity} units"
            )

        else:
            return Result.error(
                code='INVALID_OPERATION',
                msg=f"Unknown operation type: {operation_type}",
                data={'operation_type': operation_type}
            )

    @staticmethod
    def get_cost_for_location(location: InventoryLocation, product) -> Result:
        """
        Get current cost for product at location - NEW Result-based method
        """
        try:
            # 1. Try InventoryItem average cost
            try:
                item = InventoryItem.objects.get(location=location, product=product)
                if item.avg_cost > 0:
                    return Result.success(
                        data={
                            'cost_price': item.avg_cost,
                            'source': 'INVENTORY_ITEM_AVG_COST',
                            'last_updated': item.updated_at,
                            'product_code': product.code,
                            'location_code': location.code
                        },
                        msg=f"Cost from inventory average: {item.avg_cost}"
                    )
            except InventoryItem.DoesNotExist:
                pass

            # 2. Try last purchase cost
            try:
                item = InventoryItem.objects.get(location=location, product=product)
                if hasattr(item, 'last_purchase_cost') and item.last_purchase_cost and item.last_purchase_cost > 0:
                    return Result.success(
                        data={
                            'cost_price': item.last_purchase_cost,
                            'source': 'LAST_PURCHASE_COST',
                            'last_updated': getattr(item, 'last_purchase_date', None),
                            'product_code': product.code,
                            'location_code': location.code
                        },
                        msg=f"Cost from last purchase: {item.last_purchase_cost}"
                    )
            except (InventoryItem.DoesNotExist, AttributeError):
                pass

            # 3. Fallback
            return Result.success(
                data={
                    'cost_price': Decimal('0.00'),
                    'source': 'FALLBACK_ZERO',
                    'last_updated': None,
                    'product_code': product.code,
                    'location_code': location.code
                },
                msg="No cost information available, using zero"
            )

        except Exception as e:
            return Result.error(
                code='COST_RETRIEVAL_ERROR',
                msg=f"Error retrieving cost: {str(e)}",
                data={'product_code': product.code, 'location_code': location.code}
            )

    # =====================================================
    # LEGACY METHODS - BACKWARD COMPATIBILITY
    # =====================================================

    @staticmethod
    def check_availability(location: InventoryLocation, product, required_qty: Decimal) -> Dict:
        """
        LEGACY METHOD: Use validate_availability() for new code

        Maintained for backward compatibility
        """
        result = InventoryService.validate_availability(location, product, required_qty)
        return result.data if result.ok else {'available': False, 'error': result.msg}

    @staticmethod
    def check_batch_availability(location: InventoryLocation, product, required_qty: Decimal) -> Dict:
        """
        LEGACY METHOD: Use validate_batch_availability() for new code

        Maintained for backward compatibility
        """
        result = InventoryService.validate_batch_availability(location, product, required_qty)
        return result.data if result.ok else {'error': result.msg}

    @staticmethod
    def reserve_stock(location: InventoryLocation, product, quantity: Decimal, reason: str = '') -> Dict:
        """
        LEGACY METHOD: Use reserve_stock_qty() for new code

        Maintained for backward compatibility
        """
        result = InventoryService.reserve_stock_qty(location, product, quantity, reason)
        if result.ok:
            return {'success': True, **result.data}
        else:
            return {'success': False, 'error': result.msg, **result.data}

    @staticmethod
    def get_stock_info(location: InventoryLocation, product) -> Dict:
        """
        LEGACY METHOD: Use get_stock_summary() for new code

        Maintained for backward compatibility
        """
        result = InventoryService.get_stock_summary(location, product)
        return result.data if result.ok else {'error': result.msg}

    @staticmethod
    def get_cost_for_location_legacy(location: InventoryLocation, product) -> Decimal:
        """
        LEGACY METHOD: Use get_cost_for_location() for new code

        Maintained for backward compatibility
        """
        result = InventoryService.get_cost_for_location(location, product)
        return result.data.get('cost_price', Decimal('0.00')) if result.ok else Decimal('0.00')

    # =====================================================
    # ANALYTICS METHODS (unchanged, already good)
    # =====================================================

    @staticmethod
    def get_location_stock_summary(location: InventoryLocation) -> Dict:
        """Get summary of all stock at location"""
        items = InventoryItem.objects.filter(location=location).select_related('product')

        summary = {
            'total_products': items.count(),
            'total_value': items.aggregate(
                total=Sum(F('current_qty') * F('avg_cost'))
            )['total'] or Decimal('0'),
            'out_of_stock_count': items.filter(current_qty=0).count(),
            'low_stock_count': items.filter(current_qty__lte=F('product__min_stock_level')).count(),
            'reserved_value': items.aggregate(
                total=Sum(F('reserved_qty') * F('avg_cost'))
            )['total'] or Decimal('0'),
        }

        return summary

    @staticmethod
    def get_product_locations(product) -> List[Dict]:
        """Get all locations where product is stocked"""
        items = InventoryItem.objects.filter(product=product).select_related('location')

        locations = []
        for item in items:
            locations.append({
                'location': item.location,
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'last_movement_date': item.updated_at,
            })

        return locations