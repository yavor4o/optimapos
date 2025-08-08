# products/services/validation_service.py - REFACTORED

from typing import Tuple, Dict, List, Optional
from decimal import Decimal
from django.core.exceptions import ValidationError

from ..models import Product, ProductLifecycleChoices


class ProductValidationService:
    """
    Service for product validation logic
    REFACTORED: Removed stock field references, uses location-based checks
    """

    @staticmethod
    def can_sell_product(
            product: Product,
            quantity: Decimal = Decimal('1'),
            location=None
    ) -> Tuple[bool, str, Dict]:
        """
        Check if product can be sold
        Now includes optional location for stock checks
        """
        details = {
            'product_code': product.code,
            'lifecycle_status': product.lifecycle_status,
            'is_sellable': product.is_sellable,
            'sales_blocked': product.sales_blocked,
            'requested_quantity': quantity
        }

        # 1. Lifecycle validation
        if not product.is_sellable:
            if product.sales_blocked:
                return False, "Sales administratively blocked", details
            else:
                return False, f"Product not sellable: {product.get_lifecycle_status_display()}", details

        # 2. Basic quantity validation
        if quantity <= 0:
            return False, "Quantity must be positive", details

        # 3. Unit type validation for PIECE products
        if product.unit_type == Product.PIECE:
            if quantity != int(quantity):
                return False, "Piece products must be sold in whole numbers", details

        # 4. Location-based stock validation (if location provided)
        if location and not product.allow_negative_sales:
            from inventory.models import InventoryItem

            try:
                item = InventoryItem.objects.get(
                    product=product,
                    location=location
                )

                details['current_stock'] = item.current_qty
                details['available_stock'] = item.available_qty
                details['reserved_stock'] = item.reserved_qty

                if item.available_qty < quantity:
                    if not location.allow_negative_stock:
                        return False, f"Insufficient stock. Available: {item.available_qty}", details
                    else:
                        details['warning'] = "Selling will create negative stock"

            except InventoryItem.DoesNotExist:
                details['current_stock'] = Decimal('0')
                details['available_stock'] = Decimal('0')

                if not location.allow_negative_stock and not product.allow_negative_sales:
                    return False, "No stock available at this location", details

        return True, "OK", details

    @staticmethod
    def can_purchase_product(
            product: Product,
            quantity: Decimal = Decimal('1'),
            supplier=None
    ) -> Tuple[bool, str, Dict]:
        """Check if product can be purchased"""
        details = {
            'product_code': product.code,
            'lifecycle_status': product.lifecycle_status,
            'is_purchasable': product.is_purchasable,
            'purchase_blocked': product.purchase_blocked,
            'requested_quantity': quantity
        }

        # 1. Lifecycle validation
        if not product.is_purchasable:
            if product.purchase_blocked:
                return False, "Purchases administratively blocked", details
            else:
                return False, f"Product not purchasable: {product.get_lifecycle_status_display()}", details

        # 2. Basic quantity validation
        if quantity <= 0:
            return False, "Quantity must be positive", details

        # 3. Unit type validation for PIECE products
        if product.unit_type == Product.PIECE:
            if quantity != int(quantity):
                details['warning'] = "Ordering fractional quantities for PIECE products"

        # 4. Supplier validation (if provided)
        if supplier:
            # TODO: Add supplier-product relationship validation
            # For now, just add to details
            details['supplier'] = str(supplier)

        return True, "OK", details

    @staticmethod
    def get_product_restrictions(product: Product) -> Dict:
        """Get comprehensive product restrictions info"""
        return {
            'lifecycle_status': product.lifecycle_status,
            'lifecycle_display': product.get_lifecycle_status_display(),
            'is_sellable': product.is_sellable,
            'is_purchasable': product.is_purchasable,
            'sales_blocked': product.sales_blocked,
            'purchase_blocked': product.purchase_blocked,
            'allow_negative_sales': product.allow_negative_sales,
            'has_restrictions': product.has_restrictions,
            'restrictions_summary': product.get_restrictions_summary() if hasattr(product,
                                                                                  'get_restrictions_summary') else '',
            'lifecycle_badge_class': product.lifecycle_badge_class
        }

    @staticmethod
    def validate_lifecycle_change(
            product: Product,
            new_status: str,
            user=None
    ) -> Tuple[bool, str]:
        """Validate lifecycle status change"""

        if new_status not in ProductLifecycleChoices.values:
            return False, f"Invalid lifecycle status: {new_status}"

        old_status = product.lifecycle_status

        # Business rules for transitions
        if old_status == ProductLifecycleChoices.DISCONTINUED:
            return False, "Cannot change status from DISCONTINUED (create new product instead)"

        if old_status == ProductLifecycleChoices.NEW and new_status == ProductLifecycleChoices.PHASE_OUT:
            return False, "Cannot phase out a product that was never active"

        # Check stock before discontinuing (using property)
        if new_status == ProductLifecycleChoices.DISCONTINUED:
            if product.total_stock > 0:
                return False, f"Cannot discontinue product with remaining stock: {product.total_stock}"

        return True, "OK"

    @staticmethod
    def validate_product_data(product_data: Dict) -> Tuple[bool, List[str]]:
        """Validate product data for creation/update"""
        errors = []

        # Required fields
        required_fields = ['code', 'name', 'base_unit', 'tax_group']
        for field in required_fields:
            if not product_data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Code validation
        if product_data.get('code'):
            code = product_data['code'].strip().upper()

            # Length check
            if len(code) < 2:
                errors.append("Product code must be at least 2 characters")
            if len(code) > 50:
                errors.append("Product code must not exceed 50 characters")

            # Character validation
            if not code.replace('-', '').replace('_', '').replace('.', '').isalnum():
                errors.append("Product code can only contain letters, numbers, dash, underscore and dot")

            # Check uniqueness (if not updating existing)
            if not product_data.get('id'):
                if Product.objects.filter(code=code).exists():
                    errors.append(f"Product with code {code} already exists")

        # Name validation
        if product_data.get('name'):
            name = product_data['name'].strip()
            if len(name) < 2:
                errors.append("Product name must be at least 2 characters")
            if len(name) > 255:
                errors.append("Product name must not exceed 255 characters")

        # Lifecycle validation
        if product_data.get('lifecycle_status'):
            if product_data['lifecycle_status'] not in ProductLifecycleChoices.values:
                errors.append(f"Invalid lifecycle status: {product_data['lifecycle_status']}")

        # Unit type validation
        if product_data.get('unit_type'):
            valid_types = [Product.PIECE, Product.WEIGHT, Product.VOLUME, Product.LENGTH]
            if product_data['unit_type'] not in valid_types:
                errors.append(f"Invalid unit type. Must be one of: {', '.join(valid_types)}")

        # Tracking settings validation
        if product_data.get('track_serial_numbers'):
            if product_data.get('unit_type') != Product.PIECE:
                errors.append("Serial numbers can only be tracked for PIECE type products")

        if product_data.get('track_batches') and product_data.get('track_serial_numbers'):
            errors.append("Product cannot track both batches and serial numbers")

        return len(errors) == 0, errors

    @staticmethod
    def bulk_validate_products(
            products: List[Product],
            operation: str = 'sell',
            location=None
    ) -> Dict:
        """Bulk validation for multiple products"""
        results = {
            'valid': [],
            'invalid': [],
            'warnings': [],
            'summary': {}
        }

        for product in products:
            if operation == 'sell':
                can_do, reason, details = ProductValidationService.can_sell_product(
                    product,
                    location=location
                )
            elif operation == 'purchase':
                can_do, reason, details = ProductValidationService.can_purchase_product(product)
            else:
                can_do, reason, details = False, f"Unknown operation: {operation}", {}

            if can_do:
                results['valid'].append(product)
                if details.get('warning'):
                    results['warnings'].append({
                        'product': product,
                        'warning': details['warning']
                    })
            else:
                results['invalid'].append({
                    'product': product,
                    'reason': reason,
                    'details': details
                })

        results['summary'] = {
            'total': len(products),
            'valid_count': len(results['valid']),
            'invalid_count': len(results['invalid']),
            'warning_count': len(results['warnings'])
        }

        return results

    @staticmethod
    def validate_barcode_assignment(product: Product, barcode: str) -> Tuple[bool, str]:
        """Validate barcode assignment to product"""
        from ..models import ProductBarcode

        # Check if barcode already exists
        existing = ProductBarcode.objects.filter(barcode=barcode).first()
        if existing and existing.product != product:
            return False, f"Barcode already assigned to product: {existing.product.code}"

        # Validate barcode format
        if not barcode:
            return False, "Barcode cannot be empty"

        barcode = barcode.strip()

        # Check length for standard barcodes
        if barcode.isdigit():
            if len(barcode) not in [8, 12, 13, 14]:
                return False, f"Invalid barcode length: {len(barcode)}. Standard barcodes are 8, 12, 13 or 14 digits"

        # Check for weight barcode format (28xxxxx...)
        if barcode.startswith('28') and len(barcode) == 13:
            if product.unit_type != Product.WEIGHT:
                return False, "Weight barcodes (28xxx) can only be assigned to WEIGHT type products"

        return True, "OK"

    @staticmethod
    def validate_plu_assignment(product: Product, plu_code: str) -> Tuple[bool, str]:
        """Validate PLU code assignment to product"""
        from ..models import ProductPLU

        # Check product type
        if product.unit_type != Product.WEIGHT:
            return False, "PLU codes can only be assigned to WEIGHT type products"

        # Check if PLU already exists
        existing = ProductPLU.objects.filter(plu_code=plu_code).first()
        if existing and existing.product != product:
            return False, f"PLU code already assigned to product: {existing.product.code}"

        # Validate PLU format
        if not plu_code:
            return False, "PLU code cannot be empty"

        plu_code = plu_code.strip()

        # PLU codes are typically 4-5 digits
        if not plu_code.isdigit():
            return False, "PLU code must contain only digits"

        if len(plu_code) < 4 or len(plu_code) > 5:
            return False, "PLU code must be 4-5 digits"

        return True, "OK"

    @staticmethod
    def validate_packaging(product: Product, packaging_data: Dict) -> Tuple[bool, List[str]]:
        """Validate packaging configuration"""
        errors = []

        # Required fields
        if not packaging_data.get('unit'):
            errors.append("Packaging unit is required")

        if not packaging_data.get('conversion_factor'):
            errors.append("Conversion factor is required")

        # Conversion factor validation
        if packaging_data.get('conversion_factor'):
            factor = Decimal(str(packaging_data['conversion_factor']))
            if factor <= 0:
                errors.append("Conversion factor must be positive")
            if factor == 1:
                errors.append("Conversion factor of 1 is not allowed (use base unit instead)")

        # Unit validation
        if packaging_data.get('unit') == product.base_unit_id:
            errors.append("Packaging unit cannot be the same as base unit")

        # Physical properties validation
        if packaging_data.get('weight_kg'):
            if Decimal(str(packaging_data['weight_kg'])) < 0:
                errors.append("Weight cannot be negative")

        if packaging_data.get('volume_m3'):
            if Decimal(str(packaging_data['volume_m3'])) < 0:
                errors.append("Volume cannot be negative")

        return len(errors) == 0, errors