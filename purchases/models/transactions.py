# purchases/models/transactions.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .base import BaseDocumentLine, LineManager
from .procurement import PurchaseDocument


class PurchaseDocumentLine(BaseDocumentLine):
    """Ред от purchase документ"""

    # Връзка с документа
    document = models.ForeignKey(
        PurchaseDocument,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Document')
    )

    # Ценообразуване - анализ и предложения
    old_sale_price = models.DecimalField(
        _('Current Sale Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Current selling price before this purchase')
    )
    new_sale_price = models.DecimalField(
        _('Suggested Sale Price'),
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('Suggested selling price based on purchase cost')
    )
    markup_percentage = models.DecimalField(
        _('Markup Percentage'),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Calculated markup percentage')
    )

    # Специализирани полета за purchases
    received_quantity = models.DecimalField(
        _('Received Quantity'),
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text=_('Actually received quantity (may differ from ordered)')
    )

    # Quality control
    quality_approved = models.BooleanField(
        _('Quality Approved'),
        default=True,
        help_text=_('Whether the received goods passed quality control')
    )
    quality_notes = models.TextField(
        _('Quality Notes'),
        blank=True,
        help_text=_('Notes about quality issues or inspections')
    )

    # Managers
    objects = LineManager()

    class Meta:
        verbose_name = _('Purchase Document Line')
        verbose_name_plural = _('Purchase Document Lines')
        unique_together = ('document', 'line_number')
        ordering = ['document', 'line_number']
        indexes = [
            models.Index(fields=['document', 'line_number']),
            models.Index(fields=['product', 'document']),
            models.Index(fields=['batch_number']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - Line {self.line_number}: {self.product.code}"

    def clean(self):
        """Допълнителни валидации за purchase line"""
        super().clean()

        # Проверяваме дали received quantity не е повече от ordered
        if self.received_quantity > self.quantity:
            raise ValidationError({
                'received_quantity': _('Received quantity cannot exceed ordered quantity')
            })

        # Batch number е задължителен ако document type го изисква
        if (self.document and self.document.document_type and
                self.document.document_type.requires_batch and not self.batch_number):
            raise ValidationError({
                'batch_number': _('Batch number is required for this document type')
            })

        # Expiry date е задължителна ако document type го изисква
        if (self.document and self.document.document_type and
                self.document.document_type.requires_expiry and not self.expiry_date):
            raise ValidationError({
                'expiry_date': _('Expiry date is required for this document type')
            })

        # Проверяваме дали unit-а е валиден за продукта
        if self.product and self.unit:
            valid_units = [self.product.base_unit]
            if hasattr(self.product, 'packagings'):
                valid_units.extend([p.unit for p in self.product.packagings.all()])

            if self.unit not in valid_units:
                raise ValidationError({
                    'unit': _('This unit is not valid for the selected product')
                })

    def save(self, *args, **kwargs):
        """Базова логика при записване - само data integrity"""

        if self.received_quantity == 0 and self.quantity > 0:
            self.received_quantity = self.quantity
        super().save(*args, **kwargs)

    def calculate_pricing_suggestions(self):
        """Изчислява предложения за продажни цени"""
        try:
            from pricing.services import PricingService

            # Вземаме текущата продажна цена
            current_price = PricingService.get_sale_price(
                location=self.document.location,
                product=self.product
            )
            self.old_sale_price = current_price

            # Изчисляваме markup на база default за location-а
            default_markup = getattr(self.document.location, 'default_markup_percentage', 30)

            # Предлагаме нова цена с markup
            self.new_sale_price = self.final_unit_price * (1 + default_markup / 100)

            # Изчисляваме markup процента
            if self.final_unit_price > 0:
                self.markup_percentage = ((self.new_sale_price - self.final_unit_price) / self.final_unit_price) * 100

            # Записваме промените с отделен save за да избегнем рекурсия
            PurchaseDocumentLine.objects.filter(pk=self.pk).update(
                old_sale_price=self.old_sale_price,
                new_sale_price=self.new_sale_price,
                markup_percentage=self.markup_percentage
            )

        except Exception as e:
            # Ако има грешка, просто продължаваме без pricing suggestions
            pass

    def apply_suggested_price(self):
        """Прилага предложената продажна цена към продукта"""
        if not self.new_sale_price:
            raise ValidationError("No suggested price available")

        try:
            from pricing.models import ProductPrice

            # Създаваме или обновяваме ProductPrice за продукта в location-а
            price_record, created = ProductPrice.objects.get_or_create(
                location=self.document.location,
                product=self.product,
                defaults={
                    'base_price': self.new_sale_price,
                    'effective_price': self.new_sale_price,
                    'pricing_method': 'MARKUP',
                    'markup_percentage': self.markup_percentage or Decimal('30'),
                    'is_active': True
                }
            )

            if not created:
                # Обновяваме съществуващия price record
                price_record.base_price = self.new_sale_price
                price_record.effective_price = self.new_sale_price
                price_record.markup_percentage = self.markup_percentage or Decimal('30')
                price_record.pricing_method = 'MARKUP'
                price_record.last_cost_update = timezone.now()
                price_record.save()

            return True

        except Exception as e:
            raise ValidationError(f"Error updating price: {str(e)}")

    def get_variance_percentage(self):
        """Изчислява разликата между поръчано и получено количество"""
        if self.quantity == 0:
            return Decimal('0.00')

        variance = ((self.received_quantity - self.quantity) / self.quantity) * 100
        return variance

    def get_variance_amount(self):
        """Изчислява стойностната разлика между поръчано и получено"""
        quantity_diff = self.received_quantity - self.quantity
        return quantity_diff * self.final_unit_price

    def is_fully_received(self):
        """Проверява дали реда е напълно получен"""
        return self.received_quantity >= self.quantity

    def is_over_received(self):
        """Проверява дали е получено повече от поръчаното"""
        return self.received_quantity > self.quantity

    def is_under_received(self):
        """Проверява дали е получено по-малко от поръчаното"""
        return self.received_quantity < self.quantity

    def get_cost_per_base_unit(self):
        """Връща себестойността за базова единица"""
        return self.unit_price_base

    def get_total_cost_base_unit(self):
        """Връща общата себестойност в базови единици"""
        return self.received_quantity * self.get_cost_per_base_unit()

    def create_quality_issue(self, issue_description, severity='LOW'):
        """Създава quality issue запис"""
        self.quality_approved = False
        self.quality_notes = f"ISSUE: {issue_description}\n{self.quality_notes}"
        self.save(update_fields=['quality_approved', 'quality_notes'])

    def get_expiry_status(self):
        """Връща статуса на срока на годност"""
        if not self.expiry_date:
            return 'no_expiry'



        today = timezone.now().date()
        days_to_expiry = (self.expiry_date - today).days

        if days_to_expiry < 0:
            return 'expired'
        elif days_to_expiry <= 7:
            return 'expires_soon'
        elif days_to_expiry <= 30:
            return 'expires_this_month'
        else:
            return 'good'

    def get_expiry_badge(self):
        """Връща HTML badge за срока на годност"""
        status = self.get_expiry_status()

        badges = {
            'expired': '<span style="background-color: #DC3545; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">EXPIRED</span>',
            'expires_soon': '<span style="background-color: #FFC107; color: black; padding: 2px 6px; border-radius: 3px; font-size: 11px;">EXPIRES SOON</span>',
            'expires_this_month': '<span style="background-color: #FD7E14; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">THIS MONTH</span>',
            'good': '<span style="background-color: #28A745; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">GOOD</span>',
            'no_expiry': '<span style="background-color: #6C757D; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">NO EXPIRY</span>'
        }

        return badges.get(status, badges['no_expiry'])


class PurchaseAuditLog(models.Model):
    """Одит лог за промени в purchase документи"""

    # Типове промени
    CREATE = 'create'
    UPDATE = 'update'
    CONFIRM = 'confirm'
    RECEIVE = 'receive'
    CANCEL = 'cancel'
    PRICE_UPDATE = 'price_update'

    ACTION_CHOICES = [
        (CREATE, _('Created')),
        (UPDATE, _('Updated')),
        (CONFIRM, _('Confirmed')),
        (RECEIVE, _('Received')),
        (CANCEL, _('Cancelled')),
        (PRICE_UPDATE, _('Price Updated')),
    ]

    # Основна информация
    document = models.ForeignKey(
        PurchaseDocument,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name=_('Document')
    )
    action = models.CharField(
        _('Action'),
        max_length=20,
        choices=ACTION_CHOICES
    )
    timestamp = models.DateTimeField(_('Timestamp'), auto_now_add=True)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        verbose_name=_('User')
    )

    # Детайли за промяната
    field_name = models.CharField(
        _('Field Name'),
        max_length=50,
        blank=True
    )
    old_value = models.TextField(_('Old Value'), blank=True)
    new_value = models.TextField(_('New Value'), blank=True)
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Purchase Audit Log')
        verbose_name_plural = _('Purchase Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['document', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.document.document_number} - {self.get_action_display()} by {self.user.username}"

    @classmethod
    def log_action(cls, document, action, user, field_name=None, old_value=None, new_value=None, notes=None):
        """Създава audit log запис"""
        return cls.objects.create(
            document=document,
            action=action,
            user=user,
            field_name=field_name or '',
            old_value=str(old_value) if old_value else '',
            new_value=str(new_value) if new_value else '',
            notes=notes or ''
        )