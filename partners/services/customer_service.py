from django.db.models import Sum, Count, Q, Avg, Max
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class CustomerService:
    """
    Сервис за работа с клиенти
    Централизира бизнес логиката за продажби, кредит, задължения
    """

    @staticmethod
    def get_customer_dashboard(customer_id: int) -> Dict:
        """
        Връща пълни данни за customer dashboard/modal
        """
        from ..models import Customer

        try:
            customer = Customer.objects.select_related('price_group').prefetch_related(
                'sites', 'day_schedules'
            ).get(id=customer_id)
        except Customer.DoesNotExist:
            return {'error': 'Customer not found'}

        # Основни данни
        basic_info = {
            'id': customer.id,
            'name': customer.name,
            'type': customer.type,
            'type_display': customer.get_type_display(),
            'category': customer.category,
            'category_display': customer.get_category_display(),
            'contact_person': customer.contact_person,
            'phone': customer.phone,
            'email': customer.email,
            'is_active': customer.is_active,
            'can_buy': customer.can_buy(),
            'can_buy_on_credit': customer.can_buy_on_credit(),
        }

        # Обекти/адреси
        sites = CustomerService.get_customer_sites(customer)

        # График
        schedule = CustomerService.get_customer_schedule(customer)

        # Кредитен статус
        credit_status = CustomerService.get_credit_status(customer)

        # История на продажби
        sales = CustomerService.get_sales_history(customer, limit=10)

        # Статистики
        statistics = CustomerService.get_customer_statistics(customer)

        return {
            'basic_info': basic_info,
            'sites': sites,
            'schedule': schedule,
            'credit_status': credit_status,
            'sales': sales,
            'statistics': statistics,
        }

    @staticmethod
    def get_customer_sites(customer) -> List[Dict]:
        """Връща обектите на клиента"""
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
        return sites

    @staticmethod
    def get_customer_schedule(customer) -> Dict:
        """Връща графика на клиента"""
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

        return {
            'order_days': order_days,
            'delivery_days': delivery_days,
            'order_days_count': len(order_days),
            'delivery_days_count': len(delivery_days),
        }

    @staticmethod
    def get_credit_status(customer) -> Dict:
        """Връща кредитния статус на клиента"""
        try:
            # Когато имаме sales app
            # from sales.models import SalesDocument

            # current_debt = SalesDocument.objects.filter(
            #     customer=customer,
            #     is_paid=False
            # ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

            # За сега връщаме mock данни
            current_debt = Decimal('0')

            # Просрочени задължения
            overdue_date = timezone.now().date() - timedelta(days=customer.payment_delay_days)
            # overdue_debt = SalesDocument.objects.filter(
            #     customer=customer,
            #     is_paid=False,
            #     document_date__lt=overdue_date
            # ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

            overdue_debt = Decimal('0')

            return {
                'credit_limit': customer.credit_limit,
                'payment_delay_days': customer.payment_delay_days,
                'current_debt': current_debt,
                'available_credit': customer.credit_limit - current_debt,
                'overdue_debt': overdue_debt,
                'credit_utilization': (current_debt / customer.credit_limit * 100) if customer.credit_limit > 0 else 0,
                'is_over_limit': current_debt > customer.credit_limit,
                'has_overdue': overdue_debt > 0,
                'credit_blocked': customer.credit_blocked,
                'effective_discount': customer.get_effective_discount(),
            }

        except ImportError:
            return {
                'credit_limit': customer.credit_limit,
                'payment_delay_days': customer.payment_delay_days,
                'effective_discount': customer.get_effective_discount(),
                'message': 'Credit data not available - sales app not installed'
            }

    @staticmethod
    def get_sales_history(customer, date_from=None, date_to=None, limit=None) -> List[Dict]:
        """Връща история на продажбите"""
        try:
            # Когато имаме sales app
            # from sales.models import SalesDocument

            # queryset = SalesDocument.objects.filter(customer=customer)

            # if date_from:
            #     queryset = queryset.filter(document_date__gte=date_from)
            # if date_to:
            #     queryset = queryset.filter(document_date__lte=date_to)

            # queryset = queryset.select_related('warehouse').order_by('-document_date')

            # if limit:
            #     queryset = queryset[:limit]

            # sales = []
            # for doc in queryset:
            #     sales.append({
            #         'id': doc.id,
            #         'document_number': doc.document_number,
            #         'document_date': doc.document_date,
            #         'warehouse': doc.warehouse.name,
            #         'grand_total': doc.grand_total,
            #         'is_paid': doc.is_paid,
            #     })

            # return sales

            # Mock данни за сега
            return []

        except ImportError:
            return []

    @staticmethod
    def get_customer_statistics(customer) -> Dict:
        """Връща статистики за клиента"""
        try:
            # Когато имаме sales app
            # from sales.models import SalesDocument, SalesDocumentLine

            # twelve_months_ago = timezone.now().date() - timedelta(days=365)

            # monthly_stats = SalesDocument.objects.filter(
            #     customer=customer,
            #     document_date__gte=twelve_months_ago
            # ).extra(
            #     select={'month': "strftime('%%Y-%%m', document_date)"}
            # ).values('month').annotate(
            #     total_amount=Sum('grand_total'),
            #     order_count=Count('id')
            # ).order_by('month')

            # top_products = SalesDocumentLine.objects.filter(
            #     document__customer=customer,
            #     document__document_date__gte=twelve_months_ago
            # ).values(
            #     'product__code', 'product__name'
            # ).annotate(
            #     total_quantity=Sum('quantity'),
            #     total_amount=Sum('line_total'),
            #     order_count=Count('document', distinct=True)
            # ).order_by('-total_amount')[:10]

            # Mock данни за сега
            return {
                'total_sites': customer.sites.count(),
                'active_sites': customer.sites.filter(is_active=True).count(),
                'primary_site': customer.sites.filter(is_primary=True).first(),
                'message': 'Full statistics will be available when sales app is connected'
            }

        except ImportError:
            return {
                'total_sites': customer.sites.count(),
                'active_sites': customer.sites.filter(is_active=True).count(),
                'message': 'Statistics not available - sales app not installed'
            }

    @staticmethod
    def can_make_sale(customer, amount: Decimal, site=None) -> Tuple[bool, str]:
        """Проверява дали може да се направи продажба"""
        if not customer.is_active:
            return False, "Customer is not active"

        if customer.sales_blocked:
            return False, "Sales are blocked for this customer"

        # За продажби на кредит
        if amount > 0:  # Ако не е cash продажба
            if customer.credit_blocked:
                return False, "Credit sales are blocked for this customer"

            if customer.credit_limit > 0:
                credit_status = CustomerService.get_credit_status(customer)
                if credit_status['available_credit'] < amount:
                    return False, f"Credit limit exceeded. Available: {credit_status['available_credit']}"

        return True, "OK"

    @staticmethod
    def get_customer_discount(customer, product=None, site=None) -> Decimal:
        """Връща приложимата отстъпка за клиента"""
        # Проверка за специална отстъпка на обекта
        if site and site.special_discount:
            return site.special_discount

        # Ефективната отстъпка от клиента
        return customer.get_effective_discount()

    @staticmethod
    def get_vip_customers():
        """Връща VIP клиентите"""
        from ..models import Customer

        return Customer.objects.filter(
            category=Customer.CATEGORY_VIP,
            is_active=True
        ).select_related('price_group').prefetch_related('sites')

    @staticmethod
    def get_problematic_customers():
        """Връща проблемните клиенти"""
        from ..models import Customer

        return Customer.objects.filter(
            Q(category=Customer.CATEGORY_PROBLEMATIC) |
            Q(sales_blocked=True) |
            Q(credit_blocked=True),
            is_active=True
        ).select_related('price_group')

    @staticmethod
    def get_customers_with_overdue_payments():
        """Връща клиенти с просрочени плащания"""
        try:
            # Когато имаме sales app
            # from sales.models import SalesDocument
            # from ..models import Customer

            # overdue_customers = Customer.objects.filter(
            #     sales_documents__is_paid=False,
            #     sales_documents__document_date__lt=timezone.now().date() - timedelta(days=F('payment_delay_days'))
            # ).distinct()

            # return overdue_customers

            # За сега връщаме празен списък
            from ..models import Customer
            return Customer.objects.none()

        except ImportError:
            from ..models import Customer
            return Customer.objects.none()