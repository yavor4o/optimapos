# nomenclatures/services/document/__init__.py
"""
Document service components - SPLIT VERSION

Разделяме големия DocumentService на специализирани компоненти:
- DocumentCreator: създаване на документи
- StatusManager: управление на статуси
- DocumentValidator: валидации
- DocumentQuery: queries и информация
"""

from .creator import DocumentCreator
from .status_manager import StatusManager
from .validator import DocumentValidator
from .query import DocumentQuery

__all__ = [
    'DocumentCreator',
    'StatusManager',
    'DocumentValidator',
    'DocumentQuery'
]