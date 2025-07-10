from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class ProductType(models.Model):
    """Product type classification"""
    FOOD = 'FOOD'
    NON_FOOD = 'NONFOOD'
    TOBACCO = 'TOBACCO'
    ALCOHOL = 'ALCOHOL'
    SERVICE = 'SERVICE'

    CATEGORY_CHOICES = [
        (FOOD, _('Food Products')),
        (NON_FOOD, _('Non-Food Products')),
        (TOBACCO, _('Tobacco Products')),
        (ALCOHOL, _('Alcoholic Beverages')),
        (SERVICE, _('Services')),
    ]

    code = models.CharField(_('Code'), max_length=20, unique=True)
    name = models.CharField(_('Name'), max_length=100)
    category = models.CharField(
        _('Category'),
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=FOOD
    )
    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False
    )
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Product Type')
        verbose_name_plural = _('Product Types')
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProductGroup(models.Model):
    """Product group classification (simplified - no MPTT for now)"""
    code = models.CharField(_('Code'), max_length=20, unique=True)
    name = models.CharField(_('Name'), max_length=100)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='children'
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    sort_order = models.IntegerField(_('Sort Order'), default=0)

    class Meta:
        verbose_name = _('Product Group')
        verbose_name_plural = _('Product Groups')
        ordering = ['sort_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} / {self.name}"
        return self.name


class Brand(models.Model):
    """Product brands"""
    code = models.CharField(_('Code'), max_length=20, unique=True)
    name = models.CharField(_('Name'), max_length=100, unique=True)
    logo = models.ImageField(
        _('Logo'),
        upload_to='brands/logos/',
        null=True,
        blank=True
    )
    website = models.URLField(_('Website'), blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Brand')
        verbose_name_plural = _('Brands')
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.code:
            self.code = self.code.upper().strip()
        if self.name:
            self.name = self.name.strip()