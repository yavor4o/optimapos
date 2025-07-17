from django.contrib import admin
from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .models import (
    PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine,
    DeliveryReceipt, DeliveryLine
)

# ===========================
# FORMS
# ===========================

class PurchaseRequestLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequestLine
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        requested_quantity = cleaned_data.get('requested_quantity')
        if requested_quantity is None:
            raise ValidationError({'requested_quantity': _('Requested quantity is required')})
        if requested_quantity <= 0:
            raise ValidationError({'requested_quantity': _('Requested quantity must be positive')})
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Ensure quantity matches requested_quantity
        instance.quantity = instance.requested_quantity
        if commit:
            instance.save()
        return instance


# ===========================
# INLINES
# ===========================

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    form = PurchaseRequestLineForm
    extra = 1
    fields = ('line_number', 'product', 'requested_quantity', 'unit', 'estimated_price')

class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ('line_number', 'product', 'ordered_quantity', 'unit', 'unit_price')

class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1
    fields = ('line_number', 'product', 'received_quantity', 'unit', 'unit_price')

# ===========================
# ADMIN CLASSES
# ===========================

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    list_display = ('line_number', 'product', 'requested_quantity', 'unit')
    search_fields = ('product__name',)

@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = ('line_number', 'product', 'ordered_quantity', 'unit')
    search_fields = ('product__name',)

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ('document_number', 'supplier', 'status', 'document_date')
    search_fields = ('document_number', 'supplier__name')
    inlines = [PurchaseRequestLineInline]

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('document_number', 'supplier', 'status', 'expected_delivery_date')
    search_fields = ('document_number', 'supplier__name')
    inlines = [PurchaseOrderLineInline]

@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = ('document_number', 'supplier', 'status', 'delivery_date')
    search_fields = ('document_number', 'supplier__name')
    inlines = [DeliveryLineInline]