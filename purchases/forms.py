# purchases/forms.py

from decimal import Decimal
from django import forms
from django.forms import formset_factory
from django.core.exceptions import ValidationError
from products.models import Product
from nomenclatures.models import UnitOfMeasure
from partners.models import Supplier
from inventory.models import InventoryLocation
from core.utils.error_codes import PurchaseErrorCodes, ErrorMessages
from core.utils.decimal_utils import round_currency
from .models.deliveries import DeliveryReceipt


class DeliveryReceiptForm(forms.ModelForm):
    """
    🆕 Main form for delivery receipt - includes ALL required fields
    """
    partner_id = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True),
        empty_label="Изберете доставчик...",
        error_messages={
            'required': ErrorMessages.get_message(PurchaseErrorCodes.DELIVERY_PARTNER_REQUIRED),
            'invalid_choice': 'Избраният доставчик не е валиден'
        },
        widget=forms.Select(attrs={
            'class': 'kt-select',
            'data-kt-select': '{}',
            'id': 'partner_id'
        })
    )
    
    location_id = forms.ModelChoiceField(
        queryset=InventoryLocation.objects.filter(is_active=True),
        empty_label="Изберете местоположение...",
        error_messages={
            'required': ErrorMessages.get_message(PurchaseErrorCodes.DELIVERY_LOCATION_REQUIRED),
            'invalid_choice': 'Избраното местоположение не е валидно'
        },
        widget=forms.Select(attrs={
            'class': 'kt-select',
            'data-kt-select': '{}',
            'id': 'location_id'
        })
    )
    
    document_date = forms.DateField(
        error_messages={'required': 'Дата на документа е задължителна'},
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    delivery_date = forms.DateField(
        required=False,
        error_messages={'invalid': 'Невалидна дата на доставка'},
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    supplier_delivery_reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Референция на доставчика'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Бележки'
        })
    )

    class Meta:
        model = DeliveryReceipt
        fields = ['document_date', 'delivery_date', 'supplier_delivery_reference', 'notes']

