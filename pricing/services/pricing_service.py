# pricing/services/pricing_service.py - COMPLETE RESULT PATTERN REFACTORING
"""
PRICING SERVICE - COMPLETE REFACTORED WITH RESULT PATTERN

Централизирана pricing логика с Result pattern за консистентност.
Запазена пълна функционалност от оригиналния service.

ПРОМЕНИ:
- Всички публични методи връщат Result objects
- Legacy методи запазени за backward compatibility
- Enhanced error handling и validation
- Structured pricing data в responses
- Integration готовност с останалите services
"""

from django.utils import timezone
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal
from typing import Optional, Dict, List
import logging

from core.utils.result import Result
from ..models import (
    ProductPrice, ProductPriceByGroup,
    ProductStepPrice, PromotionalPrice, PackagingPrice
)

logger = logging.getLogger(__name__)


class PricingService:
    """
    PRICING SERVICE - REFACTORED WITH RESULT PATTERN

    CHANGES: All public methods now return Result objects
    Legacy methods available for backward compatibility
    ALL ORIGINAL FUNCTIONALITY PRESERVED + Enhanced data structures
    """

    # =====================================================
    # NEW: RESULT-BASED PUBLIC API
    # =====================================================

    @staticmethod
    def get_product_pricing(
            location,
            product,
            customer=None,
            quantity: Decimal = Decimal('1'),
            date=None
    ) -> Result:
        """
        🎯 PRIMARY API: Get complete pricing information - NEW Result-based method

        Args:
            location: Pricing location (must support ILocation protocol)
            product: Product to price
            customer: Customer for group pricing (optional)
            quantity: Quantity for step pricing
            date: Date for promotional pricing (defaults to today)

        Returns:
            Result with comprehensive pricing data or error
        """
        try:
            if date is None:
                date = timezone.now().date()

            # Validate inputs
            validation_result = PricingService._validate_pricing_inputs(
                location, product, quantity
            )
            if not validation_result.ok:
                return validation_result

            # Get all pricing components using legacy methods
            base_price = PricingService._get_base_price_internal(location, product)
            promo_price = PricingService._get_promotional_price_internal(
                location, product, quantity, date, customer
            )
            group_price = None
            if customer and hasattr(customer, 'price_group') and customer.price_group:
                group_price = PricingService._get_group_price_internal(
                    location, product, customer.price_group, quantity
                )

            step_price = PricingService._get_step_price_internal(location, product, quantity)
            fallback_price = PricingService._get_fallback_price_internal(location, product)
            cost_price = PricingService._get_inventory_cost_internal(location, product)

            # Determine final price and pricing rule
            final_price, pricing_rule = PricingService._determine_final_price(
                base_price, promo_price, group_price, step_price, fallback_price
            )

            # Calculate profit metrics
            profit_data = PricingService._calculate_profit_metrics(cost_price, final_price)

            # Prepare comprehensive pricing data
            pricing_data = {
                'final_price': final_price,
                'pricing_rule': pricing_rule,
                'base_price': base_price,
                'promotional_price': promo_price,
                'group_price': group_price,
                'step_price': step_price,
                'fallback_price': fallback_price,
                'cost_price': cost_price,
                'quantity': quantity,
                'date': date,
                'location_code': getattr(location, 'code', str(location)),
                'product_code': getattr(product, 'code', str(product)),
                'customer_info': {
                    'customer_id': getattr(customer, 'id', None),
                    'price_group': getattr(customer.price_group, 'name', None) if customer and hasattr(customer,
                                                                                                       'price_group') else None
                },
                'profit_metrics': profit_data,
                'pricing_timestamp': timezone.now()
            }

            logger.info(f"Pricing calculated: {product} @ {location} = {final_price} ({pricing_rule})")

            return Result.success(
                data=pricing_data,
                msg=f'Pricing calculated successfully using {pricing_rule}'
            )

        except Exception as e:
            logger.error(f"Error in product pricing: {e}")
            return Result.error(
                code='PRICING_ERROR',
                msg=f'Failed to calculate pricing: {str(e)}',
                data={'product_code': getattr(product, 'code', '?'), 'location_code': getattr(location, 'code', '?')}
            )

    @staticmethod
    def get_pricing_analysis(
            location,
            product,
            customer=None,
            quantity: Decimal = Decimal('1')
    ) -> Result:
        """
        🎯 ANALYSIS API: Get comprehensive pricing analysis - NEW Result-based method

        Returns detailed analysis of all pricing components and their impact
        """
        try:
            # Get main pricing data
            pricing_result = PricingService.get_product_pricing(
                location, product, customer, quantity
            )

            if not pricing_result.ok:
                return pricing_result

            pricing_data = pricing_result.data

            # Get all available pricing options
            all_prices_result = PricingService.get_all_pricing_options(location, product, customer)
            if not all_prices_result.ok:
                logger.warning(f"Could not get all pricing options: {all_prices_result.msg}")
                all_options = {}
            else:
                all_options = all_prices_result.data

            # Calculate discounts and savings
            base_price = pricing_data.get('base_price', Decimal('0'))
            final_price = pricing_data.get('final_price', Decimal('0'))

            discount_analysis = {
                'customer_discount': base_price - final_price if base_price > final_price else Decimal('0'),
                'discount_percentage': ((
                                                    base_price - final_price) / base_price * 100) if base_price > 0 and base_price > final_price else Decimal(
                    '0'),
                'savings_amount': (base_price - final_price) * quantity if base_price > final_price else Decimal('0')
            }

            # Price comparison with other rules
            price_comparison = {
                'cheapest_available': min([p for p in [
                    pricing_data.get('base_price'),
                    pricing_data.get('promotional_price'),
                    pricing_data.get('group_price'),
                    pricing_data.get('step_price')
                ] if p and p > 0], default=Decimal('0')),
                'most_expensive': max([p for p in [
                    pricing_data.get('base_price'),
                    pricing_data.get('promotional_price'),
                    pricing_data.get('group_price'),
                    pricing_data.get('step_price')
                ] if p and p > 0], default=Decimal('0'))
            }

            analysis_data = {
                'pricing_summary': pricing_data,
                'all_pricing_options': all_options,
                'discount_analysis': discount_analysis,
                'price_comparison': price_comparison,
                'recommendations': PricingService._generate_pricing_recommendations(pricing_data, all_options),
                'analysis_timestamp': timezone.now()
            }

            return Result.success(
                data=analysis_data,
                msg='Pricing analysis completed successfully'
            )

        except Exception as e:
            logger.error(f"Error in pricing analysis: {e}")
            return Result.error(
                code='ANALYSIS_ERROR',
                msg=f'Pricing analysis failed: {str(e)}'
            )

    @staticmethod
    def get_all_pricing_options(location, product, customer=None) -> Result:
        """
        🎯 OPTIONS API: Get all available pricing options - NEW Result-based method

        Returns all pricing rules and their values for the product
        """
        try:
            options_data = {
                'base_price': PricingService._get_base_price_internal(location, product),
                'fallback_price': PricingService._get_fallback_price_internal(location, product),
                'cost_price': PricingService._get_inventory_cost_internal(location, product),
                'step_prices': [],
                'group_prices': [],
                'promotions': [],
                'packaging_prices': []
            }

            # Get step prices
            try:
                step_prices = ProductStepPrice.objects.for_location(location).filter(
                    product=product,
                    is_active=True
                ).order_by('min_quantity')

                for step_price in step_prices:
                    options_data['step_prices'].append({
                        'min_quantity': step_price.min_quantity,
                        'price': step_price.price,
                        'savings_vs_base': options_data['base_price'] - step_price.price if options_data[
                                                                                                'base_price'] > step_price.price else Decimal(
                            '0')
                    })
            except Exception as e:
                logger.warning(f"Error getting step prices: {e}")

            # Get group prices
            try:
                group_prices = ProductPriceByGroup.objects.for_location(location).filter(
                    product=product,
                    is_active=True
                ).select_related('customer_group')

                for group_price in group_prices:
                    options_data['group_prices'].append({
                        'group_name': group_price.customer_group.name,
                        'price': group_price.price,
                        'savings_vs_base': options_data['base_price'] - group_price.price if options_data[
                                                                                                 'base_price'] > group_price.price else Decimal(
                            '0')
                    })
            except Exception as e:
                logger.warning(f"Error getting group prices: {e}")

            # Get active promotions
            try:
                current_date = timezone.now().date()
                promotions = PromotionalPrice.objects.for_location(location).filter(
                    product=product,
                    is_active=True,
                    start_date__lte=current_date,
                    end_date__gte=current_date
                )

                for promo in promotions:
                    options_data['promotions'].append({
                        'name': promo.name,
                        'price': promo.price,
                        'start_date': promo.start_date,
                        'end_date': promo.end_date,
                        'min_quantity': getattr(promo, 'min_quantity', None),
                        'savings_vs_base': options_data['base_price'] - promo.price if options_data[
                                                                                           'base_price'] > promo.price else Decimal(
                            '0')
                    })
            except Exception as e:
                logger.warning(f"Error getting promotions: {e}")

            # Get packaging prices
            try:
                packaging_prices = PackagingPrice.objects.for_location(location).filter(
                    product=product,
                    is_active=True
                ).select_related('packaging')

                for pkg_price in packaging_prices:
                    options_data['packaging_prices'].append({
                        'packaging_name': pkg_price.packaging.name,
                        'conversion_factor': pkg_price.packaging.conversion_factor,
                        'price': pkg_price.price,
                        'price_per_base_unit': pkg_price.price / pkg_price.packaging.conversion_factor,
                    })
            except Exception as e:
                logger.warning(f"Error getting packaging prices: {e}")

            return Result.success(
                data=options_data,
                msg='All pricing options retrieved successfully'
            )

        except Exception as e:
            logger.error(f"Error getting all pricing options: {e}")
            return Result.error(
                code='OPTIONS_ERROR',
                msg=f'Failed to get pricing options: {str(e)}'
            )

    @staticmethod
    def validate_pricing_setup(location, product) -> Result:
        """
        🎯 VALIDATION API: Validate pricing configuration - NEW Result-based method

        Checks if product has proper pricing setup and identifies issues
        """
        try:
            validation_data = {
                'location_code': getattr(location, 'code', str(location)),
                'product_code': getattr(product, 'code', str(product)),
                'has_base_price': False,
                'has_cost_price': False,
                'has_fallback_price': False,
                'pricing_issues': [],
                'pricing_warnings': [],
                'recommendations': []
            }

            # Check base price
            base_price = PricingService._get_base_price_internal(location, product)
            validation_data['has_base_price'] = base_price > 0

            if not validation_data['has_base_price']:
                validation_data['pricing_issues'].append('No base price configured')
                validation_data['recommendations'].append('Set up base price for this product at this location')

            # Check cost price
            cost_price = PricingService._get_inventory_cost_internal(location, product)
            validation_data['has_cost_price'] = cost_price > 0

            if not validation_data['has_cost_price']:
                validation_data['pricing_warnings'].append('No cost price available from inventory')
                validation_data['recommendations'].append('Ensure product has inventory records with cost information')

            # Check fallback price
            fallback_price = PricingService._get_fallback_price_internal(location, product)
            validation_data['has_fallback_price'] = fallback_price > 0

            # Validate price relationships
            if validation_data['has_base_price'] and validation_data['has_cost_price']:
                if base_price <= cost_price:
                    validation_data['pricing_warnings'].append('Base price is not higher than cost price (no profit)')
                    validation_data['recommendations'].append('Review pricing to ensure profitable margins')

            # Check for pricing options
            step_price_count = ProductStepPrice.objects.for_location(location).filter(
                product=product, is_active=True
            ).count()

            group_price_count = ProductPriceByGroup.objects.for_location(location).filter(
                product=product, is_active=True
            ).count()

            promo_count = PromotionalPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                start_date__lte=timezone.now().date(),
                end_date__gte=timezone.now().date()
            ).count()

            validation_data['pricing_options'] = {
                'step_prices': step_price_count,
                'group_prices': group_price_count,
                'active_promotions': promo_count
            }

            # Determine overall validation result
            has_critical_issues = len(validation_data['pricing_issues']) > 0
            has_warnings = len(validation_data['pricing_warnings']) > 0

            if has_critical_issues:
                return Result.error(
                    code='PRICING_SETUP_INVALID',
                    msg=f'Critical pricing issues found: {len(validation_data["pricing_issues"])} issues',
                    data=validation_data
                )
            elif has_warnings:
                return Result.success(
                    data=validation_data,
                    msg=f'Pricing setup valid but has {len(validation_data["pricing_warnings"])} warnings'
                )
            else:
                return Result.success(
                    data=validation_data,
                    msg='Pricing setup is fully valid'
                )

        except Exception as e:
            logger.error(f"Error validating pricing setup: {e}")
            return Result.error(
                code='VALIDATION_ERROR',
                msg=f'Pricing validation failed: {str(e)}'
            )

    @staticmethod
    def get_barcode_pricing(barcode: str, location, customer=None) -> Result:
        """
        🎯 BARCODE API: Get pricing for barcode - NEW Result-based method

        Handles both product barcodes and packaging barcodes
        """
        try:
            # Try to find product by barcode
            product = None
            packaging = None

            try:
                from products.models import Product, ProductPackaging

                # Try product barcode first
                try:
                    product = Product.objects.get(barcode=barcode)
                except Product.DoesNotExist:
                    # Try packaging barcode
                    try:
                        packaging_obj = ProductPackaging.objects.get(barcode=barcode)
                        product = packaging_obj.product
                        packaging = packaging_obj
                    except ProductPackaging.DoesNotExist:
                        pass

            except ImportError:
                logger.warning("Product models not available for barcode lookup")

            if not product:
                return Result.error(
                    code='BARCODE_NOT_FOUND',
                    msg=f'No product found for barcode: {barcode}',
                    data={'barcode': barcode}
                )

            # Get pricing for the product
            if packaging:
                # Packaging barcode - get packaging-specific pricing or calculate from base
                try:
                    pkg_price = PackagingPrice.objects.for_location(location).filter(
                        product=product,
                        packaging=packaging,
                        is_active=True
                    ).first()

                    if pkg_price:
                        price = pkg_price.price
                        unit_price = price / packaging.conversion_factor
                    else:
                        # Calculate from product price
                        product_pricing = PricingService.get_product_pricing(location, product, customer)
                        if not product_pricing.ok:
                            return product_pricing

                        unit_price = product_pricing.data['final_price']
                        price = unit_price * packaging.conversion_factor

                    barcode_data = {
                        'barcode': barcode,
                        'product': {
                            'code': product.code,
                            'name': product.name
                        },
                        'packaging': {
                            'name': packaging.name,
                            'conversion_factor': packaging.conversion_factor
                        },
                        'price': price,
                        'unit_price': unit_price,
                        'quantity_represented': packaging.conversion_factor,
                        'pricing_type': 'PACKAGING'
                    }

                except Exception as e:
                    logger.error(f"Error getting packaging pricing: {e}")
                    return Result.error(
                        code='PACKAGING_PRICING_ERROR',
                        msg=f'Failed to get packaging pricing: {str(e)}',
                        data={'barcode': barcode}
                    )
            else:
                # Product barcode - get standard pricing
                product_pricing = PricingService.get_product_pricing(location, product, customer)
                if not product_pricing.ok:
                    return product_pricing

                barcode_data = {
                    'barcode': barcode,
                    'product': {
                        'code': product.code,
                        'name': product.name
                    },
                    'packaging': None,
                    'price': product_pricing.data['final_price'],
                    'unit_price': product_pricing.data['final_price'],
                    'quantity_represented': Decimal('1'),
                    'pricing_type': 'PRODUCT',
                    'pricing_details': product_pricing.data
                }

            return Result.success(
                data=barcode_data,
                msg=f'Barcode pricing retrieved successfully for {barcode}'
            )

        except Exception as e:
            logger.error(f"Error getting barcode pricing: {e}")
            return Result.error(
                code='BARCODE_ERROR',
                msg=f'Barcode pricing failed: {str(e)}',
                data={'barcode': barcode}
            )

    # =====================================================
    # INTERNAL HELPER METHODS (PRESERVED ORIGINAL LOGIC)
    # =====================================================

    @staticmethod
    def _validate_pricing_inputs(location, product, quantity) -> Result:
        """Internal validation of pricing inputs"""
        if not location:
            return Result.error(
                code='INVALID_LOCATION',
                msg='Location is required for pricing'
            )

        if not product:
            return Result.error(
                code='INVALID_PRODUCT',
                msg='Product is required for pricing'
            )

        if quantity <= 0:
            return Result.error(
                code='INVALID_QUANTITY',
                msg='Quantity must be positive',
                data={'quantity': quantity}
            )

        return Result.success()

    @staticmethod
    def _determine_final_price(base_price, promo_price, group_price, step_price, fallback_price) -> tuple:
        """Determine final price and pricing rule used"""

        # Priority order: promotions → customer groups → step prices → base price → fallback
        if promo_price and promo_price > 0:
            return promo_price, 'PROMOTION'
        elif group_price and group_price > 0:
            return group_price, 'CUSTOMER_GROUP'
        elif step_price and step_price > 0:
            return step_price, 'STEP_PRICE'
        elif base_price and base_price > 0:
            return base_price, 'BASE_PRICE'
        else:
            return fallback_price, 'FALLBACK'

    @staticmethod
    def _calculate_profit_metrics(cost_price, final_price) -> Dict:
        """Calculate profit metrics"""
        if cost_price <= 0 or final_price <= 0:
            return {
                'profit_amount': Decimal('0'),
                'markup_percentage': Decimal('0'),
                'margin_percentage': Decimal('0'),
                'cost_valid': cost_price > 0
            }

        profit_amount = final_price - cost_price
        markup_percentage = (profit_amount / cost_price * 100) if cost_price > 0 else Decimal('0')
        margin_percentage = (profit_amount / final_price * 100) if final_price > 0 else Decimal('0')

        return {
            'profit_amount': profit_amount,
            'markup_percentage': markup_percentage,
            'margin_percentage': margin_percentage,
            'cost_valid': True
        }

    @staticmethod
    def _generate_pricing_recommendations(pricing_data, all_options) -> List[str]:
        """Generate pricing recommendations based on analysis"""
        recommendations = []

        final_price = pricing_data.get('final_price', Decimal('0'))
        cost_price = pricing_data.get('cost_price', Decimal('0'))
        pricing_rule = pricing_data.get('pricing_rule', '')

        # Profit margin recommendations
        if cost_price > 0 and final_price > 0:
            margin = (final_price - cost_price) / final_price * 100
            if margin < 10:
                recommendations.append('Consider increasing price - profit margin is very low (<10%)')
            elif margin > 60:
                recommendations.append(
                    'Consider reducing price - profit margin is very high (>60%), may hurt competitiveness')

        # Pricing rule recommendations
        if pricing_rule == 'FALLBACK':
            recommendations.append('Set up proper base price instead of relying on fallback pricing')

        # Promotional opportunities
        if pricing_rule == 'BASE_PRICE' and all_options.get('promotions'):
            recommendations.append('Consider setting up promotional pricing for special offers')

        return recommendations

    # =====================================================
    # INTERNAL PRICING METHODS (PRESERVED ORIGINAL LOGIC)
    # =====================================================

    @staticmethod
    def _get_base_price_internal(location, product) -> Decimal:
        """Internal base price retrieval - preserved original logic"""
        try:
            price_record = ProductPrice.objects.for_location(location).filter(
                product=product,
                is_active=True
            ).first()

            return price_record.effective_price if price_record else Decimal('0')
        except Exception as e:
            logger.error(f"Error getting base price: {e}")
            return Decimal('0')

    @staticmethod
    def _get_step_price_internal(location, product, quantity: Decimal) -> Optional[Decimal]:
        """Internal step price retrieval - preserved original logic"""
        try:
            step_prices = ProductStepPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                min_quantity__lte=quantity
            ).order_by('-min_quantity')

            return step_prices.first().price if step_prices.exists() else None

        except Exception as e:
            logger.error(f"Error getting step price: {e}")
            return None

    @staticmethod
    def _get_group_price_internal(location, product, customer_group, quantity: Decimal = Decimal('1')) -> Optional[
        Decimal]:
        """Internal group price retrieval - preserved original logic"""
        try:
            group_price = ProductPriceByGroup.objects.for_location(location).filter(
                product=product,
                customer_group=customer_group,
                is_active=True
            ).first()

            return group_price.price if group_price else None
        except Exception as e:
            logger.error(f"Error getting group price: {e}")
            return None

    @staticmethod
    def _get_promotional_price_internal(location, product, quantity, date, customer=None) -> Optional[Decimal]:
        """Internal promotional price retrieval - preserved original logic"""
        try:
            promotions = PromotionalPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                start_date__lte=date,
                end_date__gte=date
            )

            # Filter by quantity if specified
            if hasattr(PromotionalPrice, 'min_quantity'):
                promotions = promotions.filter(
                    models.Q(min_quantity__isnull=True) | models.Q(min_quantity__lte=quantity)
                )

            # Filter by customer if specified
            if customer and hasattr(PromotionalPrice, 'customer_groups'):
                customer_group = getattr(customer, 'price_group', None)
                if customer_group:
                    promotions = promotions.filter(
                        models.Q(customer_groups__isnull=True) | models.Q(customer_groups=customer_group)
                    )

            promo = promotions.order_by('-price').first()  # Highest promotion wins
            return promo.price if promo else None

        except Exception as e:
            logger.error(f"Error getting promotional price: {e}")
            return None

    @staticmethod
    def _get_fallback_price_internal(location, product) -> Decimal:
        """Internal fallback price calculation - preserved original logic"""
        try:
            cost_price = PricingService._get_inventory_cost_internal(location, product)

            if cost_price <= 0:
                return Decimal('0')

            # Apply location's default markup
            default_markup = getattr(location, 'default_markup_percentage', 30)
            markup_price = cost_price * (1 + default_markup / 100)

            return markup_price

        except Exception as e:
            logger.error(f"Error calculating fallback price: {e}")
            return Decimal('0')

    @staticmethod
    def _get_inventory_cost_internal(location, product) -> Decimal:
        """Internal inventory cost retrieval - preserved original logic"""
        try:
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(location=location, product=product)
            return item.avg_cost or Decimal('0')
        except Exception as e:
            # Silent fallback to zero - this is expected when no inventory exists
            return Decimal('0')

    # =====================================================
    # LEGACY METHODS - BACKWARD COMPATIBILITY (COMPLETE)
    # =====================================================

    @staticmethod
    def get_sale_price(location, product, customer=None, quantity: Decimal = Decimal('1'), date=None) -> Decimal:
        """
        LEGACY METHOD: Use get_product_pricing() for new code

        Maintained for backward compatibility
        """
        result = PricingService.get_product_pricing(location, product, customer, quantity, date)
        if result.ok:
            return result.data.get('final_price', Decimal('0'))
        else:
            logger.error(f"Pricing failed: {result.msg}")
            return PricingService._get_fallback_price_internal(location, product)

    @staticmethod
    def get_base_price(location, product) -> Decimal:
        """LEGACY METHOD: Use get_product_pricing() for new code"""
        return PricingService._get_base_price_internal(location, product)

    @staticmethod
    def get_step_price(location, product, quantity: Decimal) -> Optional[Decimal]:
        """LEGACY METHOD: Use get_product_pricing() for new code"""
        return PricingService._get_step_price_internal(location, product, quantity)

    @staticmethod
    def get_group_price(location, product, customer_group, quantity: Decimal = Decimal('1')) -> Optional[Decimal]:
        """LEGACY METHOD: Use get_product_pricing() for new code"""
        return PricingService._get_group_price_internal(location, product, customer_group, quantity)

    @staticmethod
    def get_fallback_price(location, product) -> Decimal:
        """LEGACY METHOD: Use get_product_pricing() for new code"""
        return PricingService._get_fallback_price_internal(location, product)

    @staticmethod
    def get_pricing_analysis(location, product, customer=None, quantity: Decimal = Decimal('1')) -> Dict:
        """
        LEGACY METHOD: Use get_pricing_analysis() Result version for new code

        Maintained for backward compatibility
        """
        result = PricingService.get_pricing_analysis(location, product, customer, quantity)
        if result.ok:
            return result.data
        else:
            return {'error': result.msg, 'code': result.code}

    @staticmethod
    def get_all_prices_for_product(location, product, customer=None) -> Dict:
        """
        LEGACY METHOD: Use get_all_pricing_options() for new code

        Maintained for backward compatibility
        """
        result = PricingService.get_all_pricing_options(location, product, customer)
        if result.ok:
            return result.data
        else:
            return {'error': result.msg, 'code': result.code}

    @staticmethod
    def get_barcode_pricing(barcode: str, location, customer=None) -> Dict:
        """
        LEGACY METHOD: Use get_barcode_pricing() Result version for new code

        Maintained for backward compatibility
        """
        result = PricingService.get_barcode_pricing(barcode, location, customer)
        if result.ok:
            return {'success': True, **result.data}
        else:
            return {'success': False, 'error': result.msg, 'barcode': barcode}

    # =====================================================
    # UTILITY METHODS (PRESERVED ORIGINAL FUNCTIONALITY)
    # =====================================================

    @staticmethod
    def calculate_markup_percentage(cost_price: Decimal, sale_price: Decimal) -> Decimal:
        """Calculate markup percentage"""
        if cost_price <= 0:
            return Decimal('0')
        return (sale_price - cost_price) / cost_price * 100

    @staticmethod
    def calculate_margin_percentage(cost_price: Decimal, sale_price: Decimal) -> Decimal:
        """Calculate margin percentage"""
        if sale_price <= 0:
            return Decimal('0')
        return (sale_price - cost_price) / sale_price * 100

    @staticmethod
    def get_applied_pricing_rule(location, product, customer=None, quantity=Decimal('1')) -> str:
        """
        LEGACY METHOD: Determine which pricing rule was applied

        Maintained for backward compatibility
        """
        result = PricingService.get_product_pricing(location, product, customer, quantity)
        if result.ok:
            return result.data.get('pricing_rule', 'UNKNOWN')
        else:
            return 'ERROR'


# =====================================================
# MODULE EXPORTS
# =====================================================

__all__ = ['PricingService']