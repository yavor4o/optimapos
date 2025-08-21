# partners/services/customer_service.py - REFACTORED WITH RESULT PATTERN
from typing import Dict, Any

from django.utils import timezone
from decimal import Decimal
from datetime import  timedelta


from core.utils.result import Result


class CustomerService:
    """
    Сервис за работа с клиенти

    REFACTORED: All methods now return Result objects for consistency
    Legacy methods available for backward compatibility
    """

    # =====================================================
    # NEW: RESULT-BASED METHODS
    # =====================================================

    @staticmethod
    def get_dashboard_data(customer_id: int) -> Result:
        """
        Връща пълни данни за customer dashboard - NEW Result-based method
        """
        from ..models import Customer

        try:
            customer = Customer.objects.select_related('price_group').prefetch_related(
                'sites', 'day_schedules'
            ).get(id=customer_id)
        except Customer.DoesNotExist:
            return Result.error(
                code='CUSTOMER_NOT_FOUND',
                msg=f'Customer with ID {customer_id} not found',
                data={'customer_id': customer_id}
            )

        # Основни данни
        basic_info = {
            'id': customer.id,
            'name': customer.name,
            'code': getattr(customer, 'code', ''),  # От новия IPartner protocol
            'type': customer.type,
            'type_display': customer.get_type_display(),
            'contact_person': customer.contact_person,
            'phone': customer.phone,
            'email': customer.email,
            'is_active': customer.is_active,
            'price_group': customer.price_group.name if customer.price_group else None,
        }

        # Обекти/адреси
        sites_result = CustomerService.get_sites_data(customer)
        sites = sites_result.data if sites_result.ok else []

        # График
        schedule_result = CustomerService.get_schedule_data(customer)
        schedule = schedule_result.data if schedule_result.ok else {}

        # Кредитен статус
        credit_result = CustomerService.get_credit_data(customer)
        credit_status = credit_result.data if credit_result.ok else {}

        # История на продажби (placeholder)
        sales_result = CustomerService.get_sales_data(customer, limit=10)
        sales = sales_result.data if sales_result.ok else []

        # Статистики
        statistics_result = CustomerService.get_statistics_data(customer)
        statistics = statistics_result.data if statistics_result.ok else {}

        dashboard_data = {
            'basic_info': basic_info,
            'sites': sites,
            'schedule': schedule,
            'credit_status': credit_status,
            'sales': sales,
            'statistics': statistics,
            'customer_id': customer_id,
            'generated_at': timezone.now().isoformat()
        }

        return Result.success(
            data=dashboard_data,
            msg=f"Dashboard data for {customer.name} retrieved successfully"
        )

    @staticmethod
    def get_sites_data(customer) -> Result:
        """Връща обектите на клиента - NEW Result-based method"""
        try:
            sites = []
            for site in customer.sites.filter(is_active=True):
                sites.append({
                    'id': site.id,
                    'name': site.name,
                    'city': site.city,
                    'address': site.address,
                    'contact_person': site.contact_person,
                    'phone': site.phone,
                    'email': site.email,
                    'is_primary': site.is_primary,
                    'is_delivery_address': site.is_delivery_address,
                    'is_billing_address': site.is_billing_address,
                    'special_discount': site.special_discount,
                })

            return Result.success(
                data=sites,
                msg=f"Found {len(sites)} active sites"
            )

        except Exception as e:
            return Result.error(
                code='SITES_ERROR',
                msg=f"Error retrieving sites: {str(e)}",
                data={'customer_id': customer.id}
            )

    @staticmethod
    def get_schedule_data(customer) -> Result:
        """Връща графика на клиента - NEW Result-based method"""
        try:
            schedules = customer.day_schedules.all()

            order_days = []
            delivery_days = []

            for schedule in schedules:
                day_info = {
                    'day': schedule.day,
                    'day_display': schedule.get_day_display(),
                    'delivery_from': schedule.preferred_delivery_time_from,
                    'delivery_to': schedule.preferred_delivery_time_to,
                }

                if schedule.expects_order:
                    order_days.append(day_info)
                if schedule.expects_delivery:
                    delivery_days.append(day_info)

            schedule_data = {
                'order_days': order_days,
                'delivery_days': delivery_days,
                'order_days_count': len(order_days),
                'delivery_days_count': len(delivery_days),
            }

            return Result.success(
                data=schedule_data,
                msg=f"Schedule: {len(order_days)} order days, {len(delivery_days)} delivery days"
            )

        except Exception as e:
            return Result.error(
                code='SCHEDULE_ERROR',
                msg=f"Error retrieving schedule: {str(e)}",
                data={'customer_id': customer.id}
            )

    @staticmethod
    def get_credit_data(customer) -> Result:
        """Връща кредитния статус - NEW Result-based method"""
        try:
            # Основни кредитни данни
            credit_data = {
                'credit_limit': customer.credit_limit,
                'payment_delay_days': customer.payment_delay_days,
                'credit_blocked': getattr(customer, 'credit_blocked', False),
                'sales_blocked': getattr(customer, 'sales_blocked', False),
            }

            # TODO: Когато имаме sales app, добави:
            # - used_credit (от неплатени фактури)
            # - available_credit (credit_limit - used_credit)
            # - overdue_amount (просрочени плащания)

            # За сега - placeholder стойности
            credit_data.update({
                'used_credit': Decimal('0'),
                'available_credit': customer.credit_limit,
                'overdue_amount': Decimal('0'),
                'last_payment_date': None,
                'message': 'Full credit data will be available when sales app is connected'
            })

            return Result.success(
                data=credit_data,
                msg=f"Credit limit: {customer.credit_limit}, Available: {credit_data['available_credit']}"
            )

        except Exception as e:
            return Result.error(
                code='CREDIT_ERROR',
                msg=f"Error retrieving credit data: {str(e)}",
                data={'customer_id': customer.id}
            )

    @staticmethod
    def get_sales_data(customer, date_from=None, date_to=None, limit=None) -> Result:
        """Връща история на продажбите - NEW Result-based method"""
        try:
            # TODO: Когато имаме sales app, имплементирай истинска логика
            # from sales.models import SalesInvoice

            # За сега връщаме placeholder
            sales_data = []

            # Mock данни за демонстрация
            if limit and limit > 0:
                for i in range(min(3, limit)):  # Максимум 3 mock записа
                    sales_data.append({
                        'id': f'mock_{i + 1}',
                        'document_number': f'INV-2024-{1000 + i}',
                        'document_date': timezone.now().date() - timedelta(days=i * 30),
                        'total': Decimal('150.00') * (i + 1),
                        'status': 'paid',
                        'is_paid': True,
                        'note': 'Mock sales data'
                    })

            return Result.success(
                data=sales_data,
                msg=f"Found {len(sales_data)} sales records (mock data)"
            )

        except Exception as e:
            return Result.error(
                code='SALES_ERROR',
                msg=f"Error retrieving sales data: {str(e)}",
                data={'customer_id': customer.id}
            )

    @staticmethod
    def get_statistics_data(customer) -> Result:
        """Връща статистики за клиента - NEW Result-based method"""
        try:
            # TODO: Когато имаме sales app, имплементирай истинска логика

            # За сега използваме sites данни
            statistics_data = {
                'total_sites': customer.sites.count(),
                'active_sites': customer.sites.filter(is_active=True).count(),
                'primary_site': None,
                'message': 'Full statistics will be available when sales app is connected'
            }

            # Намери primary site
            primary_site = customer.sites.filter(is_primary=True).first()
            if primary_site:
                statistics_data['primary_site'] = {
                    'id': primary_site.id,
                    'name': primary_site.name,
                    'city': primary_site.city
                }

            return Result.success(
                data=statistics_data,
                msg=f"Statistics: {statistics_data['active_sites']} active sites"
            )

        except Exception as e:
            return Result.error(
                code='STATISTICS_ERROR',
                msg=f"Error retrieving statistics: {str(e)}",
                data={'customer_id': customer.id}
            )

    @staticmethod
    def validate_sale(customer, amount: Decimal, site=None) -> Result:
        """Проверява дали може да се направи продажба - NEW Result-based method"""
        if not customer.is_active:
            return Result.error(
                code='CUSTOMER_INACTIVE',
                msg="Customer is not active",
                data={'customer_id': customer.id, 'name': customer.name}
            )

        sales_blocked = getattr(customer, 'sales_blocked', False)
        if sales_blocked:
            return Result.error(
                code='SALES_BLOCKED',
                msg="Sales are blocked for this customer",
                data={'customer_id': customer.id, 'name': customer.name}
            )

        # За продажби на кредит
        if amount > 0:  # Ако не е cash продажба
            credit_blocked = getattr(customer, 'credit_blocked', False)
            if credit_blocked:
                return Result.error(
                    code='CREDIT_BLOCKED',
                    msg="Credit sales are blocked for this customer",
                    data={'customer_id': customer.id, 'name': customer.name}
                )

            if customer.credit_limit > 0:
                credit_result = CustomerService.get_credit_data(customer)
                if credit_result.ok:
                    available_credit = credit_result.data.get('available_credit', 0)
                    if available_credit < amount:
                        return Result.error(
                            code='CREDIT_LIMIT_EXCEEDED',
                            msg=f"Credit limit exceeded. Available: {available_credit}",
                            data={
                                'credit_limit': customer.credit_limit,
                                'available_credit': available_credit,
                                'requested_amount': amount
                            }
                        )

        # Site validation
        site_info = {}
        if site:
            site_info = {
                'site_id': site.id,
                'site_name': site.name,
                'is_delivery_address': site.is_delivery_address
            }

        return Result.success(
            data={
                'amount': amount,
                'customer_id': customer.id,
                'site_info': site_info
            },
            msg="Sale can be processed"
        )

    @staticmethod
    def get_customer_discount(customer, product=None, site=None) -> Result:
        """Връща отстъпка за клиент - NEW Result-based method"""
        try:
            discount_info: Dict[str, Any] = {  # ← ДОБАВИ Any за mixed types
                'base_discount': Decimal('0'),
                'site_discount': Decimal('0'),
                'product_discount': Decimal('0'),
                'total_discount': Decimal('0'),
                'price_group': None
            }

            # Price group discount
            if customer.price_group:
                price_group_discount = getattr(customer.price_group, 'discount_percent', Decimal('0'))

                discount_info['price_group'] = {
                    'id': customer.price_group.id,
                    'name': customer.price_group.name,
                    'discount_percent': price_group_discount
                }
                # ПОПРАВКА: използвай price_group_discount, не цялия dict
                discount_info['base_discount'] = price_group_discount

            # Site-specific discount
            if site and hasattr(site, 'special_discount') and site.special_discount:
                discount_info['site_discount'] = site.special_discount

            # Calculate total (use max, not sum, for discounts)
            discount_info['total_discount'] = max(
                discount_info['base_discount'],
                discount_info['site_discount']
            )

            return Result.success(
                data=discount_info,
                msg=f"Customer discount: {discount_info['total_discount']}%"
            )

        except Exception as e:
            return Result.error(
                code='DISCOUNT_ERROR',
                msg=f"Error calculating discount: {str(e)}",
                data={'customer_id': customer.id}
            )

