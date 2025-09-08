#!/usr/bin/env python
"""
Debug скрипт за проследяване на delivery статуси и creation actions

Проверява:
1. Какви DocumentType-и има за delivery
2. Какви статуси са конфигурирани за всеки DocumentType  
3. Как работи get_initial_status
4. Как работи get_next_possible_statuses
5. Как работи get_creation_actions
"""
import os
import sys
import django

# Setup Django
sys.path.append('/Users/yavordobrev/Desktop/projects/optimapos')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from nomenclatures.models import DocumentType, DocumentTypeStatus, DocumentStatus
from nomenclatures.services._status_resolver import StatusResolver
from nomenclatures.services.document_service import DocumentService
from purchases.models import DeliveryReceipt
from django.contrib.auth import get_user_model
from purchases.services.purchase_service import PurchaseDocumentService

User = get_user_model()

def debug_delivery_document_types():
    print("=" * 60)
    print("1. DELIVERY DOCUMENT TYPES")
    print("=" * 60)
    
    # Find document types related to delivery
    doc_types = DocumentType.objects.filter(
        app_name='purchases'
    ).order_by('name')
    
    if not doc_types.exists():
        print("❌ No document types found for app 'purchases'")
        # Try legacy lookup
        doc_types = DocumentType.objects.filter(
            name__icontains='delivery'
        ).order_by('name')
        print(f"Found {doc_types.count()} document types with 'delivery' in name")
    else:
        print(f"Found {doc_types.count()} document types for app 'purchases'")
    
    for doc_type in doc_types:
        print(f"\nDocumentType: {doc_type.name} (ID: {doc_type.id})")
        print(f"  - Code: {doc_type.code}")
        print(f"  - App: {doc_type.app_name}")
        print(f"  - Type Key: {doc_type.type_key}")
        print(f"  - Is Active: {doc_type.is_active}")
        
        # Show configured statuses
        statuses = DocumentTypeStatus.objects.filter(
            document_type=doc_type,
            is_active=True
        ).select_related('status').order_by('sort_order')
        
        print(f"  - Configured Statuses ({statuses.count()}):")
        for status_config in statuses:
            flags = []
            if status_config.is_initial: flags.append("INITIAL")
            if status_config.is_final: flags.append("FINAL")
            if status_config.allow_edit: flags.append("EDITABLE")
            if status_config.allow_delete: flags.append("DELETABLE")
            
            print(f"    * {status_config.status.code} ({status_config.status.name}) "
                  f"[Order: {status_config.sort_order}] "
                  f"[{', '.join(flags) if flags else 'No flags'}]")

    return doc_types.first()  # Return first found for further testing


def debug_status_resolver_methods(doc_type):
    if not doc_type:
        print("❌ No document type available for StatusResolver testing")
        return
        
    print("\n" + "=" * 60)
    print("2. STATUS RESOLVER METHODS")
    print("=" * 60)
    
    print(f"\nTesting StatusResolver methods for DocumentType: {doc_type.name}")
    
    # Test get_initial_status
    initial = StatusResolver.get_initial_status(doc_type)
    print(f"✅ get_initial_status(): '{initial}'")
    
    if initial:
        # Test get_next_possible_statuses from initial
        next_statuses = StatusResolver.get_next_possible_statuses(doc_type, initial)
        print(f"✅ get_next_possible_statuses('{initial}'): {next_statuses}")
        
        # Test get_final_statuses
        final_statuses = StatusResolver.get_final_statuses(doc_type)
        print(f"✅ get_final_statuses(): {final_statuses}")
        
        return initial
    else:
        print("❌ No initial status found!")
        return None


