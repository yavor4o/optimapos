from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Главна страница - Dashboard с обзор на системата
    
    Показва:
    - Статистики за продажби
    - Последни документи
    - Бързи действия
    - Системни метрики
    """
    template_name = 'frontend/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Основни статистики
        context.update({
            'dashboard_title': 'OptimaPOS Dashboard',
            'user': self.request.user,
            'today': timezone.now().date(),
            
            # Статистики за периода
            'stats': self.get_dashboard_stats(),
            
            # Последни активности
            'recent_activities': self.get_recent_activities(),
            
            # Бързи линкове
            'quick_actions': self.get_quick_actions(),
            
            # Системна информация
            'system_info': self.get_system_info(),
        })
        
        return context
    
    def get_dashboard_stats(self):
        """Статистики за dashboard"""
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        stats = {
            'sales_today': self.get_sales_stats('today'),
            'sales_week': self.get_sales_stats('week'),
            'sales_month': self.get_sales_stats('month'),
            
            'documents_today': self.get_document_stats('today'),
            'documents_pending': self.get_document_stats('pending'),
            
            'inventory_alerts': self.get_inventory_alerts(),
            'system_health': self.get_system_health(),
        }
        
        return stats
    
    def get_sales_stats(self, period):
        """Статистики за продажби по период"""
        # TODO: Имплементирай с реални данни когато има sales модели
        mock_data = {
            'today': {'amount': Decimal('2850.50'), 'count': 12, 'growth': '+5.2%'},
            'week': {'amount': Decimal('18450.75'), 'count': 87, 'growth': '+12.8%'},
            'month': {'amount': Decimal('95700.25'), 'count': 342, 'growth': '+8.9%'},
        }
        return mock_data.get(period, {'amount': Decimal('0'), 'count': 0, 'growth': '0%'})
    
    def get_document_stats(self, period):
        """Статистики за документи"""
        if period == 'today':
            return {'count': 8, 'types': ['delivery', 'request', 'order']}
        elif period == 'pending':
            return {'count': 3, 'urgent': 1}
        return {'count': 0}
    
    def get_inventory_alerts(self):
        """Алерти за инвентар"""
        return {
            'low_stock': 5,
            'out_of_stock': 2,
            'expiring_soon': 3,
        }
    
    def get_system_health(self):
        """Системно здраве"""
        return {
            'status': 'healthy',
            'uptime': '99.8%',
            'last_backup': timezone.now() - timedelta(hours=2),
            'active_users': 4,
        }
    
    def get_recent_activities(self):
        """Последни активности в системата"""
        # TODO: Имплементирай с реални данни от audit log
        mock_activities = [
            {
                'type': 'document_created',
                'message': 'Създадена нова поръчка #PO-2024-001',
                'user': 'admin',
                'timestamp': timezone.now() - timedelta(minutes=15),
                'icon': 'ki-document'
            },
            {
                'type': 'delivery_received',
                'message': 'Получена доставка от Supplier ABC Ltd',
                'user': 'warehouse_user',
                'timestamp': timezone.now() - timedelta(hours=1),
                'icon': 'ki-truck'
            },
            {
                'type': 'inventory_updated',
                'message': 'Обновен инвентар за продукт XYZ-123',
                'user': 'inventory_manager',
                'timestamp': timezone.now() - timedelta(hours=2),
                'icon': 'ki-package'
            },
        ]
        return mock_activities
    
    def get_quick_actions(self):
        """Бързи действия за потребителя"""
        actions = [
            {
                'title': 'Нова поръчка',
                'url': '/purchases/orders/create/',
                'icon': 'ki-plus',
                'color': 'primary',
                'permission': 'purchases.add_purchaseorder'
            },
            {
                'title': 'Нова доставка', 
                'url': '/purchases/deliveries/create/',
                'icon': 'ki-truck',
                'color': 'success',
                'permission': 'purchases.add_deliveryreceipt'
            },
            {
                'title': 'Инвентар',
                'url': '/inventory/',
                'icon': 'ki-package',
                'color': 'info',
                'permission': 'inventory.view_inventoryentry'
            },
            {
                'title': 'Отчети',
                'url': '/reports/',
                'icon': 'ki-chart',
                'color': 'warning',
                'permission': 'core.view_reports'
            },
        ]
        
        # Филтрирай според permissions на потребителя
        user_actions = []
        for action in actions:
            if self.request.user.has_perm(action.get('permission', '')):
                user_actions.append(action)
        
        return user_actions
    
    def get_system_info(self):
        """Системна информация"""
        return {
            'version': '1.0.0',
            'environment': 'production',  # TODO: от settings
            'database': 'PostgreSQL',  # TODO: от settings  
            'cache': 'Redis',  # TODO: от settings
        }
