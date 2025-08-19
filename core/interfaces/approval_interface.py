# core/interfaces/approval_interface.py
from abc import ABC, abstractmethod
from typing import List, Dict
from core.utils.result import Result


class IApprovalService(ABC):
    """Interface за approval workflow"""

    @abstractmethod
    def authorize_transition(self, document, user, to_status: str):
        """Проверява дали user може да направи transition"""
        pass

    @abstractmethod
    def get_available_transitions(self, document, user) -> List[Dict]:
        """Връща възможните transitions за user"""
        pass

    @abstractmethod
    def get_workflow_info(self, document):
        """Връща пълна workflow информация"""
        pass

    @abstractmethod
    def get_approval_history(self, document) -> List[Dict]:
        """Връща история на одобренията"""
        pass