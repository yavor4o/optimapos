
"""
Dynamic Status Resolution System

🎯 ПРОБЛЕМ КОЙТО РЕШАВАМЕ:
- Hardcoded status names в services ('draft', 'submitted', etc.)
- Невъзможност за custom status names
- Счупена логика при промяна на статуси

💡 РЕШЕНИЕ:
- Semantic role-based status resolution
- Configuration-driven status mapping
- Flexible custom status support
"""

from typing import Optional, List, Set, Dict
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class StatusResolver:
    """
    Dynamic Status Resolution System
    
    Maps semantic roles to actual status codes based on configuration
    """
    
    # Cache timeout - 1 hour
    CACHE_TIMEOUT = 3600
    
    @staticmethod
    def get_initial_status(document_type) -> Optional[str]:
        """
        Get initial status code for document type
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            str: Initial status code or None
        """
        cache_key = f"initial_status_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
            
        try:
            from ..models import DocumentTypeStatus
            
            initial_config = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_initial=True,
                is_active=True
            ).first()
            
            status_code = initial_config.status.code if initial_config else None
            cache.set(cache_key, status_code, StatusResolver.CACHE_TIMEOUT)
            return status_code
            
        except Exception as e:
            logger.error(f"Error getting initial status: {e}")
            return None
    
    @staticmethod
    def get_final_statuses(document_type) -> Set[str]:
        """
        Get all final status codes for document type
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            Set[str]: Final status codes
        """
        cache_key = f"final_statuses_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            from ..models import DocumentTypeStatus
            
            final_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_final=True,
                is_active=True
            ).select_related('status')
            
            status_codes = {config.status.code for config in final_configs}
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting final statuses: {e}")
            return set()
    
    @staticmethod
    def get_cancellation_status(document_type) -> Optional[str]:
        """
        Get cancellation status code for document type
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            str: Cancellation status code or None
        """
        cache_key = f"cancellation_status_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
            
        try:
            from ..models import DocumentTypeStatus
            
            cancel_config = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_cancellation=True,
                is_active=True
            ).first()
            
            status_code = cancel_config.status.code if cancel_config else None
            cache.set(cache_key, status_code, StatusResolver.CACHE_TIMEOUT)
            return status_code
            
        except Exception as e:
            logger.error(f"Error getting cancellation status: {e}")
            return None
    
    @staticmethod
    def get_approval_status(document_type) -> Optional[str]:
        """
        Get approval status code for document type
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            str: Approval status code or None
        """
        cache_key = f"approval_status_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
            
        try:
            from ..models import DocumentTypeStatus
            
            # Look for status with approval-like name in active statuses
            all_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_active=True
            ).select_related('status')
            
            for config in all_configs:
                status_lower = config.status.code.lower()
                if any(word in status_lower for word in ['approved', 'одобрен', 'pending', 'review', 'submit']):
                    status_code = config.status.code
                    cache.set(cache_key, status_code, StatusResolver.CACHE_TIMEOUT)
                    return status_code
            
            # No approval status found
            cache.set(cache_key, None, StatusResolver.CACHE_TIMEOUT)
            return None
            
        except Exception as e:
            logger.error(f"Error getting approval status: {e}")
            return None
    
    @staticmethod
    def get_rejection_status(document_type) -> Optional[str]:
        """
        Get rejection status code for document type
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            str: Rejection status code or None
        """
        cache_key = f"rejection_status_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
            
        try:
            from ..models import DocumentTypeStatus
            
            # Look for status with rejection-like name
            all_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_active=True
            ).select_related('status')
            
            for config in all_configs:
                status_lower = config.status.code.lower()
                if any(word in status_lower for word in ['rejected', 'отказан', 'отхвърлен', 'refuse', 'deny']):
                    status_code = config.status.code
                    cache.set(cache_key, status_code, StatusResolver.CACHE_TIMEOUT)
                    return status_code
            
            # No rejection status found
            cache.set(cache_key, None, StatusResolver.CACHE_TIMEOUT)
            return None
            
        except Exception as e:
            logger.error(f"Error getting rejection status: {e}")
            return None
    
    @staticmethod
    def get_editable_statuses(document_type) -> Set[str]:
        """
        Get all statuses that allow editing
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            Set[str]: Editable status codes
        """
        cache_key = f"editable_statuses_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            from ..models import DocumentTypeStatus
            
            editable_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                allows_editing=True,
                is_active=True
            ).select_related('status')
            
            status_codes = {config.status.code for config in editable_configs}
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting editable statuses: {e}")
            return set()
    
    @staticmethod
    def get_deletable_statuses(document_type) -> Set[str]:
        """
        Get all statuses that allow deletion
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            Set[str]: Deletable status codes
        """
        cache_key = f"deletable_statuses_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            from ..models import DocumentTypeStatus
            
            deletable_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                allows_deletion=True,
                is_active=True
            ).select_related('status')
            
            status_codes = {config.status.code for config in deletable_configs}
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting deletable statuses: {e}")
            return set()
    
    @staticmethod
    def get_movement_creating_statuses(document_type) -> Set[str]:
        """
        Get statuses that create.html inventory movements
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            Set[str]: Movement-creating status codes
        """
        cache_key = f"movement_creating_statuses_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            from ..models import DocumentTypeStatus
            
            creating_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                creates_inventory_movements=True,
                is_active=True
            ).select_related('status')
            
            status_codes = {config.status.code for config in creating_configs}
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting movement creating statuses: {e}")
            return set()
    
    @staticmethod
    def get_movement_reversing_statuses(document_type) -> Set[str]:
        """
        Get statuses that reverse inventory movements
        
        Args:
            document_type: DocumentType instance
            
        Returns:
            Set[str]: Movement-reversing status codes
        """
        cache_key = f"movement_reversing_statuses_{document_type.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            from ..models import DocumentTypeStatus
            
            reversing_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                reverses_inventory_movements=True,
                is_active=True
            ).select_related('status')
            
            status_codes = {config.status.code for config in reversing_configs}
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting movement reversing statuses: {e}")
            return set()
    
    @staticmethod
    def get_next_possible_statuses(document_type, current_status: str) -> List[str]:
        """
        Get possible next statuses from current status
        
        ✅ UNIFIED: Delegates to StatusManager for consistent logic
        
        Args:
            document_type: DocumentType instance
            current_status: Current status code
            
        Returns:
            List[str]: Possible next status codes
        """
        cache_key = f"next_statuses_{document_type.id}_{current_status}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
            
        try:
            # ✅ NEW: Delegate to StatusManager which has the proper workflow logic
            from .status_manager import StatusManager
            next_statuses = StatusManager.get_next_statuses(document_type, current_status)
            
            cache.set(cache_key, next_statuses, StatusResolver.CACHE_TIMEOUT)
            return next_statuses
            
        except Exception as e:
            logger.error(f"Error getting next statuses: {e}")
            # Fallback to empty list
            return []
    
    @staticmethod
    def is_status_in_role(document_type, status_code: str, role: str) -> bool:
        """
        Check if status has specific semantic role
        
        Args:
            document_type: DocumentType instance
            status_code: Status code to check
            role: Role to check ('initial', 'final', 'cancellation', 'editable', 'deletable')
            
        Returns:
            bool: True if status has the role
        """
        role_methods = {
            'initial': lambda dt: StatusResolver.get_initial_status(dt) == status_code,
            'final': lambda dt: status_code in StatusResolver.get_final_statuses(dt),
            'cancellation': lambda dt: StatusResolver.get_cancellation_status(dt) == status_code,
            'editable': lambda dt: status_code in StatusResolver.get_editable_statuses(dt),
            'deletable': lambda dt: status_code in StatusResolver.get_deletable_statuses(dt),
            'movement_creating': lambda dt: status_code in StatusResolver.get_movement_creating_statuses(dt),
            'movement_reversing': lambda dt: status_code in StatusResolver.get_movement_reversing_statuses(dt),
        }
        
        method = role_methods.get(role)
        if not method:
            logger.warning(f"Unknown status role: {role}")
            return False
            
        try:
            return method(document_type)
        except Exception as e:
            logger.error(f"Error checking status role {role}: {e}")
            return False
    
    @staticmethod
    def get_statuses_by_semantic_type(document_type, semantic_type: str) -> Set[str]:
        """
        Get statuses by semantic type - aggregate method for query.py compatibility
        
        Args:
            document_type: DocumentType instance
            semantic_type: 'approval', 'processing', 'completion', 'initial', 'final', etc.
            
        Returns:
            Set[str]: Status codes matching semantic type
        """
        cache_key = f"semantic_statuses_{document_type.id}_{semantic_type}"
        cached = cache.get(cache_key)
        
        if cached:
            return set(cached)
            
        try:
            statuses = set()
            
            if semantic_type == 'approval':
                # Approval workflow statuses - pending approval states
                approval_status = StatusResolver.get_approval_status(document_type)
                if approval_status:
                    statuses.add(approval_status)
                
                # Also include statuses with approval-like names
                from ..models import DocumentTypeStatus
                approval_configs = DocumentTypeStatus.objects.filter(
                    document_type=document_type,
                    is_active=True
                ).select_related('status')
                
                for config in approval_configs:
                    status_lower = config.status.code.lower()
                    if any(word in status_lower for word in ['submit', 'pending', 'review', 'approval']):
                        statuses.add(config.status.code)
                        
            elif semantic_type == 'processing':
                # Processing statuses - approved but not final
                from ..models import DocumentTypeStatus
                processing_configs = DocumentTypeStatus.objects.filter(
                    document_type=document_type,
                    is_active=True,
                    is_final=False  # Not final = still processing
                ).select_related('status')
                
                # Exclude initial statuses
                initial_status = StatusResolver.get_initial_status(document_type)
                
                for config in processing_configs:
                    status_code = config.status.code
                    if status_code != initial_status:  # Skip initial
                        status_lower = status_code.lower()
                        if any(word in status_lower for word in [
                            'approved', 'confirmed', 'sent', 'ready', 'processing', 
                            'одобрен', 'потвърден', 'изпратен'
                        ]):
                            statuses.add(status_code)
                            
            elif semantic_type == 'completion':
                # Completion statuses - final positive outcomes
                final_statuses = StatusResolver.get_final_statuses(document_type)
                cancellation_status = StatusResolver.get_cancellation_status(document_type)
                rejection_status = StatusResolver.get_rejection_status(document_type)
                
                for status in final_statuses:
                    # Exclude negative outcomes
                    if status not in [cancellation_status, rejection_status]:
                        statuses.add(status)
                        
            elif semantic_type == 'initial':
                # Initial statuses
                initial_status = StatusResolver.get_initial_status(document_type)
                if initial_status:
                    statuses.add(initial_status)
                    
            elif semantic_type == 'final':
                # All final statuses
                statuses.update(StatusResolver.get_final_statuses(document_type))
                
            elif semantic_type == 'cancellation':
                # Cancellation statuses
                cancellation_status = StatusResolver.get_cancellation_status(document_type)
                if cancellation_status:
                    statuses.add(cancellation_status)
                    
            elif semantic_type == 'rejection':
                # Rejection statuses  
                rejection_status = StatusResolver.get_rejection_status(document_type)
                if rejection_status:
                    statuses.add(rejection_status)
                    
            else:
                logger.warning(f"Unknown semantic type: {semantic_type}")
                
            # Cache result
            cache.set(cache_key, list(statuses), StatusResolver.CACHE_TIMEOUT)
            return statuses
            
        except Exception as e:
            logger.error(f"Error getting statuses by semantic type {semantic_type}: {e}")
            return set()
    
    @staticmethod
    def clear_cache(document_type=None):
        """
        Clear status resolution cache
        
        Args:
            document_type: Specific document type to clear (None = clear all)
        """
        if document_type:
            # Clear specific document type cache
            keys_to_clear = [
                f"initial_status_{document_type.id}",
                f"final_statuses_{document_type.id}",
                f"cancellation_status_{document_type.id}",
                f"editable_statuses_{document_type.id}",
                f"deletable_statuses_{document_type.id}",
                f"movement_creating_statuses_{document_type.id}",
                f"movement_reversing_statuses_{document_type.id}",
            ]
            
            for key in keys_to_clear:
                cache.delete(key)
                
            # Also clear next_statuses cache (all current_status combinations)
            try:
                from ..models import DocumentTypeStatus
                all_statuses = DocumentTypeStatus.objects.filter(
                    document_type=document_type,
                    is_active=True
                ).values_list('status__code', flat=True)
                
                for status in all_statuses:
                    cache.delete(f"next_statuses_{document_type.id}_{status}")
                    
            except Exception:
                pass
        else:
            # Clear all status resolution cache
            # This is less efficient but ensures all is cleared
            cache.clear()
            
        logger.info(f"Status resolution cache cleared for document type: {document_type}")


