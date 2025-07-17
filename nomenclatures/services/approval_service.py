# nomenclatures/services/approval_service.py

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, models
from django.utils import timezone

from ..models.approvals import ApprovalRule, ApprovalLog

User = get_user_model()


class ApprovalService:
    """
    Dynamic Approval Service

    Интелигентен engine който управлява одобренията базирано на ApprovalRule конфигурация
    """

    @staticmethod
    def get_available_transitions(document, user) -> List[Dict]:
        """
        Намира всички възможни преходи за потребител и документ

        Returns:
            List[Dict]: [
                {
                    'to_status': 'regional_approved',
                    'rule': ApprovalRule instance,
                    'action': 'approve',
                    'level': 1
                }
            ]
        """
        current_status = document.status

        # Намираме всички правила за този документ
        applicable_rules = ApprovalRule.objects.for_document(document).filter(
            from_status=current_status,
            is_active=True
        )

        # Филтрираме по сума ако документът има стойност
        if hasattr(document, 'get_estimated_total'):
            amount = document.get_estimated_total()
            if amount:
                applicable_rules = applicable_rules.filter(
                    min_amount__lte=amount
                ).filter(
                    models.Q(max_amount__isnull=True) |
                    models.Q(max_amount__gte=amount)
                )

        # Проверяваме кои правила потребителят може да изпълни
        available_transitions = []

        for rule in applicable_rules:
            if rule.can_approve(user, document):
                # Проверяваме дали са изпълнени предишните нива (ако е нужно)
                if rule.requires_previous_level:
                    if not ApprovalService._check_previous_levels_completed(document, rule):
                        continue

                available_transitions.append({
                    'to_status': rule.to_status,
                    'rule': rule,
                    'action': 'approve',
                    'level': rule.approval_level,
                    'can_reject': rule.rejection_allowed
                })

        return available_transitions

    @staticmethod
    def execute_transition(document, to_status: str, user, comments: str = '', **kwargs) -> Dict:
        """
        Изпълнява преход от един статус в друг

        Args:
            document: Документът който се одобрява
            to_status: Целевия статус
            user: Потребителят който прави действието
            comments: Коментари/причини

        Returns:
            Dict: Резултат от операцията
        """

        # Намираме подходящото правило
        rule = ApprovalService._find_applicable_rule(document, to_status, user)

        if not rule:
            raise PermissionDenied(f"No approval rule found for transition to '{to_status}'")

        # Валидираме прехода
        ApprovalService._validate_transition(document, rule, user)

        try:
            with transaction.atomic():
                # Запазваме предишния статус
                from_status = document.status

                # Изпълняваме прехода
                document.status = to_status

                # Ъпдейтваме документа според правилото
                ApprovalService._update_document_fields(document, rule, user)

                # Запазваме документа
                document.save()

                # Логваме действието
                ApprovalService._log_approval_action(
                    document, rule, 'approved', from_status, to_status, user, comments
                )

                # Изпращаме нотификации
                ApprovalService._send_notifications(document, rule, user, 'approved')

                # Проверяваме за автоматични следващи действия
                ApprovalService._check_auto_transitions(document, user)

                return {
                    'success': True,
                    'message': f'Document successfully transitioned to {to_status}',
                    'new_status': to_status,
                    'applied_rule': rule.name,
                    'approval_level': rule.approval_level
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error executing transition: {str(e)}',
                'error': str(e)
            }

    @staticmethod
    def reject_document(document, user, reason: str, **kwargs) -> Dict:
        """Отхвърля документ"""

        # Намираме правило за rejection
        rejection_rules = ApprovalRule.objects.for_document(document).filter(
            from_status=document.status,
            rejection_allowed=True,
            is_active=True
        )

        applicable_rule = None
        for rule in rejection_rules:
            if rule.can_approve(user, document):
                applicable_rule = rule
                break

        if not applicable_rule:
            raise PermissionDenied("You cannot reject this document")

        try:
            with transaction.atomic():
                from_status = document.status

                # Статусът за rejection (обикновено 'rejected')
                to_status = 'rejected'

                document.status = to_status

                # Ъпдейтваме документа
                if hasattr(document, 'rejection_reason'):
                    document.rejection_reason = reason
                if hasattr(document, 'rejected_by'):
                    document.rejected_by = user
                if hasattr(document, 'rejected_at'):
                    document.rejected_at = timezone.now()

                document.save()

                # Логваме rejection
                ApprovalService._log_approval_action(
                    document, applicable_rule, 'rejected', from_status, to_status, user, reason
                )

                # Нотификации
                ApprovalService._send_notifications(document, applicable_rule, user, 'rejected')

                return {
                    'success': True,
                    'message': 'Document rejected successfully',
                    'new_status': to_status,
                    'reason': reason
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error rejecting document: {str(e)}',
                'error': str(e)
            }

    @staticmethod
    def get_approval_history(document) -> List[Dict]:
        """Връща историята на одобренията за документ"""

        content_type = ContentType.objects.get_for_model(document)

        logs = ApprovalLog.objects.filter(
            content_type=content_type,
            object_id=document.pk
        ).order_by('timestamp')

        history = []
        for log in logs:
            history.append({
                'timestamp': log.timestamp,
                'action': log.get_action_display(),
                'actor': log.actor.get_full_name(),
                'from_status': log.from_status,
                'to_status': log.to_status,
                'rule': log.rule.name,
                'comments': log.comments,
                'level': log.rule.approval_level
            })

        return history

    @staticmethod
    def get_workflow_status(document) -> Dict:
        """Връща пълна информация за workflow статуса на документ"""

        current_transitions = ApprovalService.get_available_transitions(document, None)
        approval_history = ApprovalService.get_approval_history(document)

        # Намираме всички нива в workflow-a
        all_rules = ApprovalRule.objects.for_document(document).order_by('approval_level')

        workflow_levels = []
        for rule in all_rules:
            # Проверяваме дали това ниво е завършено
            completed = any(
                log['to_status'] == rule.to_status and log['action'] == 'Approved'
                for log in approval_history
            )

            workflow_levels.append({
                'level': rule.approval_level,
                'name': rule.name,
                'to_status': rule.to_status,
                'approver': rule.get_approver_display(),
                'completed': completed,
                'amount_range': rule.get_amount_range_display()
            })

        return {
            'current_status': document.status,
            'available_transitions': len(current_transitions),
            'workflow_levels': workflow_levels,
            'approval_history': approval_history,
            'is_completed': document.status in ['converted', 'completed', 'rejected', 'cancelled']
        }

    # =====================
    # PRIVATE HELPER METHODS
    # =====================

    @staticmethod
    def _find_applicable_rule(document, to_status: str, user) -> Optional[ApprovalRule]:
        """Намира подходящото правило за прехода"""

        applicable_rules = ApprovalRule.objects.for_document(document).filter(
            from_status=document.status,
            to_status=to_status,
            is_active=True
        )

        # Филтрираме по сума
        if hasattr(document, 'get_estimated_total'):
            amount = document.get_estimated_total()
            if amount:
                applicable_rules = applicable_rules.filter(
                    min_amount__lte=amount
                ).filter(
                    models.Q(max_amount__isnull=True) |
                    models.Q(max_amount__gte=amount)
                )

        # Намираме първото правило което потребителят може да изпълни
        for rule in applicable_rules:
            if rule.can_approve(user, document):
                return rule

        return None

    @staticmethod
    def _check_previous_levels_completed(document, rule) -> bool:
        """Проверява дали предишните нива са завършени"""

        if not rule.requires_previous_level:
            return True

        # Намираме всички правила с по-ниско ниво
        previous_rules = ApprovalRule.objects.for_document(document).filter(
            approval_level__lt=rule.approval_level
        )

        # Проверяваме дали всички са изпълнени
        content_type = ContentType.objects.get_for_model(document)

        for prev_rule in previous_rules:
            completed = ApprovalLog.objects.filter(
                content_type=content_type,
                object_id=document.pk,
                rule=prev_rule,
                action='approved'
            ).exists()

            if not completed:
                return False

        return True

    @staticmethod
    def _validate_transition(document, rule, user):
        """Валидира дали преходът е възможен"""

        # Проверка на статуса
        if document.status != rule.from_status:
            raise ValidationError(
                f"Document status '{document.status}' does not match rule requirement '{rule.from_status}'")

        # Проверка на права
        if not rule.can_approve(user, document):
            raise PermissionDenied(f"User does not have permission to execute this transition")

        # Проверка на предишни нива
        if rule.requires_previous_level:
            if not ApprovalService._check_previous_levels_completed(document, rule):
                raise ValidationError("Previous approval levels must be completed first")

    @staticmethod
    def _update_document_fields(document, rule, user):
        """Ъпдейтва полетата на документа според правилото"""

        # Стандартни полета за одобрение
        if hasattr(document, 'approved_by') and rule.to_status.endswith('_approved'):
            document.approved_by = user
        if hasattr(document, 'approved_at') and rule.to_status.endswith('_approved'):
            document.approved_at = timezone.now()

        # Ъпдейт на updated_by
        if hasattr(document, 'updated_by'):
            document.updated_by = user

    @staticmethod
    def _log_approval_action(document, rule, action, from_status, to_status, user, comments):
        """Логва действието в ApprovalLog"""

        content_type = ContentType.objects.get_for_model(document)

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

    @staticmethod
    def _send_notifications(document, rule, user, action):
        """Изпраща нотификации според настройките на правилото"""

        # TODO: Интеграция с NotificationService
        # if rule.notify_approver:
        #     NotificationService.notify_approval_action(document, rule, user, action)
        # if rule.notify_requester:
        #     NotificationService.notify_requester(document, action)
        pass

    @staticmethod
    def _check_auto_transitions(document, user):
        """Проверява за автоматични следващи преходи"""

        # Намираме правила с auto-approve условия
        auto_rules = ApprovalRule.objects.for_document(document).filter(
            from_status=document.status,
            is_active=True
        ).exclude(auto_approve_conditions={})

        for rule in auto_rules:
            if ApprovalService._evaluate_auto_approve_conditions(document, rule):
                # Автоматично изпълняваме прехода
                ApprovalService.execute_transition(
                    document, rule.to_status, user,
                    comments="Auto-approved based on rule conditions"
                )
                break

    @staticmethod
    def _evaluate_auto_approve_conditions(document, rule) -> bool:
        """Оценява дали са изпълнени условията за автоматично одобрение"""

        conditions = rule.auto_approve_conditions
        if not conditions:
            return False

        # Примерни условия:
        # {"max_amount": 100, "supplier_trusted": true}

        try:
            if 'max_amount' in conditions:
                if hasattr(document, 'get_estimated_total'):
                    total = document.get_estimated_total()
                    if total > Decimal(str(conditions['max_amount'])):
                        return False

            if 'supplier_trusted' in conditions:
                if hasattr(document, 'supplier'):
                    trusted = getattr(document.supplier, 'is_trusted', False)
                    if conditions['supplier_trusted'] and not trusted:
                        return False

            return True

        except Exception:
            return False