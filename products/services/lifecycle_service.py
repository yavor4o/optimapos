# products/services/lifecycle_service.py - COMPLETE RESULT PATTERN REFACTORING
"""
PRODUCT LIFECYCLE SERVICE - COMPLETE REFACTORED WITH RESULT PATTERN

Централизирана product lifecycle логика с Result pattern за консистентност.
Управлява lifecycle transitions и автоматизира related операции.

ПРОМЕНИ:
- Всички публични методи връщат Result objects
- Legacy методи запазени за backward compatibility
- Enhanced error handling и validation
- Automatic side effects management
- Integration готовност с останалите services
"""

from typing import List, Dict, Optional
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal
import logging

from core.utils.result import Result
from ..models import Product, ProductLifecycleChoices

logger = logging.getLogger(__name__)


class ProductLifecycleService:
    """
    PRODUCT LIFECYCLE SERVICE - REFACTORED WITH RESULT PATTERN

    CHANGES: All public methods now return Result objects
    Legacy methods available for backward compatibility
    Enhanced lifecycle management with automatic side effects
    """

    # =====================================================
    # NEW: RESULT-BASED PUBLIC API
    # =====================================================

    @staticmethod
    @transaction.atomic
    def change_product_lifecycle(
            product: Product,
            new_status: str,
            user=None,
            reason: str = "",
            force: bool = False
    ) -> Result:
        """
        🎯 PRIMARY API: Change product lifecycle status - NEW Result-based method

        Args:
            product: Product to change
            new_status: Target lifecycle status
            user: User making the change
            reason: Reason for change
            force: Skip validation checks if True

        Returns:
            Result with lifecycle change details or error
        """
        try:
            # Validate inputs
            validation_result = ProductLifecycleService._validate_lifecycle_inputs(
                product, new_status, user
            )
            if not validation_result.ok:
                return validation_result

            # Check if change is allowed (unless forced)
            if not force:
                from .validation_service import ProductValidationService
                validation_check = ProductValidationService.validate_lifecycle_transition(
                    product, new_status, user
                )
                if not validation_check.ok:
                    return Result.error(
                        code='LIFECYCLE_CHANGE_DENIED',
                        msg=f'Lifecycle change not allowed: {validation_check.msg}',
                        data={'product_code': product.code, 'current_status': product.lifecycle_status}
                    )

            old_status = product.lifecycle_status

            # Perform the lifecycle change
            change_result = ProductLifecycleService._execute_lifecycle_change(
                product, new_status, user, reason
            )
            if not change_result.ok:
                return change_result

            # Handle automatic side effects
            side_effects_result = ProductLifecycleService._handle_lifecycle_side_effects(
                product, old_status, new_status, user
            )

            # Log side effects warnings but don't fail the main operation
            if not side_effects_result.ok:
                logger.warning(f"Side effects warning: {side_effects_result.msg}")

            # Prepare response data
            lifecycle_data = {
                'product_id': product.id,
                'product_code': product.code,
                'old_status': old_status,
                'new_status': new_status,
                'status_display': product.get_lifecycle_status_display(),
                'changed_by': user.username if user else None,
                'reason': reason,
                'change_timestamp': timezone.now(),
                'side_effects': side_effects_result.data if side_effects_result.ok else {},
                'restrictions_updated': ProductLifecycleService._get_updated_restrictions(product),
                'force_applied': force
            }

            logger.info(f"Lifecycle changed: {product.code} {old_status} → {new_status} by {user}")

            return Result.success(
                data=lifecycle_data,
                msg=f'Lifecycle successfully changed from {old_status} to {new_status}'
            )

        except Exception as e:
            logger.error(f"Error changing product lifecycle: {e}")
            return Result.error(
                code='LIFECYCLE_CHANGE_ERROR',
                msg=f'Failed to change lifecycle: {str(e)}',
                data={'product_code': getattr(product, 'code', '?'), 'target_status': new_status}
            )

    @staticmethod
    def get_lifecycle_analysis(product: Product) -> Result:
        """
        🎯 ANALYSIS API: Get comprehensive lifecycle analysis - NEW Result-based method

        Returns detailed analysis of product lifecycle status and implications
        """
        try:
            current_status = product.lifecycle_status

            # Get lifecycle history if available
            lifecycle_history = ProductLifecycleService._get_lifecycle_history(product)

            # Analyze current status implications
            status_implications = ProductLifecycleService._analyze_status_implications(product)

            # Get available transitions
            available_transitions = ProductLifecycleService._get_available_transitions(product)

            # Calculate lifecycle metrics
            lifecycle_metrics = ProductLifecycleService._calculate_lifecycle_metrics(product, lifecycle_history)

            # Get business impact analysis
            business_impact = ProductLifecycleService._analyze_business_impact(product)

            analysis_data = {
                'product_id': product.id,
                'product_code': product.code,
                'current_status': current_status,
                'status_display': product.get_lifecycle_status_display(),
                'status_implications': status_implications,
                'available_transitions': available_transitions,
                'lifecycle_history': lifecycle_history,
                'lifecycle_metrics': lifecycle_metrics,
                'business_impact': business_impact,
                'recommendations': ProductLifecycleService._generate_lifecycle_recommendations(product),
                'analysis_timestamp': timezone.now()
            }

            return Result.success(
                data=analysis_data,
                msg='Lifecycle analysis completed successfully'
            )

        except Exception as e:
            logger.error(f"Error in lifecycle analysis: {e}")
            return Result.error(
                code='ANALYSIS_ERROR',
                msg=f'Lifecycle analysis failed: {str(e)}'
            )

    @staticmethod
    def validate_lifecycle_setup(product: Product) -> Result:
        """
        🎯 VALIDATION API: Validate product lifecycle setup - NEW Result-based method

        Checks if product has proper lifecycle configuration
        """
        try:
            validation_data = {
                'product_id': product.id,
                'product_code': product.code,
                'current_status': product.lifecycle_status,
                'has_valid_status': False,
                'status_consistency': True,
                'validation_issues': [],
                'validation_warnings': [],
                'recommendations': []
            }

            # Check if current status is valid
            valid_statuses = [choice[0] for choice in ProductLifecycleChoices.choices]
            validation_data['has_valid_status'] = product.lifecycle_status in valid_statuses

            if not validation_data['has_valid_status']:
                validation_data['validation_issues'].append(f'Invalid lifecycle status: {product.lifecycle_status}')
                validation_data['recommendations'].append('Set a valid lifecycle status from available choices')

            # Check status vs properties consistency
            consistency_issues = ProductLifecycleService._check_status_consistency(product)
            if consistency_issues:
                validation_data['status_consistency'] = False
                validation_data['validation_warnings'].extend(consistency_issues)

            # Check for potential business logic conflicts
            business_conflicts = ProductLifecycleService._check_business_conflicts(product)
            if business_conflicts:
                validation_data['validation_warnings'].extend(business_conflicts)

            # Check lifecycle progression logic
            progression_issues = ProductLifecycleService._check_progression_logic(product)
            if progression_issues:
                validation_data['validation_warnings'].extend(progression_issues)

            # Generate specific recommendations
            if product.lifecycle_status == ProductLifecycleChoices.NEW:
                if not hasattr(product, 'created_at') or (timezone.now() - product.created_at).days > 30:
                    validation_data['recommendations'].append(
                        'Consider moving from NEW status - product is older than 30 days')

            if product.lifecycle_status == ProductLifecycleChoices.DISCONTINUED:
                try:
                    # Check if product still has inventory or active sales
                    from inventory.models import InventoryItem
                    has_inventory = InventoryItem.objects.filter(product=product, current_qty__gt=0).exists()
                    if has_inventory:
                        validation_data['validation_warnings'].append('Product is discontinued but still has inventory')
                        validation_data['recommendations'].append(
                            'Consider inventory clearance or moving to PHASE_OUT status')
                except ImportError:
                    pass

            # Determine overall validation result
            has_critical_issues = len(validation_data['validation_issues']) > 0
            has_warnings = len(validation_data['validation_warnings']) > 0

            if has_critical_issues:
                return Result.error(
                    code='LIFECYCLE_SETUP_INVALID',
                    msg=f'Critical lifecycle issues found: {len(validation_data["validation_issues"])} issues',
                    data=validation_data
                )
            elif has_warnings:
                return Result.success(
                    data=validation_data,
                    msg=f'Lifecycle setup valid but has {len(validation_data["validation_warnings"])} warnings'
                )
            else:
                return Result.success(
                    data=validation_data,
                    msg='Lifecycle setup is fully valid'
                )

        except Exception as e:
            logger.error(f"Error validating lifecycle setup: {e}")
            return Result.error(
                code='VALIDATION_ERROR',
                msg=f'Lifecycle validation failed: {str(e)}'
            )

    @staticmethod
    def bulk_lifecycle_operation(
            products: List[Product],
            operation: str,
            target_status: str = None,
            user=None,
            reason: str = ""
    ) -> Result:
        """
        🎯 BULK API: Perform bulk lifecycle operations - NEW Result-based method

        Args:
            products: List of products to operate on
            operation: Operation type ('change_status', 'validate', 'analyze')
            target_status: Target status for change operations
            user: User performing the operation
            reason: Reason for bulk operation

        Returns:
            Result with bulk operation statistics
        """
        try:
            if not products:
                return Result.error(
                    code='NO_PRODUCTS',
                    msg='No products provided for bulk operation'
                )

            bulk_results = {
                'total_products': len(products),
                'successful_operations': 0,
                'failed_operations': 0,
                'operation_type': operation,
                'target_status': target_status,
                'results': [],
                'errors': []
            }

            for product in products:
                try:
                    if operation == 'change_status':
                        if not target_status:
                            bulk_results['errors'].append({
                                'product_code': product.code,
                                'error': 'Target status required for change_status operation'
                            })
                            bulk_results['failed_operations'] += 1
                            continue

                        result = ProductLifecycleService.change_product_lifecycle(
                            product, target_status, user, reason
                        )
                    elif operation == 'validate':
                        result = ProductLifecycleService.validate_lifecycle_setup(product)
                    elif operation == 'analyze':
                        result = ProductLifecycleService.get_lifecycle_analysis(product)
                    else:
                        bulk_results['errors'].append({
                            'product_code': product.code,
                            'error': f'Unknown operation: {operation}'
                        })
                        bulk_results['failed_operations'] += 1
                        continue

                    if result.ok:
                        bulk_results['successful_operations'] += 1
                        bulk_results['results'].append({
                            'product_code': product.code,
                            'success': True,
                            'message': result.msg,
                            'data': result.data
                        })
                    else:
                        bulk_results['failed_operations'] += 1
                        bulk_results['errors'].append({
                            'product_code': product.code,
                            'error': result.msg,
                            'error_code': result.code
                        })

                except Exception as e:
                    bulk_results['failed_operations'] += 1
                    bulk_results['errors'].append({
                        'product_code': getattr(product, 'code', '?'),
                        'error': str(e)
                    })

            # Determine overall result
            success_rate = bulk_results['successful_operations'] / bulk_results['total_products'] * 100

            if bulk_results['successful_operations'] == bulk_results['total_products']:
                return Result.success(
                    data=bulk_results,
                    msg=f'Bulk {operation} completed successfully for all {bulk_results["total_products"]} products'
                )
            elif bulk_results['successful_operations'] > 0:
                return Result.success(
                    data=bulk_results,
                    msg=f'Bulk {operation} completed with {success_rate:.1f}% success rate'
                )
            else:
                return Result.error(
                    code='BULK_OPERATION_FAILED',
                    msg=f'Bulk {operation} failed for all products',
                    data=bulk_results
                )

        except Exception as e:
            logger.error(f"Error in bulk lifecycle operation: {e}")
            return Result.error(
                code='BULK_OPERATION_ERROR',
                msg=f'Bulk lifecycle operation failed: {str(e)}'
            )

    # =====================================================
    # INTERNAL HELPER METHODS
    # =====================================================

    @staticmethod
    def _validate_lifecycle_inputs(product, new_status, user) -> Result:
        """Internal validation of lifecycle inputs"""
        if not product:
            return Result.error(
                code='INVALID_PRODUCT',
                msg='Product is required'
            )

        if not new_status:
            return Result.error(
                code='INVALID_STATUS',
                msg='New status is required'
            )

        # Check if status is valid
        valid_statuses = [choice[0] for choice in ProductLifecycleChoices.choices]
        if new_status not in valid_statuses:
            return Result.error(
                code='INVALID_STATUS_VALUE',
                msg=f'Invalid lifecycle status: {new_status}',
                data={'valid_statuses': valid_statuses}
            )

        # Check if it's actually a change
        if product.lifecycle_status == new_status:
            return Result.error(
                code='NO_CHANGE_NEEDED',
                msg=f'Product is already in {new_status} status'
            )

        return Result.success()

    @staticmethod
    @transaction.atomic
    def _execute_lifecycle_change(product, new_status, user, reason) -> Result:
        """Execute the actual lifecycle change"""
        try:
            old_status = product.lifecycle_status

            # Use product's set_lifecycle_status method if available
            if hasattr(product, 'set_lifecycle_status'):
                product.set_lifecycle_status(new_status, user, reason)
            else:
                # Fallback to direct assignment
                product.lifecycle_status = new_status
                if hasattr(product, 'updated_by'):
                    product.updated_by = user
                if hasattr(product, 'updated_at'):
                    product.updated_at = timezone.now()
                product.save()

            return Result.success(
                data={'old_status': old_status, 'new_status': new_status},
                msg='Lifecycle status updated successfully'
            )

        except Exception as e:
            return Result.error(
                code='EXECUTION_ERROR',
                msg=f'Failed to execute lifecycle change: {str(e)}'
            )

    @staticmethod
    def _handle_lifecycle_side_effects(product, old_status, new_status, user) -> Result:
        """Handle automatic side effects of lifecycle changes"""
        try:
            side_effects = {
                'purchase_blocking_changed': False,
                'sales_blocking_changed': False,
                'inventory_actions': [],
                'pricing_actions': [],
                'notifications_sent': []
            }

            # PHASE_OUT → Block new purchases
            if new_status == ProductLifecycleChoices.PHASE_OUT:
                if not product.purchase_blocked:
                    product.purchase_blocked = True
                    product.save(update_fields=['purchase_blocked'])
                    side_effects['purchase_blocking_changed'] = True
                    logger.info(f"Blocked purchases for product {product.code} (PHASE_OUT)")

            # ACTIVE → Unblock if was blocked
            elif new_status == ProductLifecycleChoices.ACTIVE:
                if product.purchase_blocked:
                    product.purchase_blocked = False
                    product.save(update_fields=['purchase_blocked'])
                    side_effects['purchase_blocking_changed'] = True
                    logger.info(f"Unblocked purchases for product {product.code} (ACTIVE)")

            # DISCONTINUED → Block both sales and purchases
            elif new_status == ProductLifecycleChoices.DISCONTINUED:
                changes_made = []
                if not product.purchase_blocked:
                    product.purchase_blocked = True
                    changes_made.append('purchase_blocked')
                    side_effects['purchase_blocking_changed'] = True

                if not product.sales_blocked:
                    product.sales_blocked = True
                    changes_made.append('sales_blocked')
                    side_effects['sales_blocking_changed'] = True

                if changes_made:
                    product.save(update_fields=changes_made)
                    logger.info(f"Blocked sales and purchases for product {product.code} (DISCONTINUED)")

            # Try to update pricing if pricing service is available
            try:
                if new_status in [ProductLifecycleChoices.PHASE_OUT, ProductLifecycleChoices.DISCONTINUED]:
                    # Could trigger clearance pricing
                    side_effects['pricing_actions'].append('clearance_pricing_candidate')
            except Exception as e:
                logger.warning(f"Could not handle pricing side effects: {e}")

            # Try to handle inventory implications
            try:
                if new_status == ProductLifecycleChoices.DISCONTINUED:
                    side_effects['inventory_actions'].append('inventory_clearance_needed')
            except Exception as e:
                logger.warning(f"Could not handle inventory side effects: {e}")

            return Result.success(
                data=side_effects,
                msg='Side effects handled successfully'
            )

        except Exception as e:
            return Result.error(
                code='SIDE_EFFECTS_ERROR',
                msg=f'Error handling side effects: {str(e)}'
            )

    @staticmethod
    def _get_updated_restrictions(product) -> Dict:
        """Get updated restriction info after lifecycle change"""
        return {
            'is_sellable': product.is_sellable,
            'is_purchasable': product.is_purchasable,
            'sales_blocked': product.sales_blocked,
            'purchase_blocked': product.purchase_blocked,
            'allow_negative_sales': getattr(product, 'allow_negative_sales', False),
            'restrictions_summary': getattr(product, 'get_restrictions_summary', lambda: '')()
        }

    @staticmethod
    def _get_lifecycle_history(product) -> List[Dict]:
        """Get lifecycle change history if available"""
        # This would integrate with audit/history system if available
        return []

    @staticmethod
    def _analyze_status_implications(product) -> Dict:
        """Analyze implications of current lifecycle status"""
        status = product.lifecycle_status

        implications = {
            'status': status,
            'can_sell': product.is_sellable,
            'can_purchase': product.is_purchasable,
            'business_implications': [],
            'operational_implications': [],
            'financial_implications': []
        }

        if status == ProductLifecycleChoices.NEW:
            implications['business_implications'] = [
                'Product is new and may require market introduction',
                'Consider promotional pricing for market entry'
            ]
            implications['operational_implications'] = [
                'May need special handling for new product launch',
                'Monitor initial sales performance closely'
            ]

        elif status == ProductLifecycleChoices.PHASE_OUT:
            implications['business_implications'] = [
                'Product is being phased out - no new purchases',
                'Focus on inventory clearance'
            ]
            implications['operational_implications'] = [
                'Stop new procurement',
                'Clear existing inventory'
            ]
            implications['financial_implications'] = [
                'Consider clearance pricing',
                'Monitor inventory carrying costs'
            ]

        elif status == ProductLifecycleChoices.DISCONTINUED:
            implications['business_implications'] = [
                'Product is discontinued - no sales or purchases',
                'Complete phase-out of product'
            ]
            implications['operational_implications'] = [
                'Remove from all active processes',
                'Archive product data'
            ]

        return implications

    @staticmethod
    def _get_available_transitions(product) -> List[Dict]:
        """Get available lifecycle transitions"""
        current_status = product.lifecycle_status

        # Define allowed transitions
        transition_matrix = {
            ProductLifecycleChoices.NEW: [ProductLifecycleChoices.ACTIVE],
            ProductLifecycleChoices.ACTIVE: [ProductLifecycleChoices.PHASE_OUT, ProductLifecycleChoices.DISCONTINUED],
            ProductLifecycleChoices.PHASE_OUT: [ProductLifecycleChoices.DISCONTINUED, ProductLifecycleChoices.ACTIVE],
            ProductLifecycleChoices.DISCONTINUED: [],  # Usually no transitions from discontinued
            ProductLifecycleChoices.ARCHIVED: []  # No transitions from archived
        }

        allowed_statuses = transition_matrix.get(current_status, [])

        transitions = []
        for status in allowed_statuses:
            transitions.append({
                'to_status': status,
                'display_name': dict(ProductLifecycleChoices.choices).get(status, status),
                'requires_confirmation': status in [ProductLifecycleChoices.DISCONTINUED],
                'warning_message': ProductLifecycleService._get_transition_warning(current_status, status)
            })

        return transitions

    @staticmethod
    def _get_transition_warning(from_status, to_status) -> Optional[str]:
        """Get warning message for specific transitions"""
        if to_status == ProductLifecycleChoices.DISCONTINUED:
            return "This will block all sales and purchases for this product"
        elif to_status == ProductLifecycleChoices.PHASE_OUT:
            return "This will block new purchases but allow continued sales"
        return None

    @staticmethod
    def _calculate_lifecycle_metrics(product, history) -> Dict:
        """Calculate lifecycle-related metrics"""
        metrics = {
            'days_in_current_status': 0,
            'total_lifecycle_days': 0,
            'status_changes_count': len(history),
            'average_status_duration': 0
        }

        # Calculate days in current status
        if hasattr(product, 'updated_at'):
            metrics['days_in_current_status'] = (timezone.now() - product.updated_at).days

        # Calculate total lifecycle if created_at is available
        if hasattr(product, 'created_at'):
            metrics['total_lifecycle_days'] = (timezone.now() - product.created_at).days

        return metrics

    @staticmethod
    def _analyze_business_impact(product) -> Dict:
        """Analyze business impact of current lifecycle status"""
        impact = {
            'revenue_impact': 'neutral',
            'operational_impact': 'neutral',
            'inventory_impact': 'neutral',
            'impact_description': []
        }

        if not product.is_sellable:
            impact['revenue_impact'] = 'negative'
            impact['impact_description'].append('No revenue possible - sales blocked')

        if not product.is_purchasable:
            impact['operational_impact'] = 'negative'
            impact['impact_description'].append('Cannot replenish inventory - purchases blocked')

        return impact

    @staticmethod
    def _generate_lifecycle_recommendations(product) -> List[str]:
        """Generate recommendations based on lifecycle analysis"""
        recommendations = []
        status = product.lifecycle_status

        if status == ProductLifecycleChoices.NEW:
            recommendations.append('Consider moving to ACTIVE status once product launch is complete')
            recommendations.append('Monitor initial sales performance')

        elif status == ProductLifecycleChoices.PHASE_OUT:
            recommendations.append('Focus on inventory clearance strategies')
            recommendations.append('Consider promotional pricing to move stock')

        elif status == ProductLifecycleChoices.DISCONTINUED:
            recommendations.append('Ensure all inventory is cleared')
            recommendations.append('Archive product documentation')

        # Check for inventory-related recommendations
        try:
            from inventory.models import InventoryItem
            has_inventory = InventoryItem.objects.filter(product=product, current_qty__gt=0).exists()

            if has_inventory and status == ProductLifecycleChoices.DISCONTINUED:
                recommendations.append('Clear remaining inventory before finalizing discontinuation')
        except ImportError:
            pass

        return recommendations

    @staticmethod
    def _check_status_consistency(product) -> List[str]:
        """Check consistency between status and product properties"""
        issues = []

        if product.lifecycle_status == ProductLifecycleChoices.ACTIVE:
            if product.sales_blocked:
                issues.append('Product is ACTIVE but sales are blocked')
            if product.purchase_blocked:
                issues.append('Product is ACTIVE but purchases are blocked')

        elif product.lifecycle_status == ProductLifecycleChoices.DISCONTINUED:
            if not product.sales_blocked:
                issues.append('Product is DISCONTINUED but sales are not blocked')
            if not product.purchase_blocked:
                issues.append('Product is DISCONTINUED but purchases are not blocked')

        return issues

    @staticmethod
    def _check_business_conflicts(product) -> List[str]:
        """Check for business logic conflicts"""
        conflicts = []

        # Check if product has active orders while discontinued
        # This would require integration with purchases/sales modules

        return conflicts

    @staticmethod
    def _check_progression_logic(product) -> List[str]:
        """Check if lifecycle progression makes sense"""
        issues = []

        # Add checks for logical progression
        # e.g., NEW -> ACTIVE is normal, NEW -> DISCONTINUED might be unusual

        return issues

    # =====================================================
    # LEGACY METHODS - BACKWARD COMPATIBILITY
    # =====================================================

    @staticmethod
    @transaction.atomic
    def change_lifecycle_status(
            product: Product,
            new_status: str,
            user=None,
            reason: str = ""
    ) -> Dict:
        """
        LEGACY METHOD: Use change_product_lifecycle() for new code

        Maintained for backward compatibility
        """
        result = ProductLifecycleService.change_product_lifecycle(product, new_status, user, reason)

        if result.ok:
            data = result.data
            return {
                'success': True,
                'message': result.msg,
                'product': product,
                'old_status': data.get('old_status'),
                'new_status': data.get('new_status')
            }
        else:
            return {
                'success': False,
                'message': result.msg,
                'product': product,
                'error_code': result.code
            }



# =====================================================
# MODULE EXPORTS
# =====================================================

__all__ = ['ProductLifecycleService']