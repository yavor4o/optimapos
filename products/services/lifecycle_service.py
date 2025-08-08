# products/services/lifecycle_service.py - REFACTORED

from typing import List, Dict, Optional
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal

from ..models import Product, ProductLifecycleChoices


class ProductLifecycleService:
    """
    Service for managing product lifecycle operations
    REFACTORED: Removed references to stock fields, uses new properties
    """

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

        # DISCONTINUED → Block both sales and purchases
        if new_status == ProductLifecycleChoices.DISCONTINUED:
            product.sales_blocked = True
            product.purchase_blocked = True
            product.save(update_fields=['sales_blocked', 'purchase_blocked'])

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
                results['successful'].append({
                    'product': product,
                    'old_status': result['old_status'],
                    'new_status': result['new_status']
                })
            else:
                results['failed'].append({
                    'product': product,
                    'reason': result['message']
                })

        results['summary'] = {
            'total': len(products),
            'successful_count': len(results['successful']),
            'failed_count': len(results['failed'])
        }

        return results

    @staticmethod
    def block_sales(product: Product, user=None, reason: str = "") -> Dict:
        """Block sales for a product"""
        product.block_sales(reason)

        return {
            'success': True,
            'message': f"Sales blocked for {product.code}",
            'product': product
        }

    @staticmethod
    def unblock_sales(product: Product, user=None) -> Dict:
        """Unblock sales for a product"""
        product.unblock_sales()

        return {
            'success': True,
            'message': f"Sales unblocked for {product.code}",
            'product': product
        }

    @staticmethod
    def block_purchases(product: Product, user=None, reason: str = "") -> Dict:
        """Block purchases for a product"""
        product.block_purchases(reason)

        return {
            'success': True,
            'message': f"Purchases blocked for {product.code}",
            'product': product
        }

    @staticmethod
    def unblock_purchases(product: Product, user=None) -> Dict:
        """Unblock purchases for a product"""
        product.unblock_purchases()

        return {
            'success': True,
            'message': f"Purchases unblocked for {product.code}",
            'product': product
        }

    @staticmethod
    def get_lifecycle_statistics() -> Dict:
        """
        Get comprehensive lifecycle statistics
        REFACTORED: Uses properties for stock data
        """
        total = Product.objects.count()

        stats = {
            'total_products': total,
            'by_lifecycle': {},
            'lifecycle_transitions': [],
            'blocked_products': {
                'sales_blocked': Product.objects.filter(sales_blocked=True).count(),
                'purchase_blocked': Product.objects.filter(purchase_blocked=True).count(),
                'both_blocked': Product.objects.filter(
                    sales_blocked=True,
                    purchase_blocked=True
                ).count()
            },
            'actionable_items': {}
        }

        # Statistics by lifecycle status
        for status, label in ProductLifecycleChoices.choices:
            count = Product.objects.filter(lifecycle_status=status).count()
            percentage = (count / total * 100) if total > 0 else 0

            stats['by_lifecycle'][status] = {
                'name': label,
                'count': count,
                'percentage': round(percentage, 1)
            }

        # Get actionable items using properties
        stats['actionable_items'] = ProductLifecycleService._get_actionable_items()

        return stats

    @staticmethod
    def _get_actionable_items() -> Dict:
        """
        Get items needing attention
        REFACTORED: Uses product properties instead of direct field access
        """
        actionable = {
            'phase_out_with_stock': [],
            'discontinued_with_stock': [],
            'new_products_not_activated': [],
            'blocked_but_active': []
        }

        # Phase out products with stock
        phase_out = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.PHASE_OUT
        )[:10]

        for product in phase_out:
            if product.total_stock > 0:  # Using property
                actionable['phase_out_with_stock'].append({
                    'product': product,
                    'stock': product.total_stock,
                    'value': product.stock_value  # Using property
                })

        # Discontinued products with stock
        discontinued = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.DISCONTINUED
        )[:10]

        for product in discontinued:
            if product.total_stock > 0:  # Using property
                actionable['discontinued_with_stock'].append({
                    'product': product,
                    'stock': product.total_stock,
                    'value': product.stock_value  # Using property
                })

        # New products not yet activated (30+ days)
        new_old = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.NEW,
            created_at__lt=timezone.now() - timezone.timedelta(days=30)
        )[:10]

        actionable['new_products_not_activated'] = list(new_old)

        # Active products that are blocked
        blocked_active = Product.objects.filter(
            lifecycle_status=ProductLifecycleChoices.ACTIVE
        ).filter(
            models.Q(sales_blocked=True) | models.Q(purchase_blocked=True)
        )[:10]

        actionable['blocked_but_active'] = list(blocked_active)

        return actionable

    @staticmethod
    def recommend_lifecycle_action(product: Product) -> Dict:
        """
        Recommend lifecycle action based on product state
        REFACTORED: Uses properties for stock analysis
        """
        recommendations = []

        # Check current status
        if product.lifecycle_status == ProductLifecycleChoices.NEW:
            if product.created_at < timezone.now() - timezone.timedelta(days=30):
                recommendations.append({
                    'action': 'ACTIVATE',
                    'reason': 'Product in NEW status for over 30 days',
                    'priority': 'HIGH'
                })

        elif product.lifecycle_status == ProductLifecycleChoices.ACTIVE:
            # Check if product has no stock for long time
            if product.total_stock == 0:  # Using property
                from inventory.models import InventoryMovement

                # Check last sale
                last_sale = InventoryMovement.objects.filter(
                    product=product,
                    movement_type='OUT'
                ).order_by('-created_at').first()

                if last_sale and last_sale.created_at < timezone.now() - timezone.timedelta(days=180):
                    recommendations.append({
                        'action': 'PHASE_OUT',
                        'reason': 'No sales in last 6 months',
                        'priority': 'MEDIUM'
                    })

        elif product.lifecycle_status == ProductLifecycleChoices.PHASE_OUT:
            if product.total_stock == 0:  # Using property
                recommendations.append({
                    'action': 'DISCONTINUE',
                    'reason': 'Phase-out product with no remaining stock',
                    'priority': 'LOW'
                })

        return {
            'product': product,
            'current_status': product.lifecycle_status,
            'recommendations': recommendations,
            'has_recommendations': len(recommendations) > 0
        }

    @staticmethod
    def can_transition_to(product: Product, target_status: str) -> tuple[bool, str]:
        """Check if product can transition to target status"""

        current = product.lifecycle_status

        # Define allowed transitions
        allowed_transitions = {
            ProductLifecycleChoices.NEW: [
                ProductLifecycleChoices.ACTIVE,
                ProductLifecycleChoices.DISCONTINUED
            ],
            ProductLifecycleChoices.ACTIVE: [
                ProductLifecycleChoices.PHASE_OUT,
                ProductLifecycleChoices.DISCONTINUED
            ],
            ProductLifecycleChoices.PHASE_OUT: [
                ProductLifecycleChoices.DISCONTINUED,
                ProductLifecycleChoices.ACTIVE  # Can reactivate
            ],
            ProductLifecycleChoices.DISCONTINUED: []  # Cannot transition from discontinued
        }

        if target_status in allowed_transitions.get(current, []):
            return True, "Transition allowed"
        else:
            return False, f"Cannot transition from {current} to {target_status}"