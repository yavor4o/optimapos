# core/interfaces/inventory_interface.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal
from core.utils.result import Result



class IInventoryService(ABC):
    """Interface за inventory operations"""

    @abstractmethod
    def check_availability(self, location, product, quantity: Decimal) -> Dict:
        """Проверява наличност"""
        pass

    @abstractmethod
    def reserve_stock(self, location, product, quantity: Decimal, reason: str = '') -> Dict:
        """Резервира стока"""
        pass

    @abstractmethod
    def release_reservation(self, location, product, quantity: Decimal) -> Dict:
        """Освобождава резервация"""
        pass

    @abstractmethod
    def get_stock_info(self, location, product) -> Dict:
        """Връща информация за наличности"""
        pass


class IMovementService(ABC):
    """Interface за inventory movements"""

    @abstractmethod
    def create_incoming_movement(self, location, product, quantity: Decimal, **kwargs) -> Result:
        """Създава входящо движение"""
        pass

    @abstractmethod
    def create_outgoing_movement(self, location, product, quantity: Decimal, **kwargs) -> Result:
        """Създава изходящо движение"""
        pass

    @abstractmethod
    def create_from_document(self, document) -> List:
        """Създава движения от документ"""
        pass