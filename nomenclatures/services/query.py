# nomenclatures/services/document/query.py
"""
Document Query - queries и информационни методи

МЕТОДИ ПРЕМЕСТЕНИ ОТ DocumentService:
- get_pending_approval_documents()
- get_ready_for_processing_documents()
- get_active_documents()
- get_available_actions()
- _get_button_style()
"""

from typing import List, Dict
from django.contrib.auth import get_user_model
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentQuery:
    """Специализиран service за queries и информация"""

    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """
        Get documents pending approval - DYNAMIC

        КОПИРАНО 1:1 от DocumentService.get_pending_approval_documents()
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ...models.approvals import ApprovalRule
            from nomenclatures.services.creator import DocumentCreator

            pending_statuses = set()

            # Get document type for this model
            doc_type = DocumentCreator._get_document_type_for_model(queryset.model)
            if doc_type and doc_type.requires_approval:
                # Use ApprovalRule
                rules = ApprovalRule.objects.filter(
                    document_type=doc_type,
                    is_active=True
                )
                pending_statuses.update(rules.values_list('from_status_obj__code', flat=True))

            # FIXED: Use StatusResolver instead of hardcoded statuses
            if not pending_statuses:
                try:
                    from ._status_resolver import StatusResolver
                    # Get approval semantic statuses
                    approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
                    pending_statuses = approval_statuses if approval_statuses else {'submitted', 'pending_approval'}
                except Exception:
                    pending_statuses = {'submitted', 'pending_approval', 'pending_review'}

            return queryset.filter(status__in=pending_statuses)

        except ImportError:
            # Fallback without ApprovalRule - use basic semantic matching
            try:
                from ._status_resolver import StatusResolver
                doc_type = DocumentCreator._get_document_type_for_model(queryset.model)
                if doc_type:
                    approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
                    if approval_statuses:
                        return queryset.filter(status__in=approval_statuses)
            except:
                pass
            return queryset.filter(status__in=['submitted', 'pending_approval'])

    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """
        Get documents ready for next processing step

        КОПИРАНО 1:1 от DocumentService.get_ready_for_processing_documents()
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ...models.approvals import ApprovalRule
            from ...models.statuses import DocumentTypeStatus
            from nomenclatures.services.creator import DocumentCreator

            processing_statuses = set()

            # Get document type for this model
            doc_type = DocumentCreator._get_document_type_for_model(queryset.model)

            if doc_type and doc_type.requires_approval:
                # === APPROVAL WORKFLOW LOGIC ===
                # Find statuses that are result of successful approval
                rules = ApprovalRule.objects.filter(
                    document_type=doc_type,
                    is_active=True
                )
                # Get to_status from approval rules (these are approved statuses)
                processing_statuses.update(rules.values_list('to_status_obj__code', flat=True))

            else:
                # === SIMPLE WORKFLOW LOGIC ===
                # Use DocumentTypeStatus for "processing ready" statuses
                type_statuses = DocumentTypeStatus.objects.filter(
                    document_type=doc_type,
                    is_active=True,
                    is_final=False  # Not final
                )
                processing_statuses.update(type_statuses.values_list('status__code', flat=True))

            # FIXED: Use StatusResolver for semantic type matching instead of hardcoded
            if not processing_statuses:
                try:
                    from ._status_resolver import StatusResolver
                    # Get processing semantic statuses
                    processing_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'processing')
                    
                    # If no processing statuses, try completion statuses minus final ones
                    if not processing_statuses:
                        completion_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'completion')
                        final_statuses = StatusResolver.get_final_statuses(doc_type)
                        processing_statuses = completion_statuses - final_statuses
                        
                except Exception:
                    # Emergency fallback with model type detection
                    model_name = queryset.model.__name__.lower()
                    if 'request' in model_name:
                        processing_statuses = {'approved'}
                    elif 'order' in model_name:
                        processing_statuses = {'confirmed', 'sent'}
                    elif 'delivery' in model_name or 'receipt' in model_name:
                        processing_statuses = {'received', 'partial'}
                    elif 'invoice' in model_name:
                        processing_statuses = {'approved', 'sent'}
                    else:
                        processing_statuses = {'approved', 'confirmed', 'ready'}

            return queryset.filter(status__in=processing_statuses)

        except ImportError:
            # FIXED: Try StatusResolver even without nomenclatures
            try:
                from ._status_resolver import StatusResolver
                doc_type = DocumentCreator._get_document_type_for_model(queryset.model)
                if doc_type:
                    processing_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'processing')
                    if processing_statuses:
                        return queryset.filter(status__in=processing_statuses)
            except:
                pass
                
            # === COMPLETE FALLBACK WITH MODEL TYPE DETECTION ===
            model_name = queryset.model.__name__.lower()
            if 'request' in model_name:
                return queryset.filter(status='approved')
            elif 'order' in model_name:
                return queryset.filter(status='confirmed')
            elif 'delivery' in model_name:
                return queryset.filter(status='received')
            else:
                return queryset.filter(status__in=['approved', 'confirmed', 'ready'])

    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """
        Get active documents - DYNAMIC

        КОПИРАНО 1:1 от DocumentService.get_active_documents()
        """
        if queryset is None:
            if model_class is None:
                raise ValueError("Either model_class or queryset must be provided")
            queryset = model_class.objects.all()

        try:
            from ...models.statuses import DocumentTypeStatus
            from nomenclatures.services.creator import DocumentCreator

            doc_type = DocumentCreator._get_document_type_for_model(queryset.model)
            if doc_type:
                # Use DocumentTypeStatus for final statuses
                final_statuses = DocumentTypeStatus.objects.filter(
                    document_type=doc_type,
                    is_final=True,
                    is_active=True
                ).values_list('status__code', flat=True)

                if final_statuses:
                    # Exclude final statuses
                    return queryset.exclude(status__in=final_statuses)

            # FIXED: Use StatusResolver for dynamic fallback
            try:
                from ._status_resolver import StatusResolver
                final_statuses = StatusResolver.get_final_statuses(doc_type)
                cancellation_status = StatusResolver.get_cancellation_status(doc_type)
                
                exclude_statuses = list(final_statuses)
                if cancellation_status:
                    exclude_statuses.append(cancellation_status)
                    
                return queryset.exclude(status__in=exclude_statuses)
            except Exception:
                return queryset.exclude(status__in=['cancelled', 'completed', 'rejected'])

        except ImportError:
            # FIXED: Try StatusResolver even without full nomenclatures
            try:
                from ._status_resolver import StatusResolver
                doc_type = DocumentCreator._get_document_type_for_model(queryset.model)
                if doc_type:
                    final_statuses = StatusResolver.get_final_statuses(doc_type)
                    cancellation_status = StatusResolver.get_cancellation_status(doc_type)
                    
                    exclude_statuses = list(final_statuses)
                    if cancellation_status:
                        exclude_statuses.append(cancellation_status)
                        
                    return queryset.exclude(status__in=exclude_statuses)
            except:
                pass
            # Simple fallback
            return queryset.exclude(status__in=['cancelled', 'completed', 'rejected'])

    @staticmethod
    def get_available_actions(document, user: User) -> List[Dict]:
        """
        Get available actions for document and user

        КОПИРАНО 1:1 от DocumentService.get_available_actions()
        """
        try:
            actions = []

            if not document.document_type:
                return actions

            if document.document_type.requires_approval:
                # === APPROVAL WORKFLOW ACTIONS ===
                try:

                    from .. import ApprovalService
                    transitions_result = ApprovalService.get_available_transitions(document, user)
                    transitions = []

                    if transitions_result.ok:
                        transitions = transitions_result.data.get('transitions', [])

                    for trans in transitions:


                        actions.append({
                            'action': 'transition',
                            'status': trans['to_status'],
                            'label': trans.get('label', trans.get('to_status_name', trans.get('to_status', 'Unknown'))),
                            'can_perform': True,
                            'requires_approval': True,
                            'button_style': DocumentQuery._get_button_style(trans['to_status']),
                            'icon': trans.get('icon', 'fas fa-arrow-right'),
                            'rule_id': trans.get('rule_id')
                        })
                except ImportError:
                    logger.warning("ApprovalService not available")

            else:
                # === SIMPLE WORKFLOW ACTIONS ===
                from nomenclatures.services.status_manager import StatusManager
                available_statuses = StatusManager._get_simple_next_statuses(document)

                for status in available_statuses:
                    actions.append({
                        'action': 'transition',
                        'status': status,
                        'label': status.replace('_', ' ').title(),
                        'can_perform': True,
                        'requires_approval': False,
                        'button_style': DocumentQuery._get_button_style(status),
                        'icon': 'fas fa-arrow-right'
                    })

            # Add edit action if allowed
            from nomenclatures.services.validator import DocumentValidator
            can_edit, reason = DocumentValidator.can_edit_document(document, user)
            if can_edit:
                actions.append({
                    'action': 'edit',
                    'label': 'Edit',
                    'can_perform': True,
                    'button_style': 'btn-secondary',
                    'icon': 'fas fa-edit'
                })

            return actions

        except Exception as e:
            logger.error(f"Error getting available actions: {e}")
            return []

    @staticmethod
    def _get_button_style(status: str) -> str:
        """
        Get button style for status

        КОПИРАНО 1:1 от DocumentService._get_button_style()
        """
        status_lower = status.lower()

        # Approval actions
        if any(word in status_lower for word in ['approve', 'accept', 'confirm']):
            return 'btn-success'

        # Rejection actions
        if any(word in status_lower for word in ['reject', 'deny', 'decline']):
            return 'btn-danger'

        # Cancel actions
        if 'cancel' in status_lower:
            return 'btn-warning'

        # Submit actions
        if any(word in status_lower for word in ['submit', 'send']):
            return 'btn-primary'

        # Complete actions
        if any(word in status_lower for word in ['complete', 'finish', 'finalize']):
            return 'btn-info'

        # Default
        return 'btn-secondary'