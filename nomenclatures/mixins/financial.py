# nomenclatures/mixins/financial.py
"""
Financial Mixins - EXTRACTED FROM purchases.models.base
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal



class FinancialMixin(models.Model):
    """
    Financial fields mixin - REFACTORED VERSION

    ВАЖНО: Не прави изчисления! Само държи полета.
    Всички изчисления се правят от VATCalculationService
    """

    # === TOTALS (всички суми се записват БЕЗ ДДС в базата) ===
    subtotal = models.DecimalField(
        _('Subtotal'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total before VAT and discounts')
    )

    discount_total = models.DecimalField(
        _('Discount Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total discount amount')
    )

    vat_total = models.DecimalField(
        _('VAT Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total VAT amount')
    )

    total = models.DecimalField(
        _('Total'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Final total including VAT')
    )

    # === VAT SETTINGS ===
    prices_entered_with_vat = models.BooleanField(
        _('Prices Include VAT'),
        null=True,
        blank=True,
        help_text=_('Override location settings. NULL means use location defaults')
    )

    class Meta:
        abstract = True

    def recalculate_totals(self, save=True):
        """
        Преизчислява всички totals от линиите
        Делегира на VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService

        # Делегира изчислението
        totals = VATCalculationService.recalculate_document_totals(self)

        # Update полетата
        self.subtotal = totals['subtotal']
        self.vat_total = totals['vat_total']
        self.discount_total = totals['discount_total']
        self.total = totals['total']

        if save:
            self.save(update_fields=['subtotal', 'vat_total', 'discount_total', 'total'])

        return totals

    def get_price_entry_mode(self) -> bool:
        """
        Делегира на VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        return VATCalculationService.get_price_entry_mode(self)

    def validate_totals(self) -> bool:
        """
        Валидира че totals са правилни
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService
        is_valid, error = VATCalculationService.validate_vat_consistency(self)
        if not is_valid:
            raise ValueError(f"VAT calculation error: {error}")
        return is_valid


class FinancialLineMixin(models.Model):
    """
    Financial fields for document lines - REFACTORED VERSION

    ВАЖНО: Не прави изчисления! Само държи полета.
    """

    # === PRICES (всички цени БЕЗ ДДС в базата) ===
    entered_price = models.DecimalField(
        _('Entered Price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Price as entered by user (may include VAT)')
    )

    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Unit price WITHOUT VAT (stored value)')
    )

    unit_price_with_vat = models.DecimalField(
        _('Unit Price with VAT'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Unit price INCLUDING VAT (calculated)')
    )

    # === VAT ===
    vat_rate = models.DecimalField(
        _('VAT Rate'),
        max_digits=5,
        decimal_places=3,
        default=Decimal('0.200'),
        help_text=_('VAT rate (0.20 = 20%)')
    )

    vat_amount = models.DecimalField(
        _('VAT Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('VAT amount for this line')
    )

    # === DISCOUNTS ===
    discount_percent = models.DecimalField(
        _('Discount %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Discount percentage')
    )

    discount_amount = models.DecimalField(
        _('Discount Amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Discount amount')
    )

    # === TOTALS ===
    net_amount = models.DecimalField(
        _('Net Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount excluding VAT')
    )

    gross_amount = models.DecimalField(
        _('Gross Amount'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Line amount including VAT')
    )

    class Meta:
        abstract = True

    def get_quantity_for_calculation(self) -> Decimal:
        """
        Връща количеството за изчисления
        Override в наследниците според техните полета
        """
        # За PurchaseRequestLine -> requested_quantity
        if hasattr(self, 'requested_quantity'):
            return self.requested_quantity or Decimal('1')

        # За PurchaseOrderLine -> ordered_quantity
        if hasattr(self, 'ordered_quantity'):
            return self.ordered_quantity or Decimal('1')

        # За DeliveryLine -> received_quantity
        if hasattr(self, 'received_quantity'):
            return self.received_quantity or Decimal('1')

        # Default
        return Decimal('1')

    def process_entered_price(self):
        """
        ✅ FIXED: Обработва въведената цена със unified VATCalculationService
        """
        from nomenclatures.services.vat_calculation_service import VATCalculationService

        # Намери entered_price
        entered_price = getattr(self, 'entered_price', None)
        if entered_price is None:  # ✅ Само ако няма стойност
            return

        # Намери quantity
        if hasattr(self, 'requested_quantity'):
            quantity = self.requested_quantity
        elif hasattr(self, 'ordered_quantity'):
            quantity = self.ordered_quantity
        elif hasattr(self, 'received_quantity'):
            quantity = self.received_quantity
        else:
            quantity = Decimal('1')

        if not quantity:
            return

        try:
            calc_result = VATCalculationService.calculate_line_totals(
                line=self,
                entered_price=entered_price,
                quantity=quantity,
                document=getattr(self, 'document', None)
            )

            # Apply results
            if hasattr(self, 'unit_price'):
                self.unit_price = calc_result['unit_price']
            if hasattr(self, 'vat_rate'):
                self.vat_rate = calc_result['vat_rate']
            if hasattr(self, 'vat_amount'):
                self.vat_amount = calc_result['vat_amount']
            if hasattr(self, 'net_amount'):
                self.net_amount = calc_result['net_amount']
            if hasattr(self, 'gross_amount'):
                self.gross_amount = calc_result['gross_amount']

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"VAT calculation failed: {e}")

    def save(self, *args, **kwargs):
        """
        Преизчислява при save
        """
        # Изчисли преди save
        if self.entered_price is not None or self.unit_price:
            self.process_entered_price()

        super().save(*args, **kwargs)

        # Update document totals след save
        if hasattr(self, 'document') and self.document:
            if hasattr(self.document, 'recalculate_totals'):
                self.document.recalculate_totals(save=True)

