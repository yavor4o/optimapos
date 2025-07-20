# management/commands/setup_pos_document_types.py
# Създава стандартни документи за POS система
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from nomenclatures.models import DocumentType


class Command(BaseCommand):
    help = 'Създава стандартни DocumentType конфигурации за POS система'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Създаване на стандартни POS документи...\n')

        # =================================================================
        # 1. PURCHASE REQUEST - Заявка за покупка
        # =================================================================
        req_doc_type, created = DocumentType.objects.get_or_create(
            code='PURCHASE_REQ',
            defaults={
                'name': 'Purchase Request',
                'type_key': 'purchase_request',
                'app_name': 'purchases',
                'model_name': 'PurchaseRequest',
                'number_prefix': 'REQ',
                'sort_order': 10,

                # WORKFLOW - Минимален approval process
                'allowed_statuses': [
                    'draft',
                    'submitted',
                    'approved',
                    'rejected',
                    'converted',
                    'cancelled'
                ],
                'default_status': 'draft',
                'status_transitions': {
                    'draft': ['submitted', 'cancelled'],
                    'submitted': ['approved', 'rejected', 'cancelled'],
                    'approved': ['converted', 'cancelled'],
                    'rejected': [],  # Final status
                    'converted': [],  # Final status
                    'cancelled': []  # Final status
                },
                'final_statuses': ['rejected', 'converted', 'cancelled'],

                # BUSINESS RULES
                'requires_approval': True,
                'requires_lines': True,
                'affects_inventory': False,  # Заявките не влияят на склада
                'auto_number': True,
                'pos_document': False,
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {req_doc_type}')
        else:
            self.stdout.write(f'• Exists: {req_doc_type}')

        # =================================================================
        # 2. PURCHASE ORDER - Поръчка към доставчик
        # =================================================================
        order_doc_type, created = DocumentType.objects.get_or_create(
            code='PURCHASE_ORDER',
            defaults={
                'name': 'Purchase Order',
                'type_key': 'purchase_order',
                'app_name': 'purchases',
                'model_name': 'PurchaseOrder',
                'number_prefix': 'PO',
                'sort_order': 20,

                # WORKFLOW - Прост процес
                'allowed_statuses': [
                    'draft',
                    'confirmed',
                    'sent',
                    'partially_delivered',
                    'delivered',
                    'completed',
                    'cancelled'
                ],
                'default_status': 'draft',
                'status_transitions': {
                    'draft': ['confirmed', 'cancelled'],
                    'confirmed': ['sent', 'cancelled'],
                    'sent': ['partially_delivered', 'delivered', 'cancelled'],
                    'partially_delivered': ['delivered', 'cancelled'],
                    'delivered': ['completed'],
                    'completed': [],  # Final status
                    'cancelled': []  # Final status
                },
                'final_statuses': ['completed', 'cancelled'],

                # BUSINESS RULES
                'requires_approval': False,  # Поръчките не изискват approval
                'requires_lines': True,
                'affects_inventory': False,  # Поръчките НЕ влияят директно на склада
                'requires_vat_calculation': True,
                'requires_payment': False,  # Не се плаща при поръчването
                'auto_number': True,
                'pos_document': False,

                # VALIDATION
                'min_total_amount': Decimal('0.01'),
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {order_doc_type}')
        else:
            self.stdout.write(f'• Exists: {order_doc_type}')

        # =================================================================
        # 3. DELIVERY RECEIPT - Доставка/Получаване
        # =================================================================
        delivery_doc_type, created = DocumentType.objects.get_or_create(
            code='DELIVERY_RECEIPT',
            defaults={
                'name': 'Delivery Receipt',
                'type_key': 'delivery_receipt',
                'app_name': 'purchases',
                'model_name': 'DeliveryReceipt',
                'number_prefix': 'DEL',
                'sort_order': 30,

                # WORKFLOW - Фокус върху качеството
                'allowed_statuses': [
                    'draft',
                    'received',
                    'inspected',
                    'accepted',
                    'rejected',
                    'completed'
                ],
                'default_status': 'draft',
                'status_transitions': {
                    'draft': ['received'],
                    'received': ['inspected'],
                    'inspected': ['accepted', 'rejected'],
                    'accepted': ['completed'],
                    'rejected': [],  # Final status - Връща се на доставчика
                    'completed': []  # Final status
                },
                'final_statuses': ['rejected', 'completed'],

                # BUSINESS RULES
                'requires_approval': False,  # Доставките не изискват approval
                'requires_lines': True,
                'affects_inventory': True,  # ⭐ ВЛИЯЕ НА СКЛАДА!
                'inventory_direction': 'in',  # Увеличава склада
                'inventory_timing': 'on_complete',  # При завършване
                'requires_vat_calculation': True,
                'auto_number': True,
                'pos_document': False,

                # QUALITY CONTROL
                'requires_batch_tracking': True,  # Задължителни партиди
                'requires_expiry_dates': True,  # Задължителни срокове
                'requires_quality_check': True,  # Задължителна проверка
            }
        )
        if created:
            self.stdout.write(f'✓ Created: {delivery_doc_type}')
        else:
            self.stdout.write(f'• Exists: {delivery_doc_type}')

        # =================================================================
        # 4. SALES INVOICE - Продажба (бонус за по-късно)
        # =================================================================



        self.stdout.write(self.style.SUCCESS('\n🎉 Стандартните POS документи са готови!'))

        # Показваме кратко резюме
        self.stdout.write('\n📋 РЕЗЮМЕ НА WORKFLOW-ТЕ:')
        self.stdout.write('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')

        self.stdout.write('\n1️⃣  ЗАЯВКА (REQ): draft → submitted → approved → converted')
        self.stdout.write('   ├─ Изисква approval')
        self.stdout.write('   ├─ Не влияе на склада')
        self.stdout.write('   └─ Конвертира се в поръчка')

        self.stdout.write('\n2️⃣  ПОРЪЧКА (PO): draft → confirmed → sent → delivered → completed')
        self.stdout.write('   ├─ БЕЗ approval')
        self.stdout.write('   ├─ Не влияе на склада')
        self.stdout.write('   └─ Създава доставки')

        self.stdout.write('\n3️⃣  ДОСТАВКА (DEL): draft → received → inspected → accepted → completed')
        self.stdout.write('   ├─ БЕЗ approval')
        self.stdout.write('   ├─ ⭐ ВЛИЯЕ НА СКЛАДА при completed')
        self.stdout.write('   └─ Задължителна качествена проверка')

        self.stdout.write('\n4️⃣  ПРОДАЖБА (INV): draft → confirmed → paid')
        self.stdout.write('   ├─ БЕЗ approval')
        self.stdout.write('   ├─ ⭐ ВЛИЯЕ НА СКЛАДА при confirmed')
        self.stdout.write('   └─ Фискален POS документ')

        self.stdout.write('\n🚀 Готово за използване! Можеш да тестваш в админ панела.')