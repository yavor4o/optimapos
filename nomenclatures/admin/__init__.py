# nomenclatures/admin/__init__.py - UPDATED
"""
Nomenclatures admin configuration - ГЛАВЕН ФАЙЛ В ПАПКАТА

Импортира и регистрира всички админ класове
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

# =======================
# IMPORT ALL ADMIN CLASSES (Django auto-registers with @admin.register decorators)
# =======================

# Product admins (existing) - ALREADY REGISTERED with @admin.register
from .product import ProductGroupAdmin, BrandAdmin, ProductTypeAdmin

# Financial admins (new) - NEED TO REGISTER
from .financial import CurrencyAdmin, ExchangeRateAdmin, TaxGroupAdmin, PriceGroupAdmin

# Operational admins (existing) - ALREADY REGISTERED
from .operational import UnitOfMeasureAdmin, PaymentTypeAdmin

# Documents admin (new) - NEED TO REGISTER
from .documents import DocumentTypeAdmin

# Workflow admins (new - conditional) - NEED TO REGISTER
from .workflow import ApprovalRuleAdmin, ApprovalLogAdmin

# =======================
# IMPORT MODELS
# =======================

from ..models import (
    # Product
    ProductGroup, Brand, ProductType,

    # Financial
    Currency, ExchangeRate, TaxGroup, PriceGroup,

    # Operational
    UnitOfMeasure, PaymentType,

    # Documents
    DocumentType,
)

# Conditional imports
try:
    from ..models import ApprovalRule, ApprovalLog

    HAS_APPROVAL_MODELS = True
except ImportError:
    HAS_APPROVAL_MODELS = False

try:
    from ..models import NumberingConfiguration

    HAS_NUMBERING = True
except ImportError:
    HAS_NUMBERING = False

# =======================
# REGISTER ALL MODELS
# =======================

# Product related - ОСНОВНИ НОМЕНКЛАТУРИ
admin.site.register(ProductGroup, ProductGroupAdmin)
admin.site.register(Brand, BrandAdmin)
admin.site.register(ProductType, ProductTypeAdmin)

# Financial related - ФИНАНСОВИ НОМЕНКЛАТУРИ
admin.site.register(Currency, CurrencyAdmin)
admin.site.register(ExchangeRate, ExchangeRateAdmin)
admin.site.register(TaxGroup, TaxGroupAdmin)
admin.site.register(PriceGroup, PriceGroupAdmin)

# Operational related - ОПЕРАТИВНИ НОМЕНКЛАТУРИ
admin.site.register(UnitOfMeasure, UnitOfMeasureAdmin)
admin.site.register(PaymentType, PaymentTypeAdmin)

# Documents - ТИПОВЕ ДОКУМЕНТИ
admin.site.register(DocumentType, DocumentTypeAdmin)

# Workflow (conditional) - WORKFLOW СИСТЕМА
if HAS_APPROVAL_MODELS:
    admin.site.register(ApprovalRule, ApprovalRuleAdmin)
    admin.site.register(ApprovalLog, ApprovalLogAdmin)

# Numbering system (conditional) - НОМЕРИРАНЕ
if HAS_NUMBERING:
    try:
        from .numbering import NumberingConfigurationAdmin

        admin.site.register(NumberingConfiguration, NumberingConfigurationAdmin)
    except ImportError:
        # Numbering admin file doesn't exist yet - use default admin
        admin.site.register(NumberingConfiguration)


# =======================
# COMMON ADMIN ACTIONS
# =======================

@admin.action(description=_('Activate selected items'))
def make_active(modeladmin, request, queryset):
    """Mass activate nomenclatures"""
    updated = queryset.update(is_active=True)
    modeladmin.message_user(
        request,
        _('Successfully activated {} items.').format(updated)
    )


@admin.action(description=_('Deactivate selected items'))
def make_inactive(modeladmin, request, queryset):
    """Mass deactivate nomenclatures"""
    # Check for system items
    system_items = queryset.filter(is_system=True).count() if hasattr(queryset.model, 'is_system') else 0

    if system_items > 0:
        modeladmin.message_user(
            request,
            _('Cannot deactivate system items. {} items skipped.').format(system_items),
            level='WARNING'
        )
        queryset = queryset.filter(is_system=False)

    updated = queryset.update(is_active=False)
    modeladmin.message_user(
        request,
        _('Successfully deactivated {} items.').format(updated)
    )


# =======================
# ADMIN SITE CUSTOMIZATION
# =======================

# Customize admin site headers
admin.site.site_header = _('OptimaPOS Administration')
admin.site.site_title = _('OptimaPOS Admin')
admin.site.index_title = _('System Administration')

# =======================
# EXPORTS FOR OTHER APPS
# =======================

__all__ = [
    # Product admins
    'ProductGroupAdmin',
    'BrandAdmin',
    'ProductTypeAdmin',

    # Financial admins
    'CurrencyAdmin',
    'ExchangeRateAdmin',
    'TaxGroupAdmin',
    'PriceGroupAdmin',

    # Operational admins
    'UnitOfMeasureAdmin',
    'PaymentTypeAdmin',

    # Documents admin
    'DocumentTypeAdmin',

    # Actions
    'make_active',
    'make_inactive',
]

# Add conditional exports
if HAS_APPROVAL_MODELS:
    __all__.extend(['ApprovalRuleAdmin', 'ApprovalLogAdmin'])


# =======================
# HEALTH CHECK UTILITIES
# =======================

def get_nomenclatures_health():
    """Check nomenclatures system health"""
    health = {
        'status': 'healthy',
        'issues': [],
        'warnings': []
    }

    try:
        # Check base currency
        base_currencies = Currency.objects.filter(is_base=True).count()
        if base_currencies == 0:
            health['issues'].append(_('No base currency configured'))
            health['status'] = 'error'
        elif base_currencies > 1:
            health['issues'].append(_('Multiple base currencies found'))
            health['status'] = 'error'

        # Check default tax group
        if not TaxGroup.objects.filter(is_default=True).exists():
            health['warnings'].append(_('No default tax group configured'))
            if health['status'] == 'healthy':
                health['status'] = 'warning'

        # Check units
        if not UnitOfMeasure.active.exists():
            health['issues'].append(_('No active units of measure'))
            health['status'] = 'error'

    except Exception as e:
        health['issues'].append(f'Health check error: {str(e)}')
        health['status'] = 'error'

    return health


def get_nomenclatures_stats():
    """Get nomenclatures statistics"""
    try:
        return {
            'product': {
                'brands': Brand.active.count(),
                'groups': ProductGroup.active.count(),
                'types': ProductType.active.count(),
            },
            'financial': {
                'currencies': Currency.active.count(),
                'tax_groups': TaxGroup.active.count(),
                'price_groups': PriceGroup.active.count(),
            },
            'operational': {
                'units': UnitOfMeasure.active.count(),
                'payment_types': PaymentType.active.count(),
            },
            'documents': {
                'document_types': DocumentType.active.count(),
            }
        }
    except Exception as e:
        return {'error': str(e)}