# products/services/lifecycle_service.py - NEW FILE

from typing import List, Dict, Optional
from django.db import transaction
from django.utils import timezone

from ..models import Product, ProductLifecycleChoices


class ProductLifecycleService:
    """Service for managing product lifecycle operations"""

    @staticmethod
    @transaction.atomic
    def change_lifecycle_status(
            product: Product,
            new_status: str,
            user=None,
            reason: str = ""
    ) -> Dict:
        """Change product lifecycle status with full validation"""

        from .validation_service import ProductValidationService

        # Validate the change
        can_change, validation_reason = ProductValidationService.validate_lifecycle_change(
            product, new_status, user
        )

        if not can_change:
            return {
                'success': False,
                'message': validation_reason,
                'product': product
            }

        old_status = product.lifecycle_status

        # Make the change
        product.set_lifecycle_status(new_status, user, reason)

        # Handle side effects
        ProductLifecycleService._handle_lifecycle_side_effects(
            product, old_status, new_status
        )

        return {
            'success': True,
            'message': f"Lifecycle changed: {old_status} → {new_status}",
            'product': product,
            'old_status': old_status,
            'new_status': new_status
        }

    @staticmethod
    def _handle_lifecycle_side_effects(product: Product, old_status: str, new_status: str):
        """Handle side effects of lifecycle changes"""

        # PHASE_OUT → Block new purchases
        if new_status == ProductLifecycleChoices.PHASE_OUT:
            product.purchase_blocked = True
            product.save(update_fields=['purchase_blocked'])

        # ACTIVE → Unblock if was blocked
        if new_status == ProductLifecycleChoices.ACTIVE:
            if product.purchase_blocked:
                product.purchase_blocked = False
                product.save(update_fields=['purchase_blocked'])

    @staticmethod
    @transaction.atomic
    def bulk_change_lifecycle(
            products: List[Product],
            new_status: str,
            user=None,
            reason: str = ""
    ) -> Dict:
        """Bulk lifecycle change with detailed results"""

        results = {
            'successful': [],
            'failed': [],
            'summary': {}
        }

        for product in products:
            result = ProductLifecycleService.change_lifecycle_status(
                product, new_status, user, reason
            )

            if result['success']:
                results['successful'].append(result)
            else:
                results['failed'].append(result)

        results['summary'] = {
            'total': len(products),
            'successful_count': len(results['successful']),
            'failed_count': len(results['failed'])
        }

        return results

    @staticmethod
    def get_lifecycle_statistics() -> Dict:
        """Get system-wide lifecycle statistics"""

        total_products = Product.objects.count()

        stats = {
            'total_products': total_products,
            'by_lifecycle': {},
            'blocked_products': {
                'sales_blocked': Product.objects.filter(sales_blocked=True).count(),
                'purchase_blocked': Product.objects.filter(purchase_blocked=True).count(),
            },
            'sellable_products': Product.objects.sellable().count(),
            'purchasable_products': Product.objects.purchasable().count(),
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