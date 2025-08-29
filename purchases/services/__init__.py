# purchases/services/__init__.py - CLEAN START

"""
Purchase Services - Thin Wrappers ONLY

 &: 100% 87?>;720=5 =0 nomenclatures services
- A8G:8 operations -> DocumentService facade
- !0<> domain-specific purchase conversions
- 0% 4C1;8@0=0 ;>38:0
"""

from .purchase_service import (
    PurchaseDocumentService,
    PurchaseRequestService, 
    PurchaseOrderService,
    DeliveryReceiptService
)

__all__ = [
    'PurchaseDocumentService',
    'PurchaseRequestService',
    'PurchaseOrderService', 
    'DeliveryReceiptService'
]