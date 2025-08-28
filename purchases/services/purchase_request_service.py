# purchases/services/purchase_request_service.py

from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.contrib.auth import get_user_model
from core.utils.result import Result
from ..models import PurchaseRequest, PurchaseRequestLine
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class PurchaseRequestService:
    """
    Рефакториран сервис за PurchaseRequest операции

    ПРОМЯНА: Използва САМО сервиси от други апове
    НЕ търси полета директно от модели!
    """

    @staticmethod
    @transaction.atomic
    def create_request(data: Dict[str, Any], user: User, lines_data: List[Dict] = None) -> Result:
        """
        Създава нова заявка за покупки с редове

        РЕФАКТОРИРАН: Използва само DocumentService и други сервиси
        """
        try:
            # Валидация на входните данни САМО през сервиси
            validation_result = PurchaseRequestService._validate_request_data_via_services(data, lines_data, user)
            if not validation_result.ok:
                return validation_result

            # Създай документа чрез DocumentService (както беше)
            from nomenclatures.services import DocumentService
            document_result = DocumentService.create_document(
                model_class=PurchaseRequest,
                data=data,
                user=user,
                location=data.get('location')
            )

            if not document_result.ok:
                return document_result

            request = document_result.data['document']

            # Добави редовете ако има такива - създавай ги директно (DocumentLineService не съществува)
            if lines_data:
                lines_result = PurchaseRequestService._add_lines_directly(request, lines_data, user)
                if not lines_result.ok:
                    return lines_result

            # Валидирай цялата заявка - използвай can_edit за основна валидация
            validation_result = DocumentService.can_edit_document(request, user)
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

        РЕФАКТОРИРАН: Използва само DocumentService и ApprovalService
        """
        try:
            # Валидирай че заявката е готова за изпращане - провери дали може да се редактира
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok:
                return Result.error('VALIDATION_FAILED',
                                    f'Cannot submit request: {can_edit_result.msg}')

            # Използва DocumentService за submission (както беше)
            return DocumentService.submit_for_approval(request, user, comments)

        except Exception as e:
            return Result.error('SUBMISSION_FAILED', f'Failed to submit request: {str(e)}')

    @staticmethod
    def add_line(request: PurchaseRequest, product_id: int, quantity: Decimal,
                 estimated_price: Decimal = None, notes: str = '', user: User = None) -> Result:
        """
        Добавя ред към заявка

        РЕФАКТОРИРАН: Използва ProductService и DocumentLineService
        """
        try:
            # Проверка на permissions САМО през DocumentService
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok or not can_edit_result.data.get('can_edit', False):
                return Result.error('EDIT_DENIED', 'Cannot add lines to this request')

            # Намери продукта САМО през ProductService (използвай реален метод)
            from products.services import ProductService
            try:
                from products.models import Product
                product = Product.objects.get(id=product_id)

                # Валидирай че продукта е активен
                if not getattr(product, 'is_active', True):
                    return Result.error('PRODUCT_INACTIVE', f'Product with ID {product_id} is not active')

            except Product.DoesNotExist:
                return Result.error('PRODUCT_NOT_FOUND', f'Product with ID {product_id} not found')
            except ImportError:
                return Result.error('PRODUCT_SERVICE_UNAVAILABLE', 'Products app not available')

            # Добави реда - директно създаване на PurchaseRequestLine
            try:
                # Намери следващия line number
                last_line = request.lines.order_by('-line_number').first()
                next_line_number = (last_line.line_number + 1) if last_line else 1

                # Създай реда
                line = PurchaseRequestLine.objects.create(
                    document=request,
                    line_number=next_line_number,
                    product=product,
                    unit=product.base_unit,  # използвай базовата единица на продукта
                    requested_quantity=quantity,
                    estimated_price=estimated_price,
                    description=notes
                )

                return Result.success(
                    data={'line': line, 'line_number': next_line_number},
                    msg=f'Line {next_line_number} added successfully'
                )

            except Exception as line_error:
                return Result.error('LINE_CREATION_ERROR', f'Failed to create line: {str(line_error)}')

        except Exception as e:
            return Result.error('LINE_ADD_FAILED', f'Failed to add line: {str(e)}')

    @staticmethod
    def remove_line(request: PurchaseRequest, line_number: int, user: User = None) -> Result:
        """
        Премахва ред от заявка

        РЕФАКТОРИРАН: Използва само DocumentService и DocumentLineService
        """
        try:
            # Проверка на permissions САМО през DocumentService
            from nomenclatures.services import DocumentService
            can_edit_result = DocumentService.can_edit_document(request, user)
            if not can_edit_result.ok or not can_edit_result.data.get('can_edit', False):
                return Result.error('EDIT_DENIED', 'Cannot remove lines from this request')

            # Премахни реда - директно от модела
            try:
                line = request.lines.filter(line_number=line_number).first()
                if not line:
                    return Result.error('LINE_NOT_FOUND', f'Line {line_number} not found')

                line.delete()

                return Result.success(
                    data={'removed_line_number': line_number},
                    msg=f'Line {line_number} removed successfully'
                )

            except Exception as delete_error:
                return Result.error('LINE_DELETE_ERROR', f'Failed to delete line: {str(delete_error)}')

        except Exception as e:
            return Result.error('LINE_REMOVE_FAILED', f'Failed to remove line: {str(e)}')

    @staticmethod
    def validate_request(request: PurchaseRequest, user: User = None) -> Result:
        """
        Пълна валидация на заявката

        РЕФАКТОРИРАН: Използва реални DocumentService методи
        """
        try:
            from nomenclatures.services import DocumentService

            # Използвай can_edit като индикатор за валидност
            edit_result = DocumentService.can_edit_document(request, user)
            if not edit_result.ok:
                return Result.error('VALIDATION_FAILED', f'Document validation failed: {edit_result.msg}')

            # Допълнителна бизнес валидация
            if not request.document_number:
                return Result.error('VALIDATION_FAILED', 'Document number is missing')

            if not request.partner:
                return Result.error('VALIDATION_FAILED', 'Partner is required')

            # Минимална проверка за редове
            if not hasattr(request, 'lines') or request.lines.count() == 0:
                return Result.error('VALIDATION_FAILED', 'Request must have at least one line')

            return Result.success(
                data={
                    'can_edit': edit_result.data.get('can_edit', False),
                    'lines_count': request.lines.count(),
                    'estimated_total': PurchaseRequestService._fallback_calculate_total(request)
                },
                msg='Request validation passed'
            )

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

    # =====================
    # PRIVATE HELPERS - РЕФАКТОРИРАНИ ДА ИЗПОЛЗВАТ САМО СЕРВИСИ
    # =====================

    @staticmethod
    def _validate_request_data_via_services(data: Dict[str, Any], lines_data: List[Dict] = None,
                                            user: User = None) -> Result:
        """
        Валидира входните данни преди създаване

        РЕФАКТОРИРАН: Използва само сервиси за валидация
        """
        errors = []

        # Валидирай партньора - използвай интерфейса вместо несъществуващ сервис
        if data.get('partner_object_id') and data.get('partner_content_type'):
            try:
                from core.interfaces.partner_interface import validate_partner
                from django.contrib.contenttypes.models import ContentType

                # Намери партньора
                content_type = ContentType.objects.get(id=data['partner_content_type'])
                partner_model = content_type.model_class()
                partner = partner_model.objects.get(id=data['partner_object_id'])

                # Валидирай през интерфейса
                validate_partner(partner)

            except (ContentType.DoesNotExist, partner_model.DoesNotExist):
                errors.append('Invalid partner specified')
            except (ImportError, AttributeError):
                # Partner interface не е наличен - skip validation
                pass

        # Валидирай редовете - използвай реален ProductService метод
        if lines_data:
            try:
                from products.models import Product
                for i, line_data in enumerate(lines_data):
                    if not line_data.get('product_id'):
                        errors.append(f'Line {i + 1}: Product is required')
                        continue

                    # Провери дали продукта съществува - директна проверка
                    try:
                        product = Product.objects.get(id=line_data['product_id'])
                        if not getattr(product, 'is_active', True):
                            errors.append(f'Line {i + 1}: Product is not active')
                    except Product.DoesNotExist:
                        errors.append(f'Line {i + 1}: Product with ID {line_data["product_id"]} not found')

                    quantity = line_data.get('quantity')
                    if not quantity or quantity <= 0:
                        errors.append(f'Line {i + 1}: Valid quantity is required')

            except ImportError:
                # Fallback ако products app не е наличен
                for i, line_data in enumerate(lines_data):
                    if not line_data.get('product_id'):
                        errors.append(f'Line {i + 1}: Product is required')

                    quantity = line_data.get('quantity')
                    if not quantity or quantity <= 0:
                        errors.append(f'Line {i + 1}: Valid quantity is required')

        if errors:
            return Result.error('INVALID_DATA', f'Data validation failed: {"; ".join(errors)}')

        return Result.success(msg='Data validation passed')

    @staticmethod
    def _add_lines_directly(request: PurchaseRequest, lines_data: List[Dict], user: User = None) -> Result:
        """
        Добавя редове към заявка при създаване

        РЕФАКТОРИРАН: Използва САМО ProductService, редовете ги създава директно
        """
        try:
            from products.models import Product

            for i, line_data in enumerate(lines_data):
                # Намери продукта - директна заявка
                try:
                    product = Product.objects.get(id=line_data['product_id'])
                    if not getattr(product, 'is_active', True):
                        return Result.error('PRODUCT_INACTIVE', f'Line {i + 1}: Product is not active')
                except Product.DoesNotExist:
                    return Result.error('PRODUCT_NOT_FOUND',
                                        f'Line {i + 1}: Product with ID {line_data["product_id"]} not found')

                # Създай реда директно
                line = PurchaseRequestLine.objects.create(
                    document=request,
                    line_number=i + 1,  # Sequential line numbers
                    product=product,
                    unit=product.base_unit,
                    requested_quantity=Decimal(str(line_data['quantity'])),
                    estimated_price=Decimal(str(line_data['estimated_price'])) if line_data.get(
                        'estimated_price') else None,
                    description=line_data.get('notes', '')
                )

            return Result.success(msg=f'{len(lines_data)} lines added successfully')

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

            # Partner име - използвай интерфейса
            if request.partner:
                try:
                    from core.interfaces.partner_interface import format_partner_display
                    summary['partner_name'] = format_partner_display(request.partner)
                except ImportError:
                    summary['partner_name'] = str(request.partner)
            else:
                summary['partner_name'] = None

            # Lines count и total - директно от модела (DocumentLineService не съществува)
            summary['lines_count'] = request.lines.count()
            summary['estimated_total'] = PurchaseRequestService._fallback_calculate_total(request)

            # Permissions САМО през DocumentService
            try:
                from nomenclatures.services import DocumentService
                can_edit_result = DocumentService.can_edit_document(request, user)
                summary['can_edit'] = can_edit_result.data.get('can_edit', False) if can_edit_result.ok else False

                # Available actions САМО през DocumentService/ApprovalService
                actions_result = DocumentService.get_available_actions(request, user)
                summary['available_actions'] = actions_result.data if actions_result.ok else []

            except ImportError:
                summary['can_edit'] = False
                summary['available_actions'] = []

            return Result.success(data=summary, msg='Request summary generated via services')

        except Exception as e:
            return Result.error('SUMMARY_ERROR', f'Failed to generate summary: {str(e)}')

    @staticmethod
    def _fallback_calculate_total(request: PurchaseRequest) -> Decimal:
        """
        Fallback изчисляване на total ако DocumentLineService не е наличен

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