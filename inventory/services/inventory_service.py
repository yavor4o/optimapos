# inventory/services/inventory_service.py

from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from ..models import InventoryLocation, InventoryItem, InventoryBatch


class InventoryService:
    """
    Core inventory business logic
    Handles stock checking, availability, and inventory queries
    """

    @staticmethod
    def check_availability(location: InventoryLocation, product, required_qty: Decimal) -> Dict:
        """
        Quick availability check for POS/sales
        Returns availability info without detailed batch breakdown
        """
        try:
            item = InventoryItem.objects.get(location=location, product=product)

            available = item.available_qty
            can_fulfill = available >= required_qty or location.allow_negative_stock

            return {
                'available': True,
                'current_qty': item.current_qty,
                'available_qty': available,
                'reserved_qty': item.reserved_qty,
                'can_fulfill': can_fulfill,
                'shortage': max(Decimal('0'), required_qty - available) if not can_fulfill else Decimal('0'),
                'avg_cost': item.avg_cost
            }

        except InventoryItem.DoesNotExist:
            can_fulfill = location.allow_negative_stock
            return {
                'available': False,
                'current_qty': Decimal('0'),
                'available_qty': Decimal('0'),
                'reserved_qty': Decimal('0'),
                'can_fulfill': can_fulfill,
                'shortage': required_qty if not can_fulfill else Decimal('0'),
                'avg_cost': Decimal('0')
            }

    @staticmethod
    def get_stock_summary(location: InventoryLocation, product) -> Dict:
        """
        Detailed stock summary including batch information
        """
        # Get aggregate data
        availability = InventoryService.check_availability(location, product, Decimal('0'))

        result = {
            'location': location.code,
            'product_code': product.code,
            'product_name': product.name,
            'total_qty': availability['current_qty'],
            'available_qty': availability['available_qty'],
            'reserved_qty': availability['reserved_qty'],
            'avg_cost': availability['avg_cost'],
            'batches': []
        }

        # Add batch details if product tracks batches
        if product.track_batches:
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('expiry_date', 'received_date')

            for batch in batches:
                result['batches'].append({
                    'batch_number': batch.batch_number,
                    'expiry_date': batch.expiry_date,
                    'remaining_qty': batch.remaining_qty,
                    'cost_price': batch.cost_price,
                    'is_expired': batch.is_expired,
                    'days_until_expiry': batch.days_until_expiry,
                    'is_unknown_batch': batch.is_unknown_batch
                })

        return result

    @staticmethod
    def get_location_inventory(location: InventoryLocation, include_zero_stock: bool = False) -> List[Dict]:
        """
        Get all inventory for a location
        """
        queryset = location.inventory_items.select_related('product')

        if not include_zero_stock:
            queryset = queryset.filter(current_qty__gt=0)

        inventory = []
        for item in queryset:
            inventory.append({
                'product_code': item.product.code,
                'product_name': item.product.name,
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'total_value': item.current_qty * item.avg_cost,
                'needs_reorder': item.needs_reorder,
                'is_overstocked': item.is_overstocked,
                'last_movement': item.last_movement_date
            })

        return inventory

    @staticmethod
    def get_low_stock_items(location: InventoryLocation = None, threshold: Decimal = None) -> List[Dict]:
        """
        Get items with low stock across all or specific location
        """
        queryset = InventoryItem.objects.select_related('product', 'location')

        if location:
            queryset = queryset.filter(location=location)

        if threshold:
            queryset = queryset.filter(
                current_qty__lte=threshold,
                current_qty__gt=0
            )
        else:
            # Use individual min_stock_level
            queryset = queryset.filter(
                current_qty__lte=F('min_stock_level'),
                current_qty__gt=0
            )

        low_stock = []
        for item in queryset:
            low_stock.append({
                'location_code': item.location.code,
                'location_name': item.location.name,
                'product_code': item.product.code,
                'product_name': item.product.name,
                'current_qty': item.current_qty,
                'min_stock_level': item.min_stock_level,
                'shortage': item.min_stock_level - item.current_qty,
                'avg_cost': item.avg_cost,
                'last_movement': item.last_movement_date
            })

        return low_stock

    @staticmethod
    def get_expiring_batches(location: InventoryLocation = None, days_ahead: int = 30) -> List[Dict]:
        """
        Get batches expiring within specified days
        """
        from datetime import timedelta

        queryset = InventoryBatch.objects.filter(
            remaining_qty__gt=0,
            expiry_date__isnull=False
        ).select_related('product', 'location')

        if location:
            queryset = queryset.filter(location=location)

        # Expiring within days_ahead
        cutoff_date = timezone.now().date() + timedelta(days=days_ahead)
        queryset = queryset.filter(
            expiry_date__lte=cutoff_date
        ).order_by('expiry_date')

        expiring = []
        for batch in queryset:
            expiring.append({
                'location_code': batch.location.code,
                'product_code': batch.product.code,
                'product_name': batch.product.name,
                'batch_number': batch.batch_number,
                'expiry_date': batch.expiry_date,
                'remaining_qty': batch.remaining_qty,
                'days_until_expiry': batch.days_until_expiry,
                'is_expired': batch.is_expired,
                'cost_price': batch.cost_price,
                'total_value': batch.remaining_qty * batch.cost_price
            })

        return expiring

    @staticmethod
    def reserve_stock(location: InventoryLocation, product, quantity: Decimal, reason: str = "") -> Dict:
        """
        Reserve stock for orders/sales
        """
        try:
            item = InventoryItem.objects.get(location=location, product=product)

            if item.available_qty < quantity:
                return {
                    'success': False,
                    'error': 'Insufficient available stock',
                    'available': item.available_qty,
                    'requested': quantity
                }

            # Reserve the stock
            item.reserved_qty += quantity
            item.save(update_fields=['reserved_qty'])

            return {
                'success': True,
                'reserved_qty': quantity,
                'new_available_qty': item.available_qty,
                'total_reserved': item.reserved_qty
            }

        except InventoryItem.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found in location'
            }

    @staticmethod
    def unreserve_stock(location: InventoryLocation, product, quantity: Decimal) -> Dict:
        """
        Release reserved stock
        """
        try:
            item = InventoryItem.objects.get(location=location, product=product)

            if item.reserved_qty < quantity:
                return {
                    'success': False,
                    'error': 'Cannot unreserve more than reserved',
                    'reserved': item.reserved_qty,
                    'requested': quantity
                }

            # Unreserve the stock
            item.reserved_qty -= quantity
            item.save(update_fields=['reserved_qty'])

            return {
                'success': True,
                'unreserved_qty': quantity,
                'new_available_qty': item.available_qty,
                'total_reserved': item.reserved_qty
            }

        except InventoryItem.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found in location'
            }

    @staticmethod
    def get_inventory_valuation(location: InventoryLocation = None) -> Dict:
        """
        Calculate inventory valuation
        """
        queryset = InventoryItem.objects.filter(current_qty__gt=0)

        if location:
            queryset = queryset.filter(location=location)

        # Aggregate calculations
        totals = queryset.aggregate(
            total_products=Count('id'),
            total_quantity=Sum('current_qty'),
            total_value=Sum(F('current_qty') * F('avg_cost')),
            total_reserved=Sum('reserved_qty')
        )

        # Calculate by location if not filtered
        by_location = []
        if not location:
            location_totals = queryset.values(
                'location__code', 'location__name'
            ).annotate(
                products=Count('id'),
                quantity=Sum('current_qty'),
                value=Sum(F('current_qty') * F('avg_cost')),
                reserved=Sum('reserved_qty')
            ).order_by('-value')

            by_location = list(location_totals)

        return {
            'total_products': totals['total_products'] or 0,
            'total_quantity': totals['total_quantity'] or Decimal('0'),
            'total_value': totals['total_value'] or Decimal('0'),
            'total_reserved': totals['total_reserved'] or Decimal('0'),
            'by_location': by_location
        }

    @staticmethod
    def validate_stock_operation(location: InventoryLocation, product, quantity: Decimal,
                                 operation_type: str) -> Tuple[bool, str]:
        """
        Validate if stock operation can be performed
        """
        if quantity <= 0:
            return False, "Quantity must be positive"

        if operation_type == 'OUT':
            availability = InventoryService.check_availability(location, product, quantity)

            if not availability['can_fulfill']:
                return False, f"Insufficient stock. Available: {availability['available_qty']}, Required: {quantity}"

        # Additional validations can be added here
        return True, "OK"

    @staticmethod
    def get_product_locations(product) -> List[Dict]:
        """
        Get all locations where product is available
        """
        items = InventoryItem.objects.filter(
            product=product,
            current_qty__gt=0
        ).select_related('location').order_by('-current_qty')

        locations = []
        for item in items:
            locations.append({
                'location_code': item.location.code,
                'location_name': item.location.name,
                'location_type': item.location.location_type,
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'last_movement': item.last_movement_date
            })

        return locations