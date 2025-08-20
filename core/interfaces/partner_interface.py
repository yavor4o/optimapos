# core/interfaces/partner_interface.py
"""
Partner Interface Protocol - Универсална абстракция за партньори

ЦЕЛ: Направи BaseDocument независим от конкретни partner типове
ПРОБЛЕМ: BaseDocument има ForeignKey към partners.Supplier → неуниверсален
РЕШЕНИЕ: Protocol който работи с всякакви партньори (Supplier, Customer, Company)

USAGE:
    from core.interfaces import IPartner, validate_partner

    # Type checking
    if isinstance(some_object, IPartner):
        print(some_object.name)

    # Runtime validation
    validate_partner(some_object)
"""

from typing import Protocol, runtime_checkable, Optional, Any, Dict, Tuple
from decimal import Decimal
from abc import ABC, abstractmethod
from django.core.exceptions import ValidationError


@runtime_checkable
class IPartner(Protocol):
    """
    Partner Protocol - Дефинира какво ТРЯБВА да имат всички партньори

    ЗАДЪЛЖИТЕЛНИ ПОЛЕТА:
    - pk: Уникален идентификатор
    - name: Име на партньора
    - code: Кратък код
    - is_active: Активен ли е

    ЗАДЪЛЖИТЕЛНИ КОНТАКТНИ ДАННИ:
    - contact_person: Лице за контакт
    - phone: Телефон
    - email: Имейл
    """

    # Основни полета
    pk: Any  # Django primary key (може да е int, UUID и т.н.)
    name: str
    code: str
    is_active: bool

    # Контактни данни
    contact_person: Optional[str]
    phone: Optional[str]
    email: Optional[str]

    # Django model методи
    def save(self, *args, **kwargs) -> None: ...

    def delete(self, *args, **kwargs) -> None: ...

    def __str__(self) -> str: ...


# =================================================================
# SERVICE INTERFACES (за backward compatibility)
# =================================================================

class ISupplierService(ABC):
    """Interface за supplier operations"""

    @abstractmethod
    def get_supplier_info(self, supplier) -> Dict:
        """Връща информация за доставчик"""
        pass

    @abstractmethod
    def check_credit_limit(self, supplier, amount: Decimal) -> Tuple[bool, str]:
        """Проверява кредитен лимит"""
        pass


class ICustomerService(ABC):
    """Interface за customer operations"""

    @abstractmethod
    def get_customer_info(self, customer) -> Dict:
        """Връща информация за клиент"""
        pass

    @abstractmethod
    def can_make_sale(self, customer, amount: Decimal, site=None) -> Tuple[bool, str]:
        """Проверява дали може да се направи продажба"""
        pass

    @abstractmethod
    def get_customer_discount(self, customer, product=None, site=None) -> Decimal:
        """Връща отстъпка за клиент"""
        pass


def validate_partner(obj: Any) -> None:
    """
    Валидира че обект спазва IPartner Protocol

    Args:
        obj: Обектът за проверка

    Raises:
        ValidationError: Ако обектът не спазва протокола

    Example:
        supplier = Supplier.objects.get(pk=1)
        validate_partner(supplier)  # OK

        invalid_obj = SomeRandomClass()
        validate_partner(invalid_obj)  # ValidationError
    """
    errors = []

    # Проверка за основни полета
    required_fields = ['pk', 'name', 'code', 'is_active']
    for field in required_fields:
        if not hasattr(obj, field):
            errors.append(f"Missing required field: {field}")
        elif getattr(obj, field) is None:
            if field in ['name', 'code']:  # Тези НЕ могат да са None
                errors.append(f"Field {field} cannot be None")

    # Проверка за контактни полета (могат да са None, но трябва да съществуват)
    contact_fields = ['contact_person', 'phone', 'email']
    for field in contact_fields:
        if not hasattr(obj, field):
            errors.append(f"Missing contact field: {field}")

    # Проверка за Django model методи
    django_methods = ['save', 'delete', '__str__']
    for method in django_methods:
        if not hasattr(obj, method) or not callable(getattr(obj, method)):
            errors.append(f"Missing or invalid Django method: {method}")

    if errors:
        raise ValidationError(f"Object does not implement IPartner protocol: {', '.join(errors)}")


def assert_partner(obj: Any, context: str = "") -> None:
    """
    Assert че обект е валиден партньор

    Args:
        obj: Обектът за проверка
        context: Контекст за по-добро error съобщение

    Raises:
        AssertionError: Ако обектът не е валиден партньор

    Example:
        assert_partner(supplier, "BaseDocument.save()")
    """
    try:
        validate_partner(obj)
    except ValidationError as e:
        context_msg = f" in {context}" if context else ""
        raise AssertionError(f"Invalid partner{context_msg}: {e}")


def is_valid_partner(obj: Any) -> bool:
    """
    Проверява дали обект е валиден партньор БЕЗ да хвърля грешка

    Args:
        obj: Обектът за проверка

    Returns:
        bool: True ако е валиден партньор, False иначе

    Example:
        if is_valid_partner(some_object):
            # Можем безопасно да го използваме като партньор
            document.partner = some_object
    """
    try:
        validate_partner(obj)
        return True
    except (ValidationError, AttributeError):
        return False


# =================================================================
# TYPE CHECKING HELPERS
# =================================================================

def get_partner_info(partner: IPartner) -> dict:
    """
    Извлича основна информация от партньор в standardized формат

    Args:
        partner: Обект, който имплементира IPartner

    Returns:
        dict: Стандартизирана информация за партньора

    Example:
        info = get_partner_info(supplier)
        # {'pk': 1, 'name': 'ABC Ltd', 'code': 'ABC', 'active': True, ...}
    """
    assert_partner(partner, "get_partner_info()")

    return {
        'pk': partner.pk,
        'name': partner.name,
        'code': partner.code,
        'is_active': partner.is_active,
        'contact_person': getattr(partner, 'contact_person', None),
        'phone': getattr(partner, 'phone', None),
        'email': getattr(partner, 'email', None),
        'type': partner.__class__.__name__,  # 'Supplier', 'Customer' и т.н.
        'app_label': partner._meta.app_label if hasattr(partner, '_meta') else None
    }


def format_partner_display(partner: IPartner) -> str:
    """
    Форматира партньор за показване в UI

    Args:
        partner: Обект, който имплементира IPartner

    Returns:
        str: Форматиран низ за показване

    Example:
        display = format_partner_display(supplier)
        # "ABC Ltd (ABC) - Active"
    """
    assert_partner(partner, "format_partner_display()")

    base = f"{partner.name} ({partner.code})"
    status = "Active" if partner.is_active else "Inactive"
    return f"{base} - {status}"