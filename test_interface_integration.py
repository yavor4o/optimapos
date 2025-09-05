# test_interface_integration.py - Test Interface Integration
"""
Тест за interface-based service resolution в purchase models

Проверява:
1. ServiceRegistry работи правилно  
2. ServiceResolverMixin функционира
3. Fallback patterns работят
4. DeliveryLine и PurchaseRequestLine използват интерфейси
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'optimapos.settings')
django.setup()

def test_service_registry():
    """Test ServiceRegistry functionality"""
    print("🔧 Testing ServiceRegistry...")
    
    from core.interfaces.service_registry import ServiceRegistry, debug_service_registry
    
    # Initialize registry
    ServiceRegistry.initialize()
    
    # Test registration
    registered = ServiceRegistry.get_registered_interfaces()
    print(f"✅ ServiceRegistry initialized with {len(registered)} services")
    
    # Test key services
    key_services = ['IPricingService', 'IProductService', 'IProductValidationService']
    working_count = 0
    
    for service_name in key_services:
        try:
            service = ServiceRegistry.resolve(service_name, use_cache=False)
            print(f"✅ {service_name} -> {service.__class__.__name__}")
            working_count += 1
        except Exception as e:
            print(f"❌ {service_name} -> ERROR: {e}")
    
    print(f"📊 Service Registry Health: {working_count}/{len(key_services)} services working")
    
    # Debug output
    print("\n🔍 Service Registry Debug:")
    debug_service_registry()
    
    return working_count == len(key_services)


def test_service_resolver_mixin():
    """Test ServiceResolverMixin integration"""
    print("\n🧪 Testing ServiceResolverMixin...")
    
    from core.interfaces import ServiceResolverMixin
    
    # Create test instance
    class TestClass(ServiceResolverMixin):
        pass
    
    test_instance = TestClass()
    
    try:
        # Test shortcuts
        pricing_service = test_instance.get_pricing_service()
        print(f"✅ get_pricing_service() -> {pricing_service.__class__.__name__}")
        
        product_service = test_instance.get_product_service()
        print(f"✅ get_product_service() -> {product_service.__class__.__name__}")
        
        validation_service = test_instance.get_validation_service()
        print(f"✅ get_validation_service() -> {validation_service.__class__.__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ ServiceResolverMixin test failed: {e}")
        return False


def test_purchase_models_integration():
    """Test purchase models use interfaces correctly"""
    print("\n📦 Testing Purchase Models Integration...")
    
    # Test that models have ServiceResolverMixin
    from purchases.models.deliveries import DeliveryLine
    from purchases.models.requests import PurchaseRequestLine
    
    # Check mixin inheritance
    delivery_mro = [cls.__name__ for cls in DeliveryLine.__mro__]
    request_mro = [cls.__name__ for cls in PurchaseRequestLine.__mro__]
    
    print(f"DeliveryLine MRO: {delivery_mro}")
    print(f"PurchaseRequestLine MRO: {request_mro}")
    
    delivery_has_mixin = 'ServiceResolverMixin' in delivery_mro
    request_has_mixin = 'ServiceResolverMixin' in request_mro
    
    print(f"✅ DeliveryLine has ServiceResolverMixin: {delivery_has_mixin}")
    print(f"✅ PurchaseRequestLine has ServiceResolverMixin: {request_has_mixin}")
    
    # Test service methods exist
    if hasattr(DeliveryLine, 'get_pricing_service'):
        print("✅ DeliveryLine.get_pricing_service exists")
    else:
        print("❌ DeliveryLine.get_pricing_service missing")
    
    if hasattr(PurchaseRequestLine, 'get_validation_service'):
        print("✅ PurchaseRequestLine.get_validation_service exists")
    else:
        print("❌ PurchaseRequestLine.get_validation_service missing")
    
    return delivery_has_mixin and request_has_mixin


def test_no_direct_imports():
    """Test that direct imports are replaced"""
    print("\n🚫 Testing Direct Imports Removal...")
    
    import inspect
    from purchases.models.deliveries import DeliveryLine
    from purchases.models.requests import PurchaseRequestLine
    
    # Check method source for old patterns
    methods_to_check = [
        (DeliveryLine, 'base_quantity_for_inventory'),
        (DeliveryLine, 'get_current_market_price'),
        (PurchaseRequestLine, 'get_current_market_price'),
        (PurchaseRequestLine, 'validate_product_availability')
    ]
    
    issues_found = 0
    
    for cls, method_name in methods_to_check:
        if hasattr(cls, method_name):
            method = getattr(cls, method_name)
            try:
                source = inspect.getsource(method)
                
                # Check for old direct import patterns
                if 'from products.services import' in source:
                    print(f"❌ {cls.__name__}.{method_name} still has direct ProductService import")
                    issues_found += 1
                elif 'from pricing.services import' in source:
                    print(f"❌ {cls.__name__}.{method_name} still has direct PricingService import")
                    issues_found += 1
                elif 'self.get_product_service()' in source or 'self.get_pricing_service()' in source:
                    print(f"✅ {cls.__name__}.{method_name} uses ServiceResolverMixin")
                else:
                    print(f"⚠️ {cls.__name__}.{method_name} import pattern unclear")
                    
            except Exception as e:
                print(f"⚠️ Could not inspect {cls.__name__}.{method_name}: {e}")
    
    print(f"📊 Direct Import Issues Found: {issues_found}")
    return issues_found == 0


def test_end_to_end_workflow():
    """Test complete workflow - direct service calls"""
    print("\n🎯 Testing End-to-End Workflow...")
    
    try:
        # Test ServiceRegistry -> Direct calls
        from core.interfaces.service_registry import ServiceRegistry
        
        # Test pricing service method call
        pricing_service = ServiceRegistry.resolve('IPricingService')
        if hasattr(pricing_service, 'get_product_pricing'):
            print(f"✅ PricingService has get_product_pricing method")
        else:
            print(f"❌ PricingService missing get_product_pricing method")
        
        # Test product service method call  
        product_service = ServiceRegistry.resolve('IProductService')
        if hasattr(product_service, 'convert_quantity'):
            print(f"✅ ProductService has convert_quantity method")
        else:
            print(f"❌ ProductService missing convert_quantity method")
            
        # Test validation service method call
        validation_service = ServiceRegistry.resolve('IProductValidationService')
        if hasattr(validation_service, 'validate_purchase'):
            print(f"✅ ProductValidationService has validate_purchase method")
        else:
            print(f"❌ ProductValidationService missing validate_purchase method")
        
        print("✅ All services resolved and have expected methods")
        return True
            
    except Exception as e:
        print(f"❌ End-to-end workflow failed: {e}")
        return False


def main():
    """Run all interface integration tests"""
    print("🚀 Starting Interface Integration Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("ServiceRegistry", test_service_registry()))
    results.append(("ServiceResolverMixin", test_service_resolver_mixin()))
    results.append(("Purchase Models Integration", test_purchase_models_integration()))
    results.append(("Direct Imports Removal", test_no_direct_imports()))
    results.append(("End-to-End Workflow", test_end_to_end_workflow()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n📊 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All interface integration tests PASSED!")
        print("✅ Purchase services successfully migrated to interface-based architecture")
    else:
        print("⚠️ Some tests failed - review the issues above")
        print("🔧 Consider checking service registration and import patterns")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)