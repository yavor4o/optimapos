# core/interfaces/pricing_interface.py
from abc import ABC, abstractmethod
from typing import Optional, Dict
from decimal import Decimal
from core.utils.result import Result


class IPricingService(ABC):
    """Interface за pricing operations"""

    @abstractmethod
    def get_product_price(self, location, product, customer=None, quantity: Decimal = Decimal('1')) -> Optional[
        Decimal]:
        """Връща цена на продукт"""
        pass

    @abstractmethod
    def calculate_price_with_rules(self, location, product, quantity: Decimal, customer=None) -> Decimal:
        """Изчислява цена с правила"""
        pass

    @abstractmethod
    def get_promotional_price(self, location, product, quantity: Decimal, date=None) -> Optional[Decimal]:
        """Връща промоционална цена"""
        pass

    @abstractmethod
    def update_pricing_after_inventory_change(self, location, product, new_avg_cost: Decimal) -> int:
        """Обновява цени след промяна в inventory"""
        pass