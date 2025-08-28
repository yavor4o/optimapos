# purchases/services/purchase_request_service.py - ФИНАЛНО РЕФАКТОРИРАН

from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.contrib.auth import get_user_model
from core.utils.result import Result
from ..models import PurchaseRequest
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PurchaseRequestService:
    """
    Финално рефакториран сервис за PurchaseRequest операции

    ПРИНЦИПИ:
    - Използва САМО сервиси от други апове
    - НЕ търси полета директно от модели
    - location като обект, не като content_type данни
    - Редовете се управляват през DocumentLineService
    - Пълна service-based архитектура
    """

    @staticmethod
    @transaction.atomic
    def create_request(location, data: Dict[str, Any], user: User, lines_data: List[Dict] = None) -> Result:
        """
        Създава нова заявка за покупки

        Args:
            location: InventoryLocation обект (професионален подход)
            data: Dict с document данни (notes, priority, etc.)
            user: User обект
            lines_data: List[Dict] с данни за редовете

        Returns:
            Result с създадената заявка
        """
        try:
            # Валидация на входните данни САМО през сервиси
            validation_result = PurchaseRequestService._validate_request_data_via_services(
                location, data, lines_data, user
            )
            if not validation_result.ok:
                return validation_result

            # Създай документа чрез DocumentService
            from nomenclatures.services import DocumentService
            document_result = DocumentService.create_document(
                model_class=PurchaseRequest,
                location=location,  # Директно location обект
                data=data,
                user=user
            )

            if not document_result.ok:
                return document_result

            request = document_result.data['document']

            # Добави редовете САМО през DocumentLineService
            if lines_data:
                lines_result = PurchaseRequestService._add_lines_via_service(request, lines_data, user)
                if not lines_result.ok:
                    return lines_result

            # Валидирай цялата заявка - използвай композиция от реални методи
            validation_result = PurchaseRequestService.validate_request(request, user)
            if not validation_result.ok:
                return Result.error('VALIDATION_FAILED', f'Document validation failed: {validation_result.msg}')

            # Получи summary САМО през сервиси
            summary_result = PurchaseRequestService._get_request_summary_via_services(request, user)
            summary_data = summary_result.data if summary_result.ok else {}

            return Result.success(
                data={
                    'request': request,
                    'document_number': request.document_number,
                    'status': request.status,
                    'lines_count': summary_data.get('lines_count', 0),
                    'estimated_total': summary_data.get('estimated_total', Decimal('0')),
                    **summary_data
                },
                msg=f'Purchase request {request.document_number} created successfully'
            )

        except Exception as e:
            logger.error(f"Error creating purchase request: {e}")
            return Result.error('REQUEST_CREATION_FAILED', f'Failed to create request: {str(e)}')

    @staticmethod
    def submit_for_approval(request: PurchaseRequest, user: User, comments: str = '') -> Result:
        """
        Изпраща заявката за одобрение

        РЕФАКТОРИРАН: Използва само DocumentService
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.submit_for_approval(request, user, comments)

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentService not available')
        except Exception as e:
            return Result.error('SUBMISSION_FAILED', f'Failed to submit request: {str(e)}')

    @staticmethod
    def add_line(request: PurchaseRequest, product, quantity: Decimal,
                 estimated_price: Decimal = None, unit=None, notes: str = '', user: User = None) -> Result:
        """
        Добавя ред към заявка

        РЕФАКТОРИРАН: Използва DocumentLineService
        """
        try:
            # Проверка на permissions САМО през DocumentService
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok or not can_edit_result.data.get('can_edit', False):
                return Result.error('EDIT_DENIED', 'Cannot add lines to this request')

            # Добави реда САМО през DocumentLineService
            from nomenclatures.services.document_line_service import DocumentLineService
            return DocumentLineService.add_line(
                document=request,
                product=product,
                quantity=quantity,
                estimated_price=estimated_price,
                unit=unit or product.base_unit,
                description=notes
            )

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentLineService not available')
        except Exception as e:
            return Result.error('LINE_ADD_FAILED', f'Failed to add line: {str(e)}')

    @staticmethod
    def remove_line(request: PurchaseRequest, line_number: int, user: User = None) -> Result:
        """
        Премахва ред от заявка

        РЕФАКТОРИРАН: Използва DocumentLineService
        """
        try:
            # Проверка на permissions САМО през DocumentService
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok or not can_edit_result.data.get('can_edit', False):
                return Result.error('EDIT_DENIED', 'Cannot remove lines from this request')

            # Премахни реда САМО през DocumentLineService
            from nomenclatures.services.document_line_service import DocumentLineService
            return DocumentLineService.remove_line(request, line_number)

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentLineService not available')
        except Exception as e:
            return Result.error('LINE_REMOVE_FAILED', f'Failed to remove line: {str(e)}')

    @staticmethod
    def validate_request(request: PurchaseRequest, user: User = None) -> Result:
        """
        Пълна валидация на заявката

        РЕФАКТОРИРАН: Композиция от съществуващи DocumentService методи
        """
        try:
            validation_issues = []

            # 1. Проверка дали може да се редактира (permissions & status)
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok:
                validation_issues.append(f"Edit permission: {can_edit_result.msg}")
            elif not can_edit_result.data.get('can_edit', False):
                validation_issues.append(f"Edit denied: {can_edit_result.data.get('reason', 'Unknown reason')}")

            # 2. Валидация на data integrity
            integrity_result = DocumentService.validate_document_integrity(request, deep_validation=True)
            if not integrity_result.ok:
                validation_issues.append(f"Integrity check failed: {integrity_result.msg}")
            elif not integrity_result.data.get('is_valid', False):
                issues = integrity_result.data.get('validation_issues', [])
                for issue in issues:
                    if issue.get('severity') == 'error':
                        validation_issues.append(f"Data error: {issue.get('message', 'Unknown error')}")

            # 3. Валидация на редовете
            try:
                from nomenclatures.services.document_line_service import DocumentLineService
                lines_result = DocumentLineService.validate_lines(request)
                if not lines_result.ok:
                    validation_issues.append(f"Lines validation failed: {lines_result.msg}")
            except ImportError:
                # Fallback - минимална проверка за редове
                if not request.lines.exists():
                    validation_issues.append("Document has no lines")

            # 4. Business rules валидация
            try:
                from nomenclatures.services.document.validator import DocumentValidator
                business_result = DocumentValidator._validate_business_rules(request, request.status, user)
                if not business_result.ok:
                    validation_issues.append(f"Business rules: {business_result.msg}")
            except ImportError:
                pass  # Skip business rules if validator not available

            # Обобщи резултата
            if validation_issues:
                return Result.error(
                    'VALIDATION_FAILED',
                    f'Validation failed: {"; ".join(validation_issues)}',
                    data={'validation_issues': validation_issues}
                )

            return Result.success(
                data={
                    'can_edit': can_edit_result.data.get('can_edit', False),
                    'lines_count': request.lines.count(),
                    'estimated_total': PurchaseRequestService._fallback_calculate_total(request),
                    'validation_issues': []
                },
                msg='Request validation passed'
            )

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentService not available')
        except Exception as e:
            return Result.error('VALIDATION_ERROR', f'Validation failed: {str(e)}')

    @staticmethod
    def get_request_summary(request: PurchaseRequest, user: User = None) -> Result:
        """
        Връща обобщение на заявката за API/UI

        РЕФАКТОРИРАН: Използва само сервиси
        """
        try:
            return PurchaseRequestService._get_request_summary_via_services(request, user)

        except Exception as e:
            return Result.error('SUMMARY_ERROR', f'Failed to generate summary: {str(e)}')

    @staticmethod
    def approve_request(request: PurchaseRequest, user: User, comments: str = '') -> Result:
        """
        Одобрява заявката

        НОВ МЕТОД: Използва реални DocumentService методи
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.approve_document(request, user, comments)

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentService not available')
        except Exception as e:
            return Result.error('APPROVAL_FAILED', f'Failed to approve request: {str(e)}')

    @staticmethod
    def reject_request(request: PurchaseRequest, user: User, reason: str) -> Result:
        """
        Отхвърля заявката

        НОВ МЕТОД: Използва реални DocumentService методи
        """
        try:
            from nomenclatures.services import DocumentService
            return DocumentService.reject_document(request, user, reason)

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentService not available')
        except Exception as e:
            return Result.error('REJECTION_FAILED', f'Failed to reject request: {str(e)}')

    # =====================
    # PRIVATE HELPERS - РЕФАКТОРИРАНИ ДА ИЗПОЛЗВАТ САМО СЕРВИСИ
    # =====================

    @staticmethod
    def _validate_request_data_via_services(location, data: Dict[str, Any], lines_data: List[Dict] = None,
                                            user: User = None) -> Result:
        """
        Валидира входните данни преди създаване

        РЕФАКТОРИРАН: Използва само сервиси за валидация
        """
        errors = []

        # Валидирай location - вече е обект
        if not location:
            errors.append('Location is required')
        elif not getattr(location, 'is_active', True):
            errors.append('Location is not active')

        # Валидирай partner ако е подаден
        if 'partner' in data and data['partner']:
            try:
                from core.interfaces.partner_interface import validate_partner
                validate_partner(data['partner'])
            except (ImportError, AttributeError):
                # Partner interface не е наличен - skip validation
                pass
            except Exception as e:
                errors.append(f'Invalid partner: {str(e)}')

        # Валидирай редовете САМО през ProductService
        if lines_data:
            for i, line_data in enumerate(lines_data):
                line_validation = PurchaseRequestService._validate_line_data_via_services(i + 1, line_data)
                if not line_validation.ok:
                    errors.append(line_validation.msg)

        if errors:
            return Result.error('INVALID_DATA', f'Data validation failed: {"; ".join(errors)}')

        return Result.success(msg='Data validation passed')

    @staticmethod
    def _validate_line_data_via_services(line_number: int, line_data: Dict) -> Result:
        """
        Валидира данните за един ред

        РЕФАКТОРИРАН: Използва ProductService за валидация
        """
        if not line_data.get('product'):
            return Result.error('INVALID_LINE', f'Line {line_number}: Product is required')

        # Валидирай продукта
        product = line_data['product']
        if hasattr(product, 'lifecycle_status') and product.lifecycle_status != 'ACTIVE':
            return Result.error('INVALID_LINE', f'Line {line_number}: Product is not active')

        # Валидирай количеството
        quantity = line_data.get('quantity')
        if not quantity or quantity <= 0:
            return Result.error('INVALID_LINE', f'Line {line_number}: Valid quantity is required')

        return Result.success(msg=f'Line {line_number} validation passed')

    @staticmethod
    def _add_lines_via_service(request: PurchaseRequest, lines_data: List[Dict], user: User = None) -> Result:
        """
        Добавя редове към заявка САМО през DocumentLineService

        РЕФАКТОРИРАН: Използва DocumentLineService за всички операции с редове
        """
        try:
            from nomenclatures.services.document_line_service import DocumentLineService

            added_lines = []

            for i, line_data in enumerate(lines_data):
                # Валидирай реда
                validation_result = PurchaseRequestService._validate_line_data_via_services(i + 1, line_data)
                if not validation_result.ok:
                    return validation_result

                # Добави реда през DocumentLineService
                line_result = DocumentLineService.add_line(
                    document=request,
                    product=line_data['product'],
                    quantity=line_data['quantity'],
                    estimated_price=line_data.get('estimated_price'),
                    entered_price=line_data.get('entered_price'),
                    unit=line_data.get('unit') or line_data['product'].base_unit,
                    description=line_data.get('notes', '')
                )

                if not line_result.ok:
                    return line_result

                added_lines.append(line_result.data['line'])

            return Result.success(
                data={'lines': added_lines, 'count': len(added_lines)},
                msg=f'{len(added_lines)} lines added successfully'
            )

        except ImportError:
            return Result.error('SERVICE_UNAVAILABLE', 'DocumentLineService not available')
        except Exception as e:
            return Result.error('LINES_ADD_FAILED', f'Failed to add lines: {str(e)}')

    @staticmethod
    def _get_request_summary_via_services(request: PurchaseRequest, user: User = None) -> Result:
        """
        Генерира summary САМО през сервиси

        РЕФАКТОРИРАН: НЕ използва директни заявки към модели
        """
        try:
            # Основни данни - минимални директни достъпи до request полета
            summary = {
                'document_number': request.document_number,
                'status': request.status,
                'created_at': request.created_at,
                'created_by': request.created_by.username if request.created_by else None,
            }

            # Location data
            if request.location:
                summary['location_name'] = getattr(request.location, 'name', str(request.location))
                summary['location_code'] = getattr(request.location, 'code', '')

            # Partner име - използвай интерфейса
            if request.partner:
                try:
                    from core.interfaces.partner_interface import format_partner_display
                    summary['partner_name'] = format_partner_display(request.partner)
                except ImportError:
                    summary['partner_name'] = str(request.partner)
            else:
                summary['partner_name'] = None

            # Lines count и total САМО през DocumentLineService
            try:
                from nomenclatures.services.document_line_service import DocumentLineService
                lines_result = DocumentLineService.validate_lines(request)
                if lines_result.ok:
                    summary['lines_count'] = lines_result.data.get('lines_count', 0)
                    summary['estimated_total'] = PurchaseRequestService._calculate_total_via_service(request)
                else:
                    summary['lines_count'] = 0
                    summary['estimated_total'] = Decimal('0')
            except ImportError:
                # Fallback - минимален директен достъп
                summary['lines_count'] = request.lines.count()
                summary['estimated_total'] = PurchaseRequestService._fallback_calculate_total(request)

            # Permissions САМО през DocumentService
            try:
                from nomenclatures.services import DocumentService
                can_edit_result = DocumentService.can_edit_document(request, user)
                summary['can_edit'] = can_edit_result.data.get('can_edit', False) if can_edit_result.ok else False

                # Available actions САМО през DocumentService
                actions_result = DocumentService.get_available_actions(request, user)
                summary['available_actions'] = actions_result if isinstance(actions_result, list) else []

            except ImportError:
                summary['can_edit'] = False
                summary['available_actions'] = []

            return Result.success(data=summary, msg='Request summary generated via services')

        except Exception as e:
            return Result.error('SUMMARY_ERROR', f'Failed to generate summary: {str(e)}')

    @staticmethod
    def _calculate_total_via_service(request: PurchaseRequest) -> Decimal:
        """
        Изчислява total САМО през реални DocumentService методи

        РЕФАКТОРИРАН: Използва съществуващи методи
        """
        try:
            # 1. Опитай DocumentService.analyze_document_financial_impact()
            from nomenclatures.services import DocumentService
            analysis_result = DocumentService.analyze_document_financial_impact(request, compare_to_budget=False)
            if analysis_result.ok:
                return request.total or Decimal('0')
        except ImportError:
            pass

        try:
            # 2. Опитай DocumentService.recalculate_document_lines()
            from nomenclatures.services import DocumentService
            recalc_result = DocumentService.recalculate_document_lines(request, recalc_vat=False, update_pricing=False)
            if recalc_result.ok:
                return Decimal(str(recalc_result.data.get('new_total', '0')))
        except ImportError:
            pass

        # 3. Fallback - използвай model property ако има
        if hasattr(request, 'total_estimated_cost'):
            return request.total_estimated_cost

        # 4. Last fallback
        return PurchaseRequestService._fallback_calculate_total(request)

    @staticmethod
    def _fallback_calculate_total(request: PurchaseRequest) -> Decimal:
        """
        Fallback изчисляване на total ако сервисите не са налични

        МИНИМАЛЕН директен достъп - само когато сервисите не работят
        """
        try:
            total = Decimal('0')
            for line in request.lines.all():
                if hasattr(line, 'requested_quantity') and hasattr(line, 'estimated_price'):
                    if line.requested_quantity and line.estimated_price:
                        total += line.requested_quantity * line.estimated_price
            return total
        except:
            return Decimal('0')


# =====================
# CONVENIENCE FUNCTIONS
# =====================

def create_purchase_request(location, user: User, partner=None, notes: str = '',
                            priority: str = 'normal', lines_data: List[Dict] = None) -> Result:
    """
    Convenience function за създаване на заявка с по-лесен API

    Args:
        location: InventoryLocation обект
        user: User обект
        partner: Partner обект (optional)
        notes: Забележки
        priority: Приоритет ('low', 'normal', 'high', 'urgent')
        lines_data: List[Dict] с редовете

    Returns:
        Result със създадената заявка
    """
    data = {
        'notes': notes,
        'priority': priority,
    }

    if partner:
        data['partner'] = partner

    return PurchaseRequestService.create_request(location, data, user, lines_data)


def add_product_to_request(request: PurchaseRequest, product, quantity: Decimal,
                           estimated_price: Decimal = None, user: User = None) -> Result:
    """
    Convenience function за добавяне на продукт към заявка

    Args:
        request: PurchaseRequest обект
        product: Product обект
        quantity: Количество
        estimated_price: Прогнозна цена
        user: User обект

    Returns:
        Result с добавения ред
    """
    return PurchaseRequestService.add_line(request, product, quantity, estimated_price, user=user)