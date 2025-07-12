# purchases/managers/__init__.py

"""
Purchases managers package

Организация:
- document_manager.py: Специализирани querysets за PurchaseDocument
- line_manager.py: Специализирани querysets за PurchaseDocumentLine
"""

from .document_manager import PurchaseDocumentManager
from .line_manager import PurchaseLineManager

__all__ = [
    'PurchaseDocumentManager',
    'PurchaseLineManager',
]