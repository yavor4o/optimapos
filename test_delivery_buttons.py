#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optimapos.settings')
django.setup()

from purchases.models import DeliveryReceipt
from purchases.services.purchase_service import PurchaseDocumentService
from accounts.models import User

def test_delivery_buttons():
    print("🧪 Testing Delivery Receipt Button Logic")
    print("="*60)
    
    try:
        user = User.objects.first()
        if not user:
            print("❌ No users found")
            return
            
        print(f"👤 Using user: {user.username}")
        print()
        
        # Test with different document statuses
        test_statuses = ['draft', 'completed', 'cancelled', 'rejected']
        
        for status in test_statuses:
            # Find or create.html delivery with this status
            delivery = DeliveryReceipt.objects.filter(status=status).first()
            
            if not delivery:
                print(f"📦 No delivery with status '{status}' found, skipping...")
                continue
                
            print(f"📦 Testing delivery {delivery.document_number} (status: {status})")
            print(f"   Document type: {delivery.document_type}")
            print(f"   Has document_type: {bool(delivery.document_type)}")
            
            # Test semantic actions using PurchaseDocumentService
            if delivery.document_type:
                doc_service = PurchaseDocumentService(delivery, user)
                
                # Get available semantic actions
                try:
                    available_actions = doc_service.facade.get_available_semantic_actions()
                    action_labels = doc_service.facade.get_semantic_action_labels()
                    
                    print(f"   Available semantic actions:")
                    for action, available in available_actions.items():
                        indicator = "✅" if available else "❌"
                        label = action_labels.get(action.replace('can_', ''), 'No label')
                        print(f"     {indicator} {action}: '{label}'")
                        
                except Exception as e:
                    print(f"   ❌ Error getting semantic actions: {e}")
                    
            else:
                print(f"   ⚠️  No document_type configured - buttons won't work")
            
            print()
            
        # Show template context simulation
        print("🎨 Template Context Simulation:")
        print("-" * 40)
        
        # Get a real delivery to simulate template context
        delivery = DeliveryReceipt.objects.first()
        if delivery and delivery.document_type:
            doc_service = PurchaseDocumentService(delivery, user)
            
            # Simulate _get_semantic_actions_for_delivery logic
            available_actions = doc_service.facade.get_available_semantic_actions()
            action_labels = doc_service.facade.get_semantic_action_labels()
            
            # Simulate permission checks
            final_actions = {}
            
            # Mock user.has_perm() as True for testing
            if available_actions.get('can_approve'):
                final_actions['approve'] = True
                
            if available_actions.get('can_submit'):
                final_actions['submit'] = True
                
            if available_actions.get('can_reject'):
                final_actions['reject'] = True
                
            if available_actions.get('can_return_to_draft'):
                final_actions['return_to_draft'] = True
                
            if available_actions.get('can_cancel'):
                final_actions['cancel'] = True
                
            print(f"Template context 'semantic_actions':")
            print(f"  available: {final_actions}")
            print(f"  labels: {action_labels}")
            print()
            
            print("🎯 Buttons that will appear in template:")
            for action, available in final_actions.items():
                if available:
                    label = action_labels.get(action, action.title())
                    print(f"  ✅ {action.upper()} button: '{label}'")
                    
        else:
            print("❌ No delivery with document_type found for template simulation")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_delivery_buttons()