"""
Decimal configuration models for OptimaPOS

Allows configurable decimal precision at different levels:
- System-wide defaults
- Document type specific
- Field type specific
- Per-calculation context
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings
from decimal import ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN, ROUND_UP, ROUND_CEILING, ROUND_FLOOR
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DecimalPrecisionConfig(models.Model):
    """
    Global configuration for decimal precision and rounding strategies.
    
    This allows system administrators to configure decimal behavior
    according to business needs and legal requirements.
    """
    
    # Rounding strategy choices
    ROUNDING_CHOICES = [
        (ROUND_HALF_UP, _('Round Half Up (Standard Commercial)')),
        (ROUND_HALF_EVEN, _('Round Half Even (Banker\'s Rounding)')), 
        (ROUND_UP, _('Round Up (Always)')),
        (ROUND_DOWN, _('Round Down (Always)')),
        (ROUND_CEILING, _('Round Ceiling')),
        (ROUND_FLOOR, _('Round Floor'))
    ]
    
    # Context types for different calculation areas
    CONTEXT_CHOICES = [
        ('currency', _('Currency/Money Amounts')),
        ('vat', _('VAT Calculations')),
        ('tax_base', _('Tax Base Calculations')),
        ('quantity', _('Quantities')),
        ('percentage', _('Percentages')), 
        ('cost_price', _('Cost Prices')),
        ('profit', _('Profit Calculations')),
        ('discount', _('Discount Calculations')),
        ('inventory', _('Inventory Valuations')),
        ('reporting', _('Financial Reporting')),
    ]
    
    # Core fields
    context = models.CharField(
        _('Context'),
        max_length=50,
        choices=CONTEXT_CHOICES,
        unique=True,
        help_text=_('The calculation context this configuration applies to')
    )
    
    decimal_places = models.PositiveSmallIntegerField(
        _('Decimal Places'),
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_('Number of decimal places for this context')
    )
    
    rounding_strategy = models.CharField(
        _('Rounding Strategy'),
        max_length=20,
        choices=ROUNDING_CHOICES,
        default=ROUND_HALF_UP,
        help_text=_('Rounding strategy to use for this context')
    )
    
    # Legal compliance
    is_legally_required = models.BooleanField(
        _('Legally Required'),
        default=False,
        help_text=_('Whether this precision is required by law (cannot be changed)')
    )
    
    legal_reference = models.CharField(
        _('Legal Reference'),
        max_length=200,
        blank=True,
        help_text=_('Legal reference for this requirement (e.g. "Наредба № 3/2006")')
    )
    
    # Configuration metadata
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of when this configuration is used')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this configuration is currently active')
    )
    
    # Audit fields
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_decimal_configs',
        verbose_name=_('Created By')
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,
        related_name='updated_decimal_configs',
        verbose_name=_('Updated By'),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _('Decimal Precision Configuration')
        verbose_name_plural = _('Decimal Precision Configurations')
        ordering = ['context']
        
    def __str__(self):
        return f"{self.get_context_display()}: {self.decimal_places} places, {self.get_rounding_strategy_display()}"
        
    def clean(self):
        super().clean()
        
        # Validation for legally required configurations
        if self.is_legally_required:
            if not self.legal_reference:
                raise ValidationError({
                    'legal_reference': _('Legal reference is required for legally required configurations')
                })
                
        # Context-specific validations
        if self.context == 'vat' and self.decimal_places != 2:
            raise ValidationError({
                'decimal_places': _('VAT calculations must use exactly 2 decimal places per Bulgarian law')
            })
            
        if self.context == 'tax_base' and self.decimal_places != 2:
            raise ValidationError({
                'decimal_places': _('Tax base calculations must use exactly 2 decimal places per Bulgarian law')
            })
            
    @classmethod
    def get_config(cls, context: str) -> Optional['DecimalPrecisionConfig']:
        """
        Get configuration for a specific context.
        
        Args:
            context: The calculation context
            
        Returns:
            DecimalPrecisionConfig or None if not found
        """
        try:
            return cls.objects.get(context=context, is_active=True)
        except cls.DoesNotExist:
            logger.warning(f"No decimal precision configuration found for context: {context}")
            return None
            
    @classmethod 
    def get_decimal_places(cls, context: str, default: int = 2) -> int:
        """
        Get decimal places for a context with fallback.
        
        Args:
            context: The calculation context
            default: Default decimal places if config not found
            
        Returns:
            Number of decimal places to use
        """
        config = cls.get_config(context)
        return config.decimal_places if config else default
        
    @classmethod
    def get_rounding_strategy(cls, context: str, default: str = ROUND_HALF_UP) -> str:
        """
        Get rounding strategy for a context with fallback.
        
        Args:
            context: The calculation context
            default: Default rounding strategy if config not found
            
        Returns:
            Rounding strategy to use
        """
        config = cls.get_config(context)
        return config.rounding_strategy if config else default


class DocumentTypeDecimalConfig(models.Model):
    """
    Document type specific decimal configuration.
    
    Allows different document types to have different precision requirements.
    For example, Purchase Orders might need different precision than Sales Invoices.
    """
    
    document_type = models.ForeignKey(
        'nomenclatures.DocumentType',
        on_delete=models.CASCADE,
        related_name='decimal_configs',
        verbose_name=_('Document Type')
    )
    
    context = models.CharField(
        _('Context'),
        max_length=50,
        choices=DecimalPrecisionConfig.CONTEXT_CHOICES,
        help_text=_('The calculation context for this document type')
    )
    
    decimal_places = models.PositiveSmallIntegerField(
        _('Decimal Places'),
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_('Number of decimal places for this document type and context')
    )
    
    rounding_strategy = models.CharField(
        _('Rounding Strategy'),
        max_length=20,
        choices=DecimalPrecisionConfig.ROUNDING_CHOICES,
        default=ROUND_HALF_UP,
        help_text=_('Rounding strategy for this document type and context')
    )
    
    # Priority and overrides
    overrides_global = models.BooleanField(
        _('Overrides Global'),
        default=True,
        help_text=_('Whether this config overrides the global configuration')
    )
    
    priority = models.PositiveSmallIntegerField(
        _('Priority'),
        default=100,
        help_text=_('Priority when multiple configs could apply (lower = higher priority)')
    )
    
    # Metadata
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of this specific configuration')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    
    # Audit fields
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Document Type Decimal Configuration')
        verbose_name_plural = _('Document Type Decimal Configurations')
        unique_together = [('document_type', 'context')]
        ordering = ['document_type__name', 'context', 'priority']
        
    def __str__(self):
        return f"{self.document_type.name} - {self.get_context_display()}: {self.decimal_places} places"
        
    @classmethod
    def get_config(cls, document_type_id: int, context: str) -> Optional['DocumentTypeDecimalConfig']:
        """
        Get document type specific configuration.
        
        Args:
            document_type_id: ID of the document type
            context: The calculation context
            
        Returns:
            DocumentTypeDecimalConfig or None if not found
        """
        try:
            return cls.objects.get(
                document_type_id=document_type_id,
                context=context,
                is_active=True
            )
        except cls.DoesNotExist:
            return None


# =============================================================================
# UTILITY FUNCTIONS FOR GETTING CONFIGURATIONS
# =============================================================================

def get_decimal_config(context: str, 
                      document_type_id: Optional[int] = None) -> dict:
    """
    Get the appropriate decimal configuration for a context.
    
    Priority order:
    1. Document type specific configuration
    2. Global configuration
    3. Hardcoded defaults
    
    Args:
        context: Calculation context
        document_type_id: Optional document type ID for specific config
        
    Returns:
        dict: {
            'decimal_places': int,
            'rounding_strategy': str,
            'source': str  # 'document_type', 'global', or 'default'
        }
    """
    
    # Try document type specific first
    if document_type_id:
        doc_config = DocumentTypeDecimalConfig.get_config(document_type_id, context)
        if doc_config and doc_config.overrides_global:
            return {
                'decimal_places': doc_config.decimal_places,
                'rounding_strategy': doc_config.rounding_strategy,
                'source': 'document_type'
            }
    
    # Try global configuration
    global_config = DecimalPrecisionConfig.get_config(context)
    if global_config:
        return {
            'decimal_places': global_config.decimal_places,
            'rounding_strategy': global_config.rounding_strategy,
            'source': 'global'
        }
    
    # Fallback to hardcoded defaults
    defaults = {
        'currency': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'vat': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'tax_base': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'quantity': {'decimal_places': 3, 'rounding_strategy': ROUND_HALF_UP},
        'percentage': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'cost_price': {'decimal_places': 4, 'rounding_strategy': ROUND_HALF_UP},
        'profit': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'discount': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
        'inventory': {'decimal_places': 4, 'rounding_strategy': ROUND_HALF_UP},
        'reporting': {'decimal_places': 2, 'rounding_strategy': ROUND_HALF_UP},
    }
    
    default_config = defaults.get(context, {
        'decimal_places': 2, 
        'rounding_strategy': ROUND_HALF_UP
    })
    
    return {
        **default_config,
        'source': 'default'
    }


def get_quantizer_string(decimal_places: int) -> str:
    """
    Generate quantizer string for given decimal places.
    
    Args:
        decimal_places: Number of decimal places
        
    Returns:
        str: Quantizer string (e.g. '0.01' for 2 places)
        
    Example:
        >>> get_quantizer_string(2)
        '0.01'
        >>> get_quantizer_string(4)
        '0.0001'
    """
    if decimal_places == 0:
        return '1'
    return '0.' + '0' * decimal_places