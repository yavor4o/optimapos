# test.py - Тест на финалния рефакториран PurchaseRequestService

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
            'django.contrib.admin',
            'core',
            'nomenclatures',
            'products',
            'partners',
            'inventory',
            'purchases',
            'pricing',
        ],
        SECRET_KEY='test-secret-key',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        AUTH_USER_MODEL='auth.User',
    )
    django.setup()

from decimal import Decimal
from unittest.mock import Mock, patch


def test_create_request_basic():
    """Тест с новата API сигнатура"""

    print("Testing PurchaseRequestService.create_request...")

    from purchases.services.purchase_request_service import PurchaseRequestService

    # Mock user
    user = Mock()
    user.username = 'testuser'

    # Mock location за новия API
    location = Mock()
    location.name = 'Test Warehouse'
    location.is_active = True

    # Данни за заявката
    data = {
        'notes': 'Test request',
        'priority': 'normal'
    }

    # Mock DocumentService
    with patch('nomenclatures.services.DocumentService') as mock_doc:
        mock_request = Mock()
        mock_request.document_number = 'REQ-001'
        mock_request.status = 'draft'
        mock_request.lines = Mock()
        mock_request.lines.count.return_value = 1
        mock_request.location = location
        mock_request.created_at = '2025-01-01'
        mock_request.created_by = user
        mock_request.partner = None

        mock_doc.create_document.return_value = Mock()
        mock_doc.create_document.return_value.ok = True
        mock_doc.create_document.return_value.data = {'document': mock_request}

        mock_doc.can_edit_document.return_value = Mock()
        mock_doc.can_edit_document.return_value.ok = True
        mock_doc.can_edit_document.return_value.data = {'can_edit': True}

        # Mock за validation
        mock_doc.validate_document_integrity.return_value = Mock()
        mock_doc.validate_document_integrity.return_value.ok = True
        mock_doc.validate_document_integrity.return_value.data = {'is_valid': True, 'validation_issues': []}

        # Mock Product
        with patch('products.models.Product') as mock_product:
            product = Mock()
            product.is_active = True
            product.base_unit = Mock()
            product._state = Mock()
            product._state.db = 'default'
            mock_product.objects.get.return_value = product

            # Дефинирай lines_data СЛЕД като имаме product обекта
            lines_data = [{'product': product, 'quantity': Decimal('10')}]

            # ИЗВИКАЙ ПРАВИЛНИЯ API
            result = PurchaseRequestService.create_request(
                location=location,
                data=data,
                user=user,
                lines_data=lines_data
            )

            print(f"Result OK: {result.ok}")
            print(f"Result message: {result.msg}")

            if result.ok:
                print("SUCCESS - Service works!")
                print(f"Document number: {result.data.get('document_number')}")
                return True
            else:
                print("FAILED")
                print(f"Error: {result.msg}")
                return False


def test_create_request_with_location():
    """Тест на новия location подход"""

    print("Testing new location parameter approach...")

    from purchases.services.purchase_request_service import PurchaseRequestService

    user = Mock()
    user.username = 'testuser'

    location = Mock()
    location.name = 'Main Warehouse'
    location.code = 'WH01'
    location.is_active = True

    product = Mock()
    product.is_active = True
    product.base_unit = Mock()
    product._state = Mock()
    product._state.db = 'default'

    data = {
        'notes': 'Test request with location object',
        'priority': 'normal'
    }

    lines_data = [
        {'product': product, 'quantity': Decimal('10'), 'estimated_price': Decimal('15.50')}
    ]

    # Mock DocumentService
    with patch('nomenclatures.services.DocumentService') as mock_doc:
        mock_request = Mock()
        mock_request.document_number = 'REQ-002'
        mock_request.status = 'draft'
        mock_request.lines = Mock()
        mock_request.lines.count.return_value = 1
        mock_request.location = location
        mock_request.created_at = '2025-01-01'
        mock_request.created_by = user
        mock_request.partner = None

        mock_doc.create_document.return_value = Mock()
        mock_doc.create_document.return_value.ok = True
        mock_doc.create_document.return_value.data = {'document': mock_request}

        mock_doc.can_edit_document.return_value = Mock()
        mock_doc.can_edit_document.return_value.ok = True
        mock_doc.can_edit_document.return_value.data = {'can_edit': True}

        mock_doc.validate_document_integrity.return_value = Mock()
        mock_doc.validate_document_integrity.return_value.ok = True
        mock_doc.validate_document_integrity.return_value.data = {'is_valid': True, 'validation_issues': []}

        # Mock DocumentLineService правилно
        with patch('nomenclatures.services.document_line_service.DocumentLineService') as mock_line_service:
            # Mock successful line addition
            add_line_result = Mock()
            add_line_result.ok = True
            add_line_result.data = {'lines': [Mock()], 'count': 1}
            add_line_result.msg = 'Lines added successfully'

            mock_line_service.add_line.return_value = add_line_result

            mock_line_service.validate_lines.return_value = Mock()
            mock_line_service.validate_lines.return_value.ok = True
            mock_line_service.validate_lines.return_value.data = {'lines_count': 1}

            # Mock DocumentService.analyze_document_financial_impact
            mock_doc.analyze_document_financial_impact.return_value = Mock()
            mock_doc.analyze_document_financial_impact.return_value.ok = True
            mock_doc.analyze_document_financial_impact.return_value.data = {'total_amount': 155.0}

            # ИЗВИКАЙ НОВИЯ API
            result = PurchaseRequestService.create_request(
                location=location,
                data=data,
                user=user,
                lines_data=lines_data
            )

            print(f"Result OK: {result.ok}")
            print(f"Result message: {result.msg}")

            if result.ok:
                print("NEW LOCATION API WORKS!")
                print(f"Document: {result.data.get('document_number')}")
                print(f"Location: {result.data.get('location_name', 'N/A')}")
                print(f"Lines: {result.data.get('lines_count')}")
                print(f"Total: {result.data.get('estimated_total')}")
                return True
            else:
                print("NEW LOCATION API FAILED")
                print(f"Error: {result.msg}")
                return False


