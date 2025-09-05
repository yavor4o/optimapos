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

def test_cancel_different_statuses():
    print("🧪 Testing Cancel Button for Different Document Statuses")
    print("="*60)
    
    try:
        user = User.objects.first()
        delivery_doc_type = DocumentType.objects.filter(type_key__icontains='delivery').first()
        
        if not all([user, delivery_doc_type]):
            print("❌ Missing test data")
            return
            
        # Get all possible statuses
        from nomenclatures.models import DocumentTypeStatus
        all_statuses = DocumentTypeStatus.objects.filter(
            document_type=delivery_doc_type,
            is_active=True
        ).select_related('status').order_by('sort_order')
        
        cancellation_status = StatusResolver.get_cancellation_status(delivery_doc_type)
        print(f"🚫 Cancellation status: {cancellation_status}")
        print()
        
        for config in all_statuses:
            status_code = config.status.code
            
            # Test what happens from this status
            available_next = StatusResolver.get_next_possible_statuses(delivery_doc_type, status_code)
            can_cancel = cancellation_status in available_next if cancellation_status else False
            
            status_indicator = "👉" if status_code == 'draft' else "  "
            cancel_indicator = "✅" if can_cancel else "❌"
            
            print(f"{status_indicator} Status '{status_code}': {cancel_indicator} can_cancel")
            print(f"    Available next: {available_next}")
            print()
            
        print("📝 Summary:")
        print("Cancel button appears when:")
        print("1. ✅ Document type has cancellation status configured (cancelled)")
        print("2. ✅ Current status allows transition to cancellation status")
        print("3. ✅ Cancellation status is in get_next_possible_statuses() list")
        print()
        print("🔄 Logic in get_next_possible_statuses():")
        print("- Gets statuses after current in sort_order")
        print("- Always adds cancellation status if configured")
        print("- So cancel is available from ALL statuses except final ones")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cancel_different_statuses()