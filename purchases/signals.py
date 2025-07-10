from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from purchases.models import PurchaseDocumentLine, PurchaseDocument


@receiver(post_save, sender=PurchaseDocumentLine)
def update_document_totals(sender, instance, created, **kwargs):
    """Обновява общите суми на документа при промяна в ред"""

    # Избегни рекурсия - само ако не сме в процес на изчисляване
    if not getattr(instance, '_calculating', False):
        instance.document.calculate_totals()

        # Записваме без да извикваме save() за да избегнем рекурсия
        PurchaseDocument.objects.filter(pk=instance.document.pk).update(
            total_before_discount=instance.document.total_before_discount,
            total_discount=instance.document.total_discount,
            total_after_discount=instance.document.total_after_discount,
            total_vat=instance.document.total_vat,
            grand_total=instance.document.grand_total
        )


@receiver(post_delete, sender=PurchaseDocumentLine)
def update_document_totals_on_delete(sender, instance, **kwargs):
    """Обновява сумите при изтриване на ред"""
    try:
        instance.document.calculate_totals()

        PurchaseDocument.objects.filter(pk=instance.document.pk).update(
            total_before_discount=instance.document.total_before_discount,
            total_discount=instance.document.total_discount,
            total_after_discount=instance.document.total_after_discount,
            total_vat=instance.document.total_vat,
            grand_total=instance.document.grand_total
        )
    except PurchaseDocument.DoesNotExist:
        pass


@receiver(post_save, sender=PurchaseDocumentLine)
def update_warehouse_pricing(sender, instance, **kwargs):
    print(f"🔍 Сигнал се изпълнява за: {instance.product.code}")
    print(f"🔍 Статус документ: {instance.document.status}")
    print(f"🔍 Нова цена: {instance.new_sale_price}")

    if (instance.document.status == PurchaseDocument.RECEIVED and
            instance.new_sale_price):
        print("✅ Условията са изпълнени, извиквам update_warehouse_price()")
        instance.update_warehouse_price()
    else:
        print("❌ Условията НЕ са изпълнени")

print("🔧 Регистрирах всички сигнали!")