# core/models/company.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal


class CompanyManager(models.Manager):
    """Manager for Company with singleton logic"""

    def get_current(self):
        """Get the current (only) company"""
        return self.first()

    def create_if_not_exists(self, **kwargs):
        """Create company only if none exists"""
        if self.exists():
            raise ValidationError("Company already exists. Only one company allowed.")
        return self.create(**kwargs)


class Company(models.Model):
    """
    Company model - Singleton pattern

    Stores main company information including VAT registration status
    which affects entire system VAT behavior.
    """

    # Basic company info
    name = models.CharField(
        _('Company Name'),
        max_length=255,
        help_text=_('Official company name')
    )

    # VAT/Tax information
    vat_number = models.CharField(
        _('VAT Number'),
        max_length=15,
        blank=True,
        help_text=_('Official VAT registration number')
    )

    vat_registered = models.BooleanField(
        _('VAT Registered'),
        default=True,
        help_text=_('Is company registered for VAT? Affects entire system VAT behavior')
    )

    default_vat_rate = models.DecimalField(
        _('Default VAT Rate %'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        help_text=_('Default VAT rate for the country (Bulgaria: 20%)')
    )

    # Contact information
    address = models.TextField(
        _('Address'),
        blank=True,
        help_text=_('Company official address')
    )

    phone = models.CharField(
        _('Phone'),
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        _('Email'),
        blank=True
    )

    # Business information
    registration_number = models.CharField(
        _('Registration Number'),
        max_length=20,
        blank=True,
        help_text=_('Company registration number with court')
    )

    # VAT transition tracking
    vat_registration_date = models.DateField(
        _('VAT Registration Date'),
        null=True,
        blank=True,
        help_text=_('Date when company became VAT registered (for transition tracking)')
    )

    # Audit
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    objects = CompanyManager()

    class Meta:
        verbose_name = _('Company')
        verbose_name_plural = _('Companies')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Enforce singleton pattern"""
        if Company.objects.exists() and not self.pk:
            raise ValidationError(
                _('Only one company record is allowed. Edit the existing company instead.')
            )

        # Auto-set VAT registration date on first VAT registration
        if self.vat_registered and not self.vat_registration_date:
            from django.utils import timezone
            self.vat_registration_date = timezone.now().date()

        super().save(*args, **kwargs)

    def clean(self):
        """Validation"""
        super().clean()

        # VAT number validation
        if self.vat_registered and not self.vat_number.strip():
            raise ValidationError({
                'vat_number': _('VAT number is required for VAT registered companies')
            })

        # Default VAT rate validation
        if self.default_vat_rate < 0 or self.default_vat_rate > 100:
            raise ValidationError({
                'default_vat_rate': _('VAT rate must be between 0% and 100%')
            })

    # =====================
    # BUSINESS METHODS
    # =====================

    @classmethod
    def get_current(cls):
        """Get current company (singleton)"""
        return cls.objects.get_current()

    def is_vat_applicable(self) -> bool:
        """Check if VAT calculations should be applied system-wide"""
        return self.vat_registered

    def get_default_vat_rate(self) -> Decimal:
        """Get default VAT rate for the company"""
        return self.default_vat_rate

    def validate_vat_number(self) -> bool:
        """Validate VAT number format (Bulgarian format)"""
        if not self.vat_number:
            return False

        # Basic Bulgarian VAT number validation
        import re
        # Bulgarian VAT: BG + 9 or 10 digits
        pattern = r'^BG\d{9,10}$'
        return bool(re.match(pattern, self.vat_number.upper()))

    def get_vat_status_display(self) -> str:
        """Get human-readable VAT status"""
        if self.vat_registered:
            return f"VAT Registered ({self.vat_number})" if self.vat_number else "VAT Registered"
        return "Not VAT Registered"

    # =====================
    # SYSTEM INTEGRATION
    # =====================

    def trigger_vat_status_change_revaluation(self):
        """Trigger system-wide revaluation when VAT status changes"""
        if self.vat_registered:
            # TODO: Implement in ФАЗА 4 - VAT transition service
            # from core.services.vat_transition_service import VATTransitionService
            # VATTransitionService.revalue_inventory_for_vat_registration()
            pass
        else:
            # Transition to non-VAT - different logic might be needed
            pass