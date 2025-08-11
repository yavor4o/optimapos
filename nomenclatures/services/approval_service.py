# nomenclatures/services/approval_service.py - SIMPLIFIED & CLEAN


from typing import Dict, List, Optional
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

from ..models.approvals import ApprovalRule, ApprovalLog

User = get_user_model()
logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Approval Service - SIMPLIFIED VERSION

    Manages document approval workflow using ApprovalRule configuration.
    Simplified version without complex enterprise features.
    """

    # =====================
    # CORE PUBLIC METHODS
    # =====================

    @staticmethod
    def get_available_transitions(document, user) -> List[Dict]:
        """
        Get available status transitions for user and document

        Args:
            document: Document instance (PurchaseRequest, etc.)
            user: User instance

        Returns:
            List[Dict]: Available transitions with metadata
        """
        try:
            if not document or not hasattr(document, 'status'):
                return []

            # Get applicable approval rules
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status=document.status,
                is_active=True
            )

            # Filter by amount if document has amount
            amount = ApprovalService._get_document_amount(document)
            if amount is not None:
                rules = rules.filter(
                    min_amount__lte=amount
                ).filter(
                    models.Q(max_amount__gte=amount) | models.Q(max_amount__isnull=True)
                )

            # Check user permissions for each rule
            available_transitions = []
            for rule in rules:
                if rule.can_user_approve(user, document):
                    available_transitions.append({
                        'to_status': rule.to_status,
                        'label': f"{rule.from_status.title()} → {rule.to_status.title()}",
                        'rule_name': rule.name,
                        'approval_level': rule.approval_level,
                        'requires_reason': rule.requires_reason,
                        'rejection_allowed': rule.rejection_allowed,
                        'rule_id': rule.id
                    })

            # Remove duplicates (same to_status)
            seen_statuses = set()
            unique_transitions = []
            for transition in available_transitions:
                if transition['to_status'] not in seen_statuses:
                    seen_statuses.add(transition['to_status'])
                    unique_transitions.append(transition)

            return unique_transitions

        except Exception as e:
            logger.error(f"Error getting available transitions: {e}")
            return []

    @staticmethod
    @transaction.atomic
    def execute_transition(document, to_status: str, user, comments: str = '', **kwargs) -> Dict:
        """
        Execute status transition with approval validation

        Args:
            document: Document instance
            to_status: Target status
            user: User performing transition
            comments: Optional comments/reason

        Returns:
            Dict: {'success': bool, 'message': str, ...}
        """
        try:
            from_status = document.status

            # Find applicable rule
            rule = ApprovalService._find_applicable_rule(document, to_status, user)
            if not rule:
                return {
                    'success': False,
                    'message': f'No approval rule found for transition {from_status} → {to_status}',
                    'error_code': 'NO_RULE_FOUND'
                }

            # Validate user can execute this rule
            if not rule.can_user_approve(user, document):
                return {
                    'success': False,
                    'message': 'You do not have permission to perform this transition',
                    'error_code': 'PERMISSION_DENIED'
                }

            # Check if reason is required
            if rule.requires_reason and not comments:
                return {
                    'success': False,
                    'message': 'This transition requires a reason/comment',
                    'error_code': 'REASON_REQUIRED'
                }

            # Check previous approval levels (if required)
            if rule.requires_previous_level:
                prev_check = ApprovalService._check_previous_levels(document, rule)
                if not prev_check['valid']:
                    return {
                        'success': False,
                        'message': prev_check['message'],
                        'error_code': 'PREVIOUS_LEVEL_REQUIRED'
                    }

            # Execute the transition
            old_status = document.status
            document.status = to_status

            # Update approval fields if available
            if hasattr(document, 'approved_by') and 'approved' in to_status:
                document.approved_by = user
            if hasattr(document, 'approved_at') and 'approved' in to_status:
                document.approved_at = timezone.now()
            if hasattr(document, 'updated_by'):
                document.updated_by = user

            # Save document
            document.save()

            # Log the transition
            ApprovalService._log_transition(
                document=document,
                rule=rule,
                from_status=old_status,
                to_status=to_status,
                user=user,
                comments=comments
            )

            return {
                'success': True,
                'message': f'Document transitioned from {old_status} to {to_status}',
                'from_status': old_status,
                'to_status': to_status,
                'rule_applied': rule.name
            }

        except Exception as e:
            logger.error(f"Error executing transition: {e}")
            return {
                'success': False,
                'message': f'Error executing transition: {str(e)}',
                'error_code': 'EXECUTION_ERROR'
            }

    @staticmethod
    def get_approval_workflow_status(document) -> Dict:
        """
        Get complete approval workflow status for document

        Args:
            document: Document instance

        Returns:
            Dict: Workflow status information
        """
        try:
            # Get all rules for this document type
            all_rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                is_active=True
            ).order_by('approval_level', 'sort_order')

            # Get approval history
            approval_history = ApprovalService.get_approval_history(document)

            # Build workflow status
            workflow_levels = []
            for rule in all_rules:
                # Check if this level is completed
                completed = any(
                    log['to_status'] == rule.to_status and log['action'] in ['approved']
                    for log in approval_history
                )

                workflow_levels.append({
                    'level': rule.approval_level,
                    'rule_name': rule.name,
                    'from_status': rule.from_status,
                    'to_status': rule.to_status,
                    'approver': rule.get_approver_display(),
                    'completed': completed,
                    'amount_range': f"{rule.min_amount}-{rule.max_amount or '∞'} {rule.currency}"
                })

            return {
                'current_status': document.status,
                'workflow_levels': workflow_levels,
                'approval_history': approval_history,
                'document_number': getattr(document, 'document_number', 'Unknown')
            }

        except Exception as e:
            logger.error(f"Error getting workflow status: {e}")
            return {
                'current_status': getattr(document, 'status', 'unknown'),
                'error': str(e)
            }

    @staticmethod
    def get_approval_history(document) -> List[Dict]:
        """
        Get approval history for document

        Args:
            document: Document instance

        Returns:
            List[Dict]: Approval history entries
        """
        try:
            content_type = ContentType.objects.get_for_model(document.__class__)

            logs = ApprovalLog.objects.filter(
                content_type=content_type,
                object_id=document.pk
            ).select_related('rule', 'actor').order_by('-timestamp')

            history = []
            for log in logs:
                history.append({
                    'timestamp': log.timestamp,
                    'action': log.get_action_display(),
                    'from_status': log.from_status,
                    'to_status': log.to_status,
                    'actor': log.actor.get_full_name() or log.actor.username,
                    'rule_name': log.rule.name,
                    'comments': log.comments
                })

            return history

        except Exception as e:
            logger.error(f"Error getting approval history: {e}")
            return []

    # =====================
    # PRIVATE HELPER METHODS
    # =====================

    @staticmethod
    def _find_applicable_rule(document, to_status: str, user) -> Optional[ApprovalRule]:
        """Find applicable approval rule for transition"""
        try:
            # Get rules for this transition
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status=document.status,
                to_status=to_status,
                is_active=True
            )

            # Filter by amount
            amount = ApprovalService._get_document_amount(document)
            if amount is not None:
                rules = rules.filter(
                    min_amount__lte=amount
                ).filter(
                    models.Q(max_amount__gte=amount) | models.Q(max_amount__isnull=True)
                )

            # Return first rule that user can execute
            for rule in rules.order_by('approval_level', 'sort_order'):
                if rule.can_user_approve(user, document):
                    return rule

            return None

        except Exception as e:
            logger.error(f"Error finding applicable rule: {e}")
            return None

    @staticmethod
    def _get_document_amount(document) -> Optional[float]:
        """Get document amount for approval rule filtering"""
        try:
            # Try common amount field names
            amount_fields = ['total', 'grand_total', 'amount', 'total_amount']
            for field in amount_fields:
                if hasattr(document, field):
                    amount = getattr(document, field)
                    if amount is not None:
                        return float(amount)

            # Try calculated total methods
            if hasattr(document, 'get_total'):
                return float(document.get_total())
            if hasattr(document, 'calculate_total'):
                return float(document.calculate_total())

            return None

        except Exception:
            return None

    @staticmethod
    def _check_previous_levels(document, rule: ApprovalRule) -> Dict:
        """Check if previous approval levels are completed"""
        try:
            if not rule.requires_previous_level or rule.approval_level <= 1:
                return {'valid': True, 'message': 'No previous levels required'}

            # Get approval history
            content_type = ContentType.objects.get_for_model(document.__class__)

            # Check if all lower levels are approved
            required_levels = list(range(1, rule.approval_level))

            approved_levels = set()
            for log in ApprovalLog.objects.filter(
                    content_type=content_type,
                    object_id=document.pk,
                    action='approved'
            ):
                approved_levels.add(log.rule.approval_level)

            missing_levels = set(required_levels) - approved_levels
            if missing_levels:
                return {
                    'valid': False,
                    'message': f'Previous approval levels must be completed first: {sorted(missing_levels)}'
                }

            return {'valid': True, 'message': 'Previous levels completed'}

        except Exception as e:
            logger.error(f"Error checking previous levels: {e}")
            return {'valid': False, 'message': f'Error checking previous levels: {e}'}

    @staticmethod
    def _log_transition(document, rule: ApprovalRule, from_status: str, to_status: str,
                        user, comments: str = ''):
        """Log approval transition"""
        try:
            content_type = ContentType.objects.get_for_model(document.__class__)

            # Determine action based on to_status
            if 'approved' in to_status.lower():
                action = 'approved'
            elif 'rejected' in to_status.lower():
                action = 'rejected'
            else:
                action = 'submitted'

            ApprovalLog.objects.create(
                content_type=content_type,
                object_id=document.pk,
                rule=rule,
                action=action,
                from_status=from_status,
                to_status=to_status,
                actor=user,
                comments=comments
            )

        except Exception as e:
            logger.error(f"Error logging transition: {e}")


# =====================
# CONVENIENCE FUNCTIONS
# =====================

def approve_document(document, user, comments: str = '') -> Dict:
    """
    Convenience function to approve document

    Usage:
        result = approve_document(request, current_user, "Looks good")
    """
    return ApprovalService.execute_transition(
        document=document,
        to_status='approved',
        user=user,
        comments=comments
    )


def reject_document(document, user, reason: str) -> Dict:
    """
    Convenience function to reject document

    Usage:
        result = reject_document(request, current_user, "Insufficient budget")
    """
    return ApprovalService.execute_transition(
        document=document,
        to_status='rejected',
        user=user,
        comments=reason
    )


def submit_for_approval(document, user, comments: str = '') -> Dict:
    """
    Convenience function to submit document for approval

    Usage:
        result = submit_for_approval(request, current_user)
    """
    return ApprovalService.execute_transition(
        document=document,
        to_status='submitted',
        user=user,
        comments=comments
    )


def can_user_approve(document, user, to_status: str = 'approved') -> bool:
    """
    Quick check if user can approve document

    Usage:
        if can_user_approve(request, current_user):
            # Show approve button
    """
    rule = ApprovalService._find_applicable_rule(document, to_status, user)
    return rule is not None and rule.can_user_approve(user, document)