# products/services/product_service.py - REFACTORED

from django.db.models import Q, Sum, F, Count, Avg
from django.utils import timezone
from typing import List, Optional, Dict, Tuple
from decimal import Decimal

from ..models import Product, ProductPLU, ProductBarcode, ProductPackaging, ProductLifecycleChoices


class ProductService:
    """
    Product service - REFACTORED
    Removed all methods that update stock/costs (moved to InventoryService)
    Focused on product search, lookup and information retrieval
    """

    # ===== SEARCH & LOOKUP METHODS =====

    @staticmethod
    def find_by_plu(plu_code: str, only_sellable: bool = True) -> List[Product]:
        """Find products by PLU code with lifecycle filtering"""
        base_query = Product.objects.filter(
            plu_codes__plu_code=plu_code,
            plu_codes__is_active=True
        ).distinct().select_related('brand', 'product_group')

        if only_sellable:
            return list(base_query.sellable())
        else:
            return list(base_query)

    @staticmethod
    def find_by_barcode(barcode: str, only_sellable: bool = True) -> Optional[Product]:
        """Find product by barcode with lifecycle filtering"""
        try:
            base_query = ProductBarcode.objects.select_related('product').filter(
                barcode=barcode,
                is_active=True
            )

            if only_sellable:
                base_query = base_query.filter(
                    product__lifecycle_status__in=[
                        ProductLifecycleChoices.ACTIVE,
                        ProductLifecycleChoices.PHASE_OUT
                    ],
                    product__sales_blocked=False
                )

            barcode_obj = base_query.first()
            return barcode_obj.product if barcode_obj else None

        except ProductBarcode.DoesNotExist:
            return None

    @staticmethod
    def search_products(
            query: str,
            limit: int = 50,
            only_sellable: bool = False,
            include_inactive: bool = False
    ) -> List[Product]:
        """Universal product search with lifecycle filtering"""
        if not query or len(query.strip()) < 2:
            return []

        query = query.strip()

        # Base query
        if only_sellable:
            products = Product.objects.sellable()
        else:
            products = Product.objects.active() if not include_inactive else Product.objects.all()

        # Search in multiple fields
        products = products.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(barcodes__barcode__icontains=query) |
            Q(plu_codes__plu_code__icontains=query)
        ).distinct()

        # Select related for performance
        products = products.select_related('brand', 'product_group', 'base_unit', 'tax_group')

        # Apply limit
        if limit:
            products = products[:limit]

        return list(products)

    @staticmethod
    def get_product(identifier: str, only_sellable: bool = False) -> Optional[Product]:
        """Get product by code or barcode"""
        if not identifier:
            return None

        identifier = identifier.strip()

        # Try barcode first
        product = ProductService.find_by_barcode(identifier, only_sellable)
        if product:
            return product

        # Try product code
        try:
            base_query = Product.objects.filter(code=identifier)
            if only_sellable:
                base_query = base_query.sellable()
            return base_query.first()
        except Product.DoesNotExist:
            return None

    # ===== LIFECYCLE-AWARE METHODS =====

    @staticmethod
    def get_products_by_lifecycle(lifecycle_status: str) -> List[Product]:
        """Get products by specific lifecycle status"""
        return list(Product.objects.filter(lifecycle_status=lifecycle_status))

    @staticmethod
    def get_sellable_products(
            location=None,
            category=None,
            limit: int = None
    ) -> List[Product]:
        """
        Get all sellable products with optional filtering
        Note: location param kept for compatibility but stock data comes from InventoryItem
        """
        products = Product.objects.sellable()

        if category:
            products = products.filter(product_group=category)

        products = products.select_related('brand', 'product_group')

        if limit:
            products = products[:limit]

        result = []
        for product in products:
            product_data = {
                'product': product,
                'code': product.code,
                'name': product.name,
                'is_sellable': product.is_sellable
            }

            # If location specified, add stock info
            if location:
                stock_info = product.get_stock_info(location)
                product_data.update(stock_info)

            result.append(product_data)

        return result

    @staticmethod
    def get_purchasable_products(supplier=None, limit: int = None) -> List[Product]:
        """Get all purchasable products"""
        products = Product.objects.purchasable()

        if supplier:
            # TODO: Add supplier filtering when supplier-product relationship exists
            pass

        products = products.select_related('brand', 'product_group')

        if limit:
            products = products[:limit]

        return list(products)

    @staticmethod
    def get_products_needing_attention() -> Dict:
        """Get products that need manual attention"""

        # Import here to avoid circular dependency
        from inventory.models import InventoryItem

        # Products with lifecycle issues
        attention_needed = {
            'blocked_sales': list(Product.objects.filter(sales_blocked=True)[:10]),
            'blocked_purchases': list(Product.objects.filter(purchase_blocked=True)[:10]),
            'phase_out_with_stock': [],
            'discontinued_with_stock': []
        }

        # Phase out products with stock
        phase_out_products = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.PHASE_OUT
        )
        for product in phase_out_products[:10]:
            if product.total_stock > 0:
                attention_needed['phase_out_with_stock'].append({
                    'product': product,
                    'total_stock': product.total_stock,
                    'stock_value': product.stock_value
                })

        # Discontinued products with stock
        discontinued = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.DISCONTINUED
        )
        for product in discontinued[:10]:
            if product.total_stock > 0:
                attention_needed['discontinued_with_stock'].append({
                    'product': product,
                    'total_stock': product.total_stock,
                    'stock_value': product.stock_value
                })

        return attention_needed

    # ===== PACKAGING & UNIT CONVERSION =====

    @staticmethod
    def get_conversion_factor(product: Product, from_unit, to_unit) -> Optional[Decimal]:
        """Get conversion factor between units"""
        if from_unit == to_unit:
            return Decimal('1.0')

        # If one is base unit
        if from_unit == product.base_unit:
            packaging = ProductPackaging.objects.filter(
                product=product,
                unit=to_unit,
                is_active=True
            ).first()
            if packaging:
                return Decimal('1.0') / packaging.conversion_factor

        if to_unit == product.base_unit:
            packaging = ProductPackaging.objects.filter(
                product=product,
                unit=from_unit,
                is_active=True
            ).first()
            if packaging:
                return packaging.conversion_factor

        # Both are packaging units
        from_packaging = ProductPackaging.objects.filter(
            product=product,
            unit=from_unit,
            is_active=True
        ).first()

        to_packaging = ProductPackaging.objects.filter(
            product=product,
            unit=to_unit,
            is_active=True
        ).first()

        if from_packaging and to_packaging:
            return from_packaging.conversion_factor / to_packaging.conversion_factor

        return None

    @staticmethod
    def convert_quantity(
            product: Product,
            quantity: Decimal,
            from_unit,
            to_unit
    ) -> Optional[Decimal]:
        """Convert quantity between units"""
        conversion_factor = ProductService.get_conversion_factor(product, from_unit, to_unit)

        if conversion_factor is None:
            return None

        return quantity * conversion_factor

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
            'is_default_purchase': False,
            'can_sell': product.is_sellable,
            'can_purchase': product.is_purchasable
        })

        # Packaging units
        for packaging in product.packagings.filter(is_active=True):
            units.append({
                'unit': packaging.unit,
                'conversion_factor': packaging.conversion_factor,
                'is_base': False,
                'is_default_sale': packaging.is_default_sale_unit,
                'is_default_purchase': packaging.is_default_purchase_unit,
                'can_sell': product.is_sellable and packaging.allow_sale,
                'can_purchase': product.is_purchasable and packaging.allow_purchase
            })

        return units

    # ===== STATISTICS & ANALYTICS =====

    @staticmethod
    def get_product_statistics() -> Dict:
        """
        Get comprehensive product statistics
        Note: Stock statistics now come from InventoryItem
        """
        from inventory.models import InventoryItem

        total_products = Product.objects.count()

        stats = {
            'total_products': total_products,
            'by_lifecycle': {},
            'sellable_count': Product.objects.sellable().count(),
            'purchasable_count': Product.objects.purchasable().count(),
            'blocked_sales_count': Product.objects.filter(sales_blocked=True).count(),
            'blocked_purchases_count': Product.objects.filter(purchase_blocked=True).count(),
            'with_stock': 0,
            'no_stock': 0,
            'total_stock_value': Decimal('0')
        }

        # Count by lifecycle status
        for status_code, status_name in ProductLifecycleChoices.choices:
            count = Product.objects.filter(lifecycle_status=status_code).count()
            stats['by_lifecycle'][status_code] = {
                'name': status_name,
                'count': count,
                'percentage': round((count / total_products * 100), 1) if total_products > 0 else 0
            }

        # Stock statistics from InventoryItem
        products_with_stock = InventoryItem.objects.filter(
            current_qty__gt=0
        ).values('product').distinct().count()

        stats['with_stock'] = products_with_stock
        stats['no_stock'] = total_products - products_with_stock

        # Total stock value
        total_value = InventoryItem.objects.filter(
            current_qty__gt=0
        ).aggregate(
            total=Sum(F('current_qty') * F('avg_cost'))
        )['total'] or Decimal('0')

        stats['total_stock_value'] = total_value

        return stats

    @staticmethod
    def validate_product_data(product_data: Dict) -> Tuple[bool, List[str]]:
        """Validate product data before creation/update"""
        errors = []

        # Required fields
        if not product_data.get('code'):
            errors.append('Product code is required')

        if not product_data.get('name'):
            errors.append('Product name is required')

        if not product_data.get('base_unit'):
            errors.append('Base unit is required')

        if not product_data.get('tax_group'):
            errors.append('Tax group is required')

        # Code format validation
        if product_data.get('code'):
            code = product_data['code'].strip().upper()
            if len(code) < 3:
                errors.append('Product code must be at least 3 characters')
            if ' ' in code:
                errors.append('Product code cannot contain spaces')

        # Lifecycle validation
        if 'lifecycle_status' in product_data:
            if product_data['lifecycle_status'] not in ProductLifecycleChoices.values:
                errors.append('Invalid lifecycle status')

        # Unit type validation
        if 'unit_type' in product_data:
            valid_types = ['PIECE', 'WEIGHT', 'VOLUME', 'LENGTH']
            if product_data['unit_type'] not in valid_types:
                errors.append('Invalid unit type')

        # Tracking settings validation
        if product_data.get('track_serial_numbers'):
            if product_data.get('unit_type') != 'PIECE':
                errors.append('Serial numbers can only be tracked for PIECE type products')

        return len(errors) == 0, errors

    # ===== BULK OPERATIONS =====

    @staticmethod
    def bulk_update_lifecycle(
            product_ids: List[int],
            new_status: str,
            user=None
    ) -> Dict:
        """Bulk update lifecycle status"""
        if new_status not in ProductLifecycleChoices.values:
            return {
                'success': False,
                'error': 'Invalid lifecycle status'
            }

        updated = Product.objects.filter(
            id__in=product_ids
        ).update(
            lifecycle_status=new_status,
            updated_at=timezone.now()
        )

        return {
            'success': True,
            'updated_count': updated
        }

    @staticmethod
    def bulk_block_sales(product_ids: List[int], block: bool = True) -> int:
        """Bulk block/unblock sales"""
        return Product.objects.filter(
            id__in=product_ids
        ).update(
            sales_blocked=block,
            updated_at=timezone.now()
        )

    @staticmethod
    def bulk_block_purchases(product_ids: List[int], block: bool = True) -> int:
        """Bulk block/unblock purchases"""
        return Product.objects.filter(
            id__in=product_ids
        ).update(
            purchase_blocked=block,
            updated_at=timezone.now()
        )