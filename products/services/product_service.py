# products/services/product_service.py - COMPLETE VERSION

from django.db.models import Q, Sum, F, Count, Avg
from django.utils import timezone
from typing import List, Optional, Dict, Tuple
from decimal import Decimal

from ..models import Product, ProductPLU, ProductBarcode, ProductPackaging


class ProductService:
    """Complete service layer for product operations"""

    # ===== EXISTING METHODS (already implemented) =====

    @staticmethod
    def find_by_plu(plu_code: str) -> List[Product]:
        """Find products by PLU code"""
        products = Product.objects.filter(
            plu_codes__plu_code=plu_code,
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

    # ===== MISSING METHODS - NEED TO ADD =====

    @staticmethod
    def search_products(query: str, limit: int = 50) -> List[Product]:
        """Universal product search - by code, name, barcode, or PLU"""
        if not query or len(query.strip()) < 2:
            return []

        query = query.strip()

        # Search strategy based on query pattern
        products = Product.objects.filter(is_active=True)

        if query.isdigit():
            # Numeric - could be PLU, barcode, or code
            products = products.filter(
                Q(code__icontains=query) |
                Q(plu_codes__plu_code=query) |
                Q(barcodes__barcode=query)
            )
        else:
            # Text - search in name and code
            products = products.filter(
                Q(code__icontains=query) |
                Q(name__icontains=query)
            )

        return products.select_related('brand', 'product_group').distinct()[:limit]

    @staticmethod
    def get_product_by_identifier(identifier: str) -> Optional[Product]:
        """Find product by any identifier - code, barcode, or PLU"""

        # Try exact code match first
        try:
            return Product.objects.get(code=identifier, is_active=True)
        except Product.DoesNotExist:
            pass

        # Try barcode
        product = ProductService.find_by_barcode(identifier)
        if product:
            return product

        # Try PLU
        products = ProductService.find_by_plu(identifier)
        if products:
            return products[0]  # Return first match

        return None

    @staticmethod
    def update_moving_average_cost(product: Product, new_qty: Decimal, new_cost: Decimal) -> Dict:
        """Update product's moving average cost and return calculation details"""
        if new_qty <= 0:
            return {'error': 'Quantity must be positive'}

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

        return {
            'old_avg_cost': old_cost,
            'new_avg_cost': new_avg_cost,
            'old_total_value': old_total_value,
            'new_total_value': old_total_value + new_total_value,
            'quantity_added': new_qty,
            'new_total_qty': new_total_qty
        }

    @staticmethod
    def reduce_stock(product: Product, quantity: Decimal) -> Dict:
        """Reduce stock and return operation details"""
        if quantity <= 0:
            return {'error': 'Quantity must be positive'}

        if product.current_stock_qty < quantity:
            return {
                'error': 'Insufficient stock',
                'available': product.current_stock_qty,
                'requested': quantity
            }

        old_qty = product.current_stock_qty
        new_qty = old_qty - quantity

        product.current_stock_qty = new_qty
        product.save(update_fields=['current_stock_qty'])

        return {
            'success': True,
            'old_qty': old_qty,
            'new_qty': new_qty,
            'reduced_by': quantity
        }

    @staticmethod
    def get_conversion_factor(product: Product, from_unit, to_unit) -> Optional[Decimal]:
        """Get conversion factor between units for a product"""

        if from_unit == to_unit:
            return Decimal('1.0')

        # If one of them is base unit, find the other packaging
        if from_unit == product.base_unit:
            try:
                packaging = ProductPackaging.objects.get(
                    product=product, unit=to_unit, is_active=True
                )
                return packaging.conversion_factor
            except ProductPackaging.DoesNotExist:
                return None

        elif to_unit == product.base_unit:
            try:
                packaging = ProductPackaging.objects.get(
                    product=product, unit=from_unit, is_active=True
                )
                return Decimal('1.0') / packaging.conversion_factor
            except ProductPackaging.DoesNotExist:
                return None

        # Both are non-base units - convert through base unit
        try:
            from_packaging = ProductPackaging.objects.get(
                product=product, unit=from_unit, is_active=True
            )
            to_packaging = ProductPackaging.objects.get(
                product=product, unit=to_unit, is_active=True
            )

            # Convert to base, then to target unit
            return from_packaging.conversion_factor / to_packaging.conversion_factor

        except ProductPackaging.DoesNotExist:
            return None

    @staticmethod
    def convert_quantity(product: Product, quantity: Decimal, from_unit, to_unit) -> Optional[Decimal]:
        """Convert quantity between units"""
        conversion_factor = ProductService.get_conversion_factor(product, from_unit, to_unit)

        if conversion_factor is None:
            return None

        return quantity * conversion_factor

    @staticmethod
    def get_default_sale_unit(product: Product):
        """Get default sale unit for product"""
        try:
            return ProductPackaging.objects.get(
                product=product,
                is_default_sale_unit=True,
                is_active=True
            ).unit
        except ProductPackaging.DoesNotExist:
            return product.base_unit

    @staticmethod
    def get_default_purchase_unit(product: Product):
        """Get default purchase unit for product"""
        try:
            return ProductPackaging.objects.get(
                product=product,
                is_default_purchase_unit=True,
                is_active=True
            ).unit
        except ProductPackaging.DoesNotExist:
            return product.base_unit

    @staticmethod
    def get_available_units(product: Product) -> List[Dict]:
        """Get all available units for a product with conversion info"""
        units = []

        # Base unit
        units.append({
            'unit': product.base_unit,
            'conversion_factor': Decimal('1.0'),
            'is_base': True,
            'is_default_sale': False,
            'is_default_purchase': False
        })

        # Packaging units
        for packaging in product.packagings.filter(is_active=True):
            units.append({
                'unit': packaging.unit,
                'conversion_factor': packaging.conversion_factor,
                'is_base': False,
                'is_default_sale': packaging.is_default_sale_unit,
                'is_default_purchase': packaging.is_default_purchase_unit
            })

        return units

    @staticmethod
    def validate_product_data(product_data: Dict) -> Tuple[bool, List[str]]:
        """Validate product data before creation/update"""
        errors = []

        # Required fields
        if not product_data.get('code'):
            errors.append('Product code is required')
        elif len(product_data['code']) < 3:
            errors.append('Product code must be at least 3 characters')

        if not product_data.get('name'):
            errors.append('Product name is required')
        elif len(product_data['name']) < 2:
            errors.append('Product name must be at least 2 characters')

        # Unit type validation
        if product_data.get('unit_type') == Product.WEIGHT and not product_data.get('plu_codes'):
            errors.append('Weight-based products should have at least one PLU code')

        # Cost validation
        if product_data.get('current_avg_cost', 0) < 0:
            errors.append('Average cost cannot be negative')

        if product_data.get('current_stock_qty', 0) < 0:
            errors.append('Stock quantity cannot be negative')

        return len(errors) == 0, errors

    @staticmethod
    def get_low_stock_products(threshold: Decimal = Decimal('10')) -> List[Product]:
        """Get products with stock below threshold"""
        return list(Product.objects.filter(
            current_stock_qty__lte=threshold,
            is_active=True
        ).select_related('brand', 'product_group').order_by('current_stock_qty'))

    @staticmethod
    def get_inventory_value_by_group() -> Dict:
        """Get inventory value grouped by product group"""
        from django.db.models import Sum, F

        groups = Product.objects.filter(
            is_active=True,
            current_stock_qty__gt=0
        ).values(
            'product_group__name'
        ).annotate(
            total_value=Sum(F('current_stock_qty') * F('current_avg_cost')),
            product_count=Count('id'),
            total_quantity=Sum('current_stock_qty')
        ).order_by('-total_value')

        return {
            'groups': list(groups),
            'total_value': sum(group['total_value'] or 0 for group in groups)
        }

    @staticmethod
    def generate_product_code(name: str, product_group=None) -> str:
        """Generate unique product code from name"""
        # Take first 6 chars from name, uppercase, alphanumeric only
        base_code = ''.join(c for c in name.upper() if c.isalnum())[:6]

        if len(base_code) < 3:
            base_code = f"PROD{base_code}"

        # Add group prefix if available
        if product_group and product_group.code:
            base_code = f"{product_group.code[:2]}{base_code}"

        # Ensure uniqueness
        counter = 1
        code = base_code
        while Product.objects.filter(code=code).exists():
            code = f"{base_code}{counter:02d}"
            counter += 1

        return code[:20]  # Respect field max_length

    @staticmethod
    def duplicate_product(original_product: Product, new_code: str, new_name: str) -> Product:
        """Create a copy of existing product with new code and name"""

        # Create new product
        new_product = Product.objects.create(
            code=new_code,
            name=new_name,
            brand=original_product.brand,
            product_group=original_product.product_group,
            product_type=original_product.product_type,
            base_unit=original_product.base_unit,
            unit_type=original_product.unit_type,
            tax_group=original_product.tax_group,
            track_batches=original_product.track_batches,
            # Don't copy stock/cost data
            current_avg_cost=Decimal('0'),
            current_stock_qty=Decimal('0'),
            is_active=True
        )

        # Copy PLU codes
        for plu in original_product.plu_codes.all():
            ProductPLU.objects.create(
                product=new_product,
                plu_code=f"{plu.plu_code}_COPY",  # Modify to avoid conflicts
                is_primary=plu.is_primary,
                priority=plu.priority,
                description=f"Copy of {plu.description}",
                is_active=True
            )

        # Copy packagings
        for packaging in original_product.packagings.all():
            ProductPackaging.objects.create(
                product=new_product,
                unit=packaging.unit,
                conversion_factor=packaging.conversion_factor,
                is_default_sale_unit=packaging.is_default_sale_unit,
                is_default_purchase_unit=packaging.is_default_purchase_unit,
                is_active=True
            )

        return new_product