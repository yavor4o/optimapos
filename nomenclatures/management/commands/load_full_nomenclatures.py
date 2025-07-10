from django.core.management.base import BaseCommand
from django.db import transaction
from nomenclatures.models import Currency, UnitOfMeasure, PaymentType, ProductType, Brand


class Command(BaseCommand):
    help = 'Зарежда разширени номенклатури за пълна функционалност'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Зареждане на разширени номенклатури...\n')

        # Допълнителни валути
        self.load_additional_currencies()

        # Всички мерни единици
        self.load_all_units()

        # Всички типове плащания
        self.load_all_payment_types()

        # Типове продукти
        self.load_product_types()

        self.stdout.write(self.style.SUCCESS('\n✅ Разширените номенклатури са заредени!'))

    def load_additional_currencies(self):
        """Често използвани валути"""
        self.stdout.write('Добавяне на валути...')
        currencies = [
            {'code': 'EUR', 'name': 'Евро', 'symbol': '€'},
            {'code': 'USD', 'name': 'Щатски долар', 'symbol': '$'},
        ]

        for curr_data in currencies:
            curr, created = Currency.objects.get_or_create(
                code=curr_data['code'],
                defaults=curr_data
            )
            if created:
                self.stdout.write(f'  ✓ {curr.code}')

    def load_all_units(self):
        """Всички стандартни мерни единици"""
        self.stdout.write('\nДобавяне на мерни единици...')
        units = [
            # Опаковки
            {'code': 'STACK', 'name': 'Стек', 'symbol': 'ст', 'unit_type': 'PIECE'},
            {'code': 'BOX', 'name': 'Кашон', 'symbol': 'каш', 'unit_type': 'PIECE'},
            {'code': 'PAL', 'name': 'Палет', 'symbol': 'пал', 'unit_type': 'PIECE'},

            # Тегло
            {'code': 'G', 'name': 'Грам', 'symbol': 'г', 'unit_type': 'WEIGHT'},
            {'code': 'T', 'name': 'Тон', 'symbol': 'т', 'unit_type': 'WEIGHT'},

            # Обем
            {'code': 'L', 'name': 'Литър', 'symbol': 'л', 'unit_type': 'VOLUME'},
            {'code': 'ML', 'name': 'Милилитър', 'symbol': 'мл', 'unit_type': 'VOLUME'},

            # Дължина
            {'code': 'M', 'name': 'Метър', 'symbol': 'м', 'unit_type': 'LENGTH'},
            {'code': 'CM', 'name': 'Сантиметър', 'symbol': 'см', 'unit_type': 'LENGTH'},
        ]

        for unit_data in units:
            unit_data['allow_decimals'] = unit_data['unit_type'] != 'PIECE'
            unit_data['decimal_places'] = 0 if unit_data['unit_type'] == 'PIECE' else 3

            unit, created = UnitOfMeasure.objects.get_or_create(
                code=unit_data['code'],
                defaults=unit_data
            )
            if created:
                self.stdout.write(f'  ✓ {unit.name}')

    def load_all_payment_types(self):
        """Всички типове плащания"""
        self.stdout.write('\nДобавяне на типове плащания...')
        payments = [
            {
                'code': '002',
                'name': 'Дебитна/Кредитна карта',
                'key': PaymentType.CARD,
                'requires_reference': True,
                'sort_order': 2
            },
            {
                'code': '003',
                'name': 'Ваучер',
                'key': PaymentType.VOUCHER,
                'requires_reference': True,
                'sort_order': 3
            },
            {
                'code': '004',
                'name': 'На кредит',
                'key': PaymentType.CREDIT,
                'requires_approval': True,
                'sort_order': 4
            },
        ]

        for pay_data in payments:
            pay, created = PaymentType.objects.get_or_create(
                key=pay_data['key'],
                defaults=pay_data
            )
            if created:
                self.stdout.write(f'  ✓ {pay.name}')

    def load_product_types(self):
        """Типове продукти"""
        self.stdout.write('\nДобавяне на типове продукти...')
        types = [
            {'code': 'FOOD', 'name': 'Хранителни стоки', 'category': ProductType.FOOD},
            {'code': 'NFOOD', 'name': 'Нехранителни стоки', 'category': ProductType.NON_FOOD},
            {'code': 'ALC', 'name': 'Алкохол', 'category': ProductType.ALCOHOL},
            {'code': 'CIG', 'name': 'Цигари', 'category': ProductType.TOBACCO},
        ]

        for type_data in types:
            prod_type, created = ProductType.objects.get_or_create(
                code=type_data['code'],
                defaults=type_data
            )
            if created:
                self.stdout.write(f'  ✓ {prod_type.name}')