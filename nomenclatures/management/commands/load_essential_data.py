from django.core.management.base import BaseCommand
from django.db import transaction
from nomenclatures.models import Currency, TaxGroup, UnitOfMeasure, PaymentType


class Command(BaseCommand):
    help = 'Зарежда само задължителните номенклатури за стартиране на системата'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Зареждане на задължителни номенклатури...\n')

        # 1. Базова валута - ЗАДЪЛЖИТЕЛНО
        self.stdout.write('1. Създаване на базова валута...')
        bgn, created = Currency.objects.get_or_create(
            code='BGN',
            defaults={
                'name': 'Български лев',
                'symbol': 'лв',
                'is_base': True,
                'decimal_places': 2,
                'is_active': True
            }
        )
        self.stdout.write(self.style.SUCCESS(f'  ✓ BGN {"създаден" if created else "вече съществува"}'))

        # 2. Основни данъчни групи - ЗАДЪЛЖИТЕЛНО
        self.stdout.write('\n2. Създаване на ДДС групи...')
        tax_groups = [
            {'code': 'VAT20', 'name': 'ДДС 20%', 'rate': 20, 'is_default': True},
            {'code': 'VAT9', 'name': 'ДДС 9%', 'rate': 9},
            {'code': 'VAT0', 'name': 'ДДС 0%', 'rate': 0},
        ]

        for tg_data in tax_groups:
            tg, created = TaxGroup.objects.get_or_create(
                code=tg_data['code'],
                defaults=tg_data
            )
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ {tg.name} {"създадена" if created else "вече съществува"}'
            ))

        # 3. Минимални мерни единици - ЗАДЪЛЖИТЕЛНО
        self.stdout.write('\n3. Създаване на основни мерни единици...')
        units = [
            {
                'code': 'PCS',
                'name': 'Брой',
                'symbol': 'бр',
                'unit_type': UnitOfMeasure.PIECE,
                'allow_decimals': False,
                'decimal_places': 0
            },
            {
                'code': 'KG',
                'name': 'Килограм',
                'symbol': 'кг',
                'unit_type': UnitOfMeasure.WEIGHT,
                'allow_decimals': True,
                'decimal_places': 3
            },
        ]

        for unit_data in units:
            unit, created = UnitOfMeasure.objects.get_or_create(
                code=unit_data['code'],
                defaults=unit_data
            )
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ {unit.name} {"създадена" if created else "вече съществува"}'
            ))

        # 4. Задължителен тип плащане - ЗАДЪЛЖИТЕЛНО поне един
        self.stdout.write('\n4. Създаване на тип плащане в брой...')
        cash_payment, created = PaymentType.objects.get_or_create(
            key=PaymentType.CASH,
            defaults={
                'code': '001',
                'name': 'В брой',
                'is_cash': True,
                'allows_change': True,
                'is_fiscal': True,
                'sort_order': 1,
                'is_active': True
            }
        )
        self.stdout.write(self.style.SUCCESS(
            f'  ✓ Плащане в брой {"създадено" if created else "вече съществува"}'
        ))

        # Финална проверка
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('\n✅ Задължителните номенклатури са готови!'))
        self.stdout.write('\nСистемата може да стартира с:')
        self.stdout.write('  • 1 базова валута (BGN)')
        self.stdout.write('  • 2 ДДС групи (20% и 0%)')
        self.stdout.write('  • 2 мерни единици (брой и килограм)')
        self.stdout.write('  • 1 тип плащане (в брой)')

        self.stdout.write('\n💡 Съвет: За пълна функционалност изпълнете:')
        self.stdout.write('   python manage.py load_full_nomenclatures')