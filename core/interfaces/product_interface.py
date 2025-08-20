# core/interfaces/product_interface.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from core.utils.result import Result


class IProductService(ABC):
    """Interface за product operations"""

    @abstractmethod
    def search_products(self, query: str = '', filters: Dict = None) -> List:
        """Търси продукти"""
        pass

    @abstractmethod
    def get_product_info(self, product_id: int) -> Dict:
        """Връща информация за продукт"""
        pass

    @abstractmethod
    def create_product(self, product_data: Dict) -> Result:
        """Създава продукт"""
        pass


class IProductValidationService(ABC):
    """Interface за product validation"""

    @abstractmethod
    def can_sell_product(self, product, quantity=None, location=None) -> Tuple[bool, str, Dict]:
        """Проверява дали продукт може да се продава"""
        pass

    @abstractmethod
    def can_purchase_product(self, product, quantity=None, supplier=None) -> Tuple[bool, str, Dict]:
        """Проверява дали продукт може да се купува"""
        pass

    @abstractmethod
    def validate_product_data(self, product_data: Dict) -> Tuple[bool, List[str]]:
        """Валидира данни за продукт"""
        pass