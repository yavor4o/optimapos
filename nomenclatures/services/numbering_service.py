# nomenclatures/services/numbering_service.py

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from typing import  Dict, Any
import logging

logger = logging.getLogger(__name__)


class NumberingService:


    @staticmethod
    def generate_document_number(document_type, location=None, user=None) -> str:
        """
        Генерира номер на документ според настройките

        ПРИОРИТЕТ:
        1. User preference (ако е зададен)
        2. Location assignment (ако е зададен)
        3. Default config за document type
        4. Fallback стратегия

        Args:
            document_type: DocumentType instance
            location: Location instance (optional)
            user: User instance (optional)

        Returns:
            str: Генериран номер на документ

        Raises:
            ValidationError: При проблеми с генерирането
        """
        try:
            # Lazy import за избягване на circular imports
            config = NumberingService._get_numbering_config(document_type, location, user)

            if config:
                return NumberingService._generate_from_config(config)
            else:
                logger.warning(f"No numbering config found for {document_type}, using fallback")
                return NumberingService._generate_fallback_number(document_type)

        except Exception as e:
            logger.error(f"Error generating document number: {e}")
            return NumberingService._generate_emergency_fallback(document_type)

    @staticmethod
    def _get_numbering_config(document_type, location=None, user=None):
        """
        Намери правилната numbering configuration

        Lazy loading pattern - импортваме модела само при нужда
        """
        try:
            # Lazy import - избягваме circular dependency
            from ..models import NumberingConfiguration
            from ..models.numbering import get_numbering_config_for_document

            return get_numbering_config_for_document(document_type, location, user)

        except ImportError as e:
            logger.warning(f"NumberingConfiguration not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting numbering config: {e}")
            return None

    @staticmethod
    def _generate_from_config(config) -> str:
        """
        Генерира номер от NumberingConfiguration

        THREAD-SAFE: Използва database transaction за atomicity
        """
        try:
            with transaction.atomic():
                # Lock реда за update (prevent race conditions)
                locked_config = config.__class__.objects.select_for_update().get(pk=config.pk)

                # Increment counter
                locked_config.current_number += 1

                # Check max_number constraint
                if locked_config.max_number and locked_config.current_number > locked_config.max_number:
                    raise ValidationError(f"Number limit exceeded: {locked_config.max_number}")

                # Check yearly reset
                current_year = timezone.now().year
                if locked_config.reset_yearly and locked_config.last_reset_year != current_year:
                    locked_config.current_number = 1
                    locked_config.last_reset_year = current_year

                # Save new counter
                locked_config.save(update_fields=['current_number', 'last_reset_year'])

                # Format the number
                return NumberingService._format_number(
                    locked_config.prefix,
                    locked_config.current_number,
                    locked_config.digits_count,
                    locked_config.numbering_type
                )

        except Exception as e:
            logger.error(f"Error generating from config: {e}")
            raise ValidationError(f"Number generation failed: {e}")

    @staticmethod
    def _format_number(prefix: str, number: int, digits_count: int, numbering_type: str) -> str:
        """
        Форматира номера според правилата

        BULGARIAN FISCAL:
        - Фискални: точно 10 цифри, БЕЗ префикс (1000000001)
        - Вътрешни: гъвкави (REQ0001, PO000023)
        """
        if numbering_type == 'fiscal':
            # Фискални документи - Bulgarian law: точно 10 цифри
            if digits_count != 10:
                logger.warning(f"Fiscal documents require 10 digits, got {digits_count}")
                digits_count = 10

            if prefix:
                logger.warning(f"Fiscal documents cannot have prefix, ignoring '{prefix}'")
                prefix = ''

        # Pad с нули
        padded_number = str(number).zfill(digits_count)

        # Комбинирай prefix + number
        if prefix:
            return f"{prefix}{padded_number}"
        else:
            return padded_number

    @staticmethod
    def _generate_fallback_number(document_type) -> str:
        """
        Fallback стратегия когато няма NumberingConfiguration

        Използва document_type.code + timestamp
        """
        try:
            # Опитай да намериш code в document_type
            prefix = getattr(document_type, 'code', None)
            if not prefix:
                prefix = document_type.type_key[:3].upper()

            # Timestamp-based номер
            timestamp = timezone.now().strftime("%y%m%d%H%M%S")
            return f"{prefix}{timestamp}"

        except Exception as e:
            logger.error(f"Fallback numbering failed: {e}")
            return NumberingService._generate_emergency_fallback(document_type)

    @staticmethod
    def _generate_emergency_fallback(document_type) -> str:
        """
        Emergency fallback - когато всичко се счупи

        Гарантирано уникален номер с timestamp
        """
        timestamp = timezone.now().strftime("%y%m%d%H%M%S%f")[:14]  # microseconds за unique
        return f"DOC{timestamp}"

    @staticmethod
    def get_next_preview_number(document_type, location=None, user=None) -> str:
        """
        Покажи какъв ще бъде следващият номер БЕЗ да го генерира

        Полезно за preview в UI
        """
        try:
            config = NumberingService._get_numbering_config(document_type, location, user)

            if config:
                next_number = config.current_number + 1
                return NumberingService._format_number(
                    config.prefix,
                    next_number,
                    config.digits_count,
                    config.numbering_type
                )
            else:
                return NumberingService._generate_fallback_number(document_type)

        except Exception as e:
            logger.error(f"Error previewing next number: {e}")
            return "PREVIEW_ERROR"

    @staticmethod
    def get_numbering_info(document_type, location=None, user=None) -> Dict[str, Any]:
        """
        Връща информация за numbering configuration

        Полезно за debugging и админ интерфейс
        """
        try:
            config = NumberingService._get_numbering_config(document_type, location, user)

            if config:
                return {
                    'config_found': True,
                    'config_name': config.name,
                    'series_number': config.series_number,
                    'prefix': config.prefix,
                    'current_number': config.current_number,
                    'numbering_type': config.numbering_type,
                    'digits_count': config.digits_count,
                    'next_preview': NumberingService.get_next_preview_number(document_type, location, user)
                }
            else:
                return {
                    'config_found': False,
                    'fallback_preview': NumberingService._generate_fallback_number(document_type),
                    'note': 'Using fallback numbering strategy'
                }

        except Exception as e:
            return {
                'config_found': False,
                'error': str(e),
                'emergency_preview': NumberingService._generate_emergency_fallback(document_type)
            }

    @staticmethod
    def validate_numbering_setup(document_type, location=None) -> Dict[str, Any]:
        """
        Валидира дали numbering setup-а е правилен

        Използвай преди важни операции
        """
        issues = []
        warnings = []

        try:
            config = NumberingService._get_numbering_config(document_type, location, None)

            if not config:
                issues.append("No numbering configuration found")
                return {
                    'valid': False,
                    'issues': issues,
                    'warnings': warnings
                }

            # Проверки за фискални документи
            if config.numbering_type == 'fiscal':
                if config.digits_count != 10:
                    issues.append(f"Fiscal documents require 10 digits, config has {config.digits_count}")

                if config.prefix:
                    issues.append(f"Fiscal documents cannot have prefix, config has '{config.prefix}'")

            # Проверки за max_number
            if config.max_number and config.current_number >= config.max_number:
                issues.append(f"Number limit reached: {config.current_number}/{config.max_number}")

            # Warnings за близо до лимита
            if config.max_number and config.current_number > (config.max_number * 0.9):
                warnings.append(f"Approaching number limit: {config.current_number}/{config.max_number}")

            return {
                'valid': len(issues) == 0,
                'issues': issues,
                'warnings': warnings,
                'config_info': {
                    'name': config.name,
                    'type': config.numbering_type,
                    'current': config.current_number,
                    'max': config.max_number
                }
            }

        except Exception as e:
            return {
                'valid': False,
                'issues': [f"Validation failed: {e}"],
                'warnings': []
            }


# =================================================================
# CONVENIENCE FUNCTIONS - За backward compatibility
# =================================================================

def generate_document_number(document_type, location=None, user=None) -> str:
    """
    Convenience function за backward compatibility

    Просто делегира на NumberingService
    """
    return NumberingService.generate_document_number(document_type, location, user)


def get_next_preview_number(document_type, location=None, user=None) -> str:
    """
    Convenience function за preview
    """
    return NumberingService.get_next_preview_number(document_type, location, user)