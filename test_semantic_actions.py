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

def test_semantic_actions():
    print("🧪 Testing Semantic Actions Refactoring")
    print("="*50)
    
    try:
        # Get first user and document type
        user = User.objects.first()
        if not user:
            print("❌ No users found")
            return
            
        delivery_doc_type = DocumentType.objects.filter(type_key__icontains='delivery').first()
        if not delivery_doc_type:
            print("❌ No delivery document type found")
            return
            
        print(f"📋 Using document type: {delivery_doc_type.name}")
        print(f"👤 Using user: {user.username}")
        print()
        
        # Test StatusResolver new methods
        print("🔧 Testing StatusResolver methods:")
        print("-" * 30)
        
        initial_status = StatusResolver.get_initial_status(delivery_doc_type)
        print(f"Initial status: {initial_status}")
        
        approval_status = StatusResolver.get_approval_status(delivery_doc_type)  
        print(f"Approval status: {approval_status}")
        
        rejection_status = StatusResolver.get_rejection_status(delivery_doc_type)
        print(f"Rejection status: {rejection_status}")
        
        cancellation_status = StatusResolver.get_cancellation_status(delivery_doc_type)
        print(f"Cancellation status: {cancellation_status}")
        print()
        
        # Test with existing delivery if available
        delivery = DeliveryReceipt.objects.first()
        if delivery:
            print(f"📦 Testing with existing delivery: {delivery.document_number}")
            print("-" * 40)
            
            service = DocumentService(delivery, user)
            
            # Test semantic actions availability
            available_actions = service.get_available_semantic_actions()
            print(f"Available semantic actions:")
            for action, available in available_actions.items():
                print(f"  {action}: {'✅' if available else '❌'}")
            print()
            
            # Test semantic action labels
            action_labels = service.get_semantic_action_labels()
            print(f"Semantic action labels:")
            for action, label in action_labels.items():
                print(f"  {action}: '{label}'")
            print()
            
        else:
            print("📦 No existing delivery found - skipping delivery tests")
            
        print("✅ All semantic actions tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_semantic_actions()