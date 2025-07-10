from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models import Count, Sum, Q
from django.utils.safestring import mark_safe

from ..models import (
    Supplier, SupplierDivision, SupplierDaySchedule, Weekday
)


# === INLINE ADMINS ===

class SupplierDivisionInline(admin.TabularInline):
    """Inline за дивизии на доставчик"""
    model = SupplierDivision
    extra = 1
    fields = [
        'name', 'code', 'contact_person', 'phone',
        'payment_days', 'is_active'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('name')


class SupplierDayScheduleInline(admin.TabularInline):
    """Подобрен inline за график на доставчик"""
    model = SupplierDaySchedule
    extra = 0
    max_num = 7
    can_delete = False

    fields = [
        'get_day_display_custom', 'expects_order', 'order_deadline_time',
        'makes_delivery', 'delivery_time_from', 'delivery_time_to'
    ]
    readonly_fields = ('get_day_display_custom',)

    def get_day_display_custom(self, obj):
        if obj.day:
            return obj.get_day_display()
        return '-'

    get_day_display_custom.short_description = _('Day')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Подреждаме дните в правилен ред
        day_order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        return qs.extra(
            select={
                'day_order': f"CASE day {' '.join([f'WHEN %s THEN {i}' for i in range(7)])} END"
            },
            select_params=day_order
        ).order_by('day_order')

    def has_add_permission(self, request, obj=None):
        return False  # Автоматично се създават


# === CUSTOM FILTERS ===

class SupplierCreditLimitFilter(admin.SimpleListFilter):
    title = _('Credit Limit')
    parameter_name = 'credit_range'

    def lookups(self, request, model_admin):
        return (
            ('0', _('No credit')),
            ('1-1000', _('1-1000 BGN')),
            ('1001-5000', _('1001-5000 BGN')),
            ('5001+', _('Over 5000 BGN')),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(credit_limit=0)
        elif self.value() == '1-1000':
            return queryset.filter(credit_limit__gt=0, credit_limit__lte=1000)
        elif self.value() == '1001-5000':
            return queryset.filter(credit_limit__gt=1000, credit_limit__lte=5000)
        elif self.value() == '5001+':
            return queryset.filter(credit_limit__gt=5000)
        return queryset


class SupplierDeliveryDayFilter(admin.SimpleListFilter):
    title = _('Delivers Today')
    parameter_name = 'delivers_today'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Delivers today')),
            ('no', _('No delivery today')),
        )

    def queryset(self, request, queryset):
        from django.utils import timezone
        today = timezone.now().strftime('%a').lower()[:3]

        if self.value() == 'yes':
            return queryset.filter(
                day_schedules__day=today,
                day_schedules__makes_delivery=True
            ).distinct()
        elif self.value() == 'no':
            return queryset.exclude(
                day_schedules__day=today,
                day_schedules__makes_delivery=True
            ).distinct()
        return queryset


# === MAIN SUPPLIER ADMIN ===

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'contact_person', 'phone', 'email',
        'divisions_count', 'delivery_status', 'financial_info',
        'schedule_summary', 'is_active'
    ]

    list_filter = [
        'is_active', 'is_internal', 'vat_registered',
        'delivery_blocked', 'city',
        SupplierCreditLimitFilter,
        SupplierDeliveryDayFilter
    ]

    search_fields = [
        'name', 'contact_person', 'email', 'phone', 'vat_number',
        'divisions__name'
    ]

    list_editable = ['is_active']

    readonly_fields = [
        'created_at', 'updated_at', 'financial_summary',
        'delivery_statistics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'is_active', 'is_internal')
        }),
        (_('Tax Information'), {
            'fields': ('vat_number', 'vat_registered'),
        }),
        (_('Contact Information'), {
            'fields': ('contact_person', 'email', 'phone', 'city', 'address')
        }),
        (_('Banking Details'), {
            'fields': ('bank', 'bank_account'),
            'classes': ('collapse',)
        }),
        (_('Business Terms'), {
            'fields': ('division', 'payment_days', 'credit_limit'),
        }),
        (_('Restrictions'), {
            'fields': ('delivery_blocked',),
        }),
        (_('Financial Summary'), {
            'fields': ('financial_summary',),
            'classes': ('collapse',),
            'description': 'Automatically calculated financial data'
        }),
        (_('Delivery Statistics'), {
            'fields': ('delivery_statistics',),
            'classes': ('collapse',),
        }),
        (_('Additional Information'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [SupplierDivisionInline, SupplierDayScheduleInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            divisions_count_ann=Count('divisions', distinct=True),
        ).prefetch_related('divisions', 'day_schedules')

    def divisions_count(self, obj):
        """Брой дивизии"""
        count = getattr(obj, 'divisions_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: green;">{} divisions</span>',
                count
            )
        return format_html('<span style="color: gray;">No divisions</span>')

    divisions_count.short_description = _('Divisions')
    divisions_count.admin_order_field = 'divisions_count_ann'

    def delivery_status(self, obj):
        """Статус на доставки"""
        if obj.delivery_blocked:
            return format_html(
                '<span style="color: red;">🚫 Blocked</span>'
            )
        elif obj.can_deliver():
            return format_html(
                '<span style="color: green;">✅ Active</span>'
            )
        else:
            return format_html(
                '<span style="color: orange;">⚠️ Issues</span>'
            )

    delivery_status.short_description = _('Delivery Status')

    def financial_info(self, obj):
        """Финансова информация"""
        parts = []

        if obj.credit_limit > 0:
            parts.append(f"Credit: {obj.credit_limit:.0f} лв")

        if obj.payment_days > 0:
            parts.append(f"Terms: {obj.payment_days}d")

        if parts:
            return format_html(
                '<small>{}</small>',
                ' | '.join(parts)
            )
        return '-'

    financial_info.short_description = _('Financial')

    def schedule_summary(self, obj):
        """Обобщение на графика - подобрено"""
        schedules = obj.day_schedules.all()
        order_days = [s.get_day_display()[:3] for s in schedules if s.expects_order]
        delivery_days = [s.get_day_display()[:3] for s in schedules if s.makes_delivery]

        html_parts = []
        if order_days:
            html_parts.append(
                f"<span style='color: #28a745;'>📝 {', '.join(order_days)}</span>"
            )
        if delivery_days:
            html_parts.append(
                f"<span style='color: #007bff;'>🚚 {', '.join(delivery_days)}</span>"
            )

        return format_html('<br>'.join(html_parts)) if html_parts else "-"

    schedule_summary.short_description = _('Schedule')

    def financial_summary(self, obj):
        """Детайлна финансова информация"""
        if not obj.pk:
            return "Save supplier first to see financial data"

        # TODO: Когато имаме purchases app интеграция
        try:
            # from purchases.models import PurchaseDocument
            #
            # total_orders = PurchaseDocument.objects.filter(
            #     supplier=obj
            # ).aggregate(
            #     total=Sum('grand_total'),
            #     count=Count('id')
            # )

            summary_parts = [
                f"<strong>Credit Limit:</strong> {obj.credit_limit:.2f} лв",
                f"<strong>Payment Terms:</strong> {obj.payment_days} days",
                # f"<strong>Total Orders:</strong> {total_orders['count'] or 0}",
                # f"<strong>Total Value:</strong> {total_orders['total'] or 0:.2f} лв"
            ]

            return mark_safe('<br>'.join(summary_parts))
        except:
            return "Financial data will be available when purchases module is connected"

    financial_summary.short_description = _('Financial Summary')

    def delivery_statistics(self, obj):
        """Статистика по доставки"""
        if not obj.pk:
            return "Save supplier first to see statistics"

        schedules = obj.day_schedules.all()
        stats = {
            'order_days': schedules.filter(expects_order=True).count(),
            'delivery_days': schedules.filter(makes_delivery=True).count(),
            'active_divisions': obj.divisions.filter(is_active=True).count(),
        }

        stats_parts = [
            f"<strong>Order Days:</strong> {stats['order_days']}/7",
            f"<strong>Delivery Days:</strong> {stats['delivery_days']}/7",
            f"<strong>Active Divisions:</strong> {stats['active_divisions']}",
        ]

        return mark_safe('<br>'.join(stats_parts))

    delivery_statistics.short_description = _('Delivery Statistics')

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)

        # Автоматично създаване на графици за всички дни при нов доставчик
        if is_new:
            for day in Weekday.values:
                SupplierDaySchedule.objects.get_or_create(
                    supplier=obj,
                    day=day,
                    defaults={
                        'expects_order': False,
                        'makes_delivery': False
                    }
                )

    def get_inline_instances(self, request, obj=None):
        # Показваме inline формите само ако обектът вече съществува
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        # След създаване, пренасочваме към редактиране за да се покажат графиците
        return self.response_post_save_add(request, obj)


# === SUPPLIER DIVISION ADMIN ===

@admin.register(SupplierDivision)
class SupplierDivisionAdmin(admin.ModelAdmin):
    list_display = [
        'supplier', 'name', 'code', 'contact_person',
        'phone', 'payment_terms', 'is_active'
    ]

    list_filter = ['is_active', 'supplier']
    search_fields = ['name', 'code', 'supplier__name', 'contact_person']
    list_editable = ['is_active']

    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'name', 'code', 'description', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'phone', 'email'),
            'classes': ('collapse',)
        }),
        ('Business Terms', {
            'fields': ('payment_days',),
            'description': 'Leave empty to use supplier default payment terms'
        })
    )

    def payment_terms(self, obj):
        """Показва ефективните платежни условия"""
        effective_days = obj.get_effective_payment_days()
        if obj.payment_days:
            return f"{effective_days} days (override)"
        else:
            return f"{effective_days} days (from supplier)"

    payment_terms.short_description = _('Payment Terms')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('supplier')