# core/utils/result.py
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field


class ErrorCategory:
    """Standardized error categories for better error handling"""
    VALIDATION = "VALIDATION"
    BUSINESS = "BUSINESS" 
    SYSTEM = "SYSTEM"
    PERMISSION = "PERMISSION"
    NETWORK = "NETWORK"


@dataclass
class Result:
    """
    Enhanced унифициран response за всички services
    
    BACKWARD COMPATIBLE: Всички съществуващи използвания продължават да работят!
    
    Нови функции:
    - Error categorization за по-добро UX handling
    - Field-level errors за forms валидация  
    - Context data за debugging и logging
    """
    ok: bool
    code: str = 'SUCCESS'
    msg: str = ''
    data: Optional[Dict[str, Any]] = None
    
    # 🆕 NEW: Enhanced error handling (backward compatible)
    category: str = ErrorCategory.SYSTEM
    field_errors: Optional[Dict[str, List[str]]] = field(default_factory=dict)
    context: Optional[Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def success(cls, data=None, msg='Operation successful', context=None):
        """Enhanced success result with optional context"""
        return cls(
            ok=True, 
            code='SUCCESS', 
            msg=msg, 
            data=data or {},
            category=ErrorCategory.SYSTEM,
            context=context or {}
        )

    @classmethod
    def error(cls, code: str, msg: str, data=None, category=None, field_errors=None, context=None):
        """Enhanced error result with categorization and field errors"""
        return cls(
            ok=False, 
            code=code, 
            msg=msg, 
            data=data or {},
            category=category or ErrorCategory.SYSTEM,
            field_errors=field_errors or {},
            context=context or {}
        )
    
    # 🆕 NEW: Convenience methods for common error types
    @classmethod
    def validation_error(cls, msg: str, field_errors=None, context=None):
        """Create validation error with field-level details"""
        return cls.error(
            code='VALIDATION_ERROR',
            msg=msg,
            category=ErrorCategory.VALIDATION,
            field_errors=field_errors or {},
            context=context or {}
        )
    
    @classmethod 
    def business_error(cls, code: str, msg: str, context=None):
        """Create business logic error"""
        return cls.error(
            code=code,
            msg=msg,
            category=ErrorCategory.BUSINESS,
            context=context or {}
        )
    
    @classmethod
    def permission_error(cls, msg: str, context=None):
        """Create permission denied error"""
        return cls.error(
            code='PERMISSION_DENIED',
            msg=msg,
            category=ErrorCategory.PERMISSION,
            context=context or {}
        )
    
    # 🆕 NEW: Helper methods
    def has_field_errors(self) -> bool:
        """Check if result has field-level errors"""
        return bool(self.field_errors)
    
    def get_field_error(self, field_name: str) -> List[str]:
        """Get errors for specific field"""
        return self.field_errors.get(field_name, [])
    
    def add_field_error(self, field_name: str, error_msg: str):
        """Add error for specific field (mutable operation)"""
        if not self.field_errors:
            self.field_errors = {}
        if field_name not in self.field_errors:
            self.field_errors[field_name] = []
        self.field_errors[field_name].append(error_msg)
    
    def is_validation_error(self) -> bool:
        """Check if this is a validation error"""
        return self.category == ErrorCategory.VALIDATION
    
    def is_business_error(self) -> bool:
        """Check if this is a business logic error"""
        return self.category == ErrorCategory.BUSINESS