# purchases/models.py

"""
Purchases models - import all from organized structure

Това е compatibility файл който импортира всички модели
от новата организирана структура в models/ папката.

За backward compatibility всички импорти ще работят както преди:
from purchases.models import PurchaseDocument, DocumentType, etc.
"""

# Import all models from the organized structure
from .base import DocumentManager,LineManager,BaseDocument, BaseDocumentLine


from .procurement import (
    DocumentType,
    PurchaseDocument
)

from .transactions import (
    PurchaseDocumentLine,
    PurchaseAuditLog
)

# За backward compatibility експортираме всичко
__all__ = [
    # Base
    'DocumentManager',
    'LineManager',
    'BaseDocument',
    'BaseDocumentLine',

    # Procurement
    'DocumentType',
    'PurchaseDocument',

    # Transactions
    'PurchaseDocumentLine',
    'PurchaseAuditLog',
]