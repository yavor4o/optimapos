# core/models/company.py - COMPANY & ORGANIZATION MODELS

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .base import UserTrackingModel


class Company(UserTrackingModel):
    """
    Main company/organization information
    Singleton model - only one active company per system
    """

    # Basic information
    name = models.CharField(
        _('Company Name'),
        max_length=200,
        help_text=_('Legal company name')
    )
    legal_name = models.CharField(
        _('Legal Name'),
        max_length=200,
        blank=True,
        help_text=_('Full legal name if different from display name')
    )
    short_name = models.CharField(
        _('Short Name'),
        max_length=50,
        blank=True,
        help_text=_('Abbreviated name for documents and reports')
    )

    # Legal/Tax information
    registration_number = models.CharField(
        _('Registration Number'),
        max_length=50,
        blank=True,
        help_text=_('Company registration number')
    )
    vat_number = models.CharField(
        _('VAT Number'),
        max_length=50,
        blank=True,
        help_text=_('VAT/Tax identification number')
    )
    tax_office = models.CharField(
        _('Tax Office'),
        max_length=100,
        blank=True,
        help_text=_('Responsible tax office')
    )

    # Contact information
    address = models.TextField(
        _('Address'),
        blank=True,
        help_text=_('Full company address')
    )
    city = models.CharField(
        _('City'),
        max_length=100,
        blank=True
    )
    postal_code = models.CharField(
        _('Postal Code'),
        max_length=20,
        blank=True
    )
    country = models.CharField(
        _('Country'),
        max_length=100,
        default='Bulgaria'
    )

    # Contact details
    phone = models.CharField(
        _('Phone'),
        max_length=50,
        blank=True
    )
    email = models.EmailField(
        _('Email'),
        blank=True
    )
    website = models.URLField(
        _('Website'),
        blank=True
    )

    # Visual identity
    logo = models.ImageField(
        _('Company Logo'),
        upload_to='company/logos/',
        null=True,
        blank=True,
        help_text=_('Company logo for documents and interface')
    )
    favicon = models.ImageField(
        _('Favicon'),
        upload_to='company/favicons/',
        null=True,
        blank=True,
        help_text=_('Small icon for browser tabs')
    )

    # Financial settings
    default_currency = models.ForeignKey(
        'nomenclatures.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('Default Currency'),
        help_text=_('Primary currency for the company')
    )
    fiscal_year_start = models.CharField(
        _('Fiscal Year Start'),
        max_length=5,
        default='01-01',
        help_text=_('Format: MM-DD (e.g., 01-01 for January 1st)')
    )

    # System settings
    timezone = models.CharField(
        _('Timezone'),
        max_length=50,
        default='Europe/Sofia',
        help_text=_('Company timezone for date/time calculations')
    )
    date_format = models.CharField(
        _('Date Format'),
        max_length=20,
        default='DD.MM.YYYY',
        choices=[
            ('DD.MM.YYYY', 'DD.MM.YYYY'),
            ('DD/MM/YYYY', 'DD/MM/YYYY'),
            ('YYYY-MM-DD', 'YYYY-MM-DD'),
            ('MM/DD/YYYY', 'MM/DD/YYYY'),
        ]
    )

    # Status
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this company profile is active')
    )

    class Meta:
        verbose_name = _('Company')
        verbose_name_plural = _('Companies')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one active company
        if self.is_active:
            Company.objects.exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Get the active company instance"""
        return cls.objects.filter(is_active=True).first()

    def get_display_name(self):
        """Get appropriate display name"""
        return self.short_name or self.name

    def get_full_address(self):
        """Get formatted full address"""
        parts = [self.address, self.city, self.postal_code, self.country]
        return ', '.join(filter(None, parts))

    def clean(self):
        """Validate company data"""
        super().clean()

        # Validate fiscal year start format
        if self.fiscal_year_start:
            try:
                month, day = self.fiscal_year_start.split('-')
                month, day = int(month), int(day)
                if not (1 <= month <= 12) or not (1 <= day <= 31):
                    raise ValueError
            except (ValueError, TypeError):
                raise ValidationError({
                    'fiscal_year_start': _('Format must be MM-DD (e.g., 01-01)')
                })


class Branch(UserTrackingModel):
    """
    Company branches/locations
    For multi-location businesses
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='branches',
        verbose_name=_('Company')
    )

    # Basic information
    name = models.CharField(
        _('Branch Name'),
        max_length=100,
        help_text=_('Branch or location name')
    )
    code = models.CharField(
        _('Branch Code'),
        max_length=20,
        help_text=_('Short code for identification')
    )

    # Contact information
    address = models.TextField(
        _('Address'),
        blank=True
    )
    city = models.CharField(
        _('City'),
        max_length=100,
        blank=True
    )
    postal_code = models.CharField(
        _('Postal Code'),
        max_length=20,
        blank=True
    )

    phone = models.CharField(
        _('Phone'),
        max_length=50,
        blank=True
    )
    email = models.EmailField(
        _('Email'),
        blank=True
    )

    # Branch manager
    manager = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_branches',
        verbose_name=_('Branch Manager')
    )

    # Settings
    is_headquarters = models.BooleanField(
        _('Is Headquarters'),
        default=False,
        help_text=_('Whether this is the main headquarters')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    class Meta:
        verbose_name = _('Branch')
        verbose_name_plural = _('Branches')
        unique_together = ('company', 'code')
        ordering = ['company', 'name']

    def __str__(self):
        return f"{self.company.name} - {self.name}"

    def save(self, *args, **kwargs):
        # Ensure only one headquarters per company
        if self.is_headquarters:
            Branch.objects.filter(
                company=self.company
            ).exclude(pk=self.pk).update(is_headquarters=False)

        super().save(*args, **kwargs)

    def get_full_address(self):
        """Get formatted full address"""
        parts = [self.address, self.city, self.postal_code]
        return ', '.join(filter(None, parts))


class Department(UserTrackingModel):
    """
    Company departments for organization structure
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='departments',
        verbose_name=_('Company')
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='departments',
        verbose_name=_('Branch'),
        help_text=_('Branch this department belongs to (optional)')
    )

    # Department information
    name = models.CharField(
        _('Department Name'),
        max_length=100
    )
    code = models.CharField(
        _('Department Code'),
        max_length=20
    )
    description = models.TextField(
        _('Description'),
        blank=True
    )

    # Hierarchy
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subdepartments',
        verbose_name=_('Parent Department')
    )

    # Department head
    head = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments',
        verbose_name=_('Department Head')
    )

    # Settings
    cost_center = models.CharField(
        _('Cost Center'),
        max_length=50,
        blank=True,
        help_text=_('Accounting cost center code')
    )
    budget_code = models.CharField(
        _('Budget Code'),
        max_length=50,
        blank=True,
        help_text=_('Budget allocation code')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )

    class Meta:
        verbose_name = _('Department')
        verbose_name_plural = _('Departments')
        unique_together = ('company', 'code')
        ordering = ['company', 'name']

    def __str__(self):
        if self.branch:
            return f"{self.company.name} - {self.branch.name} - {self.name}"
        return f"{self.company.name} - {self.name}"

    def get_full_path(self):
        """Get full department hierarchy path"""
        path = []
        current = self
        while current:
            path.append(current.name)
            current = current.parent
        return ' / '.join(reversed(path))

    def get_all_subdepartments(self):
        """Get all subdepartments recursively"""
        subdepts = list(self.subdepartments.filter(is_active=True))
        for subdept in self.subdepartments.filter(is_active=True):
            subdepts.extend(subdept.get_all_subdepartments())
        return subdepts