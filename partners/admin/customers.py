# partners/admin/customers.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils.safestring import mark_safe

from ..models import (
    Customer, CustomerSite, CustomerDaySchedule, Weekday
)


# === INLINE ADMINS ===

class CustomerSiteInline(admin.TabularInline):
    """Inline за обекти на клиент"""
    model = CustomerSite
    extra = 1
    fields = [
        'name', 'city', 'contact_person', 'phone',
        'is_delivery_address', 'is_billing_address',
        'is_primary', 'is_active'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-is_primary', 'name')


class CustomerDayScheduleInline(admin.TabularInline):
    """Inline за график на клиент"""
    model = CustomerDaySchedule
    extra = 0
    max_num = 7
    can_delete = False

    fields = [
        'get_day_display_custom', 'expects_order', 'expects_delivery',
        'preferred_delivery_time_from', 'preferred_delivery_time_to'
    ]
    readonly_fields = ('get_day_display_custom',)

    def get_day_display_custom(self, obj):
        if obj.day:
            return obj.get_day_display()
        return '-'

    get_day_display_custom.short_description = _('Day')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        day_order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        return qs.extra(
            select={
                'day_order': f"CASE day {' '.join([f'WHEN %s THEN {i}' for i in range(7)])} END"
            },
            select_params=day_order
        ).order_by('day_order')

    def has_add_permission(self, request, obj=None):
        return False


# === CUSTOM FILTERS ===

class CustomerCreditLimitFilter(admin.SimpleListFilter):
    title = _('Credit Limit')
    parameter_name = 'credit_limit_range'

    def lookups(self, request, model_admin):
        return (
            ('0', _('No credit')),
            ('1-500', _('1-500 BGN')),
            ('501-2000', _('501-2000 BGN')),
            ('2001+', _('Over 2000 BGN')),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(credit_limit=0)
        elif self.value() == '1-500':
            return queryset.filter(credit_limit__gt=0, credit_limit__lte=500)
        elif self.value() == '501-2000':
            return queryset.filter(credit_limit__gt=500, credit_limit__lte=2000)
        elif self.value() == '2001+':
            return queryset.filter(credit_limit__gt=2000)
        return queryset


class CustomerCategoryFilter(admin.SimpleListFilter):
    title = _('Category')
    parameter_name = 'category'

    def lookups(self, request, model_admin):
        return Customer.CATEGORY_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(category=self.value())
        return queryset


# === MAIN CUSTOMER ADMIN ===

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'type_display', 'contact_person', 'phone', 'email',
        'category_badge', 'credit_info', 'pricing_info',
        'sites_count', 'restrictions_display', 'is_active'
    ]

    list_filter = [
        'is_active', 'type', 'category', 'vat_registered',
        'sales_blocked', 'credit_blocked', 'city',
        CustomerCreditLimitFilter,
        CustomerCategoryFilter
    ]

    search_fields = [
        'name', 'contact_person', 'email', 'phone', 'vat_number',
        'sites__name'
    ]

    list_editable = ['is_active']

    readonly_fields = [
        'created_at', 'updated_at', 'customer_summary',
        'sales_statistics'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('type', 'name', 'category', 'is_active')
        }),
        (_('Tax Information'), {
            'fields': ('vat_number', 'vat_registered'),
        }),
        (_('Contact Information'), {
            'fields': ('contact_person', 'email', 'phone', 'city', 'address')
        }),
        (_('Financial Settings'), {
            'fields': (
                'credit_limit', 'payment_delay_days',
                'price_group', 'discount_percent',
            ),
            'description': 'Credit and pricing settings'
        }),
        (_('Restrictions'), {
            'fields': ('sales_blocked', 'credit_blocked'),
        }),
        (_('Customer Summary'), {
            'fields': ('customer_summary',),
            'classes': ('collapse',),
            'description': 'Automatically calculated customer data'
        }),
        (_('Sales Statistics'), {
            'fields': ('sales_statistics',),
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

    inlines = [CustomerSiteInline, CustomerDayScheduleInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            sites_count_ann=Count('sites', distinct=True),
        ).select_related('price_group').prefetch_related('sites', 'day_schedules')

    def type_display(self, obj):
        """Тип клиент с икона"""
        if obj.type == Customer.COMPANY:
            return format_html('<span title="Company">🏢</span>')
        else:
            return format_html('<span title="Individual">👤</span>')

    type_display.short_description = _('Type')

    def category_badge(self, obj):
        """Категория с цветен badge"""
        colors = {
            'regular': '#6c757d',
            'vip': '#28a745',
            'problematic': '#dc3545',
        }
        color = colors.get(obj.category, '#6c757d')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_category_display().upper()
        )

    category_badge.short_description = _('Category')

    def credit_info(self, obj):
        """Кредитна информация"""
        parts = []

        if obj.credit_limit > 0:
            parts.append(f"Limit: {obj.credit_limit:.0f} лв")

        if obj.payment_delay_days > 0:
            parts.append(f"Delay: {obj.payment_delay_days}d")

        if parts:
            color = 'green' if obj.can_buy_on_credit() else 'red'
            return format_html(
                '<small style="color: {};">{}</small>',
                color,
                ' | '.join(parts)
            )
        return '-'

    credit_info.short_description = _('Credit')

    def pricing_info(self, obj):
        """Ценова информация"""
        if obj.price_group:
            return format_html(
                '<span style="color: blue;">Group: {}</span>',
                obj.price_group.name
            )
        elif obj.discount_percent:
            return format_html(
                '<span style="color: orange;">Discount: {}%</span>',
                obj.discount_percent
            )
        return '-'

    pricing_info.short_description = _('Pricing')

    def sites_count(self, obj):
        """Брой обекти"""
        count = getattr(obj, 'sites_count_ann', 0)
        if count > 0:
            return format_html(
                '<span style="color: green;">{} sites</span>',
                count
            )
        return format_html('<span style="color: gray;">No sites</span>')

    sites_count.short_description = _('Sites')
    sites_count.admin_order_field = 'sites_count_ann'

    def restrictions_display(self, obj):
        """Показва ограничения"""
        restrictions = []

        if obj.sales_blocked:
            restrictions.append('🚫 Sales')
        if obj.credit_blocked:
            restrictions.append('💳 Credit')

        if restrictions:
            return format_html(
                '<span style="color: red;">{}</span>',
                ' '.join(restrictions)
            )
        return format_html('<span style="color: green;">✅ OK</span>')

    restrictions_display.short_description = _('Restrictions')

    def customer_summary(self, obj):
        """Обобщение за клиента"""
        if not obj.pk:
            return "Save customer first to see summary"

        summary_parts = [
            f"<strong>Type:</strong> {obj.get_type_display()}",
            f"<strong>Category:</strong> {obj.get_category_display()}",
            f"<strong>Credit Limit:</strong> {obj.credit_limit:.2f} лв",
            f"<strong>Payment Delay:</strong> {obj.payment_delay_days} days",
            f"<strong>Effective Discount:</strong> {obj.get_effective_discount():.2f}%",
            f"<strong>Can Buy:</strong> {'Yes' if obj.can_buy() else 'No'}",
            f"<strong>Can Buy on Credit:</strong> {'Yes' if obj.can_buy_on_credit() else 'No'}",
        ]

        return mark_safe('<br>'.join(summary_parts))

    customer_summary.short_description = _('Customer Summary')

    def sales_statistics(self, obj):
        """Статистика по продажби"""
        if not obj.pk:
            return "Save customer first to see statistics"

        # TODO: Когато имаме sales app
        try:
            schedules = obj.day_schedules.all()
            stats = {
                'order_days': schedules.filter(expects_order=True).count(),
                'delivery_days': schedules.filter(expects_delivery=True).count(),
                'active_sites': obj.sites.filter(is_active=True).count(),
            }

            stats_parts = [
                f"<strong>Order Days:</strong> {stats['order_days']}/7",
                f"<strong>Delivery Days:</strong> {stats['delivery_days']}/7",
                f"<strong>Active Sites:</strong> {stats['active_sites']}",
            ]

            return mark_safe('<br>'.join(stats_parts))
        except:
            return "Statistics will be available when sales module is connected"

    sales_statistics.short_description = _('Sales Statistics')

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)

        # Автоматично създаване на графици за всички дни при нов клиент
        if is_new:
            for day in Weekday.values:
                CustomerDaySchedule.objects.get_or_create(
                    customer=obj,
                    day=day,
                    defaults={
                        'expects_order': False,
                        'expects_delivery': False
                    }
                )

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        return self.response_post_save_add(request, obj)


# === CUSTOMER SITE ADMIN ===

@admin.register(CustomerSite)
class CustomerSiteAdmin(admin.ModelAdmin):
    list_display = [
        'customer', 'name', 'city', 'contact_person',
        'address_types', 'special_discount', 'is_active'
    ]

    list_filter = [
        'is_active', 'is_primary', 'is_delivery_address',
        'is_billing_address', 'customer__type'
    ]

    search_fields = [
        'name', 'customer__name', 'city', 'contact_person'
    ]

    list_editable = ['is_active']

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'name', 'is_active', 'is_primary')
        }),
        ('Address Information', {
            'fields': ('city', 'address')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'phone', 'email'),
            'classes': ('collapse',)
        }),
        ('Site Settings', {
            'fields': (
                'is_delivery_address', 'is_billing_address',
                'special_discount'
            )
        })
    )

    def address_types(self, obj):
        """Типове адреси"""
        types = []
        if obj.is_primary:
            types.append('🏠 Primary')
        if obj.is_delivery_address:
            types.append('📦 Delivery')
        if obj.is_billing_address:
            types.append('📄 Billing')

        return ' '.join(types) if types else '-'

    address_types.short_description = _('Address Types')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('customer')