# purchases/signals.py - ПРОФЕСИОНАЛЕН ПОДХОД

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
import logging

from purchases.models import PurchaseDocumentLine, PurchaseDocument

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=PurchaseDocumentLine)
def preserve_document_id_before_delete(sender, instance, **kwargs):
    """Запазваме document_id преди изтриване за да можем да recalculate"""
    instance._document_id_for_cleanup = instance.document_id


@receiver(post_delete, sender=PurchaseDocumentLine)
def cleanup_document_totals_on_line_delete(sender, instance, **kwargs):
    """SYSTEM EVENT: Почиства документ когато ред се изтрие"""
    if hasattr(instance, '_document_id_for_cleanup') and instance._document_id_for_cleanup:
        try:
            from .services import DocumentService
            document = PurchaseDocument.objects.get(pk=instance._document_id_for_cleanup)

            # Използваме service за consistency
            DocumentService.recalculate_document_totals(document)

            logger.info(f"Recalculated totals for document {document.document_number} after line deletion")

        except PurchaseDocument.DoesNotExist:
            logger.warning(f"Document with ID {instance._document_id_for_cleanup} not found during cleanup")


@receiver(post_save, sender=PurchaseDocument)
def handle_document_status_changes(sender, instance, created, **kwargs):
    """SYSTEM EVENT: Обработва промени в статуса на документ"""

    if created:
        logger.info(f"New purchase document created: {instance.document_number}")
        return

    # Проверяваме дали статуса е променен
    if hasattr(instance, '_original_status'):
        old_status = instance._original_status
        new_status = instance.status

        if old_status != new_status:
            logger.info(f"Document {instance.document_number} status changed: {old_status} -> {new_status}")

            # System-level операции по статус
            if new_status == PurchaseDocument.RECEIVED:
                _handle_document_received(instance)
            elif new_status == PurchaseDocument.CANCELLED:
                _handle_document_cancelled(instance)


def _handle_document_received(document):
    """Обработва получаване на документ - system level"""
    try:
        # Audit log
        from .models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=document,
            action=PurchaseAuditLog.RECEIVE,
            user=getattr(document, 'updated_by', None),
            notes="Document automatically received"
        )

        # Интеграция с други системи ако е нужно
        # _notify_inventory_system(document)
        # _update_supplier_performance(document)

    except Exception as e:
        logger.error(f"Error handling document received for {document.document_number}: {e}")


def _handle_document_cancelled(document):
    """Обработва отказване на документ"""
    try:
        from .models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=document,
            action=PurchaseAuditLog.CANCEL,
            user=getattr(document, 'updated_by', None),
            notes="Document cancelled"
        )
    except Exception as e:
        logger.error(f"Error handling document cancellation for {document.document_number}: {e}")


# TRACKING на промени в модела
@receiver(post_save, sender=PurchaseDocument)
def track_document_changes(sender, instance, **kwargs):
    """Проследява промени за audit и reporting"""

    # Запазваме текущия статус за следващата промяна
    instance._original_status = instance.status