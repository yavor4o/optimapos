# nomenclatures/services/approval_service.py - UPDATED С DOCUMENTTYPE INTEGRATION

from typing import Dict, List, Optional, Any
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import logging

from ..models.approvals import ApprovalRule, ApprovalLog

User = get_user_model()
logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Финален ApprovalService - Пълна имплементация

    Управлява целия approval workflow динамично според ApprovalRule конфигурацията
    """

    # =====================
    # ОСНОВНИ ПУБЛИЧНИ МЕТОДИ
    # =====================

    @staticmethod
    def get_available_transitions(document, user) -> List[Dict]:
        """
        Връща всички възможни преходи за документ и потребител

        НОВА ЛОГИКА: Проверява и DocumentType и ApprovalRule ограниченията
        """
        try:
            if not document or not hasattr(document, 'status'):
                return []

            # НОВА ПРОВЕРКА: Вземаме allowed transitions от DocumentType
            document_allowed_transitions = document.get_next_statuses()

            if not document_allowed_transitions:
                logger.info(f"No DocumentType transitions allowed from status '{document.status}' for {document}")
                return []

            # Намираме всички активни ApprovalRule-и за този документ
            applicable_rules = ApprovalRule.objects.for_document(document).filter(
                from_status=document.status,
                is_active=True
            )

            # НОВА ФИЛТРАЦИЯ: Само правила които DocumentType позволява
            applicable_rules = applicable_rules.filter(
                to_status__in=document_allowed_transitions
            )

            # Филтрираме по сума ако документът има такава
            if hasattr(document, 'get_estimated_total'):
                try:
                    amount = document.get_estimated_total()
                    if amount and amount > 0:
                        applicable_rules = applicable_rules.filter(
                            min_amount__lte=amount
                        ).filter(
                            models.Q(max_amount__isnull=True) |
                            models.Q(max_amount__gte=amount)
                        )
                except Exception as e:
                    logger.warning(f"Error getting document amount: {e}")

            available_transitions = []

            for rule in applicable_rules:
                # Проверяваме дали потребителят може да изпълни това правило
                if user and ApprovalService._can_user_execute_rule(user, rule, document):
                    # Проверяваме дали предишните нива са завършени
                    if ApprovalService._check_previous_levels_completed(document, rule):
                        available_transitions.append({
                            'to_status': rule.to_status,
                            'rule': rule,
                            'level': rule.approval_level,
                            'name': rule.name,
                            'description': rule.description or f"Transition to {rule.to_status}",
                            'document_type_allowed': True  # НОВ: Маркираме че DocumentType го позволява
                        })

            # Сортираме по ниво
            available_transitions.sort(key=lambda x: x['level'])

            logger.info(f"Found {len(available_transitions)} available transitions for {document} (user: {user})")

            return available_transitions

        except Exception as e:
            logger.error(f"Error getting available transitions: {e}")
            return []

    @staticmethod
    def execute_transition(document, to_status: str, user, comments: str = '', **kwargs) -> Dict:
        """
        Изпълнява преход от един статус в друг

        НОВА ЛОГИКА: Валидира срещу DocumentType ПРЕДИ ApprovalRule
        """
        try:
            # НОВА ПРОВЕРКА 1: DocumentType compatibility ПЪРВО
            validation_result = ApprovalService._validate_document_type_transition(document, to_status)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'message': validation_result['message'],
                    'error_code': 'DOCUMENT_TYPE_RESTRICTION'
                }

            # НОВА ПРОВЕРКА 2: Намираме подходящото ApprovalRule
            rule = ApprovalService._find_applicable_rule(document, to_status, user)

            if not rule:
                return {
                    'success': False,
                    'message': f'No approval rule found for transition from "{document.status}" to "{to_status}"',
                    'error_code': 'NO_RULE_FOUND',
                    'available_transitions': [t['to_status'] for t in
                                              ApprovalService.get_available_transitions(document, user)]
                }

            # ПРОВЕРКА 3: ApprovalRule validation
            rule_validation_result = ApprovalService._validate_approval_rule_transition(document, rule, user)
            if not rule_validation_result['valid']:
                return {
                    'success': False,
                    'message': rule_validation_result['message'],
                    'error_code': 'APPROVAL_RULE_VALIDATION_FAILED'
                }

            # Изпълняваме прехода в транзакция
            with transaction.atomic():
                from_status = document.status

                # Ъпдейтваме статуса (вече НЕ се налага flag за BaseDocument)
                document.status = to_status

                # Ъпдейтваме други полета според правилото
                ApprovalService._update_document_fields(document, rule, user)

                # Запазваме документа (BaseDocument няма да прави auto-transitions)
                document.save()

                # Логваме действието
                log_entry = ApprovalService._log_approval_action(
                    document=document,
                    rule=rule,
                    action='approved',
                    from_status=from_status,
                    to_status=to_status,
                    user=user,
                    comments=comments
                )

                # Изпращаме нотификации
                ApprovalService._send_notifications(document, rule, user, 'approved')

                # Проверяваме за ApprovalRule auto-transitions
                ApprovalService._check_approval_rule_auto_transitions(document, user)

                logger.info(f"Successfully transitioned {document} from {from_status} to {to_status} by {user}")

                return {
                    'success': True,
                    'message': f'Document successfully transitioned to {to_status}',
                    'new_status': to_status,
                    'from_status': from_status,
                    'applied_rule': rule.name,
                    'approval_level': rule.approval_level,
                    'log_entry': log_entry,
                    'validation_passed': ['document_type', 'approval_rule']
                }

        except Exception as e:
            logger.error(f"Error executing transition: {e}")
            return {
                'success': False,
                'message': f'Error executing transition: {str(e)}',
                'error_code': 'EXECUTION_ERROR',
                'error': str(e)
            }

    @staticmethod
    def _validate_document_type_transition(document, to_status: str) -> Dict:
        """
        Enhanced DocumentType validation with pure configuration approach

        Returns:
            Dict: {'valid': bool, 'message': str}
        """
        try:
            if not document.document_type:
                return {
                    'valid': False,
                    'message': 'Document has no DocumentType configured'
                }

            # Check if to_status is in allowed_statuses
            allowed_statuses = document.document_type.allowed_statuses or []
            if to_status not in allowed_statuses:
                return {
                    'valid': False,
                    'message': f'Status "{to_status}" is not in DocumentType allowed statuses: {allowed_statuses}. Please check DocumentType configuration.'
                }

            # Check if transitions are configured
            allowed_transitions = document.document_type.get_allowed_transitions()
            if not allowed_transitions:
                return {
                    'valid': False,
                    'message': f'No status_transitions configured in DocumentType "{document.document_type.name}". Please configure status_transitions in DocumentType admin.'
                }

            # Check if current status has any configured transitions
            if document.status not in allowed_transitions:
                return {
                    'valid': False,
                    'message': f'No transitions configured for current status "{document.status}" in DocumentType "{document.document_type.name}". Please configure status_transitions.'
                }

            # Check if specific transition is allowed
            available_transitions = allowed_transitions.get(document.status, [])
            if to_status not in available_transitions:
                return {
                    'valid': False,
                    'message': f'Transition "{document.status}" → "{to_status}" not configured in DocumentType "{document.document_type.name}". Available transitions: {available_transitions}'
                }

            # Check if current status is final
            if document.document_type.is_final_status(document.status):
                return {
                    'valid': False,
                    'message': f'Document is in final status "{document.status}" and cannot be changed'
                }

            return {
                'valid': True,
                'message': 'DocumentType validation passed'
            }

        except Exception as e:
            logger.error(f"Error validating DocumentType transition: {e}")
            return {
                'valid': False,
                'message': f'Error during DocumentType validation: {str(e)}'
            }

    @staticmethod
    def _validate_approval_rule_transition(document, rule: ApprovalRule, user) -> Dict:
        """
        НОВ МЕТОД: Валидира ApprovalRule конкретно

        Returns:
            Dict: {'valid': bool, 'message': str}
        """
        try:
            # Проверка на статуса
            if document.status != rule.from_status:
                return {
                    'valid': False,
                    'message': f"Document status '{document.status}' does not match rule requirement '{rule.from_status}'"
                }

            # Проверка на права
            if not ApprovalService._can_user_execute_rule(user, rule, document):
                return {
                    'valid': False,
                    'message': f"User does not have permission to execute this approval rule"
                }

            # Проверка на предишни нива
            if rule.requires_previous_level:
                if not ApprovalService._check_previous_levels_completed(document, rule):
                    return {
                        'valid': False,
                        'message': "Previous approval levels must be completed first"
                    }

            return {
                'valid': True,
                'message': 'ApprovalRule validation passed'
            }

        except Exception as e:
            logger.error(f"Error validating ApprovalRule transition: {e}")
            return {
                'valid': False,
                'message': f'Error during ApprovalRule validation: {str(e)}'
            }

    @staticmethod

    def _check_document_type_auto_transitions(document, user):
        """
        НОВ МЕТОД: Проверява за DocumentType auto-transitions
        """
        try:
            if not document.document_type or not document.document_type.auto_transitions:
                return

            auto_transitions = document.document_type.auto_transitions
            auto_next_status = auto_transitions.get(document.status)

            if auto_next_status:
                # Проверяваме дали преходът е възможен
                if document.can_transition_to(auto_next_status):
                    logger.info(f"Executing DocumentType auto-transition: {document.status} → {auto_next_status}")

                    # Рекурсивно викаме execute_transition за auto-prехода
                    result = ApprovalService.execute_transition(
                        document=document,
                        to_status=auto_next_status,
                        user=user,
                        comments="Automatic transition from DocumentType configuration"
                    )

                    if result['success']:
                        logger.info(f"DocumentType auto-transition successful: {document} to {auto_next_status}")
                    else:
                        logger.warning(f"DocumentType auto-transition failed: {result['message']}")

        except Exception as e:
            logger.error(f"Error in DocumentType auto-transitions: {e}")



    @staticmethod
    def reject_document(document, user, reason: str, **kwargs) -> Dict:
        """
        Отхвърля документ

        Args:
            document: Документът за отхвърляне
            user: Потребителят който отхвърля
            reason: Причина за отхвърляне

        Returns:
            Dict: {'success': bool, 'message': str, ...}
        """
        try:
            # Намираме правило за rejection от текущия статус
            rejection_rules = ApprovalRule.objects.for_document(document).filter(
                from_status=document.status,
                to_status='rejected',
                is_active=True,
                rejection_allowed=True
            )

            # Намираме правило което потребителят може да изпълни
            applicable_rule = None
            for rule in rejection_rules:
                if ApprovalService._can_user_execute_rule(user, rule, document):
                    applicable_rule = rule
                    break

            if not applicable_rule:
                return {
                    'success': False,
                    'message': 'You do not have permission to reject this document',
                    'error_code': 'NO_REJECTION_PERMISSION'
                }

            # Изпълняваме отхвърлянето
            with transaction.atomic():
                from_status = document.status
                document.status = 'rejected'

                # Задаваме причината за отхвърляне
                if hasattr(document, 'rejection_reason'):
                    document.rejection_reason = reason

                # Ъпдейтваме полета
                ApprovalService._update_document_fields(document, applicable_rule, user)

                document.save()

                # Логваме действието
                log_entry = ApprovalService._log_approval_action(
                    document=document,
                    rule=applicable_rule,
                    action='rejected',
                    from_status=from_status,
                    to_status='rejected',
                    user=user,
                    comments=reason
                )

                # Нотификации
                ApprovalService._send_notifications(document, applicable_rule, user, 'rejected')

                logger.info(f"Document {document} rejected by {user}: {reason}")

                return {
                    'success': True,
                    'message': f'Document successfully rejected',
                    'reason': reason,
                    'applied_rule': applicable_rule.name,
                    'log_entry': log_entry
                }

        except Exception as e:
            logger.error(f"Error rejecting document: {e}")
            return {
                'success': False,
                'message': f'Error rejecting document: {str(e)}',
                'error_code': 'REJECTION_ERROR',
                'error': str(e)
            }

    @staticmethod
    def get_workflow_status(document) -> Dict:
        """
        Връща пълна информация за workflow статуса на документ

        Returns:
            Dict: Детайлна информация за статуса и прогреса
        """
        try:
            # Основна информация
            current_transitions = ApprovalService.get_available_transitions(document, None)
            approval_history = ApprovalService.get_approval_history(document)

            # Намираме всички нива в workflow-a за този документ
            all_rules = ApprovalRule.objects.for_document(document).order_by('approval_level')

            # Филтрираме по сума ако е възможно
            if hasattr(document, 'get_estimated_total'):
                try:
                    amount = document.get_estimated_total()
                    if amount and amount > 0:
                        all_rules = all_rules.filter(
                            min_amount__lte=amount
                        ).filter(
                            models.Q(max_amount__isnull=True) |
                            models.Q(max_amount__gte=amount)
                        )
                except Exception:
                    pass

            # Създаваме информация за всяко ниво
            workflow_levels = []
            for rule in all_rules:
                # Проверяваме дали това ниво е завършено
                completed = any(
                    log['to_status'] == rule.to_status and log['action'] in ['approved', 'auto_approved']
                    for log in approval_history
                )

                workflow_levels.append({
                    'level': rule.approval_level,
                    'name': rule.name,
                    'from_status': rule.from_status,
                    'to_status': rule.to_status,
                    'approver': ApprovalService._get_rule_approver_display(rule),
                    'completed': completed,
                    'amount_range': ApprovalService._get_rule_amount_display(rule),
                    'is_parallel': rule.is_parallel
                })

            # Определяме дали workflow-ът е завършен
            final_statuses = ['approved', 'rejected', 'cancelled', 'converted', 'completed']
            is_completed = document.status in final_statuses

            return {
                'current_status': document.status,
                'available_transitions': len(current_transitions),
                'workflow_levels': workflow_levels,
                'approval_history': approval_history,
                'is_completed': is_completed,
                'document_number': getattr(document, 'document_number', 'Unknown'),
                'document_type': document.__class__.__name__
            }

        except Exception as e:
            logger.error(f"Error getting workflow status: {e}")
            return {
                'current_status': getattr(document, 'status', 'unknown'),
                'available_transitions': 0,
                'workflow_levels': [],
                'approval_history': [],
                'is_completed': False,
                'error': str(e)
            }

    @staticmethod
    def get_approval_history(document) -> List[Dict]:
        """
        Връща историята на одобренията за документ

        Returns:
            List[Dict]: История на всички одобрения/отхвърляния
        """
        try:
            content_type = ContentType.objects.get_for_model(document.__class__)

            logs = ApprovalLog.objects.filter(
                content_type=content_type,
                object_id=document.pk
            ).select_related('actor', 'rule').order_by('-timestamp')

            history = []
            for log in logs:
                history.append({
                    'timestamp': log.timestamp,
                    'action': log.get_action_display(),
                    'actor': log.actor.get_full_name() if log.actor else 'System',
                    'from_status': log.from_status,
                    'to_status': log.to_status,
                    'comments': log.comments,
                    'level': log.rule.approval_level if log.rule else None,
                    'rule_name': log.rule.name if log.rule else None
                })

            return history

        except Exception as e:
            logger.error(f"Error getting approval history: {e}")
            return []

    # =====================
    # ПОМОЩНИ ЧАСТНИ МЕТОДИ
    # =====================

    @staticmethod
    def _find_applicable_rule(document, to_status: str, user) -> Optional[ApprovalRule]:
        """Намира подходящото правило за прехода"""
        try:
            applicable_rules = ApprovalRule.objects.for_document(document).filter(
                from_status=document.status,
                to_status=to_status,
                is_active=True
            )

            # Филтрираме по сума
            if hasattr(document, 'get_estimated_total'):
                try:
                    amount = document.get_estimated_total()
                    if amount and amount > 0:
                        applicable_rules = applicable_rules.filter(
                            min_amount__lte=amount
                        ).filter(
                            models.Q(max_amount__isnull=True) |
                            models.Q(max_amount__gte=amount)
                        )
                except Exception:
                    pass

            # Намираме първото правило което потребителят може да изпълни
            for rule in applicable_rules.order_by('approval_level', 'sort_order'):
                if ApprovalService._can_user_execute_rule(user, rule, document):
                    return rule

            return None

        except Exception as e:
            logger.error(f"Error finding applicable rule: {e}")
            return None

    @staticmethod
    def _can_user_execute_rule(user, rule: ApprovalRule, document) -> bool:
        """Проверява дали потребителят може да изпълни правилото"""
        try:
            if not user:
                return False

            if rule.approver_type == 'user':
                return rule.approver_user == user

            elif rule.approver_type == 'role':
                if rule.approver_role:
                    return user.groups.filter(id=rule.approver_role.id).exists()

            elif rule.approver_type == 'permission':
                if rule.approver_permission:
                    return user.has_perm(
                        f"{rule.approver_permission.content_type.app_label}.{rule.approver_permission.codename}")

            elif rule.approver_type == 'dynamic':
                # За dynamic правила можем да добавим специална логика тук
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking user rule permissions: {e}")
            return False

    @staticmethod
    def _check_previous_levels_completed(document, rule: ApprovalRule) -> bool:
        """Проверява дали предишните нива са завършени"""
        try:
            if not rule.requires_previous_level:
                return True

            # Намираме всички правила с по-ниско ниво
            previous_rules = ApprovalRule.objects.for_document(document).filter(
                approval_level__lt=rule.approval_level
            )

            content_type = ContentType.objects.get_for_model(document.__class__)

            for prev_rule in previous_rules:
                # Проверяваме дали има успешно одобрение за това правило
                completed = ApprovalLog.objects.filter(
                    content_type=content_type,
                    object_id=document.pk,
                    rule=prev_rule,
                    action__in=['approved', 'auto_approved']
                ).exists()

                if not completed:
                    return False

            return True

        except Exception as e:
            logger.error(f"Error checking previous levels: {e}")
            return True  # В случай на грешка позволяваме прехода

    @staticmethod
    def _validate_transition(document, rule: ApprovalRule, user) -> Dict:
        """Валидира дали преходът е възможен"""
        try:
            # Проверка на статуса
            if document.status != rule.from_status:
                return {
                    'valid': False,
                    'message': f"Document status '{document.status}' does not match rule requirement '{rule.from_status}'"
                }

            # Проверка на права
            if not ApprovalService._can_user_execute_rule(user, rule, document):
                return {
                    'valid': False,
                    'message': "User does not have permission to execute this transition"
                }

            # Проверка на предишни нива
            if rule.requires_previous_level:
                if not ApprovalService._check_previous_levels_completed(document, rule):
                    return {
                        'valid': False,
                        'message': "Previous approval levels must be completed first"
                    }

            return {'valid': True, 'message': 'Validation passed'}

        except Exception as e:
            logger.error(f"Error validating transition: {e}")
            return {
                'valid': False,
                'message': f"Validation error: {str(e)}"
            }

    @staticmethod
    def _update_document_fields(document, rule: ApprovalRule, user):
        """Ъпдейтва полетата на документа според правилото"""
        try:
            # Стандартни полета за одобрение
            if hasattr(document, 'approved_by') and 'approv' in rule.to_status:
                document.approved_by = user

            if hasattr(document, 'approved_at') and 'approv' in rule.to_status:
                document.approved_at = timezone.now()

            # Ъпдейт на updated_by
            if hasattr(document, 'updated_by'):
                document.updated_by = user

        except Exception as e:
            logger.error(f"Error updating document fields: {e}")

    @staticmethod
    def _log_approval_action(document, rule: ApprovalRule, action: str, from_status: str, to_status: str, user,
                             comments: str = '') -> ApprovalLog:
        """Логва действието в ApprovalLog"""
        try:
            content_type = ContentType.objects.get_for_model(document.__class__)

            log_entry = ApprovalLog.objects.create(
                content_type=content_type,
                object_id=document.pk,
                rule=rule,
                action=action,
                from_status=from_status,
                to_status=to_status,
                actor=user,
                comments=comments
            )

            return log_entry

        except Exception as e:
            logger.error(f"Error logging approval action: {e}")
            return None

    @staticmethod
    def _send_notifications(document, rule: ApprovalRule, user, action: str):
        """Изпраща нотификации според настройките на правилото"""
        try:
            # Засега само логваме, нотификациите са следваща фаза
            logger.info(f"Notification: {action} by {user} for {document} using rule {rule.name}")

            # TODO: Имплементиране на реални нотификации
            # if rule.notify_approver:
            #     NotificationService.notify_approver(...)
            # if rule.notify_requester:
            #     NotificationService.notify_requester(...)

        except Exception as e:
            logger.error(f"Error sending notifications: {e}")

    @staticmethod
    def _check_auto_transitions(document, user):
        """Проверява за автоматични следващи преходи"""
        try:
            # Търсим правила за автоматични преходи от новия статус
            auto_rules = ApprovalRule.objects.for_document(document).filter(
                from_status=document.status,
                is_active=True
            ).exclude(auto_approve_conditions__isnull=True).exclude(auto_approve_conditions__exact={})

            for rule in auto_rules:
                # Проверяваме условията за автоматично одобрение
                if ApprovalService._check_auto_conditions(document, rule):
                    # Изпълняваме автоматичния преход
                    result = ApprovalService.execute_transition(
                        document=document,
                        to_status=rule.to_status,
                        user=user,
                        comments="Automatic transition based on predefined conditions"
                    )

                    if result['success']:
                        logger.info(f"Auto-transition executed: {document} to {rule.to_status}")
                        break

        except Exception as e:
            logger.error(f"Error checking auto transitions: {e}")

    @staticmethod
    def _check_auto_conditions(document, rule: ApprovalRule) -> bool:
        """Проверява дали условията за автоматично одобрение са изпълнени"""
        try:
            conditions = rule.auto_approve_conditions
            if not conditions:
                return False

            # Примерни условия - може да се разшири
            if 'max_amount' in conditions:
                if hasattr(document, 'get_estimated_total'):
                    amount = document.get_estimated_total()
                    if amount and amount > conditions['max_amount']:
                        return False

            if 'required_fields' in conditions:
                for field in conditions['required_fields']:
                    if not getattr(document, field, None):
                        return False

            return True

        except Exception as e:
            logger.error(f"Error checking auto conditions: {e}")
            return False

    @staticmethod
    def _get_rule_approver_display(rule: ApprovalRule) -> str:
        """Връща текстово представяне на одобряващия"""
        try:
            if rule.approver_type == 'user' and rule.approver_user:
                return rule.approver_user.get_full_name() or rule.approver_user.username
            elif rule.approver_type == 'role' and rule.approver_role:
                return rule.approver_role.name
            elif rule.approver_type == 'permission' and rule.approver_permission:
                return rule.approver_permission.name
            else:
                return 'Dynamic'
        except Exception:
            return 'Unknown'

    @staticmethod
    def _get_rule_amount_display(rule: ApprovalRule) -> str:
        """Връща текстово представяне на сумовия диапазон"""
        try:
            if rule.max_amount:
                return f"{rule.min_amount} - {rule.max_amount} {rule.currency}"
            else:
                return f"From {rule.min_amount} {rule.currency}"
        except Exception:
            return "No limit"