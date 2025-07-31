from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel
from .base import BaseNomenclature, ActiveManager


class ProductGroup(MPTTModel):
    """Йерархична структура на продуктови групи"""
    code = models.CharField(
        _('Group Code'),
        max_length=20,
        unique=True,
        help_text=_('Unique code like DRINKS, FOOD, etc.')
    )
    name = models.CharField(
        _('Group Name'),
        max_length=100,
        db_index=True
    )
    parent = TreeForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
        on_delete=models.CASCADE,
        verbose_name=_('Parent Group')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        db_index=True
    )
    sort_order = models.IntegerField(
        _('Sort Order'),
        default=0,
        help_text=_('Used for custom ordering in reports and UI')
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class MPTTMeta:
        order_insertion_by = ['sort_order', 'name']

    class Meta:
        verbose_name = _('Product Group')
        verbose_name_plural = _('Product Groups')
        ordering = ['sort_order', 'name']

    def __str__(self):
        # Показваме пълна пътека: Напитки / Безалкохолни / Сокове
        return ' / '.join([a.name for a in self.get_ancestors(include_self=True)])

    def save(self, *args, **kwargs):
        """FIXED: Simple save without complex generation logic"""
        # Само основна нормализация - BaseNomenclature.save() прави останалото
        super().save(*args, **kwargs)




class Brand(BaseNomenclature):
    """Търговски марки/брандове"""
    logo = models.ImageField(
        _('Brand Logo'),
        upload_to='brands/logos/',
        null=True,
        blank=True
    )
    website = models.URLField(
        _('Website'),
        blank=True
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Brand')
        verbose_name_plural = _('Brands')
        ordering = ['name']

    def clean(self):
        # Проверка за уникалност на името (case insensitive)
        if Brand.objects.filter(
                name__iexact=self.name
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                'name': _('Brand with this name already exists.')
            })


class ProductType(BaseNomenclature):
    """Типове продукти за категоризация и анализ"""
    # Предефинирани типове
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

    category = models.CharField(
        _('Category'),
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=FOOD,
        help_text=_('Main category for reporting')
    )

    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Whether products of this type must have expiry dates')
    )

    # Managers
    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _('Product Type')
        verbose_name_plural = _('Product Types')
        ordering = ['category', 'name']