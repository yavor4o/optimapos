# products/services/product_service.py - REFACTORED

from django.db.models import Q, Sum, F
from django.utils import timezone
from typing import List, Optional, Dict, Tuple
from decimal import Decimal
from ..models import Product, ProductBarcode, ProductPackaging, ProductLifecycleChoices
from django.db import transaction
from core.utils.result import Result
from inventory.models import InventoryLocation, InventoryItem
import logging

logger = logging.getLogger(__name__)

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

    @staticmethod
    @transaction.atomic
    def create_product_with_inventory(product_data: Dict) -> Result:
        """
        🎯 NEW METHOD: Create product with automatic inventory setup

        This is the preferred way to create.html products in the system.
        Follows enterprise retail best practices.
        """
        try:
            # Step 1: Validate input data
            validation_result = ProductService.validate_product_data(product_data)
            if not validation_result.ok:
                return validation_result

            # Step 2: Create the product
            from ..models import Product
            product = Product.objects.create(**product_data)

            # Step 3: Create inventory items for all active locations
            inventory_result = ProductService._create_inventory_items_for_product(product)

            if not inventory_result.ok:
                # Log warning but continue gracefully
                logger.warning(f"Inventory creation failed for {product.code}: {inventory_result.msg}")

            success_data = {
                'product': {
                    'id': product.id,
                    'code': product.code,
                    'name': product.name,
                    'lifecycle_status': product.lifecycle_status
                },
                'inventory_items_created': inventory_result.data.get('created_count', 0) if inventory_result.ok else 0,
                'active_locations': inventory_result.data.get('total_locations', 0) if inventory_result.ok else 0,
                'warnings': [] if inventory_result.ok else [inventory_result.msg]
            }

            logger.info(f"✅ Product created successfully: {product.code}")
            return Result.success(success_data, f"Product {product.code} created successfully")

        except Exception as e:
            logger.error(f"❌ Product creation failed: {e}")
            return Result.error('PRODUCT_CREATION_FAILED', f"Failed to create.html product: {str(e)}")

    @staticmethod
    def create_product_without_inventory(product_data: Dict) -> Result:
        """
        🔧 ALTERNATIVE: Create product without inventory (for special cases)
        """
        try:
            validation_result = ProductService.validate_product_data(product_data)
            if not validation_result.ok:
                return validation_result

            from ..models import Product
            product = Product.objects.create(**product_data)

            success_data = {
                'product': {
                    'id': product.id,
                    'code': product.code,
                    'name': product.name
                },
                'inventory_items_created': 0,
                'note': 'Product created without inventory items'
            }

            logger.info(f"✅ Product created (no inventory): {product.code}")
            return Result.success(success_data, f"Product {product.code} created without inventory")

        except Exception as e:
            logger.error(f"❌ Product creation failed: {e}")
            return Result.error('PRODUCT_CREATION_FAILED', f"Failed to create.html product: {str(e)}")

    @staticmethod
    def _create_inventory_items_for_product(product) -> Result:
        """
        🏪 INTERNAL: Create InventoryItem records for all active locations
        """
        try:
            active_locations = InventoryLocation.objects.filter(is_active=True)
            created_count = 0
            skipped_count = 0

            for location in active_locations:
                inventory_item, created = InventoryItem.objects.get_or_create(
                    product=product,
                    location=location,
                    defaults={
                        'current_qty': Decimal('0'),
                        'reserved_qty': Decimal('0'),
                        'avg_cost': getattr(product, 'standard_cost', None) or Decimal('0'),
                        'min_stock_level': Decimal('0'),
                        'max_stock_level': Decimal('0'),
                    }
                )

                if created:
                    created_count += 1
                    logger.debug(f"Created InventoryItem: {product.code} @ {location.code}")
                else:
                    skipped_count += 1
                    logger.debug(f"InventoryItem already exists: {product.code} @ {location.code}")

            result_data = {
                'created_count': created_count,
                'skipped_count': skipped_count,
                'total_locations': active_locations.count()
            }

            if created_count > 0:
                logger.info(f"✅ Created {created_count} InventoryItems for {product.code}")
                return Result.success(result_data, f"Created {created_count} inventory items")
            else:
                logger.warning(f"⚠️ No inventory items created for {product.code} (all existed)")
                return Result.success(result_data, "No new inventory items needed")

        except Exception as e:
            logger.error(f"❌ Inventory creation failed for {product.code}: {e}")
            return Result.error('INVENTORY_CREATION_FAILED', f"Failed to create.html inventory items: {str(e)}")

    @staticmethod
    def add_product_to_location(product, location) -> Result:
        """
        🏪 PUBLIC METHOD: Add existing product to a specific location
        """
        try:
            inventory_item, created = InventoryItem.objects.get_or_create(
                product=product,
                location=location,
                defaults={
                    'current_qty': Decimal('0'),
                    'reserved_qty': Decimal('0'),
                    'avg_cost': getattr(product, 'standard_cost', None) or Decimal('0'),
                    'min_stock_level': Decimal('0'),
                    'max_stock_level': Decimal('0'),
                }
            )

            if created:
                logger.info(f"✅ Added {product.code} to {location.code}")
                return Result.success({
                    'product_code': product.code,
                    'location_code': location.code,
                    'created': True
                }, f"Product {product.code} added to {location.code}")
            else:
                logger.info(f"⚠️ {product.code} already exists at {location.code}")
                return Result.success({
                    'product_code': product.code,
                    'location_code': location.code,
                    'created': False
                }, f"Product {product.code} already exists at {location.code}")

        except Exception as e:
            logger.error(f"❌ Failed to add {product.code} to {location.code}: {e}")
            return Result.error('LOCATION_ADD_FAILED', f"Failed to add product to location: {str(e)}")

    @staticmethod
    def setup_inventory_for_existing_products() -> Result:
        """
        🔧 MIGRATION HELPER: Setup inventory for products created before this system
        """
        try:
            with transaction.atomic():
                from ..models import Product

                products_without_full_inventory = []
                total_created = 0

                active_locations = InventoryLocation.objects.filter(is_active=True)
                all_products = Product.objects.all()

                for product in all_products:
                    existing_items = InventoryItem.objects.filter(product=product).count()
                    expected_items = active_locations.count()

                    if existing_items < expected_items:
                        products_without_full_inventory.append(product.code)

                        # Create missing inventory items
                        for location in active_locations:
                            inventory_item, created = InventoryItem.objects.get_or_create(
                                product=product,
                                location=location,
                                defaults={
                                    'current_qty': Decimal('0'),
                                    'reserved_qty': Decimal('0'),
                                    'avg_cost': getattr(product, 'standard_cost', None) or Decimal('0'),
                                    'min_stock_level': Decimal('0'),
                                    'max_stock_level': Decimal('0'),
                                }
                            )

                            if created:
                                total_created += 1

                migration_result = {
                    'products_processed': len(products_without_full_inventory),
                    'inventory_items_created': total_created,
                    'products_with_missing_inventory': products_without_full_inventory[:10]  # Sample
                }

                logger.info(
                    f"✅ Migration completed: {total_created} inventory items created for {len(products_without_full_inventory)} products")
                return Result.success(migration_result, f"Migration completed successfully")

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            return Result.error('MIGRATION_FAILED', f"Migration failed: {str(e)}")

    @staticmethod
    def validate_product_data(product_data: Dict) -> Result:
        """
        🔍 UNIFIED: Complete product data validation before creation/update

        Combines all validation rules from existing codebase
        """
        errors = []

        # Required fields validation
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

            # Code uniqueness check
            from ..models import Product
            if Product.objects.filter(code=code).exists():
                errors.append(f"Product code '{code}' already exists")

        # Lifecycle validation
        if 'lifecycle_status' in product_data:
            from ..models import ProductLifecycleChoices
            if product_data['lifecycle_status'] not in [choice[0] for choice in ProductLifecycleChoices.choices]:
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

        # Return Result
        if errors:
            return Result.error('VALIDATION_FAILED', "Validation errors", {'errors': errors})

        return Result.success({}, "Validation passed")