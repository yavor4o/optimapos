#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optimapos.settings')
django.setup()

from nomenclatures.services._status_resolver import StatusResolver
from nomenclatures.models import DocumentType

def test_final_statuses():
    print("🧪 Testing Final Status Configuration")
    print("="*50)
    
    try:
        delivery_doc_type = DocumentType.objects.filter(type_key__icontains='delivery').first()
        
        if not delivery_doc_type:
            print("❌ No delivery document type found")
            return
            
        # Get all final statuses
        final_statuses = StatusResolver.get_final_statuses(delivery_doc_type)
        print(f"🏁 Final statuses configured: {final_statuses}")
        
        # Get all statuses and check which are final
        from nomenclatures.models import DocumentTypeStatus
        all_configs = DocumentTypeStatus.objects.filter(
            document_type=delivery_doc_type,
            is_active=True
        ).select_related('status').order_by('sort_order')
        
        print(f"\n📋 All statuses for {delivery_doc_type.name}:")
        for config in all_configs:
            is_final = "🏁" if config.is_final else "  "
            is_cancel = "🚫" if config.is_cancellation else "  "
            print(f"{is_final} {is_cancel} {config.status.code} (final: {config.is_final}, cancel: {config.is_cancellation})")
            
        print(f"\n🔍 Cancel logic analysis:")
        print("Cancel button will NOT appear for:")
        print("1. Documents already in cancellation status (cancelled)")
        print("2. Documents in final status (if any are marked is_final=True)")
        print("3. Documents where cancellation status is not configured")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_final_statuses()