# core/services/company_service.py
from typing import Optional, Dict
from decimal import Decimal
from django.core.exceptions import ValidationError


class CompanyService:
    """
    Service for company-related VAT operations
    """

    @staticmethod
    def get_current_company():
        """Get the current company instance"""
        from core.models.company import Company
        return Company.get_current()

    @staticmethod
    def is_vat_applicable() -> bool:
        """
        Check if VAT calculations should be applied system-wide

        Returns:
            bool: True if company is VAT registered, False otherwise
        """
        company = CompanyService.get_current_company()
        return company and company.is_vat_applicable()

    @staticmethod
    def get_default_vat_rate() -> Decimal:
        """
        Get default VAT rate for the company

        Returns:
            Decimal: Default VAT rate percentage
        """
        company = CompanyService.get_current_company()
        if company:
            return company.get_default_vat_rate()
        return Decimal('20.00')  # Bulgaria default

    @staticmethod
    def get_vat_status_context() -> Dict:
        """
        Get complete VAT status context for the company

        Returns:
            Dict: Complete company VAT information
        """
        company = CompanyService.get_current_company()

        if not company:
            return {
                'company_exists': False,
                'vat_registered': False,
                'vat_applicable': False,
                'default_vat_rate': Decimal('20.00'),
                'vat_number': None,
                'company_name': None
            }

        return {
            'company_exists': True,
            'vat_registered': company.vat_registered,
            'vat_applicable': company.is_vat_applicable(),
            'default_vat_rate': company.get_default_vat_rate(),
            'vat_number': company.vat_number,
            'company_name': company.name,
            'vat_registration_date': company.vat_registration_date
        }

    @staticmethod
    def validate_company_setup() -> Dict:
        """
        Validate company setup for VAT operations

        Returns:
            Dict: Validation results with issues and warnings
        """
        issues = []
        warnings = []

        company = CompanyService.get_current_company()

        if not company:
            issues.append("No company configured. Create company first.")
            return {
                'valid': False,
                'issues': issues,
                'warnings': warnings
            }

        # VAT registration validation
        if company.vat_registered:
            if not company.vat_number:
                warnings.append("VAT registered but no VAT number provided")
            elif not company.validate_vat_number():
                warnings.append("VAT number format appears invalid")

        # Basic info validation
        if not company.name:
            issues.append("Company name is required")

        if company.default_vat_rate < 0 or company.default_vat_rate > 100:
            issues.append("Default VAT rate must be between 0% and 100%")

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }