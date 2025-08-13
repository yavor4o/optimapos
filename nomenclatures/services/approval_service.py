# nomenclatures/services/approval_service.py - FIXED IMPORTS VERSION
"""
Approval Service - FIXED IMPORTS & MODERNIZED

ФИКСИРАНО:
- Унифицирани imports за модели
- Използване на САМО ForeignKey полета от ApprovalRule
- Консистентни imports с останалите services
- Error handling за missing models

ИНТЕГРИРА:
- DocumentType + DocumentTypeStatus (валидни статуси)
- ApprovalRule (кой може какво)
- DocumentStatus (визуални настройки)

ОТГОВОРНОСТИ:
- САМО authorization и policy validation
- БЕЗ state changes (те са в DocumentService)
- Навигация по workflow правила
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

# FIXED: Unified imports from models
from ..models import (
    DocumentType,
    DocumentStatus,
    DocumentTypeStatus
)

# FIXED: Conditional import for ApprovalRule
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_APPROVAL_MODELS = True
except ImportError:
    ApprovalRule = None
    ApprovalLog = None
    HAS_APPROVAL_MODELS = False

User = get_user_model()
logger = logging.getLogger(__name__)


# =====================
# RESULT TYPES - UNCHANGED
# =====================

@dataclass
class Decision:
    """Резултат от authorization проверка"""
    allowed: bool
    reason: str
    rule_id: Optional[int] = None
    level: Optional[int] = None
    next_status: Optional[str] = None
    data: Dict = field(default_factory=dict)

    @classmethod
    def allow(cls, rule, reason: str = "Authorization granted") -> 'Decision':
        """FIXED: Improved allow method"""
        if not rule:
            return cls.deny("No rule provided")

        return cls(
            allowed=True,
            reason=reason,
            rule_id=rule.id,
            level=rule.approval_level,
            next_status=rule.to_status_obj.code if rule.to_status_obj else None
        )

    @classmethod
    def deny(cls, reason: str, **kwargs) -> 'Decision':
        return cls(allowed=False, reason=reason, **kwargs)


@dataclass
class WorkflowInfo:
    """Информация за workflow статус"""
    current_status: str
    available_transitions: List[Dict]
    configured_statuses: List[Dict]
    approval_history: List[Dict]
    workflow_progress: Dict


class ApprovalService:
    """
    Approval Service - FIXED VERSION

    БЕЗ state changes! Всички document updates са в DocumentService.
    """

    # =====================
    # AVAILABILITY CHECK - FIXED
    # =====================

    @staticmethod
    def is_available() -> bool:
        """Check if approval models are available"""
        return HAS_APPROVAL_MODELS

    @staticmethod
    def _require_approval_models():
        """Raise error if approval models not available"""
        if not HAS_APPROVAL_MODELS:
            raise ImportError(
                "Approval models not available. "
                "Ensure ApprovalRule and ApprovalLog models are properly migrated."
            )

    # =====================
    # AUTHORIZATION API - FIXED
    # =====================

    @staticmethod
    def authorize_transition(document, user, to_status: str) -> Decision:
        """
        FIXED: ГЛАВНА authorization функция с improved error handling

        Проверява:
        1. Дали to_status е валиден за document_type (DocumentTypeStatus)
        2. Дали transition е позволен (ApprovalRule)
        3. Дали user има права (permissions/roles)
        4. Дали са изпълнени prerequisites (previous levels)

        Args:
            document: Document instance
            user: User performing transition
            to_status: Target status code

        Returns:
            Decision: allowed/denied с причина и metadata
        """
        try:
            # FIXED: Check availability first
            ApprovalService._require_approval_models()

            # 1. BASIC VALIDATION
            if not document or not hasattr(document, 'status'):
                return Decision.deny("Invalid document")

            if not document.document_type:
                return Decision.deny("Document has no type configured")

            # 2. VALIDATE TARGET STATUS EXISTS
            status_valid, status_msg = ApprovalService._validate_target_status(
                document.document_type, to_status
            )
            if not status_valid:
                return Decision.deny(status_msg)

            # 3. VALIDATE TRANSITION RULES
            transition_valid, transition_msg = ApprovalService._validate_transition_rules(
                document, to_status
            )
            if not transition_valid:
                return Decision.deny(transition_msg)

            # 4. FIND APPLICABLE APPROVAL RULE
            rule = ApprovalService._find_applicable_rule(document, to_status, user)
            if not rule:
                return Decision.deny(
                    f"No approval rule found for {document.status} → {to_status}",
                    data={'from_status': document.status, 'to_status': to_status}
                )

            # 5. CHECK USER PERMISSIONS
            if not rule.can_user_approve(user, document):
                return Decision.deny(
                    "You do not have permission for this transition",
                    rule_id=rule.id,
                    level=rule.approval_level
                )

            # 6. CHECK PREVIOUS LEVELS (if required)
            if rule.requires_previous_level:
                prev_valid, prev_msg = ApprovalService._check_previous_levels(document, rule)
                if not prev_valid:
                    return Decision.deny(prev_msg, rule_id=rule.id, level=rule.approval_level)

            # 7. CHECK AMOUNT LIMITS
            amount_valid, amount_msg = ApprovalService._check_amount_limits(document, rule)
            if not amount_valid:
                return Decision.deny(amount_msg, rule_id=rule.id)

            # SUCCESS!
            return Decision.allow(rule, f"Authorized transition {document.status} → {to_status}")

        except ImportError as e:
            return Decision.deny(f"Approval system not available: {e}")
        except Exception as e:
            logger.error(f"Error in authorize_transition: {e}")
            return Decision.deny(f"Authorization error: {str(e)}")

    @staticmethod
    def get_available_transitions(document, user) -> List[Dict]:
        """
        FIXED: Намери всички възможни transitions за user и document

        Returns:
            List[Dict]: Достъпни transitions с metadata
        """
        try:
            ApprovalService._require_approval_models()

            if not document or not document.document_type:
                return []

            # FIXED: Намери всички ApprovalRule за current status използвайки ForeignKey
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status_obj__code=document.status,  # FIXED: използва ForeignKey
                is_active=True
            ).select_related('to_status_obj', 'approver_user', 'approver_role')

            available = []
            for rule in rules:
                # Провери authorization за всяко правило
                decision = ApprovalService.authorize_transition(
                    document, user, rule.to_status_obj.code
                )

                if decision.allowed:
                    available.append({
                        'to_status': rule.to_status_obj.code,
                        'to_status_name': rule.to_status_obj.name,
                        'label': f"{document.status.title()} → {rule.to_status_obj.name}",
                        'rule_name': rule.name,
                        'approval_level': rule.approval_level,
                        'requires_reason': rule.requires_reason,
                        'rule_id': rule.id,
                        'color': rule.to_status_obj.color,
                        'icon': rule.to_status_obj.icon,
                        'badge_class': rule.to_status_obj.badge_class
                    })

            # Премахни дублирани to_status (взимай първия)
            seen = set()
            unique_transitions = []
            for trans in available:
                if trans['to_status'] not in seen:
                    seen.add(trans['to_status'])
                    unique_transitions.append(trans)

            return unique_transitions

        except ImportError:
            logger.warning("Approval models not available for get_available_transitions")
            return []
        except Exception as e:
            logger.error(f"Error getting available transitions: {e}")
            return []

    # =====================
    # SMART CONVENIENCE API - FIXED
    # =====================

    @staticmethod
    def find_next_approval_status(document) -> Optional[str]:
        """
        FIXED: Намери следващия approval статус за документа

        Търси ApprovalRule с to_status като approval статус
        """
        try:
            ApprovalService._require_approval_models()

            # FIXED: използва ForeignKey полета
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status_obj__code=document.status,
                is_active=True
            ).select_related('to_status_obj')

            # Търси approval pattern в to_status
            for rule in rules.order_by('approval_level'):
                status_code = rule.to_status_obj.code.lower()
                if any(pattern in status_code for pattern in ['approv', 'accept', 'confirm']):
                    return rule.to_status_obj.code

            return None

        except ImportError:
            logger.warning("Approval models not available for find_next_approval_status")
            return None
        except Exception as e:
            logger.error(f"Error finding next approval status: {e}")
            return None

    @staticmethod
    def find_rejection_status(document) -> Optional[str]:
        """FIXED: Намери rejection статус за документа"""
        try:
            ApprovalService._require_approval_models()

            # FIXED: използва ForeignKey полета
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status_obj__code=document.status,
                is_active=True
            ).select_related('to_status_obj')

            # Търси rejection pattern
            for rule in rules:
                status_code = rule.to_status_obj.code.lower()
                if any(pattern in status_code for pattern in ['reject', 'deny', 'cancel']):
                    return rule.to_status_obj.code

            # Fallback: търси в DocumentTypeStatus за cancellation статус
            cancellation_status = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                is_cancellation=True,
                is_active=True
            ).first()

            return cancellation_status.status.code if cancellation_status else None

        except ImportError:
            logger.warning("Models not available for find_rejection_status")
            return None
        except Exception as e:
            logger.error(f"Error finding rejection status: {e}")
            return None

    @staticmethod
    def find_submission_status(document) -> Optional[str]:
        """FIXED: Намери submission статус за документа"""
        try:
            ApprovalService._require_approval_models()

            # FIXED: използва ForeignKey полета
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status_obj__code=document.status,
                is_active=True
            ).select_related('to_status_obj')

            # Търси submission pattern
            for rule in rules.order_by('approval_level'):
                status_code = rule.to_status_obj.code.lower()
                if any(pattern in status_code for pattern in ['submit', 'pending', 'review']):
                    return rule.to_status_obj.code

            return None

        except ImportError:
            logger.warning("Models not available for find_submission_status")
            return None
        except Exception as e:
            logger.error(f"Error finding submission status: {e}")
            return None

    # =====================
    # WORKFLOW INFORMATION API - FIXED
    # =====================

    @staticmethod
    def get_workflow_info(document) -> WorkflowInfo:
        """FIXED: Пълна информация за workflow статуса"""
        try:
            # Available transitions
            available_transitions = ApprovalService.get_available_transitions(
                document, document.created_by if hasattr(document, 'created_by') else None
            )

            # Configured statuses за този document type
            configured_statuses = []
            type_statuses = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                is_active=True
            ).select_related('status').order_by('sort_order')

            for config in type_statuses:
                configured_statuses.append({
                    'code': config.status.code,
                    'name': config.custom_name or config.status.name,
                    'color': config.status.color,
                    'icon': config.status.icon,
                    'is_initial': config.is_initial,
                    'is_final': config.is_final,
                    'is_cancellation': config.is_cancellation,
                    'sort_order': config.sort_order
                })

            # Approval history
            approval_history = ApprovalService.get_approval_history(document)

            # Workflow progress
            workflow_progress = ApprovalService._calculate_workflow_progress(
                document, configured_statuses
            )

            return WorkflowInfo(
                current_status=document.status,
                available_transitions=available_transitions,
                configured_statuses=configured_statuses,
                approval_history=approval_history,
                workflow_progress=workflow_progress
            )

        except Exception as e:
            logger.error(f"Error getting workflow info: {e}")
            return WorkflowInfo(
                current_status=getattr(document, 'status', 'unknown'),
                available_transitions=[],
                configured_statuses=[],
                approval_history=[],
                workflow_progress={'error': str(e)}
            )

    @staticmethod
    def get_approval_history(document) -> List[Dict]:
        """FIXED: История на одобренията за документа"""
        try:
            ApprovalService._require_approval_models()

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
                    'actor_name': log.actor.get_full_name() or log.actor.username,
                    'actor_id': log.actor.id,
                    'rule_name': log.rule.name if log.rule else 'Unknown',
                    'comments': log.comments or '',
                    'level': log.rule.approval_level if log.rule else None
                })

            return history

        except ImportError:
            logger.warning("ApprovalLog not available for get_approval_history")
            return []
        except Exception as e:
            logger.error(f"Error getting approval history: {e}")
            return []

    # =====================
    # PRIVATE VALIDATION METHODS - FIXED
    # =====================

    @staticmethod
    def _validate_target_status(document_type: DocumentType, to_status: str) -> Tuple[bool, str]:
        """Провери дали to_status е валиден за document_type"""
        try:
            exists = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                status__code=to_status,
                is_active=True
            ).exists()

            if not exists:
                configured_statuses = list(
                    DocumentTypeStatus.objects.filter(
                        document_type=document_type,
                        is_active=True
                    ).values_list('status__code', flat=True)
                )

                return False, (
                    f"Status '{to_status}' is not configured for document type "
                    f"'{document_type.type_key}'. Available: {configured_statuses}"
                )

            return True, "Valid status"

        except Exception as e:
            return False, f"Error validating status: {e}"

    @staticmethod
    def _validate_transition_rules(document, to_status: str) -> Tuple[bool, str]:
        """Провери transition rules от DocumentTypeStatus"""
        try:
            # Проверка за final статус (не може transitions FROM final)
            current_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=document.status,
                is_active=True
            ).first()

            if current_config and current_config.is_final:
                return False, f"Cannot transition from final status '{document.status}'"

            # Проверка за initial статус (не може transitions TO initial освен при creation)
            target_config = DocumentTypeStatus.objects.filter(
                document_type=document.document_type,
                status__code=to_status,
                is_active=True
            ).first()

            if target_config and target_config.is_initial:
                return False, f"Cannot transition to initial status '{to_status}'"

            return True, "Transition allowed"

        except Exception as e:
            return False, f"Error validating transition: {e}"

    @staticmethod
    def _find_applicable_rule(document, to_status: str, user):
        """FIXED: Намери приложимо ApprovalRule за transition"""
        try:
            ApprovalService._require_approval_models()

            # FIXED: Намери правила за този transition използвайки ForeignKey полета
            rules = ApprovalRule.objects.filter(
                document_type=document.document_type,
                from_status_obj__code=document.status,
                to_status_obj__code=to_status,
                is_active=True
            ).order_by('approval_level', 'sort_order')

            # Филтрирай по amount ако документът има сума
            amount = ApprovalService._get_document_amount(document)
            if amount is not None:
                rules = rules.filter(
                    min_amount__lte=amount
                ).filter(
                    models.Q(max_amount__gte=amount) | models.Q(max_amount__isnull=True)
                )

            # Върни първото правило което user може да изпълни
            for rule in rules:
                if rule.can_user_approve(user, document):
                    return rule

            return None

        except ImportError:
            logger.warning("ApprovalRule not available for _find_applicable_rule")
            return None
        except Exception as e:
            logger.error(f"Error finding applicable rule: {e}")
            return None

    @staticmethod
    def _check_previous_levels(document, rule) -> Tuple[bool, str]:
        """FIXED: Провери дали предишните approval levels са завършени"""
        try:
            ApprovalService._require_approval_models()

            if not rule.requires_previous_level or rule.approval_level <= 1:
                return True, "No previous levels required"

            content_type = ContentType.objects.get_for_model(document.__class__)

            # Намери всички previous levels за този document type
            required_levels = list(range(1, rule.approval_level))

            # Провери кои levels са approved
            approved_levels = set()
            approval_logs = ApprovalLog.objects.filter(
                content_type=content_type,
                object_id=document.pk,
                action='approved'
            ).select_related('rule')

            for log in approval_logs:
                if log.rule:
                    approved_levels.add(log.rule.approval_level)

            missing_levels = set(required_levels) - approved_levels
            if missing_levels:
                return False, (
                    f"Previous approval levels must be completed first. "
                    f"Missing levels: {sorted(missing_levels)}"
                )

            return True, "Previous levels completed"

        except ImportError:
            logger.warning("ApprovalLog not available for _check_previous_levels")
            return True, "Cannot check previous levels - approval log not available"
        except Exception as e:
            logger.error(f"Error checking previous levels: {e}")
            return False, f"Error checking previous levels: {e}"

    @staticmethod
    def _check_amount_limits(document, rule) -> Tuple[bool, str]:
        """Провери amount limits на правилото"""
        try:
            amount = ApprovalService._get_document_amount(document)
            if amount is None:
                return True, "No amount to check"

            if amount < rule.min_amount:
                return False, f"Amount {amount} is below minimum {rule.min_amount}"

            if rule.max_amount and amount > rule.max_amount:
                return False, f"Amount {amount} exceeds maximum {rule.max_amount}"

            return True, "Amount within limits"

        except Exception as e:
            return False, f"Error checking amount: {e}"

    @staticmethod
    def _get_document_amount(document) -> Optional[float]:
        """Извлече сума от документа"""
        try:
            # Опитай различни field names
            amount_fields = ['total', 'grand_total', 'amount', 'total_amount', 'total_gross']
            for field in amount_fields:
                if hasattr(document, field):
                    value = getattr(document, field)
                    if value is not None:
                        return float(value)

            # Опитай методи за калкулация
            if hasattr(document, 'get_total'):
                return float(document.get_total())
            if hasattr(document, 'calculate_total'):
                return float(document.calculate_total())

            return None

        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _calculate_workflow_progress(document, configured_statuses: List[Dict]) -> Dict:
        """Изчисли progress на workflow"""
        try:
            if not configured_statuses:
                return {'percentage': 0, 'current_step': 0, 'total_steps': 0}

            # Намери current step
            current_step = 0
            for i, status in enumerate(configured_statuses):
                if status['code'] == document.status:
                    current_step = i + 1
                    break

            total_steps = len(configured_statuses)
            percentage = int((current_step / total_steps) * 100) if total_steps > 0 else 0

            return {
                'percentage': percentage,
                'current_step': current_step,
                'total_steps': total_steps,
                'current_status_name': configured_statuses[current_step - 1]['name'] if current_step > 0 else 'Unknown'
            }

        except Exception as e:
            logger.error(f"Error calculating progress: {e}")
            return {'percentage': 0, 'current_step': 0, 'total_steps': 0, 'error': str(e)}


# =====================
# CONVENIENCE FUNCTIONS - FIXED
# =====================

def get_approval_decision(document, user, action: str = 'approve') -> Decision:
    """
    FIXED: Smart convenience за approval decisions

    Args:
        document: Document instance
        user: User
        action: 'approve', 'reject', 'submit'
    """
    try:
        if not ApprovalService.is_available():
            return Decision.deny("Approval system not available")

        if action == 'approve':
            target_status = ApprovalService.find_next_approval_status(document)
        elif action == 'reject':
            target_status = ApprovalService.find_rejection_status(document)
        elif action == 'submit':
            target_status = ApprovalService.find_submission_status(document)
        else:
            return Decision.deny(f"Unknown action: {action}")

        if not target_status:
            return Decision.deny(f"No {action} status found for current state")

        return ApprovalService.authorize_transition(document, user, target_status)

    except Exception as e:
        return Decision.deny(f"Error getting {action} decision: {e}")


def can_user_approve(document, user) -> bool:
    """FIXED: Бърза проверка дали user може да approve документа"""
    try:
        if not ApprovalService.is_available():
            return False
        decision = get_approval_decision(document, user, 'approve')
        return decision.allowed
    except:
        return False


def can_user_reject(document, user) -> bool:
    """FIXED: Бърза проверка дали user може да reject документа"""
    try:
        if not ApprovalService.is_available():
            return False
        decision = get_approval_decision(document, user, 'reject')
        return decision.allowed
    except:
        return False