# pricing/services/pricing_service.py

from django.utils import timezone
from django.db import models
from decimal import Decimal
from typing import Optional, Dict, List

from ..models import (
    ProductPrice, PriceGroup, ProductPriceByGroup,
    ProductStepPrice, PromotionalPrice, PackagingPrice
)


class PricingService:
    """
    Centralized pricing logic - migrated from warehouse
    Handles all price calculations and business rules
    """

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

        # 1. Check for active promotions
        from .promotion_service import PromotionService
        promo_price = PromotionService.get_promotional_price(
            location, product, quantity, date, customer
        )
        if promo_price:
            return promo_price

        # 2. Check customer's price group
        if customer and hasattr(customer, 'price_group') and customer.price_group:
            group_price = PricingService.get_group_price(
                location, product, customer.price_group, quantity
            )
            if group_price:
                return group_price

        # 3. Check step prices
        step_price = PricingService.get_step_price(location, product, quantity)
        if step_price:
            return step_price

        # 4. Base price for location
        base_price = PricingService.get_base_price(location, product)
        if base_price > 0:
            return base_price

        # 5. Fallback - calculate from cost + location default markup
        return PricingService.get_fallback_price(location, product)

    @staticmethod
    def get_base_price(location, product) -> Decimal:
        """Get base price for product at location"""
        try:
            price_record = ProductPrice.objects.get(
                location=location,
                product=product,
                is_active=True
            )
            return price_record.effective_price
        except ProductPrice.DoesNotExist:
            return Decimal('0')

    @staticmethod
    def get_group_price(location, product, price_group, quantity=None) -> Optional[Decimal]:
        """Get price for specific customer group"""
        try:
            # Find group-specific price with quantity consideration
            group_prices = ProductPriceByGroup.objects.filter(
                location=location,
                product=product,
                price_group=price_group,
                is_active=True
            )

            if quantity:
                # Get best price for quantity
                group_prices = group_prices.filter(min_quantity__lte=quantity)

            group_price = group_prices.order_by('-min_quantity').first()

            if group_price:
                return group_price.price

        except ProductPriceByGroup.DoesNotExist:
            pass

        # Apply group's default discount to base price
        base_price = PricingService.get_base_price(location, product)
        if base_price > 0 and price_group.default_discount_percentage > 0:
            return base_price * (1 - price_group.default_discount_percentage / 100)

        return None

    @staticmethod
    def get_step_price(location, product, quantity) -> Optional[Decimal]:
        """Get step price based on quantity"""
        step_price = ProductStepPrice.objects.filter(
            location=location,
            product=product,
            min_quantity__lte=quantity,
            is_active=True
        ).order_by('-min_quantity').first()

        return step_price.price if step_price else None

    @staticmethod
    def get_fallback_price(location, product) -> Decimal:
        """Fallback pricing using location's default markup"""
        try:
            # Get cost from inventory
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(location=location, product=product)
            cost_price = item.avg_cost
        except:
            cost_price = product.current_avg_cost or Decimal('0')

        if cost_price <= 0:
            return Decimal('0')

        # Apply location's default markup
        default_markup = getattr(location, 'default_markup_percentage', 30)
        return cost_price * (1 + default_markup / 100)

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
    def update_prices_after_cost_change(location, product, new_cost: Decimal):
        """Update markup-based prices when cost changes"""
        markup_prices = ProductPrice.objects.filter(
            location=location,
            product=product,
            pricing_method='MARKUP',
            is_active=True
        )

        for price_record in markup_prices:
            price_record.calculate_effective_price()
            price_record.last_cost_update = timezone.now()
            price_record.save(update_fields=['effective_price', 'last_cost_update'])

    @staticmethod
    def bulk_update_location_prices(location, markup_change_percentage: Decimal):
        """Bulk update all prices at location by percentage"""
        ProductPrice.objects.filter(
            location=location,
            is_active=True
        ).update(
            effective_price=models.F('effective_price') * (1 + markup_change_percentage / 100)
        )

    @staticmethod
    def get_pricing_analysis(location, product, customer=None, quantity=Decimal('1')) -> Dict:
        """Complete pricing analysis for product"""
        base_price = PricingService.get_base_price(location, product)
        final_price = PricingService.get_sale_price(location, product, customer, quantity)

        try:
            from inventory.models import InventoryItem
            item = InventoryItem.objects.get(location=location, product=product)
            cost_price = item.avg_cost
        except:
            cost_price = product.current_avg_cost or Decimal('0')

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
            'quantity': quantity
        }

    @staticmethod
    def get_applied_pricing_rule(location, product, customer=None, quantity=Decimal('1')) -> str:
        """Determine which pricing rule was applied"""
        date = timezone.now().date()

        # Check promotions
        from .promotion_service import PromotionService
        if PromotionService.get_promotional_price(location, product, quantity, date, customer):
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

    @staticmethod
    def get_all_prices_for_product(location, product, customer=None) -> Dict:
        """Get all available prices for a product"""
        result = {
            'base_price': PricingService.get_base_price(location, product),
            'fallback_price': PricingService.get_fallback_price(location, product),
            'step_prices': [],
            'group_prices': [],
            'promotions': []
        }

        # Step prices
        step_prices = ProductStepPrice.objects.filter(
            location=location,
            product=product,
            is_active=True
        ).order_by('min_quantity')

        for step in step_prices:
            result['step_prices'].append({
                'min_quantity': step.min_quantity,
                'price': step.price,
                'description': step.description
            })

        # Group prices (if customer has group)
        if customer and hasattr(customer, 'price_group') and customer.price_group:
            group_prices = ProductPriceByGroup.objects.filter(
                location=location,
                product=product,
                price_group=customer.price_group,
                is_active=True
            ).order_by('min_quantity')

            for group_price in group_prices:
                result['group_prices'].append({
                    'min_quantity': group_price.min_quantity,
                    'price': group_price.price,
                    'group_name': group_price.price_group.name
                })

        # Current promotions
        promotions = PromotionalPrice.objects.filter(
            location=location,
            product=product,
            is_active=True
        ).filter(
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        )

        for promo in promotions:
            if not customer or promo.is_valid_for_customer(customer):
                result['promotions'].append({
                    'name': promo.name,
                    'price': promo.promotional_price,
                    'min_quantity': promo.min_quantity,
                    'max_quantity': promo.max_quantity,
                    'end_date': promo.end_date
                })

        return result

    @staticmethod
    def validate_price_data(price_data: Dict) -> tuple[bool, List[str]]:
        """Validate price data before creation/update"""
        errors = []

        if 'price' in price_data and price_data['price'] < 0:
            errors.append('Price cannot be negative')

        if 'markup_percentage' in price_data and price_data['markup_percentage'] < 0:
            errors.append('Markup percentage cannot be negative')

        if 'min_quantity' in price_data and price_data['min_quantity'] <= 0:
            errors.append('Minimum quantity must be positive')

        return len(errors) == 0, errors

    # === PACKAGING PRICE METHODS ===

    @staticmethod
    def get_price_by_barcode(location, barcode, customer=None, quantity: Decimal = Decimal('1')) -> Dict:
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

        except ProductBarcode.DoesNotExist:
            return {
                'success': False,
                'error': 'Barcode not found',
                'barcode': barcode
            }

    @staticmethod
    def get_packaging_price(location, packaging, customer=None, quantity: Decimal = Decimal('1')) -> Optional[Decimal]:
        """
        Get price for specific packaging
        """
        try:
            packaging_price = PackagingPrice.objects.get(
                location=location,
                packaging=packaging,
                is_active=True
            )
            return packaging_price.price

        except PackagingPrice.DoesNotExist:
            # Fallback: calculate from base product price
            base_unit_price = PricingService.get_sale_price(
                location, packaging.product, customer,
                quantity * packaging.conversion_factor
            )

            if base_unit_price > 0:
                return base_unit_price * packaging.conversion_factor

            return None

    @staticmethod
    def get_price_by_plu(location, plu_code, customer=None, quantity: Decimal = Decimal('1')) -> Dict:
        """
        Get price by PLU code (for weight-based products)
        """
        try:
            from products.models import ProductPLU
            plu_obj = ProductPLU.objects.select_related('product').get(
                plu_code=plu_code, is_active=True
            )

            product = plu_obj.product
            product_price = PricingService.get_sale_price(
                location, product, customer, quantity
            )

            return {
                'success': True,
                'product': product,
                'price': product_price,
                'unit_price': product_price,
                'pricing_type': 'PLU',
                'plu_code': plu_code
            }

        except ProductPLU.DoesNotExist:
            return {
                'success': False,
                'error': 'PLU code not found',
                'plu_code': plu_code
            }

    @staticmethod
    def get_all_packaging_prices(location, product) -> List[Dict]:
        """
        Get all packaging prices for a product at location
        """
        result = []

        # Get all packagings for this product
        from products.models import ProductPackaging
        packagings = ProductPackaging.objects.filter(
            product=product,
            is_active=True
        ).select_related('unit').order_by('conversion_factor')

        for packaging in packagings:
            packaging_price = PricingService.get_packaging_price(location, packaging)

            if packaging_price:
                unit_price = packaging_price / packaging.conversion_factor

                result.append({
                    'packaging': packaging,
                    'packaging_price': packaging_price,
                    'unit_price': unit_price,
                    'conversion_factor': packaging.conversion_factor,
                    'unit_name': packaging.unit.name,
                    'is_default_sale': packaging.is_default_sale_unit,
                    'is_default_purchase': packaging.is_default_purchase_unit
                })

        return result

    @staticmethod
    def compare_packaging_prices(location, product, customer=None) -> Dict:
        """
        Compare all packaging options and find the best deal
        """
        packaging_prices = PricingService.get_all_packaging_prices(location, product)

        if not packaging_prices:
            return {'error': 'No packaging prices available'}

        # Sort by unit price (ascending)
        packaging_prices.sort(key=lambda x: x['unit_price'])

        best_deal = packaging_prices[0]
        worst_deal = packaging_prices[-1]

        savings = worst_deal['unit_price'] - best_deal['unit_price']
        savings_percentage = (savings / worst_deal['unit_price']) * 100 if worst_deal['unit_price'] > 0 else 0

        return {
            'product': product,
            'location': location,
            'packaging_options': packaging_prices,
            'best_deal': best_deal,
            'worst_deal': worst_deal,
            'max_savings': {
                'amount': savings,
                'percentage': savings_percentage
            },
            'recommendation': f"Buy {best_deal['packaging'].unit.name} for best unit price"
        }

    @staticmethod
    def bulk_update_packaging_prices(location, markup_change_percentage: Decimal):
        """
        Bulk update packaging prices by percentage
        """
        updated_count = 0

        # Update non-fixed packaging prices
        for packaging_price in PackagingPrice.objects.filter(
            location=location,
            pricing_method__in=['MARKUP', 'AUTO'],
            is_active=True
        ):
            packaging_price.calculate_effective_price()
            packaging_price.save(update_fields=['price'])
            updated_count += 1

        # Update fixed prices by percentage
        PackagingPrice.objects.filter(
            location=location,
            pricing_method='FIXED',
            is_active=True
        ).update(
            price=models.F('price') * (1 + markup_change_percentage / 100)
        )

        return updated_count