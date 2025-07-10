from django.db.models import Q, Sum, F, Count
from django.utils import timezone
from typing import List, Optional, Dict
from decimal import Decimal

from ..models import Product, ProductPLU, ProductBarcode


class ProductService:
    """Service layer for product operations - ALL business logic here"""

    def find_by_plu(plu_code: str) -> List[Product]:
        """Find products by PLU code"""
        products = Product.objects.filter(
            plu_codes__plu_code=plu_code,  # САМО от ProductPLU
            is_active=True
        ).distinct().select_related('brand', 'product_group')

        return list(products)

    @staticmethod
    def find_by_barcode(barcode: str) -> Optional[Product]:
        """Find product by barcode"""
        try:
            barcode_obj = ProductBarcode.objects.select_related('product').get(
                barcode=barcode,
                is_active=True,
                product__is_active=True
            )
            return barcode_obj.product
        except ProductBarcode.DoesNotExist:
            return None

    @staticmethod
    def parse_weight_barcode(barcode: str) -> Optional[Dict]:
        """Parse weight-based barcode (28xxx format)"""
        if not barcode.startswith('28') or len(barcode) != 13:
            return None

        try:
            plu_code = barcode[2:7]
            weight_code = barcode[7:12]
            weight = float(weight_code) / 1000  # Convert to kg

            # Find products with this PLU
            products = ProductService.find_by_plu(plu_code)

            return {
                'plu_code': plu_code,
                'weight': weight,
                'barcode': barcode,
                'products': products
            }
        except (ValueError, IndexError):
            return None

    @staticmethod
    def update_moving_average_cost(product: Product, new_qty: Decimal, new_cost: Decimal):
        """Update product's moving average cost after purchase"""
        if new_qty <= 0:
            return

        old_total_value = product.current_stock_qty * product.current_avg_cost
        new_total_value = new_qty * new_cost
        new_total_qty = product.current_stock_qty + new_qty

        if new_total_qty > 0:
            new_avg_cost = (old_total_value + new_total_value) / new_total_qty
        else:
            new_avg_cost = new_cost

        # Update fields
        product.current_avg_cost = new_avg_cost
        product.current_stock_qty = new_total_qty
        product.last_purchase_cost = new_cost
        product.last_purchase_date = timezone.now().date()

        product.save(update_fields=[
            'current_avg_cost', 'current_stock_qty',
            'last_purchase_cost', 'last_purchase_date'
        ])

    @staticmethod
    def reduce_stock(product: Product, quantity: Decimal):
        """Reduce stock quantity after sale"""
        if quantity <= 0:
            return

        product.current_stock_qty = max(Decimal('0'), product.current_stock_qty - quantity)
        product.save(update_fields=['current_stock_qty'])

    @staticmethod
    def process_sale(product: Product, quantity: Decimal) -> Dict:
        """Process product sale - return cost information"""
        unit_cost = product.current_avg_cost
        total_cost = unit_cost * quantity

        # Update stock
        ProductService.reduce_stock(product, quantity)

        return {
            'unit_cost': unit_cost,
            'total_cost': total_cost,
            'remaining_stock': product.current_stock_qty
        }

    @staticmethod
    def calculate_profit_margin(cost: Decimal, sell_price: Decimal) -> Decimal:
        """Calculate profit margin percentage"""
        if cost <= 0 or sell_price <= 0:
            return Decimal('0.00')

        profit = sell_price - cost
        margin = (profit / sell_price) * 100
        return round(margin, 2)

    @staticmethod
    def calculate_markup_percentage(cost: Decimal, sell_price: Decimal) -> Decimal:
        """Calculate markup percentage"""
        if cost <= 0:
            return Decimal('0.00')

        markup = ((sell_price - cost) / cost) * 100
        return round(markup, 2)

    @staticmethod
    def get_products_needing_reorder(min_stock_threshold: Decimal = Decimal('0')) -> List[Product]:
        """Get products with low stock"""
        return list(Product.objects.filter(
            current_stock_qty__lte=min_stock_threshold,
            is_active=True
        ).select_related('brand', 'product_group'))

    @staticmethod
    def get_inventory_value_summary() -> Dict:
        """Calculate total inventory value"""
        result = Product.objects.filter(is_active=True).aggregate(
            total_value=Sum(F('current_stock_qty') * F('current_avg_cost')),
            total_products=Count('id'),
            total_quantity=Sum('current_stock_qty')
        )

        return {
            'total_value': result['total_value'] or Decimal('0'),
            'total_products': result['total_products'] or 0,
            'total_quantity': result['total_quantity'] or Decimal('0')
        }

    @staticmethod
    def get_product_profit_analysis(product: Product, sell_price: Decimal) -> Dict:
        """Get comprehensive profit analysis for product"""
        cost = product.current_avg_cost

        return {
            'product_code': product.code,
            'product_name': product.name,
            'current_cost': cost,
            'sell_price': sell_price,
            'profit_per_unit': sell_price - cost,
            'margin_percentage': ProductService.calculate_profit_margin(cost, sell_price),
            'markup_percentage': ProductService.calculate_markup_percentage(cost, sell_price),
            'current_stock': product.current_stock_qty,
            'potential_profit': (sell_price - cost) * product.current_stock_qty
        }