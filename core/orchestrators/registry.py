# core/orchestrators/registry.py
from typing import Dict, Any


class ServiceRegistry:
    """
    Централен registry за всички services
    Singleton pattern
    """
    _instance = None
    _services: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, service: Any):
        """Регистрира service"""
        self._services[name] = service
        print(f"✅ Registered service: {name}")

    def get(self, name: str) -> Any:
        """Взима service по име"""
        if name not in self._services:
            raise ValueError(f"Service '{name}' not found")
        return self._services[name]

    def list_services(self):
        """Списък на всички регистрирани services"""
        return list(self._services.keys())