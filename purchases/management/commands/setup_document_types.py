# purchases/management/commands/setup_document_types.py

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from purchases.models import DocumentType


class Command(BaseCommand):
    help = 'Creates standard document types for POS/retail system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['basic', 'extended', 'full'],
            default='basic',
            help='Setup mode: basic (4 types), extended (7 types), full (10 types)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing document types'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating'
        )

    def handle(self, *args, **options):
        mode = options['mode']
        force = options['force']
        dry_run = options['dry_run']

        self.stdout.write(
            self.style.SUCCESS(f'\n🚀 Setting up document types - {mode.upper()} mode\n')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made\n')
            )

        # Всички document types
        all_types = self._get_all_document_types()

        # Филтрираме според режима
        if mode == 'basic':
            types_to_create = all_types[:4]  # REQ, ORD, GRN, INV
        elif mode == 'extended':
            types_to_create = all_types[:7]  # + ADJ, TRF, WO
        else:  # full
            types_to_create = all_types  # Всички

        self.stdout.write(f"📋 Will create {len(types_to_create)} document types:\n")

        for doc_type in types_to_create:
            status = "✅ NEW" if not self._type_exists(doc_type['code']) else "🔄 EXISTS"
            self.stdout.write(f"  {status} {doc_type['code']} - {doc_type['name']}")

        self.stdout.write("")

        if not dry_run:
            created_count = self._create_document_types(types_to_create, force)
            self.stdout.write(
                self.style.SUCCESS(f'\n🎉 Successfully created/updated {created_count} document types!\n')
            )
            self._show_usage_examples()
        else:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETE - Run without --dry-run to create types\n')
            )

    def _get_all_document_types(self):
        """Връща всички предефинирани document types"""
        return [
            # PRIORITY 1 - PURCHASES (BASIC)
            {
                'code': 'REQ',
                'name': 'Procurement Request',
                'type_key': 'stock_in',
                'stock_effect': 0,  # No effect - само заявка
                'auto_confirm': False,
                'auto_receive': False,
                'requires_batch': False,
                'requires_expiry': False,
                'description': 'Заявка за покупка от магазин/склад'
            },
            {
                'code': 'ORD',
                'name': 'Purchase Order',
                'type_key': 'stock_in',
                'stock_effect': 0,  # No effect - още не е получено
                'auto_confirm': True,  # Поръчките са автоматично confirmed
                'auto_receive': False,
                'requires_batch': False,
                'requires_expiry': False,
                'description': 'Официална поръчка към доставчик'
            },
            {
                'code': 'GRN',
                'name': 'Goods Receipt Note',
                'type_key': 'stock_in',
                'stock_effect': 1,  # Increases stock
                'auto_confirm': True,
                'auto_receive': True,
                'requires_batch': True,  # За проследимост
                'requires_expiry': True,  # За храни/лекарства
                'description': 'Физическо получаване на стока'
            },
            {
                'code': 'INV',
                'name': 'Purchase Invoice',
                'type_key': 'invoice',
                'stock_effect': 0,  # No effect - финансов документ
                'auto_confirm': True,
                'auto_receive': False,
                'requires_batch': False,
                'requires_expiry': False,
                'description': 'Фактура от доставчик'
            },

            # PRIORITY 2 - INVENTORY (EXTENDED)
            {
                'code': 'ADJ',
                'name': 'Stock Adjustment',
                'type_key': 'adjustment',
                'stock_effect': 1,  # Може да е и -1 в зависимост от adjustment
                'auto_confirm': False,  # Изисква одобрение
                'auto_receive': False,
                'requires_batch': True,
                'requires_expiry': False,
                'allow_reverse_operations': True,  # Позволява негативни количества
                'description': 'Корекция на наличности след инвентаризация'
            },
            {
                'code': 'TRF',
                'name': 'Internal Transfer',
                'type_key': 'transfer',
                'stock_effect': 1,  # За receiving location
                'auto_confirm': False,
                'auto_receive': False,
                'requires_batch': True,
                'requires_expiry': False,
                'description': 'Трансфер между складове/магазини'
            },
            {
                'code': 'WO',
                'name': 'Write Off',
                'type_key': 'stock_out',
                'stock_effect': -1,  # Decreases stock
                'auto_confirm': False,  # Изисква одобрение
                'auto_receive': True,
                'requires_batch': True,
                'requires_expiry': True,
                'description': 'Отписване на развалена/изтекла стока'
            },

            # PRIORITY 3 - SALES (FULL)
            {
                'code': 'SAL',
                'name': 'Sales Receipt',
                'type_key': 'stock_out',
                'stock_effect': -1,  # Decreases stock
                'auto_confirm': True,
                'auto_receive': True,
                'requires_batch': False,
                'requires_expiry': False,
                'description': 'Касова бележка/продажба'
            },
            {
                'code': 'SOR',
                'name': 'Sales Order',
                'type_key': 'stock_out',
                'stock_effect': 0,  # No effect until delivered
                'auto_confirm': False,
                'auto_receive': False,
                'requires_batch': False,
                'requires_expiry': False,
                'description': 'Поръчка от клиент'
            },
            {
                'code': 'SRT',
                'name': 'Sales Return',
                'type_key': 'stock_in',
                'stock_effect': 1,  # Increases stock
                'auto_confirm': False,  # Изисква проверка
                'auto_receive': False,
                'requires_batch': True,
                'requires_expiry': False,
                'description': 'Връщане на стока от клиент'
            }
        ]

    def _type_exists(self, code):
        """Проверява дали document type съществува"""
        return DocumentType.objects.filter(code=code).exists()

    @transaction.atomic
    def _create_document_types(self, types_to_create, force=False):
        """Създава document types"""
        created_count = 0

        for doc_type_data in types_to_create:
            code = doc_type_data['code']

            # Проверяваме дали съществува
            existing = DocumentType.objects.filter(code=code).first()

            if existing and not force:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  {code} already exists - skipping (use --force to update)")
                )
                continue

            # Премахваме description за записа в DB
            db_data = {k: v for k, v in doc_type_data.items() if k != 'description'}

            if existing and force:
                # Обновяваме съществуващ
                for key, value in db_data.items():
                    setattr(existing, key, value)
                existing.save()
                self.stdout.write(
                    self.style.SUCCESS(f"🔄 Updated {code} - {existing.name}")
                )
                created_count += 1
            else:
                # Създаваме нов
                doc_type = DocumentType.objects.create(**db_data)
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created {code} - {doc_type.name}")
                )
                created_count += 1

        return created_count

    def _show_usage_examples(self):
        """Показва примери за използване"""
        self.stdout.write(
            self.style.SUCCESS('📚 USAGE EXAMPLES:\n')
        )

        examples = [
            "# Create procurement request:",
            "from purchases.services import ProcurementService",
            "request = ProcurementService.create_procurement_request(...)",
            "",
            "# Convert request to order:",
            "order = ProcurementService.convert_request_to_order(request)",
            "",
            "# Create document directly:",
            "from purchases.services import DocumentService",
            "doc = DocumentService.create_purchase_document(",
            "    supplier=supplier,",
            "    location=location,",
            "    document_type_code='GRN',  # Goods Receipt",
            "    lines_data=[...]",
            ")",
            "",
            "# Filter documents by type:",
            "requests = PurchaseDocument.objects.filter(document_type__code='REQ')",
            "orders = PurchaseDocument.objects.filter(document_type__code='ORD')",
        ]

        for line in examples:
            if line.startswith('#'):
                self.stdout.write(self.style.SUCCESS(line))
            else:
                self.stdout.write(f"  {line}")

        self.stdout.write(
            self.style.SUCCESS('\n🔗 Admin: /admin/purchases/documenttype/')
        )
        self.stdout.write(
            self.style.SUCCESS('🔗 Documents: /admin/purchases/purchasedocument/\n')
        )