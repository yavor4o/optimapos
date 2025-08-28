# test.py - Прост тест на PurchaseRequestService

import os
import sys
import django
from django.conf import settings

# Setup Django преди import-ване на модели
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.admin',  # Добавяме admin
            'core',
            'nomenclatures',
            'products',
            'partners',
            'inventory',
            'purchases',
            'pricing',  # Добавяме pricing app
        ],
        SECRET_KEY='test-secret-key',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        AUTH_USER_MODEL='auth.User',  # Използвай стандартния User модел
    )
    django.setup()

from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock


def test_create_request_basic():
    """Най-простия тест - дали сервисът може да се извика"""

    print("🧪 Testing PurchaseRequestService.create_request...")

    # Import-ваме сервиса
    from purchases.services.purchase_request_service import PurchaseRequestService

    # Mock user
    user = Mock()
    user.username = 'testuser'

    # Простички данни
    data = {'notes': 'Test request'}
    lines = [{'product_id': 1, 'quantity': Decimal('10')}]

    # Mock DocumentService - patch-ваме import-а в метода
    with patch('nomenclatures.services.DocumentService') as mock_doc:
        # Mock че DocumentService.create_document() работи
        mock_request = Mock()
        mock_request.document_number = 'REQ-001'
        mock_request.status = 'draft'
        mock_request.lines = Mock()
        mock_request.lines.count.return_value = 1

        mock_doc.create_document.return_value = Mock()
        mock_doc.create_document.return_value.ok = True
        mock_doc.create_document.return_value.data = {'document': mock_request}

        mock_doc.can_edit_document.return_value = Mock()
        mock_doc.can_edit_document.return_value.ok = True

        # Mock Product модела - също patch-ваме правилно
        with patch('products.models.Product') as mock_product:
            # Създай правилен Product mock
            product = Mock()
            product.is_active = True
            product.base_unit = Mock()
            product._state = Mock()  # Django ORM трябва _state
            product._state.db = 'default'
            mock_product.objects.get.return_value = product

            # Mock PurchaseRequestLine.objects.create да не се опитва да създава реален обект
            with patch('purchases.models.PurchaseRequestLine.objects.create') as mock_create:
                created_line = Mock()
                created_line.line_number = 1
                mock_create.return_value = created_line

                # ИЗВИКАЙ СЕРВИСА
                result = PurchaseRequestService.create_request(data, user, lines)

                # ПРОВЕРИ РЕЗУЛТАТА
                print(f"Result OK: {result.ok}")
                print(f"Result message: {result.msg}")

                if result.ok:
                    print("✅ SUCCESS - Service works!")
                    print(f"Document number: {result.data.get('document_number')}")
                    return True
                else:
                    print("❌ FAILED")
                    print(f"Error: {result.msg}")
                    return False


def test_validation_basic():
    """Тест на валидацията"""

    print("\n🧪 Testing validation...")

    from purchases.services.purchase_request_service import PurchaseRequestService

    user = Mock()

    # Невалидни данни - празни редове
    invalid_lines = [
        {'product_id': None, 'quantity': Decimal('10')},  # няма product
        {'product_id': 1, 'quantity': Decimal('-5')}  # отрицателно количество
    ]

    # Mock Product за да не върти база данни
    with patch('products.models.Product') as mock_product:
        # Направи така че Product.objects.get() да не се извиква
        mock_product.DoesNotExist = Exception

        # Тествай валидацията
        result = PurchaseRequestService._validate_request_data_via_services({}, invalid_lines, user)

        print(f"Validation result: {result.ok}")
        if not result.ok:
            print(f"Validation errors: {result.msg}")
            print("✅ VALIDATION WORKS - caught invalid data!")
            return True
        else:
            print("❌ VALIDATION FAILED - should have caught errors!")
            return False


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 TESTING PurchaseRequestService")
    print("=" * 50)

    # Тест 1: Основна функционалност
    test1_ok = test_create_request_basic()

    # Тест 2: Валидация
    test2_ok = test_validation_basic()

    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Basic creation test: {'✅ PASS' if test1_ok else '❌ FAIL'}")
    print(f"Validation test: {'✅ PASS' if test2_ok else '❌ FAIL'}")

    if test1_ok and test2_ok:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("💥 SOME TESTS FAILED!")

    print("=" * 50)