# nomenclatures/forms/product.py
from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import ProductGroup, Brand


class ProductGroupForm(forms.ModelForm):
    """Form for creating and editing Product Groups with Taiwan CSS v9 styling"""

    class Meta:
        model = ProductGroup
        fields = ['code', 'name', 'parent', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'kt-input',
                'placeholder': _('Enter group code'),
                'maxlength': 20,
                'required': True,
            }),
            'name': forms.TextInput(attrs={
                'class': 'kt-input',
                'placeholder': _('Enter group name'),
                'maxlength': 100,
                'required': True,
            }),
            'parent': forms.Select(attrs={
                'class': 'kt-select',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'kt-input',
                'placeholder': '0',
                'min': 0,
                'max': 999,
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'kt-checkbox',
            }),
        }
        labels = {
            'code': _('Group Code'),
            'name': _('Group Name'),
            'parent': _('Parent Group'),
            'sort_order': _('Sort Order'),
            'is_active': _('Is Active'),
        }
        help_texts = {
            'code': _('Unique identifier (e.g., DRINKS, FOOD)'),
            'name': _('Display name for the group'),
            'parent': _('Leave empty for root level group'),
            'sort_order': _('Lower numbers appear first'),
            'is_active': _('Inactive groups are hidden from selection'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Parent field customization
        self.fields['parent'].required = False
        self.fields['parent'].empty_label = _('-- Root Level Group --')

        # Filter parent choices to exclude self and descendants
        if self.instance and self.instance.pk:
            descendants = self.instance.get_descendants(include_self=True)
            self.fields['parent'].queryset = ProductGroup.objects.exclude(
                pk__in=descendants.values_list('pk', flat=True)
            )

        # Set default values
        if not self.instance.pk:
            self.fields['is_active'].initial = True
            self.fields['sort_order'].initial = 0

    def clean_code(self):
        """Validate code field"""
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper().strip()
            # Check for uniqueness
            queryset = ProductGroup.objects.filter(code__iexact=code)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError(_('A group with this code already exists.'))
        return code

    def clean_name(self):
        """Validate name field"""
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            # Check for uniqueness within same parent
            parent = self.cleaned_data.get('parent')
            queryset = ProductGroup.objects.filter(name__iexact=name, parent=parent)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError(
                    _('A group with this name already exists under the same parent.')
                )
        return name

    def clean_parent(self):
        """Validate parent field"""
        parent = self.cleaned_data.get('parent')
        if parent and self.instance.pk:
            # Prevent circular references
            if parent == self.instance:
                raise forms.ValidationError(_('A group cannot be its own parent.'))

            # Prevent setting a descendant as parent
            if parent in self.instance.get_descendants():
                raise forms.ValidationError(
                    _('Cannot set a descendant group as parent.')
                )

        return parent

    def save(self, commit=True):
        """Custom save with proper code normalization"""
        instance = super().save(commit=False)

        # Normalize code
        if instance.code:
            instance.code = instance.code.upper().strip()

        # Normalize name
        if instance.name:
            instance.name = instance.name.strip()

        if commit:
            instance.save()

        return instance


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['code', 'name', 'logo', 'website', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'kt-input',
                'placeholder': _('e.g., COCA, PEPSI'),
            }),
            'name': forms.TextInput(attrs={
                'class': 'kt-input',
                'placeholder': _('e.g., Coca-Cola, Pepsi'),
            }),
            'website': forms.URLInput(attrs={
                'class': 'kt-input',
                'placeholder': 'https://example.com',
            }),
            'logo': forms.FileInput(attrs={
                'class': 'kt-input',
                'accept': 'image/*',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'kt-checkbox',
            }),
        }
        help_texts = {
            'code': _('Unique code for the brand (e.g., COCA)'),
            'name': _('Full brand name (e.g., Coca-Cola)'),
            'logo': _('Upload brand logo (JPG, PNG, etc.)'),
            'website': _('Official brand website'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Маркираме задължителните полета
        self.fields['code'].required = True
        self.fields['name'].required = True

        # Добавяме * към labels на задължителните полета
        for field_name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"

    def clean_code(self):
        """Валидация на кода - uppercase и уникалност"""
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper().strip()

            # Проверка за уникалност
            qs = Brand.objects.filter(code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(_('Brand with this code already exists.'))

        return code

    def clean_name(self):
        """Валидация на името - уникалност (case insensitive)"""
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()

            # Проверка за уникалност (case insensitive)
            qs = Brand.objects.filter(name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(_('Brand with this name already exists.'))

        return name