class DeliveryLineForm(forms.Form):
    """
    Enhanced форма за един ред в документа за доставка
    
    Нови функционалности:
    - Custom валидация с structured error messages
    - Business rules validation
    - Enhanced error context за better UX
    """
    product = forms.ModelChoiceField(
        queryset=Product.objects.active(),
        error_messages={
            'required': ErrorMessages.get_message(PurchaseErrorCodes.DELIVERY_PRODUCT_REQUIRED),
            'invalid_choice': 'Избраният продукт не е валиден'
        },
        widget=forms.Select(attrs={
            'class': 'kt-select product-select w-full',
            'data-kt-select': '{}',
            'data-error-container': 'field'  # За JS error display
        })
    )
    quantity = forms.DecimalField(
        min_value=Decimal('0.001'),
        max_digits=10,
        decimal_places=3,
        error_messages={
            'required': ErrorMessages.get_message(PurchaseErrorCodes.DELIVERY_QUANTITY_INVALID),
            'min_value': 'Количеството трябва да е поне 0.001',
            'invalid': 'Въведете валидно число за количество',
            'max_digits': 'Количеството е твърде голямо',
            'max_decimal_places': 'Максимум 3 десетични знака за количество'
        },
        widget=forms.NumberInput(attrs={
            'class': 'quantity-input w-20 text-right',
            'step': '0.001',
            'placeholder': '0',
            'min': '0.001',
            'data-error-container': 'field'
        })
    )
    unit_price = forms.DecimalField(
        min_value=Decimal('0'),
        max_digits=10,
        decimal_places=2,
        required=False,
        error_messages={
            'min_value': 'Цената не може да е отрицателна',
            'invalid': 'Въведете валидна цена',
            'max_digits': 'Цената е твърде висока',
            'max_decimal_places': 'Максимум 2 десетични знака за цена'
        },
        widget=forms.NumberInput(attrs={
            'class': 'price-input w-24 text-right',
            'step': '0.01',
            'placeholder': 'Auto',
            'min': '0',
            'data-error-container': 'field'
        })
    )
    unit = forms.ModelChoiceField(
        queryset=UnitOfMeasure.objects.filter(is_active=True),
        required=False,
        error_messages={
            'invalid_choice': 'Избраната мерна единица не е валидна'
        },
        widget=forms.Select(attrs={
            'class': 'kt-select unit-select w-20',
            'data-kt-select': '{}',
            'data-error-container': 'field'
        })
    )
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.HiddenInput()
    )

    def clean_quantity(self):
        """Additional quantity-specific validation"""
        quantity = self.cleaned_data.get('quantity')
        
        if quantity:
            # Round to 3 decimal places for consistency
            quantity = round(quantity, 3)
            
            # Business rule: reasonable quantity ranges per type
            if quantity > Decimal('9999.999'):
                raise ValidationError('Количеството превишава максимално позволеното (9999.999)')

        return quantity

    def clean(self):
        """
        🆕 Enhanced cross-field валидация with business rules
        """
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')
        unit = cleaned_data.get('unit')

        # Business rule validation
        errors = {}

        # 1. Product-related validation
        if product:
            # Check if product is purchasable
            if not getattr(product, 'is_purchasable', True):
                errors['product'] = 'Този продукт не може да се поръчва'

            # Check if product is active
            if not getattr(product, 'is_active', True):
                errors['product'] = 'Този продукт не е активен'
                
            # 🆕 PIECE product quantity validation
            if product.unit_type == Product.PIECE and quantity is not None:
                if quantity != int(quantity):
                    errors['quantity'] = 'Въведете валидно количество, За бройкови артикули числото трябва да е цяло!'

        # 2. Unit consistency validation
        if product and unit:
            # Verify unit is compatible with product
            if hasattr(product, 'is_unit_compatible'):
                if not product.is_unit_compatible(unit):
                    errors['unit'] = f'Мерната единица {unit} не е съвместима с продукта'

        # 3. Mandatory field relationships
        if product and not quantity:
            errors['quantity'] = 'Количеството е задължително когато е избран продукт'
        
        if product and unit_price is None:
            errors['unit_price'] = 'Цената е задължителна когато е избран продукт'

        if errors:
            # Create structured ValidationError for better handling
            raise ValidationError(errors)

        return cleaned_data

    def clean_unit_price(self):
        """Additional price-specific validation"""
        unit_price = self.cleaned_data.get('unit_price')
        
        if unit_price is not None:
            # Round to currency precision
            unit_price = round_currency(unit_price)
            
            # Business validation for reasonable prices
            if unit_price > Decimal('99999.99'):
                raise ValidationError('Цената превишава максимално позволената (99,999.99)')

        return unit_price

    def has_warnings(self) -> bool:
        """Check if form has non-blocking warnings"""
        return any(key.startswith('_') and key.endswith('_warning') 
                  for key in self.cleaned_data)

    def get_warnings(self) -> dict:
        """Get all warning messages"""
        if not hasattr(self, 'cleaned_data'):
            return {}
        
        return {key.replace('_', '').replace('warning', ''): value 
                for key, value in self.cleaned_data.items() 
                if key.startswith('_') and key.endswith('_warning')}

    def get_calculated_total(self) -> Decimal:
        """Get calculated line total if available"""
        if hasattr(self, 'cleaned_data'):
            return self.cleaned_data.get('_calculated_total', Decimal('0'))
        return Decimal('0')

# "Фабрика", която създава колекция от DeliveryLineForm
DeliveryLineFormSet = formset_factory(
    DeliveryLineForm,
    extra=0,  # Започваме с 0 реда, JavaScript ще ги добавя динамично
    can_delete=True # Позволява изтриване (полезно за edit формата)
)