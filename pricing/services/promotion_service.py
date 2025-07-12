# pricing/services/promotion_service.py

from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import timedelta

from ..models import PromotionalPrice


class PromotionService:
    """
    Service for managing promotional pricing logic
    """

    @staticmethod
    def get_promotional_price(
            location,
            product,
            quantity: Decimal,
            date=None,
            customer=None
    ) -> Optional[Decimal]:
        """
        Get best promotional price for product if available
        """
        if date is None:
            date = timezone.now().date()

        # Get all valid promotions
        promotions = PromotionalPrice.objects.filter(
            location=location,
            product=product,
            start_date__lte=date,
            end_date__gte=date,
            min_quantity__lte=quantity,
            is_active=True
        )

        # Filter by max quantity if specified
        promotions = promotions.filter(
            Q(max_quantity__isnull=True) |
            Q(max_quantity__gte=quantity)
        )

        # Filter by customer groups if customer provided
        valid_promotions = []
        for promo in promotions:
            if promo.is_valid_for_customer(customer):
                valid_promotions.append(promo)

        if not valid_promotions:
            return None

        # Return best price (lowest) with highest priority
        best_promo = min(
            valid_promotions,
            key=lambda p: (p.promotional_price, -p.priority)
        )

        return best_promo.promotional_price

    @staticmethod
    def get_active_promotions(location=None, product=None, date=None) -> List[Dict]:
        """
        Get all currently active promotions
        """
        if date is None:
            date = timezone.now().date()

        queryset = PromotionalPrice.objects.filter(
            start_date__lte=date,
            end_date__gte=date,
            is_active=True
        )

        if location:
            queryset = queryset.filter(location=location)

        if product:
            queryset = queryset.filter(product=product)

        promotions = []
        for promo in queryset.select_related('location', 'product'):
            promotions.append({
                'id': promo.id,
                'name': promo.name,
                'location_code': promo.location.code,
                'product_code': promo.product.code,
                'product_name': promo.product.name,
                'promotional_price': promo.promotional_price,
                'start_date': promo.start_date,
                'end_date': promo.end_date,
                'min_quantity': promo.min_quantity,
                'max_quantity': promo.max_quantity,
                'priority': promo.priority,
                'days_remaining': (promo.end_date - date).days,
                'discount_amount': promo.get_discount_amount(),
                'discount_percentage': promo.get_discount_percentage()
            })

        return promotions

    @staticmethod
    def get_upcoming_promotions(days_ahead=7) -> List[Dict]:
        """
        Get promotions starting within specified days
        """
        today = timezone.now().date()
        future_date = today + timedelta(days=days_ahead)

        promotions = PromotionalPrice.objects.filter(
            start_date__gt=today,
            start_date__lte=future_date,
            is_active=True
        ).select_related('location', 'product').order_by('start_date')

        upcoming = []
        for promo in promotions:
            upcoming.append({
                'id': promo.id,
                'name': promo.name,
                'location_code': promo.location.code,
                'product_code': promo.product.code,
                'product_name': promo.product.name,
                'promotional_price': promo.promotional_price,
                'start_date': promo.start_date,
                'end_date': promo.end_date,
                'days_until_start': promo.days_until_start,
                'discount_amount': promo.get_discount_amount(),
                'discount_percentage': promo.get_discount_percentage()
            })

        return upcoming

    @staticmethod
    def get_expiring_promotions(days_ahead=3) -> List[Dict]:
        """
        Get promotions expiring within specified days
        """
        today = timezone.now().date()
        future_date = today + timedelta(days=days_ahead)

        promotions = PromotionalPrice.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            end_date__lte=future_date,
            is_active=True
        ).select_related('location', 'product').order_by('end_date')

        expiring = []
        for promo in promotions:
            expiring.append({
                'id': promo.id,
                'name': promo.name,
                'location_code': promo.location.code,
                'product_code': promo.product.code,
                'product_name': promo.product.name,
                'promotional_price': promo.promotional_price,
                'end_date': promo.end_date,
                'days_until_end': promo.days_until_end,
                'discount_amount': promo.get_discount_amount(),
                'discount_percentage': promo.get_discount_percentage()
            })

        return expiring

    @staticmethod
    def create_bulk_promotion(
            name: str,
            promotional_price: Decimal,
            start_date,
            end_date,
            locations: List,
            products: List,
            **kwargs
    ) -> List[PromotionalPrice]:
        """
        Create promotion for multiple locations and products
        """
        created_promotions = []

        for location in locations:
            for product in products:
                promo = PromotionalPrice.objects.create(
                    location=location,
                    product=product,
                    name=name,
                    promotional_price=promotional_price,
                    start_date=start_date,
                    end_date=end_date,
                    **kwargs
                )
                created_promotions.append(promo)

        return created_promotions

    @staticmethod
    def validate_promotion_data(promo_data: Dict) -> tuple[bool, List[str]]:
        """
        Validate promotion data before creation
        """
        errors = []

        # Required fields
        required_fields = ['name', 'promotional_price', 'start_date', 'end_date']
        for field in required_fields:
            if field not in promo_data or not promo_data[field]:
                errors.append(f'{field} is required')

        # Date validation
        if 'start_date' in promo_data and 'end_date' in promo_data:
            if promo_data['start_date'] > promo_data['end_date']:
                errors.append('End date must be after start date')

        # Price validation
        if 'promotional_price' in promo_data and promo_data['promotional_price'] < 0:
            errors.append('Promotional price cannot be negative')

        # Quantity validation
        if 'min_quantity' in promo_data and promo_data['min_quantity'] <= 0:
            errors.append('Minimum quantity must be positive')

        if ('max_quantity' in promo_data and 'min_quantity' in promo_data and
                promo_data['max_quantity'] and promo_data['max_quantity'] < promo_data['min_quantity']):
            errors.append('Maximum quantity cannot be less than minimum quantity')

        return len(errors) == 0, errors

    @staticmethod
    def get_promotion_performance(promotion_id: int) -> Dict:
        """
        Get performance metrics for a promotion (placeholder for future sales integration)
        """
        try:
            promo = PromotionalPrice.objects.get(id=promotion_id)

            # This will be implemented when we have sales data
            return {
                'promotion_name': promo.name,
                'product_code': promo.product.code,
                'location_code': promo.location.code,
                'start_date': promo.start_date,
                'end_date': promo.end_date,
                'promotional_price': promo.promotional_price,
                'discount_amount': promo.get_discount_amount(),
                'discount_percentage': promo.get_discount_percentage(),
                # Future metrics from sales:
                'units_sold': 0,  # TODO: Calculate from sales
                'revenue': Decimal('0'),  # TODO: Calculate from sales
                'profit': Decimal('0'),  # TODO: Calculate from sales
                'transaction_count': 0,  # TODO: Calculate from sales
            }
        except PromotionalPrice.DoesNotExist:
            return {'error': 'Promotion not found'}

    @staticmethod
    def deactivate_expired_promotions():
        """
        Utility method to deactivate expired promotions
        """
        today = timezone.now().date()
        expired_count = PromotionalPrice.objects.filter(
            end_date__lt=today,
            is_active=True
        ).update(is_active=False)

        return expired_count