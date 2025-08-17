# core/context_processors.py
from django.urls import resolve
from django.utils.translation import gettext_lazy as _


def navigation_context(request):
    """
    Context processor за навигацията - определя активните менюта и breadcrumbs
    """

    # Вземи текущия URL name и namespace
    current_url_name = None
    current_namespace = None
    current_path = request.path

    try:
        resolved = resolve(request.path)
        current_url_name = resolved.url_name
        current_namespace = resolved.namespace
    except:
        pass

    # Построй navigation state
    nav_state = {
        'current_url_name': current_url_name,
        'current_namespace': current_namespace,
        'current_path': current_path,
    }

    # Определи активните секции
    active_sections = {
        'dashboard': current_namespace == 'dashboard' or current_path.startswith('/dashboard/'),
        'nomenclatures': current_namespace == 'nomenclatures' or current_path.startswith('/nomenclatures/'),
        'pos_operations': current_namespace == 'pos' or current_path.startswith('/pos/'),
        'products': current_namespace == 'products' or current_path.startswith('/products/'),
        'inventory': current_namespace == 'inventory' or current_path.startswith('/inventory/'),
        'procurement': current_namespace == 'purchases' or current_path.startswith('/purchases/'),
    }

    # Определи активните sub-менюта за номенклатури
    nomenclature_active = {
        'product_classifications': (
                current_url_name in ['brands', 'product_types', 'product_groups'] or
                current_path.startswith('/nomenclatures/brands/') or
                current_path.startswith('/nomenclatures/product-types/') or
                current_path.startswith('/nomenclatures/product-groups/')
        ),
        'financial_settings': (
                current_url_name in ['currencies', 'tax_groups', 'price_groups'] or
                current_path.startswith('/nomenclatures/currencies/') or
                current_path.startswith('/nomenclatures/tax-groups/') or
                current_path.startswith('/nomenclatures/price-groups/')
        ),
        'brands': current_url_name == 'brands' or current_path.startswith('/nomenclatures/brands/'),
        'product_types': current_url_name == 'product_types' or current_path.startswith(
            '/nomenclatures/product-types/'),
        'product_groups': current_url_name == 'product_groups' or current_path.startswith(
            '/nomenclatures/product-groups/'),
        'currencies': current_path.startswith('/nomenclatures/currencies/'),
        'tax_groups': current_path.startswith('/nomenclatures/tax-groups/'),
        'price_groups': current_path.startswith('/nomenclatures/price-groups/'),
        'document_types': current_path.startswith('/nomenclatures/document-types/'),
        'workflow_settings': current_path.startswith('/nomenclatures/workflow-settings/'),
    }

    # Breadcrumbs логика
    breadcrumbs = []

    if current_namespace == 'nomenclatures':
        breadcrumbs.append({
            'title': _('System Configuration'),
            'url': None,
            'active': False
        })
        breadcrumbs.append({
            'title': _('Nomenclatures'),
            'url': None,  # Може да добавиш index URL ако имаш
            'active': False
        })

        # Специфични breadcrumbs за номенклатури
        if current_url_name == 'brands':
            breadcrumbs.append({
                'title': _('Brands'),
                'url': None,
                'active': True
            })
        elif current_url_name == 'product_types':
            breadcrumbs.append({
                'title': _('Product Types'),
                'url': None,
                'active': True
            })
        elif current_url_name == 'product_groups':
            breadcrumbs.append({
                'title': _('Product Groups'),
                'url': None,
                'active': True
            })

    return {
        'nav_state': nav_state,
        'active_sections': active_sections,
        'nomenclature_active': nomenclature_active,
        'breadcrumbs': breadcrumbs,
    }