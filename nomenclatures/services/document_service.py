# nomenclatures/services/document_service_refactored.py
"""
Document Service - REFACTORED FACADE VERSION

Вместо 916+ lines, сега е само facade който делегира на специализирани services:
- DocumentCreator: създаване
- StatusManager: status transitions
- DocumentValidator: валидации
- DocumentQuery: queries

ПУБЛИЧНИЯТ API ОСТАВА СЪЩИЯТ!
"""

from typing import Dict, List, Any, Optional
from django.contrib.auth import get_user_model
import logging

from core.utils.result import Result
from .document.creator import DocumentCreator
from .document.status_manager import StatusManager
from .document.validator import DocumentValidator
from .document.query import DocumentQuery

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentService:
    """
    Document Service - FACADE PATTERN

    Публичният interface остава същият, но вътрешно делегира на специализирани services.
    От 916 lines → ~100 lines!
    """

    # =====================
    # CREATION (делегира на DocumentCreator)
    # =====================

    @staticmethod
    def create_document(model_class, data: Dict[str, Any], user: User, location=None) -> Result:
        """Create document - делегира на DocumentCreator"""
        return DocumentCreator.create_document(model_class, data, user, location)

    # =====================
    # STATUS MANAGEMENT (делегира на StatusManager)
    # =====================

    @staticmethod
    def transition_document(document, to_status: str, user: User, comments: str = '', **kwargs) -> Result:
        """Transition document status - делегира на StatusManager"""
        return StatusManager.transition_document(document, to_status, user, comments, **kwargs)

    # =====================
    # VALIDATION (делегира на DocumentValidator)
    # =====================

    @staticmethod
    def can_edit_document(document, user: User) -> tuple[bool, str]:
        """Check if document can be edited - делегира на DocumentValidator"""
        return DocumentValidator.can_edit_document(document, user)

    # =====================
    # QUERIES (делегира на DocumentQuery)
    # =====================

    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """Get pending approval documents - делегира на DocumentQuery"""
        return DocumentQuery.get_pending_approval_documents(model_class, queryset)

    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """Get ready for processing documents - делегира на DocumentQuery"""
        return DocumentQuery.get_ready_for_processing_documents(model_class, queryset)

    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """Get active documents - делегира на DocumentQuery"""
        return DocumentQuery.get_active_documents(model_class, queryset)

    @staticmethod
    def get_available_actions(document, user: User) -> List[Dict]:
        """Get available actions - делегира на DocumentQuery"""
        return DocumentQuery.get_available_actions(document, user)

    # =====================
    # CONVENIENCE METHODS (wrappers)
    # =====================

    @staticmethod
    def submit_for_approval(document, user: User, comments: str = '') -> Result:
        """
        Submit document for approval - convenience wrapper

        Намира правилния status и прави transition
        """
        try:
            if not document.document_type.requires_approval:
                return Result.error(
                    'NO_APPROVAL_REQUIRED',
                    'This document type does not require approval'
                )

            # Find submission status
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_submission_status(document)

            if not target_status:
                return Result.error(
                    'NO_SUBMISSION_STATUS',
                    'No submission status found for current state'
                )

            return StatusManager.transition_document(
                document, target_status, user, comments
            )

        except ImportError:
            # Fallback to simple submission
            return StatusManager.transition_document(
                document, 'submitted', user, comments
            )

    @staticmethod
    def approve_document(document, user: User, notes: str = '') -> Result:
        """
        Approve document - convenience wrapper
        """
        try:
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_next_approval_status(document)

            if not target_status:
                # Default approval status
                target_status = 'approved'

            return StatusManager.transition_document(
                document, target_status, user, notes
            )

        except ImportError:
            return StatusManager.transition_document(
                document, 'approved', user, notes
            )

    @staticmethod
    def reject_document(document, user: User, reason: str) -> Result:
        """
        Reject document - convenience wrapper
        """
        try:
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_rejection_status(document)

            if not target_status:
                # Default rejection status
                target_status = 'rejected'

            return StatusManager.transition_document(
                document, target_status, user, reason
            )

        except ImportError:
            return StatusManager.transition_document(
                document, 'rejected', user, reason
            )

    # =====================
    # PRIVATE HELPERS (за backward compatibility)
    # =====================

    @staticmethod
    def _get_document_type_for_model(model_class):
        """За backward compatibility - делегира на DocumentCreator"""
        return DocumentCreator._get_document_type_for_model(model_class)

    @staticmethod
    def _get_initial_status(document_type) -> str:
        """За backward compatibility - делегира на DocumentCreator"""
        return DocumentCreator._get_initial_status(document_type)