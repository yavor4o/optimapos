# core/interfaces/document_interface.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from core.utils.result import Result


class IDocumentService(ABC):
    """Interface за всички document-related services"""

    @abstractmethod
    def create_document(self, model_class, data: Dict, user, location) -> Result:
        """Създава нов документ"""
        pass

    @abstractmethod
    def transition_document(self, document, to_status: str, user, comments: str = '') -> Result:
        """Променя статус на документ"""
        pass

    @abstractmethod
    def get_available_actions(self, document, user) -> List[Dict]:
        """Връща възможните действия за документ"""
        pass

    @abstractmethod
    def can_edit_document(self, document, user) -> tuple[bool, str]:
        """Проверява дали документ може да се редактира"""
        pass

    @abstractmethod
    def get_initial_status(self, document_type) -> str:
        """Връща началния статус за тип документ"""
        pass