# purchases/managers/line_manager.py

from django.db import models
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q, F, Case, When
from decimal import Decimal
from datetime import timedelta, date
from typing import Optional, List


class PurchaseLineQuerySet(models.QuerySet):
    """Специализиран QuerySet за PurchaseDocumentLine"""

    def for_product(self, product):
        """Редове за определен продукт"""
        return self.filter(product=product)

    def for_products(self, product_list):
        """Редове за списък от продукти"""
        return self.filter(product__in=product_list)

    def for_supplier(self, supplier):
        """Редове от документи на определен supplier"""
        return self.filter(document__supplier=supplier)

    def for_location(self, location):
        """Редове от документи за определена локация"""
        return self.filter(document__location=location)

    def received_only(self):
        """Само редове от получени документи"""
        return self.filter(document__status='received')

    def with_discount(self):
        """Редове с отстъпки"""
        return self.filter(discount_percent__gt=0)

    def high_discount(self, threshold: Decimal = Decimal('10.0')):
        """Редове с големи отстъпки"""
        return self.filter(discount_percent__gte=threshold)

    def quality_issues(self):
        """Редове с проблеми в качеството"""
        return self.filter(quality_approved=False)

    def quality_approved(self):
        """Одобрени по качество редове"""
        return self.filter(quality_approved=True)

    def with_batch(self):
        """Редове с batch номера"""
        return self.filter(batch_number__isnull=False).exclude(batch_number='')

    def expiring_soon(self, days: int = 30):
        """Редове с продукти които изтичат скоро"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return self.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )

    def expired(self):
        """Вече изтекли продукти"""
        today = timezone.now().date()
        return self.filter(expiry_date__lt=today)

    def good_expiry(self, min_days: int = 30):
        """Продукти с добър срок на годност"""
        cutoff_date = timezone.now().date() + timedelta(days=min_days)
        return self.filter(
            Q(expiry_date__gt=cutoff_date) | Q(expiry_date__isnull=True)
        )

    def over_received(self):
        """Редове където е получено повече от поръчаното"""
        return self.filter(received_quantity__gt=F('quantity'))

    def under_received(self):
        """Редове където е получено по-малко от поръчаното"""
        return self.filter(received_quantity__lt=F('quantity'))

    def fully_received(self):
        """Напълно получени редове"""
        return self.filter(received_quantity__gte=F('quantity'))

    def with_pricing_suggestions(self):
        """Редове с предложения за цени"""
        return self.filter(
            new_sale_price__isnull=False,
            markup_percentage__isnull=False
        )

    def high_markup(self, threshold: Decimal = Decimal('50.0')):
        """Редове с висок markup"""
        return self.filter(markup_percentage__gte=threshold)

    def low_markup(self, threshold: Decimal = Decimal('20.0')):
        """Редове с нисък markup"""
        return self.filter(
            markup_percentage__lte=threshold,
            markup_percentage__isnull=False
        )

    def large_quantities(self, threshold: Decimal = Decimal('100.0')):
        """Редове с големи количества"""
        return self.filter(quantity__gte=threshold)

    def high_value(self, threshold: Decimal = Decimal('500.0')):
        """Редове с висока стойност"""
        return self.filter(line_total__gte=threshold)

    def in_date_range(self, date_from: Optional[date] = None, date_to: Optional[date] = None):
        """Редове в определен период"""
        queryset = self
        if date_from:
            queryset = queryset.filter(document__document_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(document__document_date__lte=date_to)
        return queryset

    def search_product(self, query: str):
        """Търси продукти по код/име"""
        return self.filter(
            Q(product__code__icontains=query) |
            Q(product__name__icontains=query)
        )

    def with_analysis(self):
        """Добавя анализни полета"""
        return self.annotate(
            # Variance analysis
            quantity_variance=F('received_quantity') - F('quantity'),
            quantity_variance_percent=Case(
                When(quantity=0, then=0),
                default=(F('received_quantity') - F('quantity')) * 100 / F('quantity'),
                output_field=models.DecimalField(max_digits=10, decimal_places=2)
            ),

            # Value analysis
            variance_value=F('quantity_variance') * F('final_unit_price'),

            # Cost analysis
            cost_per_base_unit=F('unit_price_base'),
            total_cost_base=F('received_quantity') * F('unit_price_base'),

            # Expiry analysis
            days_to_expiry=Case(
                When(expiry_date__isnull=True, then=None),
                default=F('expiry_date') - timezone.now().date(),
                output_field=models.IntegerField()
            ),

            # Status flags
            is_over_received=Case(
                When(received_quantity__gt=F('quantity'), then=True),
                default=False,
                output_field=models.BooleanField()
            ),

            is_under_received=Case(
                When(received_quantity__lt=F('quantity'), then=True),
                default=False,
                output_field=models.BooleanField()
            ),

            is_expired=Case(
                When(expiry_date__lt=timezone.now().date(), then=True),
                default=False,
                output_field=models.BooleanField()
            ),

            is_expiring_soon=Case(
                When(
                    expiry_date__lte=timezone.now().date() + timedelta(days=30),
                    expiry_date__isnull=False,
                    then=True
                ),
                default=False,
                output_field=models.BooleanField()
            )
        )

    def cost_analysis_by_product(self):
        """Анализ на себестойности по продукт"""
        return self.values('product', 'product__code', 'product__name').annotate(
            total_quantity=Sum('received_quantity'),
            total_value=Sum('line_total'),
            avg_cost=Avg('unit_price_base'),
            min_cost=models.Min('unit_price_base'),
            max_cost=models.Max('unit_price_base'),
            cost_variance=models.Max('unit_price_base') - models.Min('unit_price_base'),
            purchase_count=Count('id'),
            latest_purchase=models.Max('document__delivery_date'),
            avg_discount=Avg('discount_percent')
        ).order_by('-total_value')

    def supplier_performance(self):
        """Анализ на performance по supplier"""
        return self.values(
            'document__supplier',
            'document__supplier__name'
        ).annotate(
            total_lines=Count('id'),
            total_quantity=Sum('received_quantity'),
            total_value=Sum('line_total'),
            avg_line_value=Avg('line_total'),
            quality_issues=Count('id', filter=Q(quality_approved=False)),
            quality_rate=Case(
                When(total_lines=0, then=0),
                default=(Count('id', filter=Q(quality_approved=True)) * 100.0) / Count('id'),
                output_field=models.DecimalField(max_digits=5, decimal_places=2)
            ),
            avg_discount=Avg('discount_percent'),
            over_deliveries=Count('id', filter=Q(received_quantity__gt=F('quantity'))),
            under_deliveries=Count('id', filter=Q(received_quantity__lt=F('quantity')))
        ).order_by('-total_value')

    def expiry_report(self):
        """Отчет за срокове на годност"""
        today = timezone.now().date()

        return self.filter(
            expiry_date__isnull=False,
            document__status='received'
        ).annotate(
            days_to_expiry=(F('expiry_date') - today)
        ).values(
            'product__code',
            'product__name',
            'batch_number',
            'expiry_date',
            'days_to_expiry',
            'received_quantity',
            'document__location__name'
        ).order_by('expiry_date')

    def pricing_opportunities(self):
        """Възможности за ценообразуване"""
        return self.filter(
            new_sale_price__isnull=False,
            markup_percentage__isnull=False
        ).values(
            'product__code',
            'product__name',
            'old_sale_price',
            'new_sale_price',
            'markup_percentage',
            'unit_price_base'
        ).annotate(
            price_increase=F('new_sale_price') - F('old_sale_price'),
            price_increase_percent=Case(
                When(old_sale_price=0, then=0),
                default=(F('new_sale_price') - F('old_sale_price')) * 100 / F('old_sale_price'),
                output_field=models.DecimalField(max_digits=10, decimal_places=2)
            )
        ).order_by('-price_increase_percent')


class PurchaseLineManager(models.Manager):
    """Manager за PurchaseDocumentLine"""

    def get_queryset(self):
        return PurchaseLineQuerySet(self.model, using=self._db)

    def for_product(self, product):
        return self.get_queryset().for_product(product)

    def for_supplier(self, supplier):
        return self.get_queryset().for_supplier(supplier)

    def for_location(self, location):
        return self.get_queryset().for_location(location)

    def received_only(self):
        return self.get_queryset().received_only()

    def with_discount(self):
        return self.get_queryset().with_discount()

    def quality_issues(self):
        return self.get_queryset().quality_issues()

    def expiring_soon(self, days: int = 30):
        return self.get_queryset().expiring_soon(days)

    def with_pricing_suggestions(self):
        return self.get_queryset().with_pricing_suggestions()

    def search_product(self, query: str):
        return self.get_queryset().search_product(query)

    def get_product_cost_history(self, product, days: int = 90):
        """История на себестойностите за продукт"""
        date_from = timezone.now().date() - timedelta(days=days)

        return self.get_queryset().for_product(product).received_only().filter(
            document__delivery_date__gte=date_from
        ).order_by('document__delivery_date').values(
            'document__delivery_date',
            'document__supplier__name',
            'unit_price_base',
            'received_quantity',
            'discount_percent'
        )

    def get_expiry_alerts(self, days_ahead: int = 7):
        """Алерти за изтичащи продукти"""
        return self.get_queryset().expiring_soon(days_ahead).values(
            'product__code',
            'product__name',
            'batch_number',
            'expiry_date',
            'received_quantity',
            'document__location__name',
            'document__supplier__name'
        ).annotate(
            days_to_expiry=F('expiry_date') - timezone.now().date()
        ).order_by('expiry_date')

    def get_reorder_suggestions(self, location=None):
        """Предложения за нови поръчки базирани на история"""
        # Основна логика - ще се разшири
        queryset = self.get_queryset().received_only()

        if location:
            queryset = queryset.for_location(location)

        # Продукти които не са поръчвани в последните 30 дни
        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        return queryset.filter(
            document__delivery_date__gte=thirty_days_ago
        ).values('product').annotate(
            avg_monthly_quantity=Avg('received_quantity'),
            last_purchase=models.Max('document__delivery_date'),
            last_cost=models.Max('unit_price_base'),
            supplier_count=Count('document__supplier', distinct=True)
        ).order_by('-avg_monthly_quantity')