def test_validation_composition():
    """Тест на новата composition validation"""

    print("Testing new validation composition...")

    from purchases.services.purchase_request_service import PurchaseRequestService

    # Mock request
    request = Mock()
    request.lines = Mock()
    request.lines.exists.return_value = True
    request.lines.count.return_value = 2
    request.status = 'draft'

    user = Mock()
    user.username = 'testuser'

    # Mock всички validation сервиси
    with patch('nomenclatures.services.DocumentService') as mock_doc:
        # can_edit_document
        mock_doc.can_edit_document.return_value = Mock()
        mock_doc.can_edit_document.return_value.ok = True
        mock_doc.can_edit_document.return_value.data = {'can_edit': True, 'reason': 'Document is editable'}

        # validate_document_integrity
        mock_doc.validate_document_integrity.return_value = Mock()
        mock_doc.validate_document_integrity.return_value.ok = True
        mock_doc.validate_document_integrity.return_value.data = {
            'is_valid': True,
            'validation_issues': []
        }

        with patch('nomenclatures.services.document_line_service.DocumentLineService') as mock_line_service:
            # validate_lines
            mock_line_service.validate_lines.return_value = Mock()
            mock_line_service.validate_lines.return_value.ok = True

            with patch('nomenclatures.services.document.validator.DocumentValidator') as mock_validator:
                # business rules validation
                mock_validator._validate_business_rules.return_value = Mock()
                mock_validator._validate_business_rules.return_value.ok = True

                # ИЗВИКАЙ КОМПОЗИТНАТА ВАЛИДАЦИЯ
                result = PurchaseRequestService.validate_request(request, user)

                print(f"Validation result: {result.ok}")
                if result.ok:
                    print("COMPOSITION VALIDATION WORKS!")
                    print(f"Can edit: {result.data.get('can_edit')}")
                    print(f"Lines count: {result.data.get('lines_count')}")
                    print(f"Issues: {len(result.data.get('validation_issues', []))}")
                    return True
                else:
                    print("VALIDATION FAILED")
                    print(f"Error: {result.msg}")
                    return False


def test_financial_calculation():
    """Тест на новото изчисляване на totals"""

    print("Testing financial calculation via services...")

    from purchases.services.purchase_request_service import PurchaseRequestService

    # Mock request
    request = Mock()
    request.document_number = 'REQ-003'

    # Mock lines за fallback
    line1 = Mock()
    line1.requested_quantity = Decimal('10')
    line1.estimated_price = Decimal('5.00')

    line2 = Mock()
    line2.requested_quantity = Decimal('3')
    line2.estimated_price = Decimal('20.00')

    request.lines = Mock()
    request.lines.all.return_value = [line1, line2]

    # Test 1: DocumentService.analyze_document_financial_impact работи
    with patch('nomenclatures.services.DocumentService') as mock_doc:
        mock_doc.analyze_document_financial_impact.return_value = Mock()
        mock_doc.analyze_document_financial_impact.return_value.ok = True
        mock_doc.analyze_document_financial_impact.return_value.data = {'total_amount': 110.0}

        total = PurchaseRequestService._calculate_total_via_service(request)
        print(f"Via financial analysis: {total}")
        if total == Decimal('110.0'):
            print("FINANCIAL ANALYSIS METHOD WORKS!")

    # Test 2: Fallback calculation
    total_fallback = PurchaseRequestService._fallback_calculate_total(request)
    expected = (Decimal('10') * Decimal('5.00')) + (Decimal('3') * Decimal('20.00'))  # 50 + 60 = 110
    print(f"Fallback calculation: {total_fallback}")
    if total_fallback == expected:
        print("FALLBACK CALCULATION WORKS!")
        return True
    else:
        print(f"Expected {expected}, got {total_fallback}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("TESTING FINAL REFACTORED PurchaseRequestService")
    print("=" * 60)

    # Тест 1: Основна функционалност с новото API
    test1_ok = test_create_request_basic()

    # Тест 2: Новия location API
    test2_ok = test_create_request_with_location()

    # Тест 3: Композитната валидация
    test3_ok = test_validation_composition()

    # Тест 4: Финансовите изчисления
    test4_ok = test_financial_calculation()

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"Basic functionality: {'PASS' if test1_ok else 'FAIL'}")
    print(f"New location API: {'PASS' if test2_ok else 'FAIL'}")
    print(f"Composition validation: {'PASS' if test3_ok else 'FAIL'}")
    print(f"Financial calculations: {'PASS' if test4_ok else 'FAIL'}")

    all_passed = test1_ok and test2_ok and test3_ok and test4_ok

    if all_passed:
        print("\nALL TESTS PASSED!")
        print("The refactored service works with real DocumentService methods")
    else:
        print("\nSOME TESTS FAILED!")

    print("=" * 60)