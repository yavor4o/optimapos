#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optimapos.settings')
django.setup()

from nomenclatures.services import DocumentService
from nomenclatures.services._status_resolver import StatusResolver
from nomenclatures.models import DocumentType
from purchases.models import DeliveryReceipt
from accounts.models import User

def test_cancel_logic():
    print("🧪 Testing Cancel Button Logic")
    print("="*50)
    
    try:
        user = User.objects.first()
        delivery_doc_type = DocumentType.objects.filter(type_key__icontains='delivery').first()
        delivery = DeliveryReceipt.objects.first()
        
        if not all([user, delivery_doc_type, delivery]):
            print("❌ Missing test data")
            return
            
        print(f"📋 Document type: {delivery_doc_type.name}")
        print(f"📦 Document: {delivery.document_number} (status: {delivery.status})")
        print()
        
        # Check cancellation status configuration
        cancellation_status = StatusResolver.get_cancellation_status(delivery_doc_type)
        print(f"🔧 Cancellation status configured: {cancellation_status}")
        
        # Get available next statuses
        available_statuses = StatusResolver.get_next_possible_statuses(delivery_doc_type, delivery.status)
        print(f"🔄 Available next statuses from '{delivery.status}': {available_statuses}")
        
        # Check if cancellation is in available statuses
        can_cancel = cancellation_status in available_statuses if cancellation_status else False
        print(f"✅ Can cancel: {can_cancel} (cancellation_status in available_statuses)")
        
        print()
        print("🎯 Cancel button appears when:")
        print("1. Document type has cancellation status configured (is_cancellation=True)")  
        print("2. Current document status allows transition to cancellation status")
        print("3. Cancellation status is in get_next_possible_statuses() list")
        
        # Test with DocumentService
        service = DocumentService(delivery, user)
        semantic_actions = service.get_available_semantic_actions()
        print(f"\n🔍 DocumentService.can_cancel: {semantic_actions.get('can_cancel', False)}")
        
        # Show all document type statuses for analysis
        from nomenclatures.models import DocumentTypeStatus
        all_configs = DocumentTypeStatus.objects.filter(
            document_type=delivery_doc_type,
            is_active=True
        ).select_related('status').order_by('sort_order')
        
        print(f"\n📋 All statuses for {delivery_doc_type.name}:")
        for i, config in enumerate(all_configs):
            is_current = "👉" if config.status.code == delivery.status else "  "
            is_cancel = "🚫" if config.is_cancellation else "  "
            print(f"{is_current} {is_cancel} {i+1}. {config.status.code} (cancellation: {config.is_cancellation})")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cancel_logic()