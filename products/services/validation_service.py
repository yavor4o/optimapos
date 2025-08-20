# products/services/validation_service.py - REFACTORED WITH RESULT PATTERN

from typing import Tuple, Dict, List, Optional
from decimal import Decimal
from django.core.exceptions import ValidationError

from core.utils.result import Result
from ..models import Product, ProductLifecycleChoices


class ProductValidationService:
    """
    Service for product validation logic

    REFACTORED: All methods now return Result objects for consistency
    Legacy methods available for backward compatibility
    """

    # =====================================================
    # NEW: RESULT-BASED METHODS
    # =====================================================

    @staticmethod
    def validate_sale(
            product: Product,
            quantity: Decimal = Decimal('1'),
            location=None
    ) -> Result:
        """
        Check if product can be sold - NEW Result-based method

        Returns:
            Result.success() with sale_details data
            Result.error() with specific error codes
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
                return Result.error(
                    code='SALES_BLOCKED',
                    msg="Sales administratively blocked",
                    data=details
                )
            else:
                return Result.error(
                    code='LIFECYCLE_RESTRICTED',
                    msg=f"Product not sellable: {product.get_lifecycle_status_display()}",
                    data=details
                )

        # 2. Basic quantity validation
        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg="Quantity must be positive",
                data=details
            )

        # 3. Unit type validation for PIECE products
        if product.unit_type == Product.PIECE:
            if quantity != int(quantity):
                return Result.error(
                    code='FRACTIONAL_PIECES',
                    msg="Piece products must be sold in whole numbers",
                    data=details
                )

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
                        return Result.error(
                            code='INSUFFICIENT_STOCK',
                            msg=f"Insufficient stock. Available: {item.available_qty}",
                            data=details
                        )
                    else:
                        details['warning'] = "Selling will create negative stock"

            except InventoryItem.DoesNotExist:
                details['current_stock'] = Decimal('0')
                details['available_stock'] = Decimal('0')

                if not location.allow_negative_stock and not product.allow_negative_sales:
                    return Result.error(
                        code='NO_STOCK',
                        msg="No stock available at this location",
                        data=details
                    )

        return Result.success(
            data=details,
            msg="Product can be sold"
        )

    @staticmethod
    def validate_purchase(
            product: Product,
            quantity: Decimal = Decimal('1'),
            supplier=None
    ) -> Result:
        """
        Check if product can be purchased - NEW Result-based method
        """
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
                return Result.error(
                    code='PURCHASE_BLOCKED',
                    msg="Purchases administratively blocked",
                    data=details
                )
            else:
                return Result.error(
                    code='LIFECYCLE_RESTRICTED',
                    msg=f"Product not purchasable: {product.get_lifecycle_status_display()}",
                    data=details
                )

        # 2. Basic quantity validation
        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg="Quantity must be positive",
                data=details
            )

        # 3. Unit type validation for PIECE products
        if product.unit_type == Product.PIECE:
            if quantity != int(quantity):
                details['warning'] = "Ordering fractional quantities for PIECE products"

        # 4. Supplier validation (if provided)
        if supplier:
            details['supplier'] = str(supplier)

        return Result.success(
            data=details,
            msg="Product can be purchased"
        )

    @staticmethod
    def validate_product_data(product_data: Dict) -> Result:
        """
        Validate product data for creation/update - NEW Result-based method
        """
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

        # Return result
        if errors:
            return Result.error(
                code='VALIDATION_FAILED',
                msg=f"Product data validation failed: {len(errors)} errors",
                data={'errors': errors, 'product_data': product_data}
            )
        else:
            return Result.success(
                data={'product_data': product_data},
                msg="Product data is valid"
            )

    @staticmethod
    def validate_lifecycle_transition(
            product: Product,
            new_status: str,
            user=None
    ) -> Result:
        """
        Validate lifecycle status change - NEW Result-based method
        """
        if new_status not in ProductLifecycleChoices.values:
            return Result.error(
                code='INVALID_STATUS',
                msg=f"Invalid lifecycle status: {new_status}",
                data={'current_status': product.lifecycle_status, 'requested_status': new_status}
            )

        old_status = product.lifecycle_status

        # Business rules for transitions
        if old_status == ProductLifecycleChoices.DISCONTINUED:
            return Result.error(
                code='TRANSITION_FORBIDDEN',
                msg="Cannot change status from DISCONTINUED (create new product instead)",
                data={'current_status': old_status, 'requested_status': new_status}
            )

        if old_status == ProductLifecycleChoices.NEW and new_status == ProductLifecycleChoices.PHASE_OUT:
            return Result.error(
                code='INVALID_TRANSITION',
                msg="Cannot phase out a product that was never active",
                data={'current_status': old_status, 'requested_status': new_status}
            )

        # Check stock before discontinuing
        if new_status == ProductLifecycleChoices.DISCONTINUED:
            if product.total_stock > 0:
                return Result.error(
                    code='HAS_STOCK',
                    msg=f"Cannot discontinue product with remaining stock: {product.total_stock}",
                    data={'total_stock': product.total_stock, 'current_status': old_status}
                )

        return Result.success(
            data={'old_status': old_status, 'new_status': new_status},
            msg=f"Lifecycle transition {old_status} → {new_status} is valid"
        )

    # =====================================================
    # LEGACY METHODS - BACKWARD COMPATIBILITY
    # =====================================================

    @staticmethod
    def can_sell_product(
            product: Product,
            quantity: Decimal = Decimal('1'),
            location=None
    ) -> Tuple[bool, str, Dict]:
        """
        LEGACY METHOD: Use validate_sale() for new code

        Maintained for backward compatibility
        """
        result = ProductValidationService.validate_sale(product, quantity, location)
        return result.ok, result.msg, result.data

    @staticmethod
    def can_purchase_product(
            product: Product,
            quantity: Decimal = Decimal('1'),
            supplier=None
    ) -> Tuple[bool, str, Dict]:
        """
        LEGACY METHOD: Use validate_purchase() for new code

        Maintained for backward compatibility
        """
        result = ProductValidationService.validate_purchase(product, quantity, supplier)
        return result.ok, result.msg, result.data

    @staticmethod
    def validate_lifecycle_change(
            product: Product,
            new_status: str,
            user=None
    ) -> Tuple[bool, str]:
        """
        LEGACY METHOD: Use validate_lifecycle_transition() for new code

        Maintained for backward compatibility
        """
        result = ProductValidationService.validate_lifecycle_transition(product, new_status, user)
        return result.ok, result.msg

    # =====================================================
    # UTILITY METHODS
    # =====================================================

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
            'restrictions_summary': getattr(product, 'get_restrictions_summary', lambda: '')(),
            'lifecycle_badge_class': getattr(product, 'lifecycle_badge_class', 'badge-secondary')
        }

    @staticmethod
    def bulk_validate_products(
            products: List[Product],
            operation: str = 'sell',
            location=None
    ) -> Result:
        """
        Bulk validation for multiple products - NEW Result-based method
        """
        results = {
            'valid': [],
            'invalid': [],
            'warnings': [],
            'summary': {}
        }

        for product in products:
            if operation == 'sell':
                validation_result = ProductValidationService.validate_sale(
                    product,
                    location=location
                )
            elif operation == 'purchase':
                validation_result = ProductValidationService.validate_purchase(product)
            else:
                return Result.error(
                    code='INVALID_OPERATION',
                    msg=f"Unknown operation: {operation}",
                    data={'operation': operation}
                )

            if validation_result.ok:
                results['valid'].append(product)
                if validation_result.data.get('warning'):
                    results['warnings'].append({
                        'product': product,
                        'warning': validation_result.data['warning']
                    })
            else:
                results['invalid'].append({
                    'product': product,
                    'reason': validation_result.msg,
                    'code': validation_result.code,
                    'details': validation_result.data
                })

        results['summary'] = {
            'total': len(products),
            'valid_count': len(results['valid']),
            'invalid_count': len(results['invalid']),
            'warning_count': len(results['warnings'])
        }

        return Result.success(
            data=results,
            msg=f"Bulk validation completed: {results['summary']['valid_count']}/{results['summary']['total']} valid"
        )