# inventory/services/movement_service.py
import logging

from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

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


        MovementService._update_product_moving_average(product, quantity, cost_price, movement_type='IN')




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
            use_fifo: bool = True,
            allow_negative_stock: bool = False,
            manual_cost_price: Decimal = None,  # ← НОВА ОПЦИЯ!
            batch_number: str = None  # ← НОВА ОПЦИЯ!
    ) -> List[InventoryMovement]:
        """
        Create outgoing inventory movements - UPDATED със smart cost price
        """
        if movement_date is None:
            movement_date = timezone.now().date()

        movements = []

        # Stock availability check
        if not allow_negative_stock:
            from .inventory_service import InventoryService
            availability = InventoryService.check_availability(location, product, quantity)
            if not availability['can_fulfill']:
                raise ValueError(
                    f"Insufficient stock for {product.code} at {location.code}. "
                    f"Available: {availability['available_qty']}, Required: {quantity}"
                )

        # =====================
        # BATCH TRACKING vs SIMPLE STOCK
        # =====================
        if product.track_batches and use_fifo and not manual_cost_price:
            # За FIFO batch movements - използваме batch цените
            movements = MovementService._create_fifo_outgoing_movements(
                location, product, quantity, source_document_type,
                source_document_number, movement_date, reason, created_by
            )

            if movements:
                total_out_qty = sum(m.quantity for m in movements)
                avg_cost = sum(
                    m.quantity * m.cost_price for m in movements) / total_out_qty if total_out_qty > 0 else Decimal('0')
                MovementService._update_product_moving_average(
                    product, total_out_qty, avg_cost, movement_type='OUT'
                )
        else:
            # =====================
            # SMART COST PRICE ЛОГИКА
            # =====================
            cost_price = MovementService._get_smart_cost_price(
                location=location,
                product=product,
                manual_price=manual_cost_price,
                batch_number=batch_number,
                movement_type='OUT'
            )

            movement = InventoryMovement.objects.create(
                location=location,
                product=product,
                movement_type=InventoryMovement.OUT,
                quantity=quantity,
                cost_price=cost_price,
                batch_number=batch_number,  # ← ДОБАВЯМЕ
                source_document_type=source_document_type,
                source_document_number=source_document_number,
                movement_date=movement_date,
                reason=reason,
                created_by=created_by
            )

            movements.append(movement)

            # Update product
            MovementService._update_product_moving_average(
                product, quantity, cost_price, movement_type='OUT'
            )

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
    def _update_product_moving_average(product, new_qty: Decimal, new_cost: Decimal, movement_type: str = 'IN'):
        """
        Update product's moving average cost - FIXED за правилни quantities
        """
        old_qty = product.current_stock_qty
        old_cost = product.current_avg_cost
        old_total_value = old_qty * old_cost

        # =====================
        # ФИКС: Правилно обработваме IN vs OUT movements
        # =====================
        if movement_type == 'IN':
            # За входящи движения - ДОБАВЯМЕ
            new_total_qty = old_qty + new_qty
            new_total_value = old_total_value + (new_qty * new_cost)

            # Пресмятаме новата средна цена
            if new_total_qty > 0:
                new_avg_cost = new_total_value / new_total_qty
            else:
                new_avg_cost = new_cost

            new_avg_cost = new_avg_cost.quantize(Decimal('0.0001'))
            new_cost = new_cost.quantize(Decimal('0.0001'))

            # Обновяваме purchase fields
            product.last_purchase_cost = new_cost
            product.last_purchase_date = timezone.now().date()

            update_fields = [
                'current_avg_cost', 'current_stock_qty',
                'last_purchase_cost', 'last_purchase_date'
            ]

        else:  # movement_type == 'OUT'
            # За изходящи движения - ИЗВАЖДАМЕ
            new_total_qty = old_qty - new_qty  # ← КЛЮЧОВАТА ПРОМЯНА!

            # За OUT movements не променяме avg_cost
            new_avg_cost = product.current_avg_cost

            update_fields = ['current_stock_qty']

        # Обновяваме Product
        product.current_avg_cost = new_avg_cost
        product.current_stock_qty = new_total_qty

        product.save(update_fields=update_fields)

        print(f"🔄 Updated Product {product.code}: {old_qty} → {new_total_qty} ({movement_type})")

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
        Създава движения от доставка - FIXED за multiple lines
        """
        movements = []

        # Валидация
        if not hasattr(delivery, 'lines'):
            logger.error(f"Delivery {delivery.document_number} has no lines")
            return movements

        # Получаваме direction от DocumentType
        direction = getattr(delivery.document_type, 'inventory_direction', 'in')

        # =====================
        # ФИКС: ОБРАБОТВАМЕ ВСЕКИ РЕД ОТДЕЛНО!
        # =====================
        for line in delivery.lines.all():
            # Пропускаме редове без количество
            if not line.received_quantity:
                continue

            print(f"🔄 Processing line {line.line_number}: {line.product.code} qty={line.received_quantity}")

            try:
                # =====================
                # ЛОГИКА за both direction
                # =====================
                if direction == 'both':
                    # За both direction: positive = IN, negative = OUT
                    if line.received_quantity > 0:
                        # Positive количество = получаваме стока
                        movement = MovementService.create_incoming_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),  # Винаги positive
                            cost_price=line.unit_price or Decimal('0.00'),
                            source_document_type='PURCHASES',
                            source_document_number=delivery.document_number,
                            movement_date=delivery.document_date,
                            batch_number=line.batch_number,
                            expiry_date=line.expiry_date,
                            reason=f"Delivery receipt - incoming (line {line.line_number})",
                            created_by=delivery.updated_by or delivery.created_by
                        )
                        movements.append(movement)
                        print(f"✅ Created IN movement: +{movement.quantity}")

                    elif line.received_quantity < 0:
                        # Negative количество = връщаме стока
                        movements_out = MovementService.create_outgoing_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),  # Винаги positive
                            source_document_type='PURCHASES',
                            source_document_number=delivery.document_number,
                            movement_date=delivery.document_date,
                            reason=f"Delivery receipt - return/correction (line {line.line_number})",
                            created_by=delivery.updated_by or delivery.created_by,
                            allow_negative_stock=True
                        )
                        # create_outgoing_movement връща списък
                        movements.extend(movements_out)
                        print(f"✅ Created OUT movement(s): {[m.quantity for m in movements_out]}")

                else:
                    # =====================
                    # ЛОГИКА за in/out direction
                    # =====================
                    if direction == 'in':
                        # За IN direction - винаги incoming movement
                        movement = MovementService.create_incoming_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),  # ФИКС: abs()
                            cost_price=line.unit_price or Decimal('0.00'),
                            source_document_type='PURCHASES',
                            source_document_number=delivery.document_number,
                            movement_date=delivery.document_date,
                            batch_number=line.batch_number,
                            expiry_date=line.expiry_date,
                            reason=f"Delivery receipt (line {line.line_number})",
                            created_by=delivery.updated_by or delivery.created_by
                        )
                        movements.append(movement)

                    elif direction == 'out':
                        # За OUT direction - винаги outgoing movement
                        movements_out = MovementService.create_outgoing_movement(
                            location=delivery.location,
                            product=line.product,
                            quantity=abs(line.received_quantity),  # ФИКС: abs()
                            source_document_type='PURCHASE',
                            source_document_number=delivery.document_number,
                            movement_date=delivery.document_date,
                            reason=f"Delivery dispatch (line {line.line_number})",
                            created_by=delivery.updated_by or delivery.created_by
                        )
                        movements.extend(movements_out)

                logger.debug(
                    f"Processed line {line.line_number}: {line.product.code} "
                    f"qty={line.received_quantity} → {len(movements)} total movements"
                )

            except Exception as e:
                logger.error(f"Error creating movement for delivery line {line.line_number}: {e}")
                continue

        print(f"🎯 Total movements created for {delivery.document_number}: {len(movements)}")
        return movements

    # =====================
    # DEBUG HELPER FUNCTION
    # =====================



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

    @staticmethod
    def _get_smart_cost_price(
            location: InventoryLocation,
            product,
            manual_price: Decimal = None,
            batch_number: str = None,
            movement_type: str = 'OUT'
    ) -> Decimal:
        """
        Интелигентно определяне на cost_price според приоритети:
        1. Ръчно въведена цена (от оператора)
        2. Batch цена (ако има batch_number)
        3. Последна покупна цена (last_purchase_cost)
        4. Средна цена (avg_cost)
        """

        # ПРИОРИТЕТ 1: Ръчно въведена цена
        if manual_price is not None and manual_price > 0:
            print(f"💰 Using MANUAL price: {manual_price}")
            return manual_price

        # ПРИОРИТЕТ 2: Batch цена
        if batch_number and product.track_batches:
            try:
                from ..models import InventoryBatch
                batch = InventoryBatch.objects.filter(
                    location=location,
                    product=product,
                    batch_number=batch_number,
                    remaining_qty__gt=0
                ).first()

                if batch and batch.cost_price:
                    print(f"📦 Using BATCH price: {batch.cost_price} (batch: {batch_number})")
                    return batch.cost_price
            except Exception as e:
                print(f"⚠️ Batch price lookup failed: {e}")

        # ПРИОРИТЕТ 3: Последна покупна цена
        if hasattr(product, 'last_purchase_cost') and product.last_purchase_cost:
            print(f"🛒 Using LAST PURCHASE price: {product.last_purchase_cost}")
            return product.last_purchase_cost

        # ПРИОРИТЕТ 4: Средна цена от InventoryItem
        try:
            from ..models import InventoryItem
            item = InventoryItem.objects.get(location=location, product=product)
            if item.avg_cost > 0:
                print(f"📊 Using AVERAGE price: {item.avg_cost}")
                return item.avg_cost
        except InventoryItem.DoesNotExist:
            pass

        # FALLBACK: Product средна цена
        fallback_price = product.current_avg_cost or Decimal('0.00')
        print(f"🆘 Using FALLBACK price: {fallback_price}")
        return fallback_price