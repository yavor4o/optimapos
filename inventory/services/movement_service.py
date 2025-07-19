# inventory/services/movement_service.py
import logging

from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from ..models import InventoryLocation, InventoryMovement, InventoryItem, InventoryBatch

logger = logging.getLogger(__name__)

class MovementService:
    """
    Service for creating and managing inventory movements
    Handles the complex logic of FIFO, batch tracking, and cache updates
    """

    @staticmethod
    @transaction.atomic
    def create_incoming_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            cost_price: Decimal,
            source_document_type: str = 'PURCHASE',
            source_document_number: str = '',
            movement_date=None,
            batch_number: str = None,
            expiry_date=None,
            reason: str = '',
            created_by=None
    ) -> InventoryMovement:
        """
        Create incoming inventory movement (purchases, receipts, production)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Auto-generate batch for batch-tracked products
        if product.track_batches and not batch_number:
            batch_number = f"AUTO_{product.code}_{movement_date.strftime('%y%m%d')}_{location.code}"

        movement = InventoryMovement.objects.create(
            location=location,
            product=product,
            movement_type=InventoryMovement.IN,
            quantity=quantity,
            cost_price=cost_price,
            batch_number=batch_number,
            expiry_date=expiry_date,
            source_document_type=source_document_type,
            source_document_number=source_document_number,
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        # Update product's moving average cost
        MovementService._update_product_moving_average(product, quantity, cost_price)

        return movement

    @staticmethod
    @transaction.atomic
    def create_outgoing_movement(
            location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_type: str = 'SALE',
            source_document_number: str = '',
            movement_date=None,
            reason: str = '',
            created_by=None,
            use_fifo: bool = True
    ) -> List[InventoryMovement]:
        """
        Create outgoing inventory movement (sales, issues, consumption)
        Handles FIFO logic for batch-tracked products
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        movements = []

        if product.track_batches and use_fifo:
            # FIFO consumption from batches
            remaining_to_consume = quantity

            # Get batches in FIFO order (oldest first, expiring first)
            batches = InventoryBatch.objects.filter(
                location=location,
                product=product,
                remaining_qty__gt=0
            ).order_by('received_date', 'expiry_date')

            for batch in batches:
                if remaining_to_consume <= 0:
                    break

                # How much to consume from this batch
                consume_qty = min(remaining_to_consume, batch.remaining_qty)

                # Create movement for this batch
                movement = InventoryMovement.objects.create(
                    location=location,
                    product=product,
                    movement_type=InventoryMovement.OUT,
                    quantity=consume_qty,
                    cost_price=batch.cost_price,  # Use batch-specific cost
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    source_document_type=source_document_type,
                    source_document_number=source_document_number,
                    movement_date=movement_date,
                    reason=reason,
                    created_by=created_by
                )

                movements.append(movement)
                remaining_to_consume -= consume_qty

            # Check if we consumed everything
            if remaining_to_consume > 0:
                raise ValueError(
                    f"Insufficient stock: {remaining_to_consume} units could not be fulfilled"
                )

        else:
            # Simple movement without FIFO (non-batch products or override)
            # Get average cost for non-batch products
            try:
                item = InventoryItem.objects.get(location=location, product=product)
                cost_price = item.avg_cost
            except InventoryItem.DoesNotExist:
                cost_price = product.current_avg_cost

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=quantity,
                cost_price=cost_price,
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )

            movements.append(movement)

        return movements

    @staticmethod
    @transaction.atomic
    def create_transfer_movement(
            from_location: InventoryLocation,
            to_location: InventoryLocation,
            product,
            quantity: Decimal,
            source_document_number: str = '',
            movement_date=None,
            reason: str = '',
            created_by=None
    ) -> Tuple[List[InventoryMovement], List[InventoryMovement]]:
        """
        Create transfer movements between locations
        Returns (outbound_movements, inbound_movements)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Create outbound movements (FIFO from source location)
        outbound_movements = MovementService.create_outgoing_movement(
            location=from_location,
            product=product,
            quantity=quantity,
            source_document_type='TRANSFER',
            source_document_number=source_document_number,
            movement_date=movement_date,
            reason=f"Transfer to {to_location.code}: {reason}",
            created_by=created_by,
            use_fifo=True
        )

        # Create corresponding inbound movements
        inbound_movements = []

        for out_movement in outbound_movements:
            in_movement = InventoryMovement.objects.create(
                location=to_location,
                product=product,
                movement_type=InventoryMovement.IN,
                quantity=out_movement.quantity,
                cost_price=out_movement.cost_price,  # Preserve cost
                batch_number=out_movement.batch_number,
                expiry_date=out_movement.expiry_date,
                source_document_type='TRANSFER',
                source_document_number=source_document_number,
                movement_date=movement_date,
                from_location=from_location,
                to_location=to_location,
                reason=f"Transfer from {from_location.code}: {reason}",
                created_by=created_by
            )
            inbound_movements.append(in_movement)

        return outbound_movements, inbound_movements

    @staticmethod
    @transaction.atomic
    def create_adjustment_movement(
            location: InventoryLocation,
            product,
            adjustment_qty: Decimal,
            reason: str,
            movement_date=None,
            created_by=None
    ) -> InventoryMovement:
        """
        Create inventory adjustment movement (positive or negative)
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        # Determine movement type and actual quantity
        if adjustment_qty > 0:
            movement_type = InventoryMovement.IN
            quantity = adjustment_qty
        else:
            movement_type = InventoryMovement.OUT
            quantity = abs(adjustment_qty)

        # Get current average cost
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            cost_price = item.avg_cost
        except InventoryItem.DoesNotExist:
            cost_price = product.current_avg_cost

        movement = InventoryMovement.objects.create(
            location=location,
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            cost_price=cost_price,
            source_document_type='ADJUSTMENT',
            source_document_number='ADJ-' + timezone.now().strftime('%Y%m%d-%H%M%S'),
            movement_date=movement_date,
            reason=reason,
            created_by=created_by
        )

        return movement

    @staticmethod
    def _update_product_moving_average(product, new_qty: Decimal, new_cost: Decimal):
        """
        Update product's moving average cost
        """
        old_qty = product.current_stock_qty
        old_cost = product.current_avg_cost
        old_total_value = old_qty * old_cost

        new_total_value = new_qty * new_cost
        new_total_qty = old_qty + new_qty

        if new_total_qty > 0:
            new_avg_cost = (old_total_value + new_total_value) / new_total_qty
        else:
            new_avg_cost = new_cost

        # Update product fields
        product.current_avg_cost = new_avg_cost
        product.current_stock_qty = new_total_qty
        product.last_purchase_cost = new_cost
        product.last_purchase_date = timezone.now().date()

        product.save(update_fields=[
            'current_avg_cost', 'current_stock_qty',
            'last_purchase_cost', 'last_purchase_date'
        ])

    @staticmethod
    def get_movement_history(
            location: InventoryLocation = None,
            product=None,
            movement_type: str = None,
            date_from=None,
            date_to=None,
            limit: int = 100
    ) -> List[Dict]:
        """
        Get movement history with filters
        """
        queryset = InventoryMovement.objects.select_related(
            'location', 'product', 'created_by'
        )

        # Apply filters
        if location:
            queryset = queryset.filter(location=location)
        if product:
            queryset = queryset.filter(product=product)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if date_from:
            queryset = queryset.filter(movement_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(movement_date__lte=date_to)

        queryset = queryset.order_by('-created_at')[:limit]

        movements = []
        for movement in queryset:
            movements.append({
                'id': movement.id,
                'location_code': movement.location.code,
                'product_code': movement.product.code,
                'product_name': movement.product.name,
                'movement_type': movement.movement_type,
                'movement_type_display': movement.get_movement_type_display(),
                'quantity': movement.quantity,
                'cost_price': movement.cost_price,
                'batch_number': movement.batch_number,
                'expiry_date': movement.expiry_date,
                'source_document_type': movement.source_document_type,
                'source_document_number': movement.source_document_number,
                'movement_date': movement.movement_date,
                'reason': movement.reason,
                'created_at': movement.created_at,
                'created_by': movement.created_by.username if movement.created_by else None
            })

        return movements

    @staticmethod
    def reconcile_inventory(location: InventoryLocation, product) -> Dict:
        """
        Reconcile inventory by recalculating from movements
        """
        # Refresh cached data
        InventoryItem.refresh_for_combination(location, product)

        # Refresh all batches for this product
        if product.track_batches:
            batch_numbers = InventoryMovement.objects.filter(
                location=location,
                product=product,
                batch_number__isnull=False
            ).values_list('batch_number', flat=True).distinct()

            for batch_number in batch_numbers:
                InventoryBatch.refresh_for_combination(
                    location=location,
                    product=product,
                    batch_number=batch_number
                )

        # Get updated data
        try:
            item = InventoryItem.objects.get(location=location, product=product)
            return {
                'success': True,
                'current_qty': item.current_qty,
                'avg_cost': item.avg_cost,
                'last_movement': item.last_movement_date
            }
        except InventoryItem.DoesNotExist:
            return {
                'success': True,
                'current_qty': Decimal('0'),
                'avg_cost': Decimal('0'),
                'last_movement': None
            }

    @staticmethod
    def validate_movement_data(
            location: InventoryLocation,
            product,
            movement_type: str,
            quantity: Decimal,
            cost_price: Decimal = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate movement data before creation
        """
        errors = []

        # Basic validations
        if quantity <= 0:
            errors.append("Quantity must be positive")

        if cost_price is not None and cost_price < 0:
            errors.append("Cost price cannot be negative")

        # Stock availability for outgoing movements
        if movement_type == InventoryMovement.OUT:
            from .inventory_service import InventoryService
            availability = InventoryService.check_availability(location, product, quantity)

            if not availability['can_fulfill']:
                errors.append(
                    f"Insufficient stock. Available: {availability['available_qty']}, "
                    f"Required: {quantity}"
                )

        return len(errors) == 0, errors

    # inventory/services/movement_service.py - Добави този метод в класа MovementService

    @staticmethod
    @transaction.atomic
    def create_from_document(document) -> List[InventoryMovement]:
        """
        Универсален метод за създаване на inventory движения от документ

        Чете DocumentType конфигурацията и създава съответните движения
        според affects_inventory, inventory_timing и типа на документа

        Args:
            document: Всеки документ с DocumentType (DeliveryReceipt, PurchaseOrder, etc.)

        Returns:
            List[InventoryMovement]: Създадените движения
        """
        movements = []

        # 1. Валидация - има ли DocumentType
        if not hasattr(document, 'document_type') or not document.document_type:
            logger.warning(f"Document {document} has no DocumentType configured")
            return movements

        # 2. Проверка affects_inventory
        if not document.document_type.affects_inventory:
            logger.debug(f"Document type {document.document_type.code} does not affect inventory")
            return movements

        # 3. Проверка inventory_timing
        timing = document.document_type.inventory_timing
        should_create = False

        if timing == 'immediate':
            should_create = True
        elif timing == 'on_confirm' and document.status == 'confirmed':
            should_create = True
        elif timing == 'on_complete' and document.status == 'completed':
            should_create = True
        elif timing == 'on_process' and document.status == 'processed':
            should_create = True
        elif timing == 'manual':
            # За manual timing, този метод трябва да се извика експлицитно
            should_create = True

        if not should_create:
            logger.debug(
                f"Document {document.document_number} with status '{document.status}' "
                f"does not meet timing requirement '{timing}'"
            )
            return movements

        # 4. Определяне на типа документ и делегиране към специфичен handler
        model_name = document._meta.model_name.lower()

        try:
            if model_name == 'deliveryreceipt':
                movements = MovementService._create_from_delivery(document)
            elif model_name == 'purchaseorder':
                movements = MovementService._create_from_purchase_order(document)
            elif model_name == 'salesinvoice':
                movements = MovementService._create_from_sales_invoice(document)
            elif model_name == 'stocktransfer':
                movements = MovementService._create_from_stock_transfer(document)
            elif model_name == 'stockadjustment':
                movements = MovementService._create_from_stock_adjustment(document)
            else:
                logger.warning(f"No inventory handler for document type: {model_name}")

            if movements:
                logger.info(
                    f"Created {len(movements)} inventory movements for "
                    f"{document.document_number} ({model_name})"
                )

        except Exception as e:
            logger.error(
                f"Error creating inventory movements for {document.document_number}: {e}",
                exc_info=True
            )
            # Re-raise за да се rollback транзакцията
            raise

        return movements

    @staticmethod
    def _create_from_delivery(delivery) -> List[InventoryMovement]:
        """
        Създава IN движения от доставка

        За всеки ред от доставката създава входящо движение
        """
        movements = []

        # Валидация
        if not hasattr(delivery, 'lines'):
            logger.error(f"Delivery {delivery.document_number} has no lines")
            return movements

        # За всеки ред от доставката
        for line in delivery.lines.all():
            # Пропускаме редове без количество
            if not line.received_quantity or line.received_quantity <= 0:
                continue

            try:
                movement = MovementService.create_incoming_movement(
                    location=delivery.location,
                    product=line.product,
                    quantity=line.received_quantity,
                    cost_price=line.unit_price or Decimal('0.00'),
                    source_document_type='PURCHASE',
                    source_document_number=delivery.document_number,
                    movement_date=delivery.delivery_date or timezone.now().date(),
                    batch_number=getattr(line, 'batch_number', None),
                    expiry_date=getattr(line, 'expiry_date', None),
                    reason=f"Delivery receipt {delivery.document_number}",
                    created_by=delivery.updated_by or delivery.created_by
                )
                movements.append(movement)

            except Exception as e:
                logger.error(
                    f"Error creating movement for line {line.line_number} "
                    f"of delivery {delivery.document_number}: {e}"
                )
                # Продължаваме с другите редове
                continue

        return movements

    @staticmethod
    def _create_from_purchase_order(order) -> List[InventoryMovement]:
        """
        Създава движения от поръчка (рядко използвано)

        Обикновено движенията се създават от доставката, не от поръчката
        Но може да се използва за auto-receive сценарии
        """
        movements = []

        # Проверка дали има auto-receive настройка
        if not getattr(order.document_type, 'auto_receive', False):
            logger.debug(f"Order {order.document_number} does not have auto-receive enabled")
            return movements

        # Логика подобна на delivery
        for line in order.lines.all():
            if not line.ordered_quantity or line.ordered_quantity <= 0:
                continue

            try:
                movement = MovementService.create_incoming_movement(
                    location=order.location,
                    product=line.product,
                    quantity=line.ordered_quantity,
                    cost_price=line.unit_price or Decimal('0.00'),
                    source_document_type='PURCHASE',
                    source_document_number=order.document_number,
                    movement_date=order.expected_delivery_date or timezone.now().date(),
                    reason=f"Auto-receive from order {order.document_number}",
                    created_by=order.updated_by or order.created_by
                )
                movements.append(movement)

            except Exception as e:
                logger.error(f"Error creating movement for order line: {e}")
                continue

        return movements

    @staticmethod
    def _create_from_sales_invoice(invoice) -> List[InventoryMovement]:
        """
        Създава OUT движения от продажба

        Placeholder - ще се имплементира когато добавим sales модула
        """
        # TODO: Implement when sales module is added
        logger.warning("Sales invoice inventory integration not yet implemented")
        return []

    @staticmethod
    def _create_from_stock_transfer(transfer) -> List[InventoryMovement]:
        """
        Създава TRANSFER движения

        Placeholder - ще се имплементира когато добавим transfers
        """
        # TODO: Implement when transfer module is added
        logger.warning("Stock transfer inventory integration not yet implemented")
        return []

    @staticmethod
    def _create_from_stock_adjustment(adjustment) -> List[InventoryMovement]:
        """
        Създава ADJUSTMENT движения

        Placeholder - ще се имплементира когато добавим adjustments
        """
        # TODO: Implement when adjustment module is added
        logger.warning("Stock adjustment inventory integration not yet implemented")
        return []