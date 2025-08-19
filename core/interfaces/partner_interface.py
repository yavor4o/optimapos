# core/interfaces/partner_interface.py
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from decimal import Decimal


class ISupplierService(ABC):
    """Interface за supplier operations"""

    @abstractmethod
    def get_supplier_info(self, supplier) -> Dict:
        """Връща информация за доставчик"""
        pass

    @abstractmethod
    def check_credit_limit(self, supplier, amount: Decimal) -> Tuple[bool, str]:
        """Проверява кредитен лимит"""
        pass


class ICustomerService(ABC):
    """Interface за customer operations"""

    @abstractmethod
    def get_customer_info(self, customer) -> Dict:
        """Връща информация за клиент"""
        pass

    @abstractmethod
    def can_make_sale(self, customer, amount: Decimal, site=None) -> Tuple[bool, str]:
        """Проверява дали може да се направи продажба"""
        pass

    @abstractmethod
    def get_customer_discount(self, customer, product=None, site=None) -> Decimal:
        """Връща отстъпка за клиент"""
        pass