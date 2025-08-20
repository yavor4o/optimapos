# pricing/services/pricing_service.py - FIXED VERSION

from django.utils import timezone
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal
from typing import Optional, Dict, List
import logging

from ..models import (
    ProductPrice, ProductPriceByGroup,
    ProductStepPrice, PromotionalPrice, PackagingPrice
)

logger = logging.getLogger(__name__)


class PricingService:
    """
    Centralized pricing logic - FULLY REFACTORED for new inventory system
    FIXED: All location field references to use manager.for_location() or GenericForeignKey
    """

    # =====================================================
    # CORE PRICING METHODS
    # =====================================================

    @staticmethod
    def get_sale_price(
            location,
            product,
            customer=None,
            quantity: Decimal = Decimal('1'),
            date=None
    ) -> Decimal:
        """
        Get final sale price for product at location
        Priority: promotions → customer groups → step prices → base price → fallback
        """
        if date is None:
            date = timezone.now().date()

        try:
            # 1. Check for active promotions
            promo_price = PricingService._get_promotional_price(
                location, product, quantity, date, customer
            )
            if promo_price and promo_price > 0:
                return promo_price

            # 2. Check customer's price group
            if customer and hasattr(customer, 'price_group') and customer.price_group:
                group_price = PricingService.get_group_price(
                    location, product, customer.price_group, quantity
                )
                if group_price and group_price > 0:
                    return group_price

            # 3. Check step prices
            step_price = PricingService.get_step_price(location, product, quantity)
            if step_price and step_price > 0:
                return step_price

            # 4. Base price for location
            base_price = PricingService.get_base_price(location, product)
            if base_price and base_price > 0:
                return base_price

            # 5. Fallback: cost + markup
            fallback_price = PricingService.get_fallback_price(location, product)
            return fallback_price

        except Exception as e:
            logger.error(f"Error getting sale price for {product} at {location}: {e}")
            return PricingService.get_fallback_price(location, product)

    @staticmethod
    def get_base_price(location, product) -> Decimal:
        """Get base price for product at location - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
            price_record = ProductPrice.objects.for_location(location).filter(
                product=product,
                is_active=True
            ).first()

            return price_record.effective_price if price_record else Decimal('0')
        except Exception as e:
            logger.error(f"Error getting base price: {e}")
            return Decimal('0')

    @staticmethod
    def get_step_price(location, product, quantity: Decimal) -> Optional[Decimal]:
        """Get step price based on quantity - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
            step_prices = ProductStepPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                min_quantity__lte=quantity  # ✅ FIXED: correct field name
            ).order_by('-min_quantity')

            return step_prices.first().price if step_prices.exists() else None

        except Exception as e:
            logger.error(f"Error getting step price: {e}")
            return None

    @staticmethod
    def get_group_price(location, product, customer_group, quantity: Decimal = Decimal('1')) -> Optional[Decimal]:
        """Get price for customer group - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
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
    def get_fallback_price(location, product) -> Decimal:
        """
        Fallback pricing: InventoryItem.avg_cost + markup
        NO PRODUCT DEPENDENCIES - uses InventoryItem only
        """
        try:
            cost_price = PricingService._get_inventory_cost(location, product)

            if cost_price <= 0:
                return Decimal('0')

            # Apply location's default markup
            default_markup = getattr(location, 'default_markup_percentage', 30)
            markup_price = cost_price * (1 + default_markup / 100)

            logger.info(
                f"Fallback price for {product}: cost={cost_price}, markup={default_markup}%, price={markup_price}")
            return markup_price

        except Exception as e:
            logger.error(f"Error calculating fallback price: {e}")
            return Decimal('0')

    # =====================================================
    # PRICING ANALYSIS & CALCULATIONS
    # =====================================================

    @staticmethod
    def get_pricing_analysis(location, product, customer=None, quantity=Decimal('1')) -> Dict:
        """Complete pricing analysis for product - NO PRODUCT DEPENDENCIES"""
        try:
            base_price = PricingService.get_base_price(location, product)
            final_price = PricingService.get_sale_price(location, product, customer, quantity)
            cost_price = PricingService._get_inventory_cost(location, product)

            # Check what pricing rule was applied
            pricing_rule = PricingService.get_applied_pricing_rule(
                location, product, customer, quantity
            )

            return {
                'base_price': base_price,
                'final_price': final_price,
                'cost_price': cost_price,
                'markup_percentage': PricingService.calculate_markup_percentage(cost_price, final_price),
                'margin_percentage': PricingService.calculate_margin_percentage(cost_price, final_price),
                'profit_amount': final_price - cost_price,
                'customer_discount': base_price - final_price if base_price > final_price else Decimal('0'),
                'pricing_rule': pricing_rule,
                'quantity': quantity,
                'analysis_timestamp': timezone.now()
            }

        except Exception as e:
            logger.error(f"Error in pricing analysis: {e}")
            return {
                'error': str(e),
                'base_price': Decimal('0'),
                'final_price': Decimal('0'),
                'cost_price': Decimal('0')
            }

    @staticmethod
    def get_applied_pricing_rule(location, product, customer=None, quantity=Decimal('1')) -> str:
        """Determine which pricing rule was applied"""
        try:
            date = timezone.now().date()

            # Check promotions
            if PricingService._get_promotional_price(location, product, quantity, date, customer):
                return 'PROMOTION'

            # Check customer group
            if customer and hasattr(customer, 'price_group') and customer.price_group:
                if PricingService.get_group_price(location, product, customer.price_group, quantity):
                    return 'CUSTOMER_GROUP'

            # Check step prices
            if PricingService.get_step_price(location, product, quantity):
                return 'STEP_PRICE'

            # Check base price
            if PricingService.get_base_price(location, product) > 0:
                return 'BASE_PRICE'

            return 'FALLBACK'

        except Exception as e:
            logger.error(f"Error determining pricing rule: {e}")
            return 'ERROR'

    # =====================================================
    # INVENTORY INTEGRATION METHODS
    # =====================================================

    @staticmethod
    def _get_inventory_cost(location, product) -> Decimal:
        """
        Get cost from InventoryItem.avg_cost - SINGLE SOURCE OF TRUTH
        NO fallback to Product fields
        """
        try:
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(location=location, product=product)
            return item.avg_cost or Decimal('0')
        except:
            # Import here to avoid circular imports
            from inventory.models import InventoryItem
            try:
                item = InventoryItem.objects.get(location=location, product=product)
                return item.avg_cost or Decimal('0')
            except InventoryItem.DoesNotExist:
                logger.warning(f"No InventoryItem found for {product} at {location}")
                return Decimal('0')
            except Exception as e:
                logger.error(f"Error getting inventory cost: {e}")
                return Decimal('0')

    @staticmethod
    def update_pricing_after_inventory_change(location, product, new_avg_cost: Decimal) -> int:
        """
        Called by InventoryItem.refresh_for_combination()
        Updates markup-based prices when inventory cost changes - FIXED
        """
        try:
            updated_count = 0

            # ✅ FIXED: Use manager.for_location() instead of location=location
            markup_prices = ProductPrice.objects.for_location(location).filter(
                product=product,
                pricing_method='MARKUP',
                is_active=True
            )

            for price_record in markup_prices:
                if price_record.markup_percentage and price_record.markup_percentage > 0:
                    old_price = price_record.effective_price
                    new_price = new_avg_cost * (1 + price_record.markup_percentage / 100)

                    price_record.effective_price = new_price
                    price_record.last_cost_update = timezone.now()
                    price_record.save(update_fields=['effective_price', 'last_cost_update'])

                    logger.info(f"Updated markup price for {product}: {old_price} → {new_price}")
                    updated_count += 1

            logger.info(f"Updated {updated_count} markup prices after cost change for {product}")
            return updated_count

        except Exception as e:
            logger.error(f"Error updating pricing after inventory change: {e}")
            return 0

    # =====================================================
    # PROMOTIONAL PRICING - FIXED
    # =====================================================

    @staticmethod
    def _get_promotional_price(location, product, quantity, date, customer=None) -> Optional[Decimal]:
        """Get promotional price if active - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
            promotions = PromotionalPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                start_date__lte=date,
                end_date__gte=date
            )

            # Filter by customer if specified
            if customer and hasattr(customer, 'price_group'):
                promotions = promotions.filter(
                    models.Q(customer_groups__isnull=True) |
                    models.Q(customer_groups=customer.price_group)
                )

            # Filter by minimum quantity
            promotions = promotions.filter(
                models.Q(min_quantity__isnull=True) |
                models.Q(min_quantity__lte=quantity)
            )

            # Get the best (lowest) promotional price
            promotion = promotions.order_by('promotional_price').first()
            return promotion.promotional_price if promotion else None

        except Exception as e:
            logger.error(f"Error getting promotional price: {e}")
            return None

    # =====================================================
    # UTILITY METHODS
    # =====================================================

    @staticmethod
    def calculate_markup_percentage(cost_price: Decimal, sale_price: Decimal) -> Decimal:
        """Calculate markup percentage over cost"""
        if cost_price <= 0:
            return Decimal('0')
        return ((sale_price - cost_price) / cost_price) * 100

    @staticmethod
    def calculate_margin_percentage(cost_price: Decimal, sale_price: Decimal) -> Decimal:
        """Calculate profit margin percentage"""
        if sale_price <= 0:
            return Decimal('0')
        return ((sale_price - cost_price) / sale_price) * 100

    @staticmethod
    def bulk_update_location_prices(location, markup_change_percentage: Decimal) -> int:
        """Bulk update all prices at location by percentage - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
            updated_count = ProductPrice.objects.for_location(location).filter(
                is_active=True
            ).update(
                effective_price=models.F('effective_price') * (1 + markup_change_percentage / 100),
                last_cost_update=timezone.now()
            )

            logger.info(f"Bulk updated {updated_count} prices at {location} by {markup_change_percentage}%")
            return updated_count

        except Exception as e:
            logger.error(f"Error in bulk price update: {e}")
            return 0

    # =====================================================
    # PACKAGING PRICING INTEGRATION - FIXED
    # =====================================================

    @staticmethod
    def get_packaging_price(location, packaging, customer=None, quantity: Decimal = Decimal('1')) -> Optional[Decimal]:
        """Get price for specific packaging - FIXED"""
        try:
            # ✅ FIXED: Use manager.for_location() instead of location=location
            packaging_price = PackagingPrice.objects.for_location(location).filter(
                packaging=packaging,
                is_active=True
            ).first()

            return packaging_price.price if packaging_price else None
        except Exception as e:
            logger.error(f"Error getting packaging price: {e}")
            return None

    @staticmethod
    def get_barcode_pricing(location, barcode, customer=None, quantity: Decimal = Decimal('1')) -> Dict:
        """
        Get price by scanning barcode (handles packaging-specific pricing)
        Returns detailed pricing information including packaging data
        """
        try:
            from products.models import ProductBarcode
            barcode_obj = ProductBarcode.objects.select_related(
                'product', 'packaging', 'packaging__unit'
            ).get(barcode=barcode, is_active=True)

            product = barcode_obj.product

            # If barcode is linked to specific packaging
            if barcode_obj.packaging:
                packaging_price = PricingService.get_packaging_price(
                    location, barcode_obj.packaging, customer, quantity
                )

                if packaging_price:
                    return {
                        'success': True,
                        'product': product,
                        'packaging': barcode_obj.packaging,
                        'price': packaging_price,
                        'unit_price': packaging_price / barcode_obj.packaging.conversion_factor,
                        'quantity_represented': barcode_obj.packaging.conversion_factor,
                        'pricing_type': 'PACKAGING',
                        'barcode': barcode
                    }

            # Fallback to regular product pricing
            product_price = PricingService.get_sale_price(
                location, product, customer, quantity
            )

            return {
                'success': True,
                'product': product,
                'packaging': None,
                'price': product_price,
                'unit_price': product_price,
                'quantity_represented': Decimal('1'),
                'pricing_type': 'PRODUCT',
                'barcode': barcode
            }

        except Exception as e:
            logger.error(f"Error getting barcode pricing: {e}")
            return {
                'success': False,
                'error': str(e),
                'barcode': barcode
            }

    # =====================================================
    # REPORTING & ANALYTICS - FIXED
    # =====================================================

    @staticmethod
    def get_all_prices_for_product(location, product, customer=None) -> Dict:
        """Get all available prices for a product - FIXED"""
        try:
            result = {
                'base_price': PricingService.get_base_price(location, product),
                'fallback_price': PricingService.get_fallback_price(location, product),
                'cost_price': PricingService._get_inventory_cost(location, product),
                'step_prices': [],
                'group_prices': [],
                'promotions': [],
                'packaging_prices': []
            }

            # ✅ FIXED: Step prices
            step_prices = ProductStepPrice.objects.for_location(location).filter(
                product=product,
                is_active=True
            ).order_by('min_quantity')

            for step_price in step_prices:
                result['step_prices'].append({
                    'min_quantity': step_price.min_quantity,
                    'price': step_price.price
                })

            # ✅ FIXED: Group prices
            group_prices = ProductPriceByGroup.objects.for_location(location).filter(
                product=product,
                is_active=True
            ).select_related('price_group')  # ✅ FIXED: correct field name

            for group_price in group_prices:
                result['group_prices'].append({
                    'customer_group': group_price.price_group.name,  # ✅ FIXED: correct field name
                    'price': group_price.price
                })

            # ✅ FIXED: Active promotions
            today = timezone.now().date()
            promotions = PromotionalPrice.objects.for_location(location).filter(
                product=product,
                is_active=True,
                start_date__lte=today,
                end_date__gte=today
            )

            for promotion in promotions:
                result['promotions'].append({
                    'name': promotion.name,
                    'promotional_price': promotion.promotional_price,
                    'start_date': promotion.start_date,
                    'end_date': promotion.end_date,
                    'min_quantity': getattr(promotion, 'min_quantity', None)
                })

            return result

        except Exception as e:
            logger.error(f"Error getting all prices for product: {e}")
            return {'error': str(e)}

    @staticmethod
    def get_price_history(location, product, days=30) -> List[Dict]:
        """Get pricing history for product"""
        try:
            from django.utils import timezone
            from datetime import timedelta

            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)

            # This would require a PriceHistory model to track changes
            # For now, return current pricing data
            current_analysis = PricingService.get_pricing_analysis(location, product)

            return [{
                'date': end_date,
                'base_price': current_analysis.get('base_price', Decimal('0')),
                'cost_price': current_analysis.get('cost_price', Decimal('0')),
                'margin_percentage': current_analysis.get('margin_percentage', Decimal('0'))
            }]

        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []