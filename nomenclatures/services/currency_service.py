# from decimal import Decimal
# from typing import Optional, Tuple
# from datetime import date
# from django.core.cache import cache
# from django.db import transaction
# from ..models import Currency, ExchangeRate
#
#
# class CurrencyService:
#     """Сервиз за работа с валути и курсове"""
#
#     CACHE_TIMEOUT = 3600  # 1 час
#
#     @staticmethod
#     def get_base_currency() -> Currency:
#         """Връща базовата валута на системата"""
#         cache_key = 'base_currency'
#         base_currency = cache.get(cache_key)
#
#         if not base_currency:
#             base_currency = Currency.objects.get(is_base=True)
#             cache.set(cache_key, base_currency, CurrencyService.CACHE_TIMEOUT)
#
#         return base_currency
#
#     @staticmethod
#     def convert_amount(
#             amount: Decimal,
#             from_currency: Currency,
#             to_currency: Currency,
#             conversion_date: Optional[date] = None,
#             rate_type: str = 'central'
#     ) -> Decimal:
#         """Конвертира сума между две валути"""
#
#         if from_currency == to_currency:
#             return amount
#
#         base_currency = CurrencyService.get_base_currency()
#
#         # Ако една от валутите е базова
#         if from_currency == base_currency:
#             # От базова към друга
#             rate = ExchangeRate.objects.get_rate_for_date(to_currency, conversion_date)
#             return rate.convert_from_base(amount, rate_type)
#
#         elif to_currency == base_currency:
#             # От друга към базова
#             rate = ExchangeRate.objects.get_rate_for_date(from_currency, conversion_date)
#             return rate.convert_to_base(amount, rate_type)
#
#         else:
#             # През базовата валута
#             # Първо към базова
#             rate_from = ExchangeRate.objects.get_rate_for_date(from_currency, conversion_date)
#             base_amount = rate_from.convert_to_base(amount, rate_type)
#
#             # После от базова към целева
#             rate_to = ExchangeRate.objects.get_rate_for_date(to_currency, conversion_date)
#             return rate_to.convert_from_base(base_amount, rate_type)
#
#     @staticmethod
#     def get_exchange_rate_for_date(
#             currency: Currency,
#             rate_date: Optional[date] = None
#     ) -> Optional[ExchangeRate]:
#         """Връща валутен курс за дата"""
#         try:
#             return ExchangeRate.objects.get_rate_for_date(currency, rate_date)
#         except ValueError:
#             return None
#
#     @staticmethod
#     @transaction.atomic
#     def import_bnb_rates(rate_date: date) -> Tuple[int, list]:
#         """
#         Импортира курсове от БНБ
#         Връща: (брой импортирани, списък с грешки)
#         """
#         # TODO: Implement BNB API integration
#         # За сега само placeholder
#         imported = 0
#         errors = []
#
#         # Примерен код за импорт
#         currencies_to_import = Currency.active.exclude(is_base=True)
#
#         for currency in currencies_to_import:
#             try:
#                 # Тук ще извикваме API на БНБ
#                 # rate_data = fetch_bnb_rate(currency.code, rate_date)
#
#                 # За сега хардкоднати стойности за тест
#                 if currency.code == 'EUR':
#                     ExchangeRate.objects.update_or_create(
#                         currency=currency,
#                         date=rate_date,
#                         defaults={
#                             'units': 1,
#                             'buy_rate': Decimal('1.955'),
#                             'sell_rate': Decimal('1.960'),
#                             'central_rate': Decimal('1.95583'),
#                         }
#                     )
#                     imported += 1
#
#             except Exception as e:
#                 errors.append(f"{currency.code}: {str(e)}")
#
#         return imported, errors
#
#     @staticmethod
#     def get_rate_spread(currency: Currency, rate_date: Optional[date] = None) -> dict:
#         """Връща информация за спреда между покупка и продажба"""
#         rate = ExchangeRate.objects.get_rate_for_date(currency, rate_date)
#
#         spread_amount = rate.sell_rate - rate.buy_rate
#         spread_percent = (spread_amount / rate.central_rate) * 100
#
#         return {
#             'currency': currency.code,
#             'date': rate.date,
#             'buy_rate': rate.buy_rate,
#             'sell_rate': rate.sell_rate,
#             'central_rate': rate.central_rate,
#             'spread_amount': spread_amount,
#             'spread_percent': round(spread_percent, 2),
#         }