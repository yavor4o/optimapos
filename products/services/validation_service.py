# products/services/validation_service.py - NEW FILE

from typing import Tuple, Dict, List
from decimal import Decimal
from django.utils.translation import gettext_lazy as _

from ..models import Product, ProductLifecycleChoices


class ProductValidationService:
    """Centralized product validation logic"""

    @staticmethod
    def can_sell_product(
            product: Product,
            location=None,
            customer=None,
            quantity: Decimal = Decimal('1')
    ) -> Tuple[bool, str, Dict]:
        """
        Master validation for product sales
        Returns: (can_sell, reason, details)
        """
        details = {
            'product_code': product.code,
            'lifecycle_status': product.lifecycle_status,
            'sales_blocked': product.sales_blocked,
            'quantity': quantity
        }

        # 1. Lifecycle validation
        if not product.is_sellable:
            if product.sales_blocked:
                return False, "Sales administratively blocked", details
            else:
                return False, f"Product not sellable: {product.get_lifecycle_status_display()}", details

        # 2. Quantity validation
        can_validate_qty, qty_reason = product.validate_sale_quantity(quantity, location)
        if not can_validate_qty:
            return False, qty_reason, details

        return True, "OK", details

    @staticmethod
    def can_purchase_product(
            product: Product,
            supplier=None,
            quantity: Decimal = Decimal('1')
    ) -> Tuple[bool, str, Dict]:
        """
        Master validation for product purchases
        """
        details = {
            'product_code': product.code,
            'lifecycle_status': product.lifecycle_status,
            'purchase_blocked': product.purchase_blocked,
            'quantity': quantity
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
            'restrictions_summary': product.get_restrictions_summary(),
            'badge_class': product.lifecycle_badge_class
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
            if new_status != ProductLifecycleChoices.DISCONTINUED:
                return False, "Cannot change status from DISCONTINUED (create new product instead)"

        return True, "OK"

    @staticmethod
    def bulk_validate_products(
            products: List[Product],
            operation: str = 'sell'
    ) -> Dict:
        """Bulk validation for multiple products"""
        results = {
            'valid': [],
            'invalid': [],
            'summary': {}
        }

        for product in products:
            if operation == 'sell':
                can_do, reason, details = ProductValidationService.can_sell_product(product)
            elif operation == 'purchase':
                can_do, reason, details = ProductValidationService.can_purchase_product(product)
            else:
                can_do, reason = False, f"Unknown operation: {operation}"

            if can_do:
                results['valid'].append(product)
            else:
                results['invalid'].append({
                    'product': product,
                    'reason': reason
                })

        results['summary'] = {
            'total': len(products),
            'valid_count': len(results['valid']),
            'invalid_count': len(results['invalid'])
        }

        return results