# =====================================================================
# CONVENIENCE FUNCTIONS FOR SERVICES
# =====================================================================

def is_initial_status(document) -> bool:
    """Check if document is in initial status"""
    if not document.document_type:
        return document.status in ['draft', '']
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'initial')

def is_final_status(document) -> bool:
    """Check if document is in final status"""
    if not document.document_type:
        return document.status in ['completed', 'finalized', 'closed']
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'final')

def is_cancellation_status(document) -> bool:
    """Check if document is in cancellation status"""
    if not document.document_type:
        return document.status in ['cancelled', 'canceled']
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'cancellation')

def can_edit_in_status(document) -> bool:
    """Check if document can be edited in current status"""
    if not document.document_type:
        return document.status in ['draft', 'pending', '']
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'editable')

def can_delete_in_status(document) -> bool:
    """Check if document can be deleted in current status"""
    if not document.document_type:
        return document.status in ['draft', '']
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'deletable')

def should_create_movements(document) -> bool:
    """Check if document should create.html inventory movements in current status"""
    if not document.document_type or not document.document_type.affects_inventory:
        return False
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'movement_creating')

def should_reverse_movements(document) -> bool:
    """Check if document should reverse inventory movements in current status"""  
    if not document.document_type or not document.document_type.affects_inventory:
        return False
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'movement_reversing')