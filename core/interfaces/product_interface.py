# core/interfaces/product_interface.py - CLEAN VERSION

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from core.utils.result import Result


class IProductService(ABC):
    """
    Interface за product operations - ENHANCED with inventory management

    CLEAN: Removed unused legacy methods after checking codebase
    """

    # ===== EXISTING METHODS (keep unchanged) =====

    @abstractmethod
    def search_products(self, query: str = '', filters: Dict = None) -> List:
        """Търси продукти"""
        pass

    @abstractmethod
    def get_product_info(self, product_id: int) -> Dict:
        """Връща информация за продукт"""
        pass

    # ===== NEW INVENTORY-AWARE CREATION METHODS =====

    @abstractmethod
    def create_product_with_inventory(self, product_data: Dict) -> Result:
        """🎯 MAIN: Създава продукт с автоматично inventory setup"""
        pass

    @abstractmethod
    def create_product_without_inventory(self, product_data: Dict) -> Result:
        """🔧 SPECIAL: Създава продукт без inventory (за специални случаи)"""
        pass

    @abstractmethod
    def add_product_to_location(self, product, location) -> Result:
        """🏪 LOCATION: Добавя съществуващ продукт към локация"""
        pass

    @abstractmethod
    def setup_inventory_for_existing_products(self) -> Result:
        """🔧 MIGRATION: Helper за създаване на липсващи inventory записи"""
        pass

    @abstractmethod
    def validate_product_data(self, product_data: Dict) -> Result:
        """🔍 VALIDATION: Валидира данни за продукт - Result-based"""
        pass


class IProductValidationService(ABC):
    """Interface за product validation"""

    @abstractmethod
    def validate_sale(self, product, quantity=None, location=None) -> Result:
        """Проверява дали продукт може да се продава - NEW Result-based"""
        pass

    @abstractmethod
    def validate_purchase(self, product, quantity=None, supplier=None) -> Result:
        """Проверява дали продукт може да се купува - NEW Result-based"""
        pass

    @abstractmethod
    def validate_product_data(self, product_data: Dict) -> Result:
        """Валидира данни за продукт - NEW Result-based"""
        pass

    # ===== LEGACY COMPATIBILITY =====
    def can_sell_product(self, product, quantity=None, location=None) -> Tuple[bool, str, Dict]:
        """Legacy method - converts Result to tuple format"""
        result = self.validate_sale(product, quantity, location)
        return (result.ok, result.msg, result.data)

    def can_purchase_product(self, product, quantity=None, supplier=None) -> Tuple[bool, str, Dict]:
        """Legacy method - converts Result to tuple format"""
        result = self.validate_purchase(product, quantity, supplier)
        return (result.ok, result.msg, result.data)