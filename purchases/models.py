from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from inventory.services import MovementService
from pricing.services import PricingService
from products.models import ProductPackaging


# === DOCUMENT TYPES ===

class DocumentType(models.Model):
    """Типове документи - складова +/-, фактура, трансфер и т.н."""

    # Предефинирани типове
    STOCK_IN = 'stock_in'
    STOCK_OUT = 'stock_out'
    INVOICE = 'invoice'
    TRANSFER = 'transfer'

    TYPE_CHOICES = [
        (STOCK_IN, _('Stock In (+)')),
        (STOCK_OUT, _('Stock Out (-)')),
        (INVOICE, _('Invoice')),
        (TRANSFER, _('Internal Transfer')),
    ]

    code = models.CharField(_('Code'), max_length=10, unique=True)
    name = models.CharField(_('Document Type Name'), max_length=100)
    type_key = models.CharField(_('Type Key'), max_length=20, choices=TYPE_CHOICES)

    # Влияние върху наличности
    stock_effect = models.IntegerField(
        _('Stock Effect'),
        choices=[(1, _('Increases stock')), (-1, _('Decreases stock')), (0, _('No effect'))],
        default=1
    )

    allow_reverse_operations = models.BooleanField(
        _('Allow Reverse Operations'),
        default=False,
        help_text=_('Allow negative quantities to reverse the stock effect')
    )

    requires_batch = models.BooleanField(_('Requires Batch'), default=False)
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')

    def __str__(self):
        return f"{self.code} - {self.name}"


# === MAIN PURCHASE DOCUMENT ===

