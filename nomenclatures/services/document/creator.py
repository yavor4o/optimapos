# nomenclatures/services/document/creator.py - ОБНОВЕН С NumberingService
"""
Document Creator - Refactored от DocumentService

ОТГОВОРНОСТИ:
- Създава документи с правилен номер
- Задава начален статус
- Валидира document type
- Логва създаването

ПРОМЯНА: Сега използва NumberingService вместо директни imports
"""

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class DocumentCreator:
    """
    Отговорен САМО за създаване на документи

    АРХИТЕКТУРА:
    - НЕ прави status transitions (това е в StatusManager)
    - НЕ прави validations (това е в DocumentValidator)
    - САМО създаване + номериране + начален статус
    """

    @staticmethod
    def create_document(instance, user: Optional[User] = None, **kwargs) -> bool:
        """
        Създава документ с генериран номер и начален статус

        Args:
            instance: Django model instance (PurchaseRequest, etc.)
            user: User creating the document
            **kwargs: Допълнителни параметри

        Returns:
            bool: True при успех

        Raises:
            ValidationError: При проблеми със създаването
        """
        try:
            # 1. Намери document type
            document_type = DocumentCreator._get_document_type_for_model(instance.__class__)
            if not document_type:
                raise ValidationError(f"No DocumentType found for {instance.__class__.__name__}")

            instance.document_type = document_type

            # 2. Генерирай номер (НОВОТО: използва NumberingService)
            if not instance.document_number:
                instance.document_number = DocumentCreator._generate_document_number(
                    document_type,
                    getattr(instance, 'location', None),
                    user
                )

            # 3. Задай начален статус
            if not instance.status:
                instance.status = DocumentCreator._get_initial_status(document_type)

            # 4. Audit fields
            if user:
                if not instance.created_by:
                    instance.created_by = user
                instance.updated_by = user

            # 5. Запази
            instance.save()

            # 6. Логване
            logger.info(f"Document created: {instance.__class__.__name__} {instance.document_number}")

            return True

        except Exception as e:
            logger.error(f"Error creating document: {e}")
            raise ValidationError(f"Document creation failed: {e}")

    @staticmethod
    def _generate_document_number(document_type, location, user: User) -> str:
        """
        Генерира номер на документ ИЗПОЛЗВАЙКИ NumberingService

        ПРОМЯНА: Вече НЕ импортваме models директно!
        """
        try:
            # НОВОТО: Използваме NumberingService
            from ..numbering_service import NumberingService

            return NumberingService.generate_document_number(
                document_type=document_type,
                location=location,
                user=user
            )

        except ImportError:
            # Fallback ако NumberingService не е наличен
            logger.warning("NumberingService not available, using basic fallback")
            return DocumentCreator._basic_fallback_number(document_type)

        except Exception as e:
            logger.error(f"NumberingService failed: {e}, using fallback")
            return DocumentCreator._basic_fallback_number(document_type)

    @staticmethod
    def _basic_fallback_number(document_type) -> str:
        """
        Базов fallback номер

        Използва се САМО ако NumberingService не работи
        """
        try:
            prefix = getattr(document_type, 'code', document_type.type_key[:3].upper())
            timestamp = timezone.now().strftime("%y%m%d%H%M%S")
            return f"{prefix}{timestamp}"
        except:
            timestamp = timezone.now().strftime("%y%m%d%H%M%S")
            return f"DOC{timestamp}"

    @staticmethod
    def _get_initial_status(document_type) -> str:
        """
        Намери начален статус от DocumentTypeStatus

        СЪЩАТА логика като преди - НЕ променяме
        """
        try:
            from ...models.statuses import DocumentTypeStatus

            initial_config = DocumentTypeStatus.objects.filter(
                document_type=document_type,
                is_initial=True,
                is_active=True
            ).first()

            if initial_config:
                return initial_config.status.code

            # Fallback
            return 'draft'

        except Exception as e:
            logger.error(f"Error getting initial status: {e}")
            return 'draft'

    @staticmethod
    def _get_document_type_for_model(model_class):
        """
        Намери DocumentType за Django model

        СЪЩАТА логика като преди - НЕ променяме
        """
        try:
            from ...models.documents import get_document_type_by_key

            # Get app and model info
            app_name = model_class._meta.app_label
            type_key = model_class.__name__.lower()

            # Try to get more specific type key if available
            try:
                # Some models might have custom get_document_type_key method
                if hasattr(model_class, 'get_document_type_key'):
                    instance = model_class()
                    type_key = instance.get_document_type_key()
            except:
                pass

            return get_document_type_by_key(app_name, type_key)

        except Exception as e:
            logger.warning(f"No DocumentType found for {model_class.__name__}: {e}")
            return None

    @staticmethod
    def preview_next_number(model_class, location=None, user=None) -> str:
        """
        НОВО: Покажи какъв ще бъде следващият номер БЕЗ да го генерира

        Полезно за UI preview
        """
        try:
            document_type = DocumentCreator._get_document_type_for_model(model_class)
            if not document_type:
                return "NO_DOCTYPE"

            from ..numbering_service import NumberingService
            return NumberingService.get_next_preview_number(document_type, location, user)

        except Exception as e:
            logger.error(f"Error previewing next number: {e}")
            return "PREVIEW_ERROR"

    @staticmethod
    def get_numbering_info(model_class, location=None, user=None) -> Dict[str, Any]:
        """
        НОВО: Информация за numbering setup

        Полезно за debugging и админ интерфейс
        """
        try:
            document_type = DocumentCreator._get_document_type_for_model(model_class)
            if not document_type:
                return {'error': 'No DocumentType found'}

            from ..numbering_service import NumberingService
            return NumberingService.get_numbering_info(document_type, location, user)

        except Exception as e:
            return {'error': str(e)}


# =================================================================
# CONVENIENCE FUNCTIONS - За external services
# =================================================================

def create_document(instance, user=None, **kwargs) -> bool:
    """
    Convenience function за използване от други services
    """
    return DocumentCreator.create_document(instance, user, **kwargs)


def preview_next_number(model_class, location=None, user=None) -> str:
    """
    Convenience function за preview на номер
    """
    return DocumentCreator.preview_next_number(model_class, location, user)