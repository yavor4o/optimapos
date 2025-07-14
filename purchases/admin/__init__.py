# # purchases/admin/__init__.py
#
# """
# Purchases admin configuration
#
# Организирана структура за admin interface:
# - documents.py: PurchaseDocument admin
# - lines.py: PurchaseDocumentLine admin
# - document_types.py: DocumentType admin
# - audit.py: PurchaseAuditLog admin
# """
#
# from .documents import PurchaseDocumentAdmin
# from .lines import PurchaseDocumentLineAdmin
# from .document_types import DocumentTypeAdmin
# from .audit import PurchaseAuditLogAdmin
#
# __all__ = [
#     'PurchaseDocumentAdmin',
#     'PurchaseDocumentLineAdmin',
#     'DocumentTypeAdmin',
#     'PurchaseAuditLogAdmin',
# ]