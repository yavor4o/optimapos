# inventory/services/inventory_service.py

from django.db.models import Sum, Count, F, Q, Avg, Max, Min
from django.utils import timezone
from django.db import transaction
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import date, timedelta

from ..models import InventoryLocation, InventoryItem, InventoryBatch, InventoryMovement


class InventoryService:
    """
    Enhanced InventoryService - designed to work with new MovementService

    INTEGRATIONS:
    - Provides data for MovementService validation
    - Supports MovementService FIFO operations
    - Complements MovementService with analytics
    - Thread-safe operations matching MovementService patterns
    """

    # =====================================================
    # CORE METHODS FOR MovementService INTEGRATION
    # =====================================================

    @staticmethod
    def check_availability(location: InventoryLocation, product, required_qty: Decimal) -> Dict:
        """
        Primary availability check used by MovementService.create_outgoing_movement()

        USED BY:
        - MovementService validation
        - ProductValidationService.can_sell_product()
        - POS real-time stock checks
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
                'avg_cost': item.avg_cost,
                # MovementService integration data:
                'last_purchase_cost': item.last_purchase_cost,
                'last_sale_price': item.last_sale_price,
                'last_movement_date': item.last_movement_date,
                'allow_negative_stock': location.allow_negative_stock
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
                'avg_cost': Decimal('0'),
                'last_purchase_cost': None,
                'last_sale_price': None,
                'last_movement_date': None,
                'allow_negative_stock': location.allow_negative_stock
            }

    @staticmethod
    def check_batch_availability(location: InventoryLocation, product, required_qty: Decimal) -> Dict:
        """
        Batch availability check for MovementService FIFO operations

        USED BY:
        - MovementService._create_fifo_outgoing_movements()
        - Batch product validation
        - FIFO cost calculation
        """
        if not location.should_track_batches(product):
            return InventoryService.check_availability(location, product, required_qty)

        try:
            # Get available batches in FIFO order (same as MovementService)
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('expiry_date', 'received_date', 'batch_number')

            total_available = sum(batch.remaining_qty for batch in batches)
            can_fulfill = total_available >= required_qty or location.allow_negative_stock

            batch_details = []
            cumulative_qty = Decimal('0')

            for batch in batches:
                cumulative_qty += batch.remaining_qty
                batch_details.append({
                    'batch_number': batch.batch_number,
                    'remaining_qty': batch.remaining_qty,
                    'cost_price': batch.cost_price,
                    'expiry_date': batch.expiry_date,
                    'is_expired': batch.is_expired,
                    'can_fulfill_from_this': cumulative_qty >= required_qty
                })

            return {
                'available': total_available > 0,
                'total_available_qty': total_available,
                'can_fulfill': can_fulfill,
                'shortage': max(Decimal('0'), required_qty - total_available) if not can_fulfill else Decimal('0'),
                'batches_needed': len([b for b in batch_details if not b['can_fulfill_from_this']]) + (
                    1 if batch_details else 0),
                'batch_details': batch_details,
                'fifo_cost': batch_details[0]['cost_price'] if batch_details else Decimal('0')
            }

        except Exception as e:
            return {
                'available': False,
                'error': str(e),
                'can_fulfill': location.allow_negative_stock
            }

    @staticmethod
    def get_smart_cost_for_operation(location: InventoryLocation, product, operation_type: str = 'OUT',
                                     batch_number: Optional[str] = None) -> Decimal:
        """
        Smart cost calculation matching MovementService._get_smart_cost_price()

        USED BY:
        - Cost preview before creating movements
        - UI cost estimation
        - Profit calculation preview
        """
        # Match MovementService priority order exactly:

        # 1. Batch-specific cost
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

        # 2. InventoryItem average cost
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            if item.avg_cost > 0:
                return item.avg_cost
        except InventoryItem.DoesNotExist:
            pass

        # 3. Fallback
        return Decimal('0.00')

    # =====================================================
    # STOCK MANAGEMENT & RESERVATIONS
    # =====================================================

    @staticmethod
    @transaction.atomic
    def reserve_stock(location: InventoryLocation, product, quantity: Decimal,
                      reason: str = '', reserved_by=None) -> Dict:
        """
        Thread-safe stock reservation
        Uses same patterns as MovementService for consistency
        """
        try:
            item = InventoryItem.objects.select_for_update().get(
                location=location,
                product=product
            )

            if item.available_qty >= quantity:
                item.reserved_qty += quantity
                item.save(update_fields=['reserved_qty'])

                return {
                    'success': True,
                    'reserved_qty': quantity,
                    'total_reserved': item.reserved_qty,
                    'remaining_available': item.available_qty - quantity,
                    'message': f'Reserved {quantity} units'
                }
            else:
                return {
                    'success': False,
                    'error': 'Insufficient available stock',
                    'available_qty': item.available_qty,
                    'requested_qty': quantity,
                    'shortage': quantity - item.available_qty
                }

        except InventoryItem.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found in location'
            }

    @staticmethod
    @transaction.atomic
    def release_reservation(location: InventoryLocation, product, quantity: Decimal,
                            reason: str = '', released_by=None) -> Dict:
        """
        Thread-safe reservation release
        """
        try:
            item = InventoryItem.objects.select_for_update().get(
                location=location,
                product=product
            )

            if item.reserved_qty >= quantity:
                item.reserved_qty -= quantity
                item.save(update_fields=['reserved_qty'])

                return {
                    'success': True,
                    'released_qty': quantity,
                    'total_reserved': item.reserved_qty,
                    'new_available': item.available_qty + quantity,
                    'message': f'Released {quantity} units'
                }
            else:
                return {
                    'success': False,
                    'error': 'Insufficient reserved stock',
                    'reserved_qty': item.reserved_qty,
                    'requested_qty': quantity
                }

        except InventoryItem.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found in location'
            }

    # =====================================================
    # VALIDATION HELPERS FOR MovementService
    # =====================================================

    @staticmethod
    def validate_stock_operation(location: InventoryLocation, product, quantity: Decimal,
                                 operation_type: str) -> Tuple[bool, str, Dict]:
        """
        Enhanced validation used by MovementService and ProductValidationService
        """
        if quantity <= 0:
            return False, "Quantity must be positive", {}

        if operation_type == 'OUT':
            availability = InventoryService.check_availability(location, product, quantity)

            if not availability['can_fulfill']:
                return False, (
                    f"Insufficient stock. Available: {availability['available_qty']}, "
                    f"Required: {quantity}, Shortage: {availability['shortage']}"
                ), availability

            return True, "OK", availability

        elif operation_type == 'IN':
            # Basic validation for incoming stock
            return True, "OK", {}

        elif operation_type == 'TRANSFER':
            # Validate source location has stock
            availability = InventoryService.check_availability(location, product, quantity)

            if not availability['can_fulfill']:
                return False, (
                    f"Insufficient stock for transfer. Available: {availability['available_qty']}, "
                    f"Required: {quantity}"
                ), availability

            return True, "OK", availability

        else:
            return False, f"Unknown operation type: {operation_type}", {}

    # =====================================================
    # REPORTING & ANALYTICS
    # =====================================================

    @staticmethod
    def get_stock_summary(location: InventoryLocation, product) -> Dict:
        """
        Comprehensive stock summary for management reporting
        """
        # Get base availability data
        availability = InventoryService.check_availability(location, product, Decimal('0'))

        result = {
            'location': location.code,
            'location_name': location.name,
            'product_code': product.code,
            'product_name': product.name,
            'product_track_batches': product.track_batches,
            'current_qty': availability['current_qty'],
            'available_qty': availability['available_qty'],
            'reserved_qty': availability['reserved_qty'],
            'avg_cost': availability['avg_cost'],
            'last_purchase_cost': availability['last_purchase_cost'],
            'last_sale_price': availability['last_sale_price'],
            'last_movement_date': availability['last_movement_date'],
            'stock_value': availability['current_qty'] * availability['avg_cost'],
            'batches': [],
            'movement_summary': {}
        }

        # Add batch details if applicable
        if product.track_batches and location.should_track_batches(product):
            batch_availability = InventoryService.check_batch_availability(location, product, Decimal('0'))

            for batch_detail in batch_availability.get('batch_details', []):
                batch = {
                    'batch_number': batch_detail['batch_number'],
                    'expiry_date': batch_detail['expiry_date'],
                    'remaining_qty': batch_detail['remaining_qty'],
                    'cost_price': batch_detail['cost_price'],
                    'is_expired': batch_detail['is_expired'],
                    'batch_value': batch_detail['remaining_qty'] * batch_detail['cost_price']
                }
                result['batches'].append(batch)

        # Add movement summary (last 30 days)
        try:
            recent_movements = InventoryMovement.objects.filter(
                location=location,
                product=product,
                movement_date__gte=timezone.now().date() - timedelta(days=30)
            ).aggregate(
                total_in=Sum('quantity', filter=Q(movement_type='IN')),
                total_out=Sum('quantity', filter=Q(movement_type='OUT')),
                movement_count=Count('id'),
                last_movement=Max('movement_date'),
                # Profit tracking from new MovementService
                total_revenue=Sum(F('quantity') * F('sale_price'),
                                  filter=Q(movement_type='OUT', sale_price__isnull=False)),
                total_profit=Sum(F('quantity') * F('profit_amount'),
                                 filter=Q(movement_type='OUT', profit_amount__isnull=False))
            )

            result['movement_summary'] = {
                'last_30_days_in': recent_movements['total_in'] or Decimal('0'),
                'last_30_days_out': recent_movements['total_out'] or Decimal('0'),
                'movement_count': recent_movements['movement_count'] or 0,
                'last_movement_date': recent_movements['last_movement'],
                'total_revenue': recent_movements['total_revenue'] or Decimal('0'),
                'total_profit': recent_movements['total_profit'] or Decimal('0')
            }

        except Exception:
            result['movement_summary'] = {
                'last_30_days_in': Decimal('0'),
                'last_30_days_out': Decimal('0'),
                'movement_count': 0,
                'last_movement_date': None,
                'total_revenue': Decimal('0'),
                'total_profit': Decimal('0')
            }

        return result

    @staticmethod
    def get_location_inventory(location: InventoryLocation, include_zero_stock: bool = False,
                               product_filter: Optional[str] = None) -> List[Dict]:
        """
        Location inventory with profit tracking integration
        """
        queryset = location.inventory_items.select_related('product', 'product__brand')

        if not include_zero_stock:
            queryset = queryset.filter(current_qty__gt=0)

        if product_filter:
            queryset = queryset.filter(
                Q(product__code__icontains=product_filter) |
                Q(product__name__icontains=product_filter) |
                Q(product__brand__name__icontains=product_filter)
            )

        inventory = []
        for item in queryset:
            inventory.append({
                'product_code': item.product.code,
                'product_name': item.product.name,
                'product_brand': item.product.brand.name if item.product.brand else '',
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'last_purchase_cost': item.last_purchase_cost,
                'last_sale_price': item.last_sale_price,
                'total_value': item.current_qty * item.avg_cost,
                'needs_reorder': item.needs_reorder,
                'is_overstocked': item.is_overstocked,
                'last_movement': item.last_movement_date,
                'track_batches': item.product.track_batches,
                # Potential profit if sold at last price
                'potential_profit': (
                    (item.last_sale_price - item.avg_cost) * item.current_qty
                    if item.last_sale_price and item.avg_cost else Decimal('0')
                )
            })

        return sorted(inventory, key=lambda x: x['total_value'], reverse=True)

    @staticmethod
    def get_inventory_valuation(location: InventoryLocation = None) -> Dict:
        """
        Enhanced inventory valuation with profit potential
        """
        queryset = InventoryItem.objects.filter(current_qty__gt=0)

        if location:
            queryset = queryset.filter(location=location)

        # Core valuation
        totals = queryset.aggregate(
            total_products=Count('id'),
            total_quantity=Sum('current_qty'),
            total_value=Sum(F('current_qty') * F('avg_cost')),
            total_reserved=Sum('reserved_qty'),
            avg_cost_per_unit=Avg('avg_cost'),
            max_single_item_value=Max(F('current_qty') * F('avg_cost'))
        )

        # Profit potential calculation
        profit_potential = queryset.filter(
            last_sale_price__isnull=False,
            avg_cost__gt=0
        ).aggregate(
            potential_revenue=Sum(F('current_qty') * F('last_sale_price')),
            potential_profit=Sum(F('current_qty') * (F('last_sale_price') - F('avg_cost')))
        )

        # Recent profit tracking from MovementService data
        recent_profit = InventoryMovement.objects.filter(
            movement_type='OUT',
            sale_price__isnull=False,
            movement_date__gte=timezone.now().date() - timedelta(days=30)
        )

        if location:
            recent_profit = recent_profit.filter(location=location)

        profit_stats = recent_profit.aggregate(
            recent_revenue=Sum(F('quantity') * F('sale_price')),
            recent_profit=Sum(F('quantity') * F('profit_amount')),
            recent_sales_count=Count('id')
        )

        return {
            'total_products': totals['total_products'] or 0,
            'total_quantity': totals['total_quantity'] or Decimal('0'),
            'total_value': totals['total_value'] or Decimal('0'),
            'total_reserved': totals['total_reserved'] or Decimal('0'),
            'avg_cost_per_unit': totals['avg_cost_per_unit'] or Decimal('0'),
            'max_single_item_value': totals['max_single_item_value'] or Decimal('0'),
            'profit_potential': {
                'potential_revenue': profit_potential['potential_revenue'] or Decimal('0'),
                'potential_profit': profit_potential['potential_profit'] or Decimal('0'),
                'potential_margin': (
                    profit_potential['potential_profit'] / profit_potential['potential_revenue'] * 100
                    if profit_potential['potential_revenue'] else Decimal('0')
                )
            },
            'recent_performance': {
                'revenue_last_30_days': profit_stats['recent_revenue'] or Decimal('0'),
                'profit_last_30_days': profit_stats['recent_profit'] or Decimal('0'),
                'sales_count_last_30_days': profit_stats['recent_sales_count'] or 0,
                'avg_profit_per_sale': (
                    profit_stats['recent_profit'] / profit_stats['recent_sales_count']
                    if profit_stats['recent_sales_count'] else Decimal('0')
                )
            },
            'generated_at': timezone.now()
        }

    # =====================================================
    # BUSINESS INTELLIGENCE
    # =====================================================

    @staticmethod
    def get_low_stock_items(location: InventoryLocation = None,
                            threshold: Decimal = None) -> List[Dict]:
        """
        Low stock analysis with actionable recommendations
        """
        queryset = InventoryItem.objects.filter(current_qty__gt=0).select_related('product', 'location')

        if location:
            queryset = queryset.filter(location=location)

        low_stock_items = []

        for item in queryset:
            needs_reorder = item.needs_reorder

            if threshold is not None:
                needs_reorder = needs_reorder or item.current_qty <= threshold

            if needs_reorder:
                suggested_qty = max(
                    item.max_stock_level - item.current_qty,
                    item.min_stock_level * 2
                ) if item.max_stock_level > 0 else item.min_stock_level * 2

                low_stock_items.append({
                    'product_code': item.product.code,
                    'product_name': item.product.name,
                    'location_code': item.location.code,
                    'current_qty': item.current_qty,
                    'min_stock_level': item.min_stock_level,
                    'max_stock_level': item.max_stock_level,
                    'available_qty': item.available_qty,
                    'reserved_qty': item.reserved_qty,
                    'last_purchase_cost': item.last_purchase_cost,
                    'suggested_order_qty': suggested_qty,
                    'urgency_level': (
                        'CRITICAL' if item.current_qty == 0
                        else 'HIGH' if item.current_qty <= item.min_stock_level * 0.5
                        else 'MEDIUM'
                    ),
                    'estimated_order_value': suggested_qty * (item.last_purchase_cost or item.avg_cost)
                })

        return sorted(low_stock_items, key=lambda x: (x['urgency_level'], x['current_qty']))

    @staticmethod
    def get_profit_analysis(location: InventoryLocation = None, days: int = 30) -> Dict:
        """
        Profit analysis using MovementService profit tracking data
        """
        cutoff_date = timezone.now().date() - timedelta(days=days)

        queryset = InventoryMovement.objects.filter(
            movement_type='OUT',
            sale_price__isnull=False,
            movement_date__gte=cutoff_date
        )

        if location:
            queryset = queryset.filter(location=location)

        # Overall profit metrics
        profit_stats = queryset.aggregate(
            total_sales=Count('id'),
            total_quantity_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('sale_price')),
            total_cost=Sum(F('quantity') * F('cost_price')),
            total_profit=Sum(F('quantity') * F('profit_amount')),
            avg_profit_per_sale=Avg(F('quantity') * F('profit_amount')),
            avg_margin=Avg(F('profit_amount') / F('sale_price') * 100)
        )

        # Top performing products
        top_products = queryset.values(
            'product__code', 'product__name'
        ).annotate(
            product_revenue=Sum(F('quantity') * F('sale_price')),
            product_profit=Sum(F('quantity') * F('profit_amount')),
            sales_count=Count('id'),
            avg_margin=Avg(F('profit_amount') / F('sale_price') * 100)
        ).order_by('-product_profit')[:10]

        # Daily trend
        daily_trends = queryset.values('movement_date').annotate(
            daily_revenue=Sum(F('quantity') * F('sale_price')),
            daily_profit=Sum(F('quantity') * F('profit_amount')),
            daily_sales=Count('id')
        ).order_by('movement_date')

        return {
            'period_days': days,
            'overall_metrics': {
                'total_sales': profit_stats['total_sales'] or 0,
                'total_quantity_sold': profit_stats['total_quantity_sold'] or Decimal('0'),
                'total_revenue': profit_stats['total_revenue'] or Decimal('0'),
                'total_cost': profit_stats['total_cost'] or Decimal('0'),
                'total_profit': profit_stats['total_profit'] or Decimal('0'),
                'profit_margin_percentage': (
                    profit_stats['total_profit'] / profit_stats['total_revenue'] * 100
                    if profit_stats['total_revenue'] else Decimal('0')
                ),
                'avg_profit_per_sale': profit_stats['avg_profit_per_sale'] or Decimal('0')
            },
            'top_products': list(top_products),
            'daily_trends': list(daily_trends),
            'generated_at': timezone.now()
        }

    @staticmethod
    def get_product_locations(product, include_zero_stock: bool = False) -> List[Dict]:
        """
        Enhanced product location lookup with profit potential
        """
        queryset = InventoryItem.objects.filter(product=product).select_related('location')

        if not include_zero_stock:
            queryset = queryset.filter(current_qty__gt=0)

        locations = []
        for item in queryset:
            # Calculate potential profit at this location
            potential_profit = Decimal('0')
            if item.last_sale_price and item.avg_cost:
                potential_profit = (item.last_sale_price - item.avg_cost) * item.current_qty

            locations.append({
                'location_code': item.location.code,
                'location_name': item.location.name,
                'location_type': item.location.location_type,
                'current_qty': item.current_qty,
                'available_qty': item.available_qty,
                'reserved_qty': item.reserved_qty,
                'avg_cost': item.avg_cost,
                'last_purchase_cost': item.last_purchase_cost,
                'last_sale_price': item.last_sale_price,
                'stock_value': item.current_qty * item.avg_cost,
                'potential_profit': potential_profit,
                'needs_reorder': item.needs_reorder,
                'is_overstocked': item.is_overstocked,
                'allow_negative_stock': item.location.allow_negative_stock
            })

        return sorted(locations, key=lambda x: x['current_qty'], reverse=True)