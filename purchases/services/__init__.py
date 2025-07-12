# purchases/services/__init__.py

"""
Purchases services package

Организация:
- procurement_service.py: Основна бизнес логика за закупки
- document_service.py: Работа с документи и workflow
- reporting_service.py: Анализи и отчети
- integration_service.py: Интеграция с други модули
"""

from .procurement_service import ProcurementService
from .document_service import DocumentService
from .reporting_service import ReportingService

__all__ = [
    'ProcurementService',
    'DocumentService',
    'ReportingService',
]