def debug_creation_actions(doc_type, initial_status):
    if not doc_type or not initial_status:
        print("❌ Cannot test creation actions without doc_type and initial_status")
        return
        
    print("\n" + "=" * 60)
    print("3. CREATION ACTIONS")
    print("=" * 60)
    
    # Create a test delivery receipt (not saved to DB)
    test_delivery = DeliveryReceipt()
    test_delivery.document_type = doc_type
    
    # Get test user
    try:
        user = User.objects.first()
        if not user:
            print("❌ No users found in database")
            return
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return
    
    print(f"Testing creation actions with user: {user.username}")
    
    # Test DocumentService.get_creation_actions
    try:
        doc_service = DocumentService(test_delivery, user)
        creation_actions = doc_service.get_creation_actions()
        
        print(f"✅ DocumentService.get_creation_actions() returned {len(creation_actions)} actions:")
        for i, action in enumerate(creation_actions, 1):
            print(f"  {i}. Action: {action.get('action')}")
            print(f"     Label: {action.get('label')}")
            print(f"     Target Status: {action.get('target_status')}")
            print(f"     Button Style: {action.get('button_style')}")
            print(f"     Can Perform: {action.get('can_perform')}")
            print()
            
    except Exception as e:
        print(f"❌ Error getting creation actions: {e}")
        import traceback
        traceback.print_exc()


def debug_purchase_service_creation(doc_type, initial_status):
    print("\n" + "=" * 60)
    print("4. PURCHASE SERVICE CREATION")
    print("=" * 60)
    
    # Test with PurchaseDocumentService 
    try:
        user = User.objects.first()
        test_delivery = DeliveryReceipt()
        test_delivery.document_type = doc_type
        test_delivery.status = initial_status
        
        purchase_service = PurchaseDocumentService(test_delivery, user)
        creation_actions = purchase_service.facade.get_creation_actions()
        
        print(f"✅ PurchaseDocumentService creation actions ({len(creation_actions)}):")
        for i, action in enumerate(creation_actions, 1):
            print(f"  {i}. {action}")
            
    except Exception as e:
        print(f"❌ Error with PurchaseDocumentService: {e}")
        import traceback
        traceback.print_exc()


def debug_transition_capabilities(doc_type, initial_status):
    print("\n" + "=" * 60)
    print("5. TRANSITION CAPABILITIES")
    print("=" * 60)
    
    if not initial_status:
        print("❌ No initial status to test transitions")
        return
        
    print(f"Testing transition capabilities from initial status: '{initial_status}'")
    
    try:
        # Get all possible next statuses
        next_statuses = StatusResolver.get_next_possible_statuses(doc_type, initial_status)
        
        if next_statuses:
            print(f"✅ Possible transitions from '{initial_status}':")
            for status in next_statuses:
                print(f"  → {status}")
                
            # Test what happens if we try to transition to first next status
            target_status = next_statuses[0]
            print(f"\n🔄 Testing transition to '{target_status}':")
            
            # Check if target status is valid
            target_config = DocumentTypeStatus.objects.filter(
                document_type=doc_type,
                status__code=target_status,
                is_active=True
            ).first()
            
            if target_config:
                print(f"✅ Target status '{target_status}' exists in configuration")
                print(f"   - Name: {target_config.status.name}")
                print(f"   - Is Final: {target_config.is_final}")
                print(f"   - Allow Edit: {target_config.allow_edit}")
            else:
                print(f"❌ Target status '{target_status}' NOT found in configuration!")
                
        else:
            print(f"❌ No next statuses available from '{initial_status}'")
            
    except Exception as e:
        print(f"❌ Error testing transitions: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("🔍 DEBUGGING DELIVERY DOCUMENT STATUS CONFIGURATION")
    print("📅 Date:", __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    try:
        # Step 1: Find document types
        doc_type = debug_delivery_document_types()
        
        # Step 2: Test StatusResolver methods  
        initial_status = debug_status_resolver_methods(doc_type)
        
        # Step 3: Test creation actions
        debug_creation_actions(doc_type, initial_status)
        
        # Step 4: Test purchase service
        debug_purchase_service_creation(doc_type, initial_status)
        
        # Step 5: Test transition capabilities
        debug_transition_capabilities(doc_type, initial_status)
        
        print("\n" + "=" * 60)
        print("✅ DEBUG COMPLETED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()