class PurchaseDocument(models.Model):
    """Основен документ за доставки"""

    # Статуси
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'
    RECEIVED = 'received'
    CANCELLED = 'cancelled'
    PAID = 'paid'
    CLOSED = 'closed'

    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (CONFIRMED, _('Confirmed')),
        (RECEIVED, _('Received')),
        (CANCELLED, _('Cancelled')),
        (PAID, _('Paid')),
        (CLOSED, _('Closed')),
    ]

    # Основна информация
    document_number = models.CharField(_('Document Number'), max_length=50, unique=True)
    document_date = models.DateField(_('Document Date'))
    delivery_date = models.DateField(_('Delivery Date'))

    # Връзки
    supplier = models.ForeignKey(
        'partners.Supplier',
        on_delete=models.PROTECT,
        verbose_name=_('Supplier')
    )
    location = models.ForeignKey(
        'inventory.InventoryLocation',
        on_delete=models.PROTECT,
        verbose_name=_('Location')
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        verbose_name=_('Document Type')
    )

    # Финанси - използваме съществуващия PaymentType
    payment_method = models.ForeignKey(
        'nomenclatures.PaymentType',  # ← ПОПРАВЕНО
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Payment Method')
    )

    # ДДС настройки
    prices_include_vat = models.BooleanField(
        _('Prices Include VAT'),
        default=True,
        help_text=_('Whether entered prices include VAT')
    )

    # Статус и плащане
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=DRAFT
    )
    is_paid = models.BooleanField(_('Is Paid'), default=False)

    # Суми (автоматично изчислявани)
    total_before_discount = models.DecimalField(
        _('Total Before Discount'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_discount = models.DecimalField(
        _('Total Discount'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_after_discount = models.DecimalField(
        _('Total After Discount'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_vat = models.DecimalField(
        _('Total VAT'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    grand_total = models.DecimalField(
        _('Grand Total'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Допълнителна информация
    notes = models.TextField(_('Notes'), blank=True)

    # Одит
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Created By')
    )

    class Meta:
        verbose_name = _('Purchase Document')
        verbose_name_plural = _('Purchase Documents')
        ordering = ['-document_date', '-document_number']

    def __str__(self):
        return f"{self.document_number} ({self.supplier.name}) - {self.document_date}"

    def save(self, *args, **kwargs):

        old_status = None
        if self.pk:
            try:
                old_instance = PurchaseDocument.objects.get(pk=self.pk)
                old_status = old_instance.status
            except PurchaseDocument.DoesNotExist:
                pass

        # ПЪРВО запазваме документа в базата
        super().save(*args, **kwargs)

        # СЛЕД ТОВА изчисляваме сумите (само ако има редове)
        if self.pk:  # Документът вече има primary key
            self.calculate_totals()

            # Ако има промени в сумите, запази отново
            if any([
                self.total_before_discount != 0 or self.total_discount != 0 or
                self.total_after_discount != 0 or self.total_vat != 0 or
                self.grand_total != 0
            ]):
                # Запазваме отново без да извикваме calculate_totals
                PurchaseDocument.objects.filter(pk=self.pk).update(
                    total_before_discount=self.total_before_discount,
                    total_discount=self.total_discount,
                    total_after_discount=self.total_after_discount,
                    total_vat=self.total_vat,
                    grand_total=self.grand_total
                )


            # Създаване на StockMovements САМО при промяна на статуса
            if old_status != self.RECEIVED and self.status == self.RECEIVED:
                self.create_stock_movements()
            elif old_status == self.RECEIVED and self.status in [self.CANCELLED, self.DRAFT]:
                self.delete_stock_movements()

    def calculate_totals(self):
        """Изчислява общите суми от редовете"""
        lines = self.lines.all()

        self.total_before_discount = sum(
            line.quantity * line.unit_price for line in lines
        )
        self.total_discount = sum(line.discount_amount for line in lines)
        self.total_after_discount = self.total_before_discount - self.total_discount

        # ДДС изчисления
        if self.prices_include_vat:
            # Цените включват ДДС
            self.grand_total = self.total_after_discount
            self.total_vat = sum(line.vat_amount for line in lines)
            self.total_after_discount = self.grand_total - self.total_vat
        else:
            # Цените са без ДДС
            self.total_vat = sum(line.vat_amount for line in lines)
            self.grand_total = self.total_after_discount + self.total_vat

    def create_stock_movements(self):
        """Създава InventoryMovements при приемане на документа"""
        from inventory.models import InventoryMovement

        for line in self.lines.all():
            # Използвай количеството в базова единица
            base_quantity = line.quantity_base_unit

            if base_quantity == 0:
                continue

            # Определяме посоката според stock_effect и знака на количеството
            if base_quantity > 0:
                # ПОЛОЖИТЕЛНО КОЛИЧЕСТВО - обикновена логика
                if self.document_type.stock_effect == 1:
                    movement_type = InventoryMovement.IN  # ← Променено
                elif self.document_type.stock_effect == -1:
                    movement_type = InventoryMovement.OUT  # ← Променено
                else:
                    continue  # stock_effect = 0 → няма движение

                actual_quantity = base_quantity
                reverse_indicator = ""

            else:
                # ✅ ОТРИЦАТЕЛНО КОЛИЧЕСТВО - проверяваме allow_reverse_operations
                if not self.document_type.allow_reverse_operations:
                    print(f"❌ SKIP: Negative quantity {base_quantity} not allowed for {self.document_type.name}")
                    continue  # Пропускаме този ред

                print(f"⚠️ REVERSE: Processing negative quantity {base_quantity} for {line.product.code}")

                # Обръщаме посоката
                if self.document_type.stock_effect == 1:
                    movement_type = InventoryMovement.OUT  # ← Променено
                elif self.document_type.stock_effect == -1:
                    movement_type = InventoryMovement.IN  # ← Променено
                else:
                    continue

                actual_quantity = abs(base_quantity)
                reverse_indicator = " (REVERSE)"

            print(f"📦 Creating movement: {line.product.code} = {actual_quantity} ({movement_type}){reverse_indicator}")

            InventoryMovement.objects.create(  # ← Променено
                location=self.location,  # ← warehouse → location
                product=line.product,
                batch_number=line.batch_number,
                quantity=actual_quantity,
                movement_type=movement_type,
                cost_price=line.unit_price_base,  # ← unit_price → cost_price
                source_document_type='PURCHASE',  # ← Ново поле
                source_document_number=self.document_number,  # ← Ново поле
                movement_date=self.delivery_date,  # ← document_date → movement_date
                reason=f"{self.document_type.name} from {self.supplier.name}{reverse_indicator}",
                expiry_date=line.expiry_date,
                created_by=self.created_by
            )

    def delete_stock_movements(self):
        """Изтрива всички движения от този документ и обновява InventoryItems"""
        from inventory.models import InventoryMovement, InventoryItem, InventoryBatch

        print(f"🔍 Търся движения за документ: {self.document_number}")

        # Намери всички движения от този документ
        movements = InventoryMovement.objects.filter(
            source_document_number=self.document_number  # ← Променено
        )

        print(f"📊 Намерени {movements.count()} движения:")
        combinations_to_refresh = []
        for movement in movements:
            print(
                f"  - {movement.product.code} @ {movement.location.code}: {movement.quantity} ({movement.movement_type})")  # ← warehouse → location
            combinations_to_refresh.append({
                'location': movement.location,  # ← warehouse → location
                'product': movement.product,
                'batch_number': movement.batch_number,
                'expiry_date': movement.expiry_date
            })

        # Провери InventoryItem ПРЕДИ изтриване
        for combo in combinations_to_refresh:
            try:
                item_before = InventoryItem.objects.get(  # ← StockLevel → InventoryItem
                    location=combo['location'],  # ← warehouse → location
                    product=combo['product']
                )
                print(
                    f"📦 ПРЕДИ: {item_before.product.code} количество: {item_before.current_qty}")  # ← quantity → current_qty
            except InventoryItem.DoesNotExist:  # ← StockLevel → InventoryItem
                print(f"❌ Няма InventoryItem за {combo['product'].code}")

        # Изтрий движенията
        print("🗑️ Изтривам движения...")
        movements.delete()

        # Обнови InventoryItems и InventoryBatches
        print("🔄 Обновявам InventoryItems...")
        for combo in combinations_to_refresh:
            print(f"   Обновявам: {combo['product'].code} @ {combo['location'].code}")  # ← warehouse → location

            # Обнови InventoryItem
            InventoryItem.refresh_for_combination(  # ← StockLevel → InventoryItem
                location=combo['location'],  # ← warehouse → location
                product=combo['product']
            )

            # Обнови InventoryBatch ако има batch
            if combo['batch_number']:
                InventoryBatch.refresh_for_combination(
                    location=combo['location'],
                    product=combo['product'],
                    batch_number=combo['batch_number'],
                    expiry_date=combo['expiry_date']
                )

            # Провери СЛЕД обновяване
            try:
                item_after = InventoryItem.objects.get(  # ← StockLevel → InventoryItem
                    location=combo['location'],  # ← warehouse → location
                    product=combo['product']
                )
                print(
                    f"📦 СЛЕД: {item_after.product.code} количество: {item_after.current_qty}")  # ← quantity → current_qty
            except InventoryItem.DoesNotExist:  # ← StockLevel → InventoryItem
                print(f"✅ InventoryItem за {combo['product'].code} е изтрит (quantity = 0)")

        print("✅ Готово!")



# === PURCHASE DOCUMENT LINES ===

class PurchaseDocumentLine(models.Model):
    """Редове от документа за доставки"""

    document = models.ForeignKey(
        PurchaseDocument,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Document')
    )
    line_number = models.PositiveIntegerField(_('Line Number'))

    # Продукт информация
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name=_('Product')
    )
    product_name = models.CharField(
        _('Product Name'),
        max_length=255,
        help_text=_('Product name at time of purchase')
    )
    unit = models.ForeignKey(
        'nomenclatures.UnitOfMeasure',
        on_delete=models.PROTECT,
        verbose_name=_('Unit')
    )

    # Количества
    quantity = models.DecimalField(
        _('Quantity'),
        max_digits=12,
        decimal_places=3
    )

    # Цени
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Base unit price from supplier')
    )
    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=0
    )

    # Автоматично изчислявани полета
    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    final_unit_price = models.DecimalField(
        _('Final Unit Price'),
        max_digits=10,
        decimal_places=4,
        default=0
    )
    line_total = models.DecimalField(
        _('Line Total'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Партиди и срокове
    batch_number = models.CharField(
        _('Batch Number'),
        max_length=50,
        null=True,
        blank=True
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True
    )

    # Ценови анализ (динамични полета)
    old_sale_price = models.DecimalField(
        _('Old Sale Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    new_sale_price = models.DecimalField(  # ← НОВО ПОЛЕ
        _('New Sale Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('New selling price to be set')
    )

    suggested_sale_price = models.DecimalField(
        _('Suggested Sale Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    markup_percentage = models.DecimalField(
        _('Markup %'),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )

    quantity_base_unit = models.DecimalField(
        _('Quantity (Base Unit)'),
        max_digits=12,
        decimal_places=3,
        default=0,
        help_text=_('Automatically calculated from quantity and unit conversion')
    )

    unit_price_base = models.DecimalField(
        _('Unit Price (Base Unit)'),
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text=_('Price per base unit - automatically calculated')
    )

    def update_warehouse_price(self):
        """Обновява цената в локацията с новата цена"""
        try:
            from pricing.models import ProductPrice

            # Използвай новата цена вместо suggested
            if self.new_sale_price:
                price_record, created = ProductPrice.objects.get_or_create(
                    location=self.document.location,  # ← warehouse → location
                    product=self.product,
                    defaults={
                        'pricing_method': 'FIXED',  # ← Ново поле
                        'base_price': self.new_sale_price,
                        'effective_price': self.new_sale_price  # ← Ново поле
                    }
                )

                # Винаги обновявай с новата цена при приемане
                if self.document.status == PurchaseDocument.RECEIVED:
                    price_record.base_price = self.new_sale_price
                    price_record.effective_price = self.new_sale_price  # ← Обнови и effective_price
                    price_record.save()

        except Exception as e:
            pass

    class Meta:
        verbose_name = _('Purchase Document Line')
        verbose_name_plural = _('Purchase Document Lines')
        unique_together = ('document', 'line_number')
        ordering = ['line_number']

    def __str__(self):
        return f"{self.document.document_number} / {self.line_number}: {self.product.code}"

    def save(self, *args, **kwargs):
        # Автоматично попълване на product_name
        if not self.product_name:
            self.product_name = self.product.name

        # Автоматично попълване на unit
        if not self.unit_id:
            self.unit = self.product.base_unit

        # ✅ ВАЛИДАЦИЯ ЗА ОТРИЦАТЕЛНИ КОЛИЧЕСТВА
        if self.quantity < 0:
            if not self.document.document_type.allow_reverse_operations:
                raise ValidationError(
                    f"Negative quantities are not allowed for document type "
                    f"'{self.document.document_type.name}'. "
                    f"Quantity: {self.quantity} for product {self.product.code}"
                )
            else:
                print(f"⚠️ REVERSE OPERATION: {self.product.code} = {self.quantity}")

        # Изчисляване на цени
        self.calculate_prices()

        # Анализ на продажни цени
        self.analyze_sale_prices()

        super().save(*args, **kwargs)

    def convert_to_base_unit(self):
        """Конвертира количеството към базова мерна единица"""
        if not self.unit or self.unit == self.product.base_unit:
            return self.quantity

        try:
            packaging = ProductPackaging.objects.get(
                product=self.product,
                unit=self.unit
            )
            return self.quantity * packaging.conversion_factor
        except ProductPackaging.DoesNotExist:
            return self.quantity

    def convert_price_to_base_unit(self):
        """Конвертира цената към базова мерна единица"""
        if not self.unit or self.unit == self.product.base_unit:
            return self.unit_price

        try:
            packaging = ProductPackaging.objects.get(
                product=self.product,
                unit=self.unit
            )
            return self.unit_price / packaging.conversion_factor
        except ProductPackaging.DoesNotExist:
            return self.unit_price

    def calculate_prices(self):
        """Изчислява всички цени в реда"""
        # Предотвратяване на рекурсия в сигналите
        self._calculating = True

        try:
            # ПЪРВО - конвертирай към базова единица
            self.quantity_base_unit = self.convert_to_base_unit()
            self.unit_price_base = self.convert_price_to_base_unit()

            # Отстъпка (върху оригиналната цена и количество)
            self.discount_amount = (self.unit_price * self.quantity * self.discount_percent) / 100

            # Крайна единична цена (в избраната единица)
            self.final_unit_price = self.unit_price * (1 - self.discount_percent / 100)

            # Общо за реда (използвай базовите стойности за точност)
            final_unit_price_base = self.unit_price_base * (1 - self.discount_percent / 100)
            self.line_total = self.quantity_base_unit * final_unit_price_base

            # ДДС
            if self.product.tax_group:
                vat_rate = self.product.tax_group.rate
                if self.document.prices_include_vat:
                    self.vat_amount = self.line_total * vat_rate / (100 + vat_rate)
                else:
                    self.vat_amount = self.line_total * vat_rate / 100
            else:
                self.vat_amount = Decimal('0.00')

        finally:
            self._calculating = False

    def analyze_sale_prices(self):
        """Анализира продажните цени и предлага нови"""
        try:
            from pricing.services import PricingService

            # Текуща продажна цена
            current_price = PricingService.get_sale_price(
                self.document.location,  # ← warehouse → location
                self.product
            )
            self.old_sale_price = current_price

            # Автоматично предложение с markup на локацията (използвай базовата цена)
            location_markup = getattr(self.document.location, 'default_markup_percentage',
                                      30)  # ← warehouse → location с fallback
            final_unit_price_base = self.unit_price_base * (1 - self.discount_percent / 100)
            self.suggested_sale_price = final_unit_price_base * (1 + location_markup / 100)

            # Ако няма зададена нова цена, използвай предложената
            if not self.new_sale_price:
                self.new_sale_price = self.suggested_sale_price

            # Изчисляване на markup процент от новата цена
            if final_unit_price_base > 0 and self.new_sale_price:
                self.markup_percentage = (
                                                 (self.new_sale_price - final_unit_price_base) / final_unit_price_base
                                         ) * 100

        except Exception:
            pass


