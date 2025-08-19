# core/interfaces/vat_interface.py
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from decimal import Decimal


class IVATCalculationService(ABC):
    """Interface за VAT calculations"""

    @abstractmethod
    def get_price_entry_mode(self, document) -> bool:
        """Определя дали цените включват ДДС"""
        pass

    @abstractmethod
    def calculate_vat_amounts(self, base_amount: Decimal, vat_rate: Decimal, prices_include_vat: bool) -> Dict:
        """Изчислява ДДС"""
        pass

    @abstractmethod
    def recalculate_document_totals(self, document) -> Dict:
        """Преизчислява totals на документ"""
        pass