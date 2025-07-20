# management/commands/setup_pos_approval_rules.py
# Създава стандартни ApprovalRule за POS система
import self
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from nomenclatures.models import DocumentType, ApprovalRule


manager_group = Group.objects.get(name='manager')
director_group = Group.objects.get(name='director')
purchasing_group = Group.objects.get(name='purchasing')



class Command(BaseCommand):
    help = 'Създава стандартни ApprovalRule за POS workflow'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Създаване на стандартни approval rules...\n')

        # Намираме DocumentType-овете
        try:
            purchase_req_type = DocumentType.objects.get(code='PURCHASE_REQ')
        except DocumentType.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ PURCHASE_REQ DocumentType не съществува!'))
            self.stdout.write('Първо изпълни: python manage.py setup_pos_document_types')
            return

        # =================================================================
        # APPROVAL RULES ЗА PURCHASE REQUEST
        # =================================================================

        # ПРАВИЛО 1: Draft → Submitted (всеки може)
        rule1, created = ApprovalRule.objects.get_or_create(
            document_type=purchase_req_type,
            from_status='draft',
            to_status='submitted',
            approval_level=0,
            defaults={
                'name': 'Submit Request',
                'description': 'Submit purchase request for approval',
                'approver_type': 'ANY_USER',  # Всеки може да submit-не
                'min_amount': Decimal('0.00'),
                'max_amount': None,  # Без лимит
                'currency': 'BGN',
                'is_active': True,
                'sort_order': 10,
                'requires_previous_level': False,
                'auto_approve_conditions': {},
                'rejection_allowed': False,  # Submit не може да се reject-не
                'notify_approver': False,  # Не е нужно известяване
                'notify_requester': False,
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {rule1.name}')

        # ПРАВИЛО 2: Submitted → Approved (Manager approval за малки суми)
        rule2, created = ApprovalRule.objects.get_or_create(
            document_type=purchase_req_type,
            from_status='submitted',
            to_status='approved',
            approval_level=1,
            min_amount=Decimal('0.01'),
            max_amount=Decimal('1000.00'),
            defaults={
                'name': 'Manager Approval - Small Amount',
                'description': 'Manager approval for purchases up to 1000 BGN',
                'approver_type': 'ROLE',
                'approver_role': manager_group,  # Трябва да има role 'manager'
                'currency': 'BGN',
                'is_active': True,
                'sort_order': 20,
                'requires_previous_level': True,  # След submit
                'auto_approve_conditions': {
                    # Може да се добави auto-approval за trusted suppliers
                    'trusted_supplier': False
                },
                'rejection_allowed': True,
                'notify_approver': True,  # Изпрати email/notification
                'notify_requester': True,  # Уведоми заявителя
                'escalation_days': 2,  # Ако няма отговор 2 дни → escalate
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {rule2.name}')

        # ПРАВИЛО 3: Submitted → Approved (Director approval за големи суми)
        rule3, created = ApprovalRule.objects.get_or_create(
            document_type=purchase_req_type,
            from_status='submitted',
            to_status='approved',
            approval_level=2,
            min_amount=Decimal('1000.01'),
            max_amount=None,  # Без горна граница
            defaults={
                'name': 'Director Approval - Large Amount',
                'description': 'Director approval for purchases over 1000 BGN',
                'approver_type': 'ROLE',
                'approver_role': director_group,  # Трябва да има role 'director'
                'currency': 'BGN',
                'is_active': True,
                'sort_order': 30,
                'requires_previous_level': True,
                'auto_approve_conditions': {},
                'rejection_allowed': True,
                'notify_approver': True,
                'notify_requester': True,
                'escalation_days': 1,  # По-кратко време за големи суми
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {rule3.name}')

        # ПРАВИЛО 4: Submitted → Rejected (Manager/Director може да reject-не)
        rule4, created = ApprovalRule.objects.get_or_create(
            document_type=purchase_req_type,
            from_status='submitted',
            to_status='rejected',
            approval_level=1,
            defaults={
                'name': 'Reject Request',
                'description': 'Reject purchase request with reason',
                'approver_type': 'ROLE',
                'approver_role': manager_group,  # Manager може да reject-не
                'min_amount': Decimal('0.00'),
                'max_amount': None,
                'currency': 'BGN',
                'is_active': True,
                'sort_order': 40,
                'requires_previous_level': True,
                'auto_approve_conditions': {},
                'rejection_allowed': True,
                'notify_approver': False,
                'notify_requester': True,  # Уведоми че е reject-нато
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {rule4.name}')

        # ПРАВИЛО 5: Approved → Converted (Purchasing може да конвертира)
        rule5, created = ApprovalRule.objects.get_or_create(
            document_type=purchase_req_type,
            from_status='approved',
            to_status='converted',
            approval_level=0,  # Ниско ниво - операционна задача
            defaults={
                'name': 'Convert to Order',
                'description': 'Convert approved request to purchase order',
                'approver_type': 'ROLE',
                'approver_role': purchasing_group,  # Purchasing отдел
                'min_amount': Decimal('0.00'),
                'max_amount': None,
                'currency': 'BGN',
                'is_active': True,
                'sort_order': 50,
                'requires_previous_level': True,
                'auto_approve_conditions': {},
                'rejection_allowed': False,  # Conversion не може да fail-не
                'notify_approver': False,
                'notify_requester': True,  # Уведоми че е конвертирано
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {rule5.name}')

        # ПРАВИЛО 6: Cancel от всеки статус (Emergency cancellation)
        for from_status in ['draft', 'submitted', 'approved']:
            rule_cancel, created = ApprovalRule.objects.get_or_create(
                document_type=purchase_req_type,
                from_status=from_status,
                to_status='cancelled',
                approval_level=1,
                defaults={
                    'name': f'Cancel from {from_status.title()}',
                    'description': f'Emergency cancellation from {from_status} status',
                    'approver_type': 'ROLE',
                    'approver_role': manager_group,
                    'min_amount': Decimal('0.00'),
                    'max_amount': None,
                    'currency': 'BGN',
                    'is_active': True,
                    'sort_order': 90,  # По-нисък приоритет
                    'requires_previous_level': False,  # Emergency action
                    'auto_approve_conditions': {},
                    'rejection_allowed': False,
                    'notify_approver': False,
                    'notify_requester': True,
                }
            )
            if created:
                self.stdout.write(f'✓ Created: {rule_cancel.name}')

        self.stdout.write(self.style.SUCCESS('\n🎉 Approval Rules са готови!'))

        # Показваме резюме
        self.stdout.write('\n📋 РЕЗЮМЕ НА APPROVAL ПРОЦЕСА:')
        self.stdout.write('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')

        self.stdout.write('\n💰 СУМИ И ОДОБРЕНИЯ:')
        self.stdout.write('   ├─ 0.01 - 1000.00 BGN → Manager approval')
        self.stdout.write('   └─ > 1000.00 BGN → Director approval')

        self.stdout.write('\n👥 РОЛИ В СИСТЕМАТА:')
        self.stdout.write('   ├─ ANY_USER: Може да submit-ва заявки')
        self.stdout.write('   ├─ manager: Одобрява до 1000 BGN, може да reject-ва и cancel-ира')
        self.stdout.write('   ├─ director: Одобрява над 1000 BGN')
        self.stdout.write('   └─ purchasing: Конвертира одобрени заявки в поръчки')

        self.stdout.write('\n⏰ ВРЕМЕВИ ЛИМИТИ:')
        self.stdout.write('   ├─ Малки суми: 2 дни за одобрение')
        self.stdout.write('   └─ Големи суми: 1 ден за одобрение')

        self.stdout.write('\n🔔 ИЗВЕСТЯВАНИЯ:')
        self.stdout.write('   ├─ Approver се уведомява при pending approval')
        self.stdout.write('   └─ Requester се уведомява при одобрение/отказ/конверсия')

        self.stdout.write('\n🚀 Готово! Можеш да тестваш approval workflow-а в админ панела.')
        self.stdout.write('   За тестване създай users с roles: manager, director, purchasing')