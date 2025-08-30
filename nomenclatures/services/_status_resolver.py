
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
            
            status_code = initial_config.status.code if initial_config else 'draft'
            cache.set(cache_key, status_code, StatusResolver.CACHE_TIMEOUT)
            return status_code
            
        except Exception as e:
            logger.error(f"Error getting initial status: {e}")
            return 'draft'
    
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
            
            # Fallback
            if not status_codes:
                status_codes = {'completed', 'finalized', 'closed'}
                
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting final statuses: {e}")
            return {'completed', 'finalized', 'closed'}
    
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
            
            # Fallback - use initial status
            if not status_codes:
                initial = StatusResolver.get_initial_status(document_type)
                status_codes = {initial} if initial else {'draft'}
                
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting editable statuses: {e}")
            return {'draft'}
    
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
            
            # Fallback - use initial status
            if not status_codes:
                initial = StatusResolver.get_initial_status(document_type)
                status_codes = {initial} if initial else {'draft'}
                
            cache.set(cache_key, list(status_codes), StatusResolver.CACHE_TIMEOUT)
            return status_codes
            
        except Exception as e:
            logger.error(f"Error getting deletable statuses: {e}")
            return {'draft'}
    
    @staticmethod
    def get_movement_creating_statuses(document_type) -> Set[str]:
        """
        Get statuses that create inventory movements
        
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
            from ..models import DocumentTypeStatus
            
            # Get all statuses ordered by workflow
            all_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_active=True
            ).select_related('status').order_by('sort_order')

            status_list = [config.status.code for config in all_configs]
            
            # Find current position
            try:
                current_index = status_list.index(current_status)
            except ValueError:
                # Current status not in workflow - return empty
                cache.set(cache_key, [], StatusResolver.CACHE_TIMEOUT)
                return []
            
            # Get remaining statuses
            next_statuses = status_list[current_index + 1:]
            
            # Add cancellation status if exists and not already included
            cancel_status = StatusResolver.get_cancellation_status(document_type)
            if cancel_status and cancel_status not in next_statuses:
                next_statuses.append(cancel_status)
                
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
        Get statuses by semantic type using pattern matching
        
        Args:
            document_type: DocumentType instance
            semantic_type: Type to find ('approval', 'processing', 'completion', etc.)
            
        Returns:
            Set[str]: Matching status codes
        """
        try:
            from ..models import DocumentTypeStatus
            
            # Get all configured statuses
            all_configs = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_active=True
            ).select_related('status')
            
            matching_statuses = set()
            
            for config in all_configs:
                status_name = config.status.name.lower()
                status_code = config.status.code.lower()
                
                # Pattern matching based on semantic type
                if semantic_type == 'approval':
                    if any(word in status_name or word in status_code 
                          for word in ['submit', 'pending', 'review', 'approval']):
                        matching_statuses.add(config.status.code)
                        
                elif semantic_type == 'processing':
                    if any(word in status_name or word in status_code 
                          for word in ['approved', 'confirmed', 'ready', 'processing']):
                        matching_statuses.add(config.status.code)
                        
                elif semantic_type == 'completion':
                    if any(word in status_name or word in status_code 
                          for word in ['complete', 'finish', 'final', 'closed']):
                        matching_statuses.add(config.status.code)
                        
                elif semantic_type == 'rejection':
                    if any(word in status_name or word in status_code 
                          for word in ['reject', 'deny', 'decline', 'refused']):
                        matching_statuses.add(config.status.code)
            
            return matching_statuses
            
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
    """Check if document should create inventory movements in current status"""
    if not document.document_type or not document.document_type.affects_inventory:
        return False
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'movement_creating')

def should_reverse_movements(document) -> bool:
    """Check if document should reverse inventory movements in current status"""  
    if not document.document_type or not document.document_type.affects_inventory:
        return False
    return StatusResolver.is_status_in_role(document.document_type, document.status, 'movement_reversing')