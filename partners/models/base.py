from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class Weekday(models.TextChoices):
    """Унифицирани дни от седмицата"""
    MONDAY = 'mon', _('Monday')
    TUESDAY = 'tue', _('Tuesday')
    WEDNESDAY = 'wed', _('Wednesday')
    THURSDAY = 'thu', _('Thursday')
    FRIDAY = 'fri', _('Friday')
    SATURDAY = 'sat', _('Saturday')
    SUNDAY = 'sun', _('Sunday')


class PartnerBase(models.Model):
    """Базов клас за партньори (Supplier/Customer)"""

    code = models.CharField(
        _('Partner Code'),
        max_length=20,
        unique=True,
        help_text=_('Short unique code for this partner (e.g. ABC, PIXEL)')
    )

    # Основни данни
    name = models.CharField(_('Name'), max_length=255)

    # Данъчни данни
    vat_number = models.CharField(_('VAT/BULSTAT'), max_length=20, blank=True)
    vat_registered = models.BooleanField(_('VAT Registered'), default=False)

    # Контактна информация
    contact_person = models.CharField(_('Contact Person'), max_length=100, blank=True)
    city = models.CharField(_('City'), max_length=100, blank=True)
    address = models.TextField(_('Address'), blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)

    # Статус
    is_active = models.BooleanField(_('Is Active'), default=True)
    notes = models.TextField(_('Notes'), blank=True)

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        abstract = True

    def clean(self):
        """Базова валидация"""
        super().clean()

        # Почистване на полетата
        if self.name:
            self.name = self.name.strip()
        if self.vat_number:
            self.vat_number = self.vat_number.strip().upper()
        if self.email:
            self.email = self.email.strip().lower()

        # Валидация
        if not self.name.strip():
            raise ValidationError({'name': _('Name cannot be empty')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PartnerScheduleBase(models.Model):
    """Базов клас за графици на партньори"""

    day = models.CharField(_('Day'), max_length=3, choices=Weekday.choices)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.get_day_display()}"