# purchases/services/workflow_service.py

from typing import Dict, Any, Optional
from django.db import transaction
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging

from core.utils.result import Result
from nomenclatures.services import DocumentService
from purchases.models import PurchaseRequest, PurchaseRequestLine

User = get_user_model()
logger = logging.getLogger(__name__)


class PurchaseWorkflowService:
    """
    Purchase-specific workflow orchestration service
    Разширява базовата функционалност с purchase логика
    """

    @staticmethod
    @transaction.atomic
    def create_purchase_request(
            location,
            user: User,
            supplier=None,
            required_by_date=None,
            priority: str = 'normal',
            notes: str = '',
            lines_data: list = None
    ) -> Result:
        """
        Създава нова purchase request

        Args:
            location: InventoryLocation където се нуждаем от стоките
            user: User който създава заявката
            supplier: Supplier от когото искаме да поръчаме (опционално)
            required_by_date: Кога са необходими стоките
            priority: low/normal/high/urgent
            notes: Бележки към заявката
            lines_data: List of dicts с данни за редовете
                [{'product': Product, 'requested_quantity': Decimal, 'notes': str}]

        Returns:
            Result със създадената заявка или грешка
        """
        try:
            # Подготовка на данните за документа - с партньор ако има
            request_data = {
                'location': location,  # BaseDocument.save() ще попълни GenericFK автоматично
                'priority': priority,
                'notes': notes,
                'created_by': user,
                'updated_by': user,
            }

            # Добави партньор ако е подаден
            if supplier:
                from django.contrib.contenttypes.models import ContentType
                request_data.update({
                    'partner_content_type': ContentType.objects.get_for_model(supplier),
                    'partner_object_id': supplier.pk
                })

            if required_by_date:
                request_data['required_by_date'] = required_by_date

            # Създаване през DocumentService - DocumentCreator ще попълни document_type
            create_result = DocumentService.create_document(
                model_class=PurchaseRequest,
                data=request_data,
                user=user,
                location=location
            )

            if not create_result.ok:
                logger.error(f"Failed to create purchase request: {create_result.msg}")
                return create_result

            purchase_request = create_result.data['document']

            # Добавяне на редове ако има
            if lines_data:
                for index, line_data in enumerate(lines_data, start=1):
                    # Проверка на задължителни полета
                    if 'product' not in line_data or line_data['product'] is None:
                        return Result.error(
                            code='MISSING_PRODUCT',
                            msg=f'Line {index}: Product is required'
                        )

                    product = line_data['product']

                    # Определяне на unit - първо от данните, после от продукта, накрая fallback
                    unit = line_data.get('unit')
                    if not unit:
                        unit = getattr(product, 'base_unit', None)
                    if not unit:
                        # Fallback - търси първи активен UnitOfMeasure
                        from nomenclatures.models import UnitOfMeasure
                        unit = UnitOfMeasure.objects.filter(is_active=True).first()
                        if not unit:
                            return Result.error(
                                code='NO_UNIT_AVAILABLE',
                                msg=f'Line {index}: No unit of measure available for product {product.code}'
                            )

                    line = PurchaseRequestLine.objects.create(
                        document=purchase_request,
                        line_number=index,
                        product=product,
                        requested_quantity=line_data.get('requested_quantity', Decimal('1')),
                        description=line_data.get('notes', ''),
                        unit=unit,
                    )

                    # Опитваме да вземем последна цена на покупка за оценка
                    try:
                        if hasattr(line.product, 'get_last_purchase_price'):
                            estimated_price = line.product.get_last_purchase_price(location)
                            if estimated_price:
                                line.estimated_price = estimated_price
                                line.save(update_fields=['estimated_price'])
                    except Exception as e:
                        logger.warning(f"Could not set estimated price for {line.product.code}: {e}")

                    # Fallback към cost_price ако няма estimated_price
                    if not getattr(line, 'estimated_price', None):
                        if hasattr(line.product, 'cost_price') and line.product.cost_price:
                            line.estimated_price = line.product.cost_price
                            line.save(update_fields=['estimated_price'])
                        elif supplier and hasattr(supplier, 'get_product_price'):
                            # Опитай да вземеш цена от supplier
                            try:
                                supplier_price = supplier.get_product_price(line.product)
                                if supplier_price:
                                    line.estimated_price = supplier_price
                                    line.save(update_fields=['estimated_price'])
                            except Exception as e:
                                logger.warning(f"Could not get supplier price for {line.product.code}: {e}")




            logger.info(
                f"Created purchase request {purchase_request.document_number} "
                f"with {len(lines_data or [])} lines by user {user.username}"
            )

            return Result.success(
                data={
                    'document': purchase_request,
                    'document_number': purchase_request.document_number,
                    'lines_count': purchase_request.lines.count(),
                    'total_amount': getattr(purchase_request, 'total', None),
                    'status': purchase_request.status
                },
                msg=f'Purchase request {purchase_request.document_number} created successfully'
            )

        except Exception as e:
            logger.error(f"Error creating purchase request: {e}")
            return Result.error(
                code='CREATE_REQUEST_ERROR',
                msg=f'Failed to create purchase request: {str(e)}'
            )