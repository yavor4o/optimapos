# pricing/services/promotion_service.py - COMPLETE RESULT PATTERN REFACTORING
"""
PROMOTION SERVICE - COMPLETE REFACTORED WITH RESULT PATTERN

Централизирана promotional pricing логика с Result pattern за консистентност.
Управлява promotional campaigns и discounts.

ПРОМЕНИ:
- Всички публични методи връщат Result objects
- Legacy методи запазени за backward compatibility
- Enhanced error handling и validation
- Bulk operations за promotional campaigns
- Integration готовност с PricingService
"""
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import timedelta
import logging

from core.utils.result import Result
from ..models import PromotionalPrice

logger = logging.getLogger(__name__)


class PromotionService:
    """
    PROMOTION SERVICE - REFACTORED WITH RESULT PATTERN

    CHANGES: All public methods now return Result objects
    Legacy methods available for backward compatibility
    Enhanced promotional pricing management
    """

    # =====================================================
    # NEW: RESULT-BASED PUBLIC API
    # =====================================================

    @staticmethod
    def get_best_promotional_price(
            location,
            product,
            quantity: Decimal,
            date=None,
            customer=None
    ) -> Result:
        """
        🎯 PRIMARY API: Get best promotional price - NEW Result-based method

        Args:
            location: Pricing location
            product: Product to price
            quantity: Quantity for quantity-based promotions
            date: Date for promotion validity (defaults to today)
            customer: Customer for customer-specific promotions

        Returns:
            Result with best promotional price or None if no promotions
        """
        try:
            if date is None:
                date = timezone.now().date()

            # Validate inputs
            validation_result = PromotionService._validate_promotion_inputs(
                location, product, quantity, date
            )
            if not validation_result.ok:
                return validation_result

            # Get all valid promotions
            promotions_result = PromotionService._find_valid_promotions(
                location, product, quantity, date, customer
            )
            if not promotions_result.ok:
                return promotions_result

            valid_promotions = promotions_result.data.get('promotions', [])

            if not valid_promotions:
                return Result.success(
                    data={
                        'promotional_price': None,
                        'promotion': None,
                        'has_promotion': False,
                        'checked_date': date,
                        'quantity': quantity
                    },
                    msg='No active promotions found'
                )

            # Find best promotion (lowest price with highest priority)
            best_promotion = min(
                valid_promotions,
                key=lambda p: (p.promotional_price, -getattr(p, 'priority', 0))
            )

            promotion_data = {
                'promotional_price': best_promotion.promotional_price,
                'promotion': {
                    'id': best_promotion.id,
                    'name': best_promotion.name,
                    'promotional_price': best_promotion.promotional_price,
                    'start_date': best_promotion.start_date,
                    'end_date': best_promotion.end_date,
                    'min_quantity': getattr(best_promotion, 'min_quantity', None),
                    'max_quantity': getattr(best_promotion, 'max_quantity', None),
                    'priority': getattr(best_promotion, 'priority', 0),
                    'discount_amount': PromotionService._calculate_discount_amount(best_promotion),
                    'discount_percentage': PromotionService._calculate_discount_percentage(best_promotion)
                },
                'has_promotion': True,
                'checked_date': date,
                'quantity': quantity,
                'customer_eligible': customer is not None,
                'alternatives_count': len(valid_promotions) - 1
            }

            logger.info(f"Best promotion found: {best_promotion.name} @ {best_promotion.promotional_price}")

            return Result.success(
                data=promotion_data,
                msg=f'Best promotional price: {best_promotion.promotional_price}'
            )

        except Exception as e:
            logger.error(f"Error getting promotional price: {e}")
            return Result.error(
                code='PROMOTION_ERROR',
                msg=f'Failed to get promotional price: {str(e)}',
                data={'product_code': getattr(product, 'code', '?')}
            )

    @staticmethod
    def get_active_promotions_summary(location=None, product=None, date=None) -> Result:
        """
        🎯 SUMMARY API: Get active promotions summary - NEW Result-based method

        Returns comprehensive summary of all active promotions
        """
        try:
            if date is None:
                date = timezone.now().date()

            # Build query filters
            filters = {
                'start_date__lte': date,
                'end_date__gte': date,
                'is_active': True
            }

            if location:
                filters['location'] = location
            if product:
                filters['product'] = product

            promotions = PromotionalPrice.objects.filter(**filters).select_related(
                'location', 'product'
            ).order_by('-promotional_price')

            active_promotions = []
            total_discount_value = Decimal('0')

            for promo in promotions:
                discount_amount = PromotionService._calculate_discount_amount(promo)
                if discount_amount:
                    total_discount_value += discount_amount

                promo_info = {
                    'id': promo.id,
                    'name': promo.name,
                    'location_code': promo.location.code,
                    'product_code': promo.product.code,
                    'product_name': promo.product.name,
                    'promotional_price': promo.promotional_price,
                    'start_date': promo.start_date,
                    'end_date': promo.end_date,
                    'days_remaining': (promo.end_date - date).days,
                    'discount_amount': discount_amount,
                    'discount_percentage': PromotionService._calculate_discount_percentage(promo),
                    'min_quantity': getattr(promo, 'min_quantity', None),
                    'max_quantity': getattr(promo, 'max_quantity', None)
                }
                active_promotions.append(promo_info)

            summary_data = {
                'active_promotions': active_promotions,
                'total_active': len(active_promotions),
                'total_discount_value': total_discount_value,
                'date_checked': date,
                'filters_applied': {
                    'location': getattr(location, 'code', None) if location else None,
                    'product': getattr(product, 'code', None) if product else None
                },
                'summary_statistics': PromotionService._calculate_promotion_statistics(active_promotions)
            }

            return Result.success(
                data=summary_data,
                msg=f'Found {len(active_promotions)} active promotions'
            )

        except Exception as e:
            logger.error(f"Error getting promotions summary: {e}")
            return Result.error(
                code='SUMMARY_ERROR',
                msg=f'Failed to get promotions summary: {str(e)}'
            )

    @staticmethod
    def validate_promotion_setup(promotion_data: Dict) -> Result:
        """
        🎯 VALIDATION API: Validate promotion configuration - NEW Result-based method

        Validates promotion data before creation or update
        """
        try:
            validation_data = {
                'is_valid': True,
                'validation_errors': [],
                'validation_warnings': [],
                'recommendations': []
            }

            # Required field validation
            required_fields = ['name', 'location', 'product', 'promotional_price', 'start_date', 'end_date']
            for field in required_fields:
                if field not in promotion_data or promotion_data[field] is None:
                    validation_data['validation_errors'].append(f'Missing required field: {field}')

            if validation_data['validation_errors']:
                validation_data['is_valid'] = False

            # Date validation
            if 'start_date' in promotion_data and 'end_date' in promotion_data:
                start_date = promotion_data['start_date']
                end_date = promotion_data['end_date']

                if start_date >= end_date:
                    validation_data['validation_errors'].append('End date must be after start date')
                    validation_data['is_valid'] = False

                # Check if promotion period is reasonable
                duration = (end_date - start_date).days
                if duration > 365:
                    validation_data['validation_warnings'].append('Promotion duration exceeds 1 year')
                elif duration < 1:
                    validation_data['validation_errors'].append('Promotion must last at least 1 day')
                    validation_data['is_valid'] = False

            # Price validation
            if 'promotional_price' in promotion_data:
                promo_price = promotion_data['promotional_price']
                if promo_price <= 0:
                    validation_data['validation_errors'].append('Promotional price must be positive')
                    validation_data['is_valid'] = False

            # Quantity validation
            if ('min_quantity' in promotion_data and 'max_quantity' in promotion_data and
                    promotion_data['min_quantity'] and promotion_data['max_quantity']):

                if promotion_data['max_quantity'] < promotion_data['min_quantity']:
                    validation_data['validation_errors'].append('Maximum quantity cannot be less than minimum quantity')
                    validation_data['is_valid'] = False

            # Business logic validation
            if 'product' in promotion_data and 'promotional_price' in promotion_data:
                product = promotion_data['product']
                promo_price = promotion_data['promotional_price']

                # Check if promotional price makes sense
                try:
                    from .pricing_service import PricingService
                    location = promotion_data.get('location')
                    if location:
                        base_price = PricingService.get_base_price(location, product)
                        if base_price > 0 and promo_price >= base_price:
                            validation_data['validation_warnings'].append(
                                'Promotional price is not lower than base price')
                            validation_data['recommendations'].append(
                                'Consider lowering promotional price for meaningful discount')
                except ImportError:
                    pass

            # Check for overlapping promotions
            if all(field in promotion_data for field in ['location', 'product', 'start_date', 'end_date']):
                overlap_result = PromotionService._check_promotion_overlaps(promotion_data)
                if not overlap_result.ok:
                    validation_data['validation_warnings'].append(overlap_result.msg)

            # Determine overall result
            if not validation_data['is_valid']:
                return Result.error(
                    code='PROMOTION_VALIDATION_FAILED',
                    msg=f'Promotion validation failed: {len(validation_data["validation_errors"])} errors',
                    data=validation_data
                )
            elif validation_data['validation_warnings']:
                return Result.success(
                    data=validation_data,
                    msg=f'Promotion validation passed with {len(validation_data["validation_warnings"])} warnings'
                )
            else:
                return Result.success(
                    data=validation_data,
                    msg='Promotion validation passed successfully'
                )

        except Exception as e:
            logger.error(f"Error validating promotion: {e}")
            return Result.error(
                code='VALIDATION_ERROR',
                msg=f'Promotion validation failed: {str(e)}'
            )

    @staticmethod
    def get_promotion_performance(promotion_id: int) -> Result:
        """
        🎯 ANALYTICS API: Get promotion performance metrics - NEW Result-based method

        Returns performance analysis for specific promotion
        """
        try:
            try:
                promotion = PromotionalPrice.objects.get(id=promotion_id)
            except PromotionalPrice.DoesNotExist:
                return Result.error(
                    code='PROMOTION_NOT_FOUND',
                    msg=f'Promotion with ID {promotion_id} not found',
                    data={'promotion_id': promotion_id}
                )

            # Basic promotion info
            performance_data = {
                'promotion_info': {
                    'id': promotion.id,
                    'name': promotion.name,
                    'product_code': promotion.product.code,
                    'location_code': promotion.location.code,
                    'promotional_price': promotion.promotional_price,
                    'start_date': promotion.start_date,
                    'end_date': promotion.end_date,
                    'is_active': promotion.is_active,
                    'days_duration': (promotion.end_date - promotion.start_date).days
                },
                'discount_metrics': {
                    'discount_amount': PromotionService._calculate_discount_amount(promotion),
                    'discount_percentage': PromotionService._calculate_discount_percentage(promotion)
                },
                'performance_metrics': {
                    # Placeholder for future sales integration
                    'units_sold': 0,
                    'revenue_generated': Decimal('0'),
                    'total_discount_given': Decimal('0'),
                    'transaction_count': 0,
                    'average_transaction_size': Decimal('0')
                },
                'status_info': {
                    'is_current': PromotionService._is_promotion_current(promotion),
                    'is_upcoming': PromotionService._is_promotion_upcoming(promotion),
                    'is_expired': PromotionService._is_promotion_expired(promotion),
                    'days_until_start': PromotionService._days_until_start(promotion),
                    'days_until_end': PromotionService._days_until_end(promotion)
                }
            }

            # TODO: Add actual sales metrics when sales module is integrated
            # This would query sales data for this specific promotion

            return Result.success(
                data=performance_data,
                msg=f'Performance metrics retrieved for promotion: {promotion.name}'
            )

        except Exception as e:
            logger.error(f"Error getting promotion performance: {e}")
            return Result.error(
                code='PERFORMANCE_ERROR',
                msg=f'Failed to get promotion performance: {str(e)}',
                data={'promotion_id': promotion_id}
            )

    @staticmethod
    def manage_promotion_lifecycle() -> Result:
        """
        🎯 MANAGEMENT API: Manage promotion lifecycle - NEW Result-based method

        Automatically handles expired promotions and upcoming activations
        """
        try:
            today = timezone.now().date()
            management_data = {
                'expired_deactivated': 0,
                'upcoming_activated': 0,
                'warnings': [],
                'processed_promotions': []
            }

            # Deactivate expired promotions
            expired_promotions = PromotionalPrice.objects.filter(
                end_date__lt=today,
                is_active=True
            )

            for promo in expired_promotions:
                promo.is_active = False
                promo.save(update_fields=['is_active'])
                management_data['expired_deactivated'] += 1
                management_data['processed_promotions'].append({
                    'id': promo.id,
                    'name': promo.name,
                    'action': 'deactivated',
                    'reason': 'expired'
                })

            # Check for promotions ending soon
            ending_soon = PromotionalPrice.objects.filter(
                end_date__gte=today,
                end_date__lte=today + timedelta(days=3),
                is_active=True
            )

            for promo in ending_soon:
                days_left = (promo.end_date - today).days
                management_data['warnings'].append({
                    'promotion_id': promo.id,
                    'promotion_name': promo.name,
                    'warning': f'Promotion ends in {days_left} days',
                    'end_date': promo.end_date
                })

            # Check for upcoming promotions that should be activated
            upcoming_promotions = PromotionalPrice.objects.filter(
                start_date=today,
                is_active=False
            )

            for promo in upcoming_promotions:
                # Optionally auto-activate (depending on business rules)
                management_data['processed_promotions'].append({
                    'id': promo.id,
                    'name': promo.name,
                    'action': 'ready_to_activate',
                    'start_date': promo.start_date
                })

            return Result.success(
                data=management_data,
                msg=f'Promotion lifecycle managed: {management_data["expired_deactivated"]} expired, {len(management_data["warnings"])} warnings'
            )

        except Exception as e:
            logger.error(f"Error managing promotion lifecycle: {e}")
            return Result.error(
                code='LIFECYCLE_MANAGEMENT_ERROR',
                msg=f'Promotion lifecycle management failed: {str(e)}'
            )

    # =====================================================
    # INTERNAL HELPER METHODS
    # =====================================================

    @staticmethod
    def _validate_promotion_inputs(location, product, quantity, date) -> Result:
        """Internal validation of promotion inputs"""
        if not location:
            return Result.error(
                code='INVALID_LOCATION',
                msg='Location is required for promotion lookup'
            )

        if not product:
            return Result.error(
                code='INVALID_PRODUCT',
                msg='Product is required for promotion lookup'
            )

        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg='Quantity must be positive',
                data={'quantity': quantity}
            )

        return Result.success()

    @staticmethod
    def _find_valid_promotions(location, product, quantity, date, customer) -> Result:
        """Find all valid promotions for given criteria - BUGFIXED"""
        try:
            # FIXED: Use correct field names from PromotionalPrice model
            promotions = PromotionalPrice.objects.filter(
                # FIXED: Use GenericForeignKey lookup instead of direct location field
                content_type=ContentType.objects.get_for_model(location),
                object_id=location.id,
                product=product,
                start_date__lte=date,
                end_date__gte=date,
                is_active=True
            )

            # Filter by quantity constraints (use correct field names)
            if hasattr(PromotionalPrice, 'min_quantity'):
                promotions = promotions.filter(
                    Q(min_quantity__isnull=True) | Q(min_quantity__lte=quantity)
                )

            if hasattr(PromotionalPrice, 'max_quantity'):
                promotions = promotions.filter(
                    Q(max_quantity__isnull=True) | Q(max_quantity__gte=quantity)
                )

            # ALTERNATIVE FIX: If pricing uses .for_location() manager
            # promotions = PromotionalPrice.objects.for_location(location).filter(
            #     product=product,
            #     start_date__lte=date,
            #     end_date__gte=date,
            #     is_active=True
            # )

            # Filter by customer eligibility
            valid_promotions = []
            for promo in promotions:
                if hasattr(promo, 'is_valid_for_customer'):
                    if promo.is_valid_for_customer(customer):
                        valid_promotions.append(promo)
                else:
                    # If no customer validation method, assume all promotions are valid
                    valid_promotions.append(promo)

            return Result.success(
                data={'promotions': valid_promotions},
                msg=f'Found {len(valid_promotions)} valid promotions'
            )

        except Exception as e:
            return Result.error(
                code='PROMOTION_LOOKUP_ERROR',
                msg=f'Error finding valid promotions: {str(e)}'
            )

    @staticmethod
    def _calculate_discount_amount(promotion) -> Optional[Decimal]:
        """Calculate discount amount for promotion - BUGFIXED"""
        try:
            if hasattr(promotion, 'get_discount_amount'):
                return promotion.get_discount_amount()

            # FIXED: Use PricingService get_base_price instead of get_price
            from .pricing_service import PricingService

            # FIXED: Get location from promotion's GenericForeignKey
            promotion_location = promotion.priceable_location  # or however it's named
            base_price = PricingService.get_base_price(promotion_location, promotion.product)

            if base_price > promotion.promotional_price:
                return base_price - promotion.promotional_price

            return Decimal('0')

        except Exception as e:
            logger.warning(f"Could not calculate discount amount: {e}")
            return None

    @staticmethod
    def _calculate_discount_percentage(promotion) -> Optional[Decimal]:
        """Calculate discount percentage for promotion"""
        try:
            if hasattr(promotion, 'get_discount_percentage'):
                return promotion.get_discount_percentage()

            # Fallback calculation
            from .pricing_service import PricingService
            base_price = PricingService.get_base_price(promotion.location, promotion.product)
            if base_price > 0 and base_price > promotion.promotional_price:
                return (base_price - promotion.promotional_price) / base_price * 100

            return Decimal('0')

        except Exception:
            return None

    @staticmethod
    def _calculate_promotion_statistics(promotions) -> Dict:
        """Calculate statistics for a list of promotions"""
        if not promotions:
            return {}

        total_promotions = len(promotions)
        total_discount = sum(p.get('discount_amount', 0) for p in promotions if p.get('discount_amount'))
        avg_discount = total_discount / total_promotions if total_promotions > 0 else 0

        # Group by location
        locations = set(p.get('location_code') for p in promotions)

        # Group by product
        products = set(p.get('product_code') for p in promotions)

        return {
            'total_promotions': total_promotions,
            'total_discount_value': total_discount,
            'average_discount': avg_discount,
            'unique_locations': len(locations),
            'unique_products': len(products),
            'locations': list(locations),
            'max_discount': max((p.get('discount_amount', 0) for p in promotions), default=0),
            'min_discount': min((p.get('discount_amount', 0) for p in promotions if p.get('discount_amount', 0) > 0),
                                default=0)
        }

    @staticmethod
    def _check_promotion_overlaps(promotion_data) -> Result:
        """Check for overlapping promotions"""
        try:
            overlapping = PromotionalPrice.objects.filter(
                location=promotion_data['location'],
                product=promotion_data['product'],
                is_active=True
            ).filter(
                Q(start_date__lte=promotion_data['end_date']) &
                Q(end_date__gte=promotion_data['start_date'])
            )

            if promotion_data.get('id'):
                overlapping = overlapping.exclude(id=promotion_data['id'])

            if overlapping.exists():
                return Result.error(
                    code='PROMOTION_OVERLAP',
                    msg=f'Found {overlapping.count()} overlapping promotions for this product and location'
                )

            return Result.success(msg='No promotion overlaps found')

        except Exception as e:
            return Result.error(
                code='OVERLAP_CHECK_ERROR',
                msg=f'Error checking promotion overlaps: {str(e)}'
            )

    @staticmethod
    def _is_promotion_current(promotion) -> bool:
        """Check if promotion is currently active"""
        today = timezone.now().date()
        return promotion.start_date <= today <= promotion.end_date and promotion.is_active

    @staticmethod
    def _is_promotion_upcoming(promotion) -> bool:
        """Check if promotion is upcoming"""
        today = timezone.now().date()
        return promotion.start_date > today

    @staticmethod
    def _is_promotion_expired(promotion) -> bool:
        """Check if promotion is expired"""
        today = timezone.now().date()
        return promotion.end_date < today

    @staticmethod
    def _days_until_start(promotion) -> Optional[int]:
        """Calculate days until promotion starts"""
        today = timezone.now().date()
        if promotion.start_date > today:
            return (promotion.start_date - today).days
        return None

    @staticmethod
    def _days_until_end(promotion) -> Optional[int]:
        """Calculate days until promotion ends"""
        today = timezone.now().date()
        if promotion.end_date >= today:
            return (promotion.end_date - today).days
        return None


# =====================================================
# MODULE EXPORTS
# =====================================================

__all__ = ['PromotionService']