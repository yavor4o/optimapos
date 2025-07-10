from django.apps import AppConfig

class PurchasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'purchases'

    def ready(self):
        print("🔧 PurchasesConfig.ready() се изпълнява!")
        from purchases import signals
        print("🔧 Сигналите са импортирани!")