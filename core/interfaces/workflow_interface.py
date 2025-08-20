# core/interfaces/workflow_interface.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from core.utils.result import Result


class IWorkflow(ABC):
    """Interface за workflows"""

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> Result:
        """Изпълнява workflow"""
        pass

    @abstractmethod
    def can_execute(self, context: Dict[str, Any]) -> bool:
        """Проверява дали workflow може да се изпълни"""
        pass

    @abstractmethod
    def rollback(self, workflow_id: str) -> Result:
        """Rollback на workflow"""
        pass