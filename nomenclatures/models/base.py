from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseNomenclature(models.Model):
    """Базов клас за всички номенклатури"""
    code = models.CharField(
        _('Code'),
        max_length=100,
        unique=True,
        help_text=_('Unique code for quick reference')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        db_index=True
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        db_index=True
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        abstract = True
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # Автоматично правим code uppercase
        if self.code:
            self.code = self.code.upper().strip()
        # Почистваме името от излишни интервали
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)


class ActiveManager(models.Manager):
    """Manager за филтриране само на активни записи"""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)