from django import forms
from ..models import ProductGroup

class ProductGroupForm(forms.ModelForm):
    class Meta:
        model = ProductGroup
        fields = ['code', 'name', 'parent', 'sort_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'kt-input w-full', 'maxlength': 20, 'required': True}),
            'name': forms.TextInput(attrs={'class': 'kt-input w-full', 'maxlength': 100, 'required': True}),
            'parent': forms.Select(attrs={'class': 'kt-select w-full'}),
            'sort_order': forms.NumberInput(attrs={'class': 'kt-input w-full', 'min': 0, 'max': 999}),
            'is_active': forms.CheckboxInput(attrs={'class': 'kt-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # по желание: подай help text или доп. атрибути динамично
        self.fields['parent'].required = False
