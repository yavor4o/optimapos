# =====================================================
# ФАЙЛ 2: nomenclatures/mixins/__init__.py
# =====================================================

# nomenclatures/mixins/__init__.py
"""
Document Mixins Package - EXTRACTED FROM purchases.models.base

Provides composable functionality for document models:
- FinancialMixin: Financial calculations and totals
- PaymentMixin: Payment tracking and status
- DeliveryMixin: Delivery information and tracking
- FinancialLineMixin: Line-level financial calculations
"""

from .financial import FinancialMixin, FinancialLineMixin
from .payment import PaymentMixin
from .delivery import DeliveryMixin

__all__ = [
    'FinancialMixin',
    'PaymentMixin',
    'DeliveryMixin',
    'FinancialLineMixin',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'

# =====================================================
# ФАЙЛ 3: nomenclatures/mixins/financial.py
# =====================================================

# nomenclatures/mixins/financial.py
"""
Financial Mixins - EXTRACTED FROM purchases.models.base

Provides financial calculation functionality for documents and lines
"""

