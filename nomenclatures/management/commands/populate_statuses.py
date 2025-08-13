# nomenclatures/management/commands/populate_statuses.py

from django.core.management.base import BaseCommand
from django.db import transaction
from nomenclatures.models import DocumentType, DocumentStatus, DocumentTypeStatus


class Command(BaseCommand):
    help = 'Populate initial document statuses'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Creating document statuses...')

        # =====================
        # 1. CREATE BASE STATUSES
        # =====================
        statuses_data = [
            {
                'code': 'draft',
                'name': 'Draft',
                'description': 'Document is being prepared',
                'allow_edit': True,
                'allow_delete': True,
                'color': '#6c757d',
                'badge_class': 'badge-secondary',
                'sort_order': 10,
            },
            {
                'code': 'submitted',
                'name': 'Submitted',
                'description': 'Submitted for approval',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#ffc107',
                'badge_class': 'badge-warning',
                'sort_order': 20,
            },
            {
                'code': 'approved',
                'name': 'Approved',
                'description': 'Document has been approved',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#28a745',
                'badge_class': 'badge-success',
                'sort_order': 30,
            },
            {
                'code': 'rejected',
                'name': 'Rejected',
                'description': 'Document has been rejected',
                'allow_edit': True,  # Може да се редактира за корекции
                'allow_delete': False,
                'color': '#dc3545',
                'badge_class': 'badge-danger',
                'sort_order': 35,
            },
            {
                'code': 'completed',
                'name': 'Completed',
                'description': 'Document has been completed',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#28a745',
                'badge_class': 'badge-success',
                'sort_order': 40,
                'is_system': True,
            },
            {
                'code': 'converted',
                'name': 'Converted',
                'description': 'Document has been converted to another type',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#007bff',
                'badge_class': 'badge-primary',
                'sort_order': 45,
            },
            {
                'code': 'cancelled',
                'name': 'Cancelled',
                'description': 'Document has been cancelled',
                'allow_edit': True,  # Може корекции след cancel
                'allow_delete': False,
                'color': '#dc3545',
                'badge_class': 'badge-danger',
                'sort_order': 50,
                'is_system': True,
            },
            # Специфични за поръчки/доставки
            {
                'code': 'sent',
                'name': 'Sent',
                'description': 'Document has been sent',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#17a2b8',
                'badge_class': 'badge-info',
                'sort_order': 25,
            },
            {
                'code': 'confirmed',
                'name': 'Confirmed',
                'description': 'Document has been confirmed',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#20c997',
                'badge_class': 'badge-success',
                'sort_order': 35,
            },
            {
                'code': 'received',
                'name': 'Received',
                'description': 'Items have been received',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#20c997',
                'badge_class': 'badge-success',
                'sort_order': 36,
            },
            {
                'code': 'new',
                'name': 'New',
                'description': 'Newly created document',
                'allow_edit': True,
                'allow_delete': True,
                'color': '#17a2b8',
                'badge_class': 'badge-info',
                'sort_order': 5,
            },
            {
                'code': 'partial',
                'name': 'Partial',
                'description': 'Partially processed',
                'allow_edit': False,
                'allow_delete': False,
                'color': '#ffc107',
                'badge_class': 'badge-warning',
                'sort_order': 37,
            },
        ]

        created_statuses = {}
        for data in statuses_data:
            status, created = DocumentStatus.objects.get_or_create(
                code=data['code'],
                defaults=data
            )
            created_statuses[data['code']] = status
            if created:
                self.stdout.write(f'  ✓ Created status: {status.name}')
            else:
                self.stdout.write(f'  - Status exists: {status.name}')

        # =====================
        # 2. CONFIGURE DOCUMENT TYPES
        # =====================
        self.stdout.write('\nConfiguring document types...')

        # Purchase Request configuration
        pr_type = DocumentType.objects.filter(type_key='purchase_request').first()
        if pr_type:
            self.stdout.write(f'\n  Configuring {pr_type.name}...')
            configs = [
                ('draft', True, False, False, 10),  # initial
                ('submitted', False, False, False, 20),
                ('approved', False, False, False, 30),
                ('rejected', False, False, False, 35),
                ('converted', False, True, False, 40),  # final
                ('cancelled', False, True, True, 50),  # final + cancellation
            ]

            for code, is_initial, is_final, is_cancel, sort_order in configs:
                config, created = DocumentTypeStatus.objects.get_or_create(
                    document_type=pr_type,
                    status=created_statuses[code],
                    defaults={
                        'is_initial': is_initial,
                        'is_final': is_final,
                        'is_cancellation': is_cancel,
                        'sort_order': sort_order,
                    }
                )
                if created:
                    self.stdout.write(f'    ✓ Added {code}')

        # Purchase Order configuration
        po_type = DocumentType.objects.filter(type_key='purchase_order').first()
        if po_type:
            self.stdout.write(f'\n  Configuring {po_type.name}...')
            configs = [
                ('draft', True, False, False, 10),
                ('sent', False, False, False, 20),
                ('confirmed', False, False, False, 30),
                ('partial', False, False, False, 35),
                ('completed', False, True, False, 40),
                ('cancelled', False, True, True, 50),
            ]

            for code, is_initial, is_final, is_cancel, sort_order in configs:
                config, created = DocumentTypeStatus.objects.get_or_create(
                    document_type=po_type,
                    status=created_statuses[code],
                    defaults={
                        'is_initial': is_initial,
                        'is_final': is_final,
                        'is_cancellation': is_cancel,
                        'sort_order': sort_order,
                    }
                )
                if created:
                    self.stdout.write(f'    ✓ Added {code}')

        # Delivery Receipt configuration
        dr_type = DocumentType.objects.filter(type_key='delivery_receipt').first()
        if dr_type:
            self.stdout.write(f'\n  Configuring {dr_type.name}...')
            configs = [
                ('new', True, False, False, 10),
                ('received', False, False, False, 20),
                ('completed', False, True, False, 30),
                ('cancelled', False, True, True, 40),
            ]

            for code, is_initial, is_final, is_cancel, sort_order in configs:
                config, created = DocumentTypeStatus.objects.get_or_create(
                    document_type=dr_type,
                    status=created_statuses[code],
                    defaults={
                        'is_initial': is_initial,
                        'is_final': is_final,
                        'is_cancellation': is_cancel,
                        'sort_order': sort_order,
                    }
                )
                if created:
                    self.stdout.write(f'    ✓ Added {code}')

        # =====================
        # 3. UPDATE EXISTING APPROVAL RULES
        # =====================
        self.stdout.write('\nUpdating ApprovalRule statuses...')
        from nomenclatures.models import ApprovalRule

        # Map старите CharField стойности към новите DocumentStatus обекти
        for rule in ApprovalRule.objects.all():
            updated = False

            # Ако има стари CharField стойности (from_status, to_status)
            # и няма нови ForeignKey стойности
            if hasattr(rule, 'from_status') and not rule.from_status_obj:
                from_status = DocumentStatus.objects.filter(code=rule.from_status).first()
                if from_status:
                    rule.from_status_obj = from_status
                    updated = True

            if hasattr(rule, 'to_status') and not rule.to_status_obj:
                to_status = DocumentStatus.objects.filter(code=rule.to_status).first()
                if to_status:
                    rule.to_status_obj = to_status
                    updated = True

            if updated:
                rule.save()
                self.stdout.write(f'  ✓ Updated rule: {rule.name}')

        self.stdout.write(self.style.SUCCESS('\n✓ Status configuration completed!'))