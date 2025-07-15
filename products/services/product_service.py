# products/services/product_service.py - ENHANCED WITH LIFECYCLE

from django.db.models import Q, Sum, F, Count, Avg
from django.utils import timezone
from typing import List, Optional, Dict, Tuple
from decimal import Decimal

from ..models import Product, ProductPLU, ProductBarcode, ProductPackaging, ProductLifecycleChoices


class ProductService:
    """Enhanced product service with lifecycle awareness"""

    # ===== EXISTING METHODS (enhanced with lifecycle) =====

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
        if include_inactive:
            products = Product.objects.all()
        elif only_sellable:
            products = Product.objects.sellable()
        else:
            products = Product.objects.exclude(
                lifecycle_status=ProductLifecycleChoices.DISCONTINUED
            )

        # Search logic
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
    def get_product_by_identifier(
            identifier: str,
            identifier_type: str = 'auto',
            only_sellable: bool = True
    ) -> Optional[Product]:
        """Get product by any identifier (auto-detect or specific type)"""

        if identifier_type == 'auto':
            # Try barcode first (most common in POS)
            product = ProductService.find_by_barcode(identifier, only_sellable)
            if product:
                return product

            # Try PLU code
            products = ProductService.find_by_plu(identifier, only_sellable)
            if products:
                return products[0]

            # Try product code
            try:
                base_query = Product.objects.filter(code=identifier)
                if only_sellable:
                    base_query = base_query.sellable()
                return base_query.first()
            except Product.DoesNotExist:
                return None

        elif identifier_type == 'barcode':
            return ProductService.find_by_barcode(identifier, only_sellable)

        elif identifier_type == 'plu':
            products = ProductService.find_by_plu(identifier, only_sellable)
            return products[0] if products else None

        elif identifier_type == 'code':
            try:
                base_query = Product.objects.filter(code=identifier)
                if only_sellable:
                    base_query = base_query.sellable()
                return base_query.first()
            except Product.DoesNotExist:
                return None

        return None

    # ===== NEW LIFECYCLE-AWARE METHODS =====

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
        """Get all sellable products with optional filtering"""
        products = Product.objects.sellable()

        if category:
            products = products.filter(product_group=category)

        products = products.select_related('brand', 'product_group')

        if limit:
            products = products[:limit]

        return list(products)

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
        return {
            'blocked_sales': list(Product.objects.filter(sales_blocked=True)[:10]),
            'blocked_purchases': list(Product.objects.filter(purchase_blocked=True)[:10]),
            'draft_old': list(Product.objects.filter(
                lifecycle_status=ProductLifecycleChoices.DRAFT,
                created_at__lt=timezone.now() - timezone.timedelta(days=30)
            )[:10]),
            'phase_out_with_stock': list(Product.objects.filter(
                lifecycle_status=ProductLifecycleChoices.PHASE_OUT,
                current_stock_qty__gt=0
            )[:10]),
            'discontinued_with_stock': list(Product.objects.filter(
                lifecycle_status=ProductLifecycleChoices.DISCONTINUED,
                current_stock_qty__gt=0
            )[:10])
        }

    # ===== PACKAGING & UNIT CONVERSION (existing, enhanced) =====

    @staticmethod
    def get_conversion_factor(product: Product, from_unit, to_unit) -> Optional[Decimal]:
        """Get conversion factor between units"""
        if from_unit == to_unit:
            return Decimal('1.0')

        # Check if both units are related to this product
        packagings = ProductPackaging.objects.filter(
            product=product,
            unit__in=[from_unit, to_unit],
            is_active=True
        )

        if packagings.count() != 2:
            return None

        from_packaging = packagings.get(unit=from_unit)
        to_packaging = packagings.get(unit=to_unit)

        return from_packaging.conversion_factor / to_packaging.conversion_factor

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
                'can_sell': product.is_sellable,
                'can_purchase': product.is_purchasable
            })

        return units

    # ===== STATISTICS & ANALYTICS =====

    @staticmethod
    def get_product_statistics() -> Dict:
        """Get comprehensive product statistics"""
        total_products = Product.objects.count()

        stats = {
            'total_products': total_products,
            'by_lifecycle': {},
            'sellable_count': Product.objects.sellable().count(),
            'purchasable_count': Product.objects.purchasable().count(),
            'blocked_sales_count': Product.objects.filter(sales_blocked=True).count(),
            'blocked_purchases_count': Product.objects.filter(purchase_blocked=True).count(),
            'with_stock': Product.objects.filter(current_stock_qty__gt=0).count(),
            'no_stock': Product.objects.filter(current_stock_qty=0).count(),
        }

        # Count by lifecycle status
        for status_code, status_name in ProductLifecycleChoices.choices:
            count = Product.objects.filter(lifecycle_status=status_code).count()
            stats['by_lifecycle'][status_code] = {
                'name': status_name,
                'count': count,
                'percentage': round((count / total_products * 100), 1) if total_products > 0 else 0
            }

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

        # Lifecycle validation
        if 'lifecycle_status' in product_data:
            if product_data['lifecycle_status'] not in ProductLifecycleChoices.values:
                errors.append('Invalid lifecycle status')

        return len(errors) == 0, errors