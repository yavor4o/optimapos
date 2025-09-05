# core/interfaces/service_registry.py
"""
Service Registry Pattern - Централизирано управление на service dependencies

ЦЕЛ: Замести директните импорти с interface-based resolution
ПРОБЛЕМ: purchase services импортират директно ProductService, PricingService и т.н.
РЕШЕНИЕ: Registry който resolve-ва интерфейси към конкретни имплементации

USAGE:
    from core.interfaces.service_registry import ServiceRegistry
    
    # В модел или service
    pricing_service = ServiceRegistry.resolve('IPricingService')
    product_service = ServiceRegistry.resolve('IProductService')
"""

from typing import Dict, Type, Any, Optional, Protocol
import logging
from django.utils.module_loading import import_string
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Централен регистър за service resolution
    
    АРХИТЕКТУРА:
    - Регистрира interface → implementation mappings
    - Resolve-ва services по interface име
    - Кешира instances за performance
    - Fallback към директни импорти за backward compatibility
    """
    
    _registry: Dict[str, str] = {}
    _instances: Dict[str, Any] = {}
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Инициализира registry с default mappings"""
        if cls._initialized:
            return
            
        # Default service mappings
        cls._registry.update({
            'IPricingService': 'pricing.services.pricing_service.PricingService',
            'IProductService': 'products.services.product_service.ProductService', 
            'IProductValidationService': 'products.services.validation_service.ProductValidationService',
            'IInventoryService': 'inventory.services.inventory_service.InventoryService',
            'IMovementService': 'inventory.services.movement_service.MovementService',
            'ISupplierService': 'partners.services.supplier_service.SupplierService',
            'ICustomerService': 'partners.services.customer_service.CustomerService',
            'IVATCalculationService': 'nomenclatures.services.vat_calculation_service.VATCalculationService',
        })
        
        cls._initialized = True
        logger.info("ServiceRegistry initialized with %d services", len(cls._registry))
    
    @classmethod
    def register(cls, interface_name: str, implementation_path: str):
        """
        Регистрира interface → implementation mapping
        
        Args:
            interface_name: Името на интерфейса (напр. 'IPricingService')
            implementation_path: Пълният import path (напр. 'pricing.services.PricingService')
        """
        cls._registry[interface_name] = implementation_path
        # Изчисти кеша ако имплементацията се променя
        if interface_name in cls._instances:
            del cls._instances[interface_name]
        logger.debug("Registered %s -> %s", interface_name, implementation_path)
    
    @classmethod
    def resolve(cls, interface_name: str, use_cache: bool = True) -> Any:
        """
        Resolve-ва service по interface име
        
        Args:
            interface_name: Името на интерфейса
            use_cache: Дали да използва кешираната instance
            
        Returns:
            Service instance
            
        Raises:
            ImproperlyConfigured: Ако service не може да се resolve-не
        """
        cls.initialize()
        
        # Проверка за кеширана instance
        if use_cache and interface_name in cls._instances:
            return cls._instances[interface_name]
        
        # Намери implementation path
        implementation_path = cls._registry.get(interface_name)
        if not implementation_path:
            raise ImproperlyConfigured(
                f"No implementation registered for interface '{interface_name}'. "
                f"Available interfaces: {list(cls._registry.keys())}"
            )
        
        try:
            # Импортирай и инстанцирай
            service_class = import_string(implementation_path)
            service_instance = service_class()
            
            # Кеширай instance
            if use_cache:
                cls._instances[interface_name] = service_instance
            
            logger.debug("Resolved %s -> %s", interface_name, service_instance.__class__.__name__)
            return service_instance
            
        except (ImportError, AttributeError) as e:
            raise ImproperlyConfigured(
                f"Could not import service '{implementation_path}' for interface '{interface_name}': {e}"
            )
    
    @classmethod
    def clear_cache(cls):
        """Изчиства кеша на instances"""
        cls._instances.clear()
        logger.debug("Service cache cleared")
    
    @classmethod
    def get_registered_interfaces(cls) -> Dict[str, str]:
        """Връща всички регистрирани интерфейси"""
        cls.initialize()
        return cls._registry.copy()
    
    @classmethod
    def is_registered(cls, interface_name: str) -> bool:
        """Проверява дали interface е регистриран"""
        cls.initialize()
        return interface_name in cls._registry


# =================================================================
# MIXIN ЗА ЛЕСНА ИНТЕГРАЦИЯ
# =================================================================

class ServiceResolverMixin:
    """
    Mixin за лесно използване на ServiceRegistry в models/services
    
    USAGE:
        class DeliveryReceipt(ServiceResolverMixin, models.Model):
            def calculate_totals(self):
                pricing_service = self.get_service('IPricingService')
                product_service = self.get_service('IProductService')
    """
    
    def get_service(self, interface_name: str, use_cache: bool = True):
        """
        Convenience method за resolve-ване на services
        
        Args:
            interface_name: Името на интерфейса
            use_cache: Дали да използва кеша
            
        Returns:
            Service instance
        """
        return ServiceRegistry.resolve(interface_name, use_cache)
    
    def get_pricing_service(self):
        """Shortcut за pricing service"""
        return self.get_service('IPricingService')
    
    def get_product_service(self):
        """Shortcut за product service"""
        return self.get_service('IProductService')
    
    def get_inventory_service(self):
        """Shortcut за inventory service"""
        return self.get_service('IInventoryService')
    
    def get_validation_service(self):
        """Shortcut за validation service"""
        return self.get_service('IProductValidationService')


# =================================================================
# FALLBACK PATTERNS
# =================================================================

def get_service_with_fallback(interface_name: str, fallback_import_path: str = None):
    """
    Helper за постепенна миграция - опитва registry, след това fallback
    
    Args:
        interface_name: Името на интерфейса
        fallback_import_path: Fallback import ако registry не работи
        
    Returns:
        Service instance
    """
    try:
        return ServiceRegistry.resolve(interface_name)
    except ImproperlyConfigured:
        if fallback_import_path:
            logger.warning(
                "ServiceRegistry failed for %s, using fallback: %s",
                interface_name, fallback_import_path
            )
            service_class = import_string(fallback_import_path)
            return service_class()
        else:
            raise


# =================================================================
# DEBUGGING HELPERS
# =================================================================

def debug_service_registry():
    """Debug helper - показва състоянието на registry"""
    ServiceRegistry.initialize()
    
    print("🔧 SERVICE REGISTRY DEBUG")
    print("=" * 50)
    
    print(f"📋 Registered interfaces ({len(ServiceRegistry._registry)}):")
    for interface, implementation in ServiceRegistry._registry.items():
        print(f"  • {interface} -> {implementation}")
    
    print(f"\n💾 Cached instances ({len(ServiceRegistry._instances)}):")
    for interface, instance in ServiceRegistry._instances.items():
        print(f"  • {interface} -> {instance.__class__.__name__}")
    
    print("\n🧪 Testing resolution:")
    for interface in ServiceRegistry._registry:
        try:
            service = ServiceRegistry.resolve(interface, use_cache=False)
            print(f"  ✅ {interface} -> {service.__class__.__name__}")
        except Exception as e:
            print(f"  ❌ {interface} -> ERROR: {e}")