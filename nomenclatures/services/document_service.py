# nomenclatures/services/document_service_refactored.py
"""
Document Service - REFACTORED FACADE VERSION

Вместо 916+ lines, сега е само facade който делегира на специализирани services:
- DocumentCreator: създаване
- StatusManager: status transitions
- DocumentValidator: валидации
- DocumentQuery: queries

ПУБЛИЧНИЯТ API ОСТАВА СЪЩИЯТ!
"""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from django.contrib.auth import get_user_model
import logging

from core.utils.result import Result
from .document.creator import DocumentCreator
from .document.status_manager import StatusManager
from .document.validator import DocumentValidator
from .document.query import DocumentQuery

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentService:
    """
    Document Service - FACADE PATTERN

    Публичният interface остава същият, но вътрешно делегира на специализирани services.
    От 916 lines → ~100 lines!
    """

    # =====================
    # CREATION (делегира на DocumentCreator)
    # =====================

    @staticmethod
    def create_document(model_class, data: Dict[str, Any], user: User, location=None) -> Result:
        """Create document - делегира на DocumentCreator"""
        return DocumentCreator.create_document(model_class, data, user, location)

    # =====================
    # STATUS MANAGEMENT (делегира на StatusManager)
    # =====================

    @staticmethod
    def transition_document(document, to_status: str, user: User, comments: str = '', **kwargs) -> Result:
        """Transition document status - делегира на StatusManager"""
        return StatusManager.transition_document(document, to_status, user, comments, **kwargs)

    # =====================
    # VALIDATION (делегира на DocumentValidator)
    # =====================

    @staticmethod
    def can_edit_document(document, user: User) -> Result:
        """Check if document can be edited - returns Result"""
        try:
            can_edit, reason = DocumentValidator.can_edit_document(document, user)
            return Result.success(
                {'can_edit': can_edit, 'reason': reason},
                reason if not can_edit else 'Document can be edited'
            )
        except Exception as e:
            return Result.error('EDIT_CHECK_ERROR', f'Failed to check edit permissions: {str(e)}')

    # ДОБАВИ след can_edit_document:
    @staticmethod
    def can_delete_document(document, user: User) -> Result:
        """Check if document can be deleted"""
        try:
            can_delete = True
            reason = "Document can be deleted"

            # Check document status
            if hasattr(document, 'status'):
                readonly_statuses = ['confirmed', 'closed', 'cancelled', 'completed']
                if document.status in readonly_statuses:
                    can_delete = False
                    reason = f"Cannot delete document in {document.status} status"

            # Check if document has lines
            if can_delete and hasattr(document, 'lines') and document.lines.exists():
                can_delete = False
                reason = "Cannot delete document with existing lines"

            return Result.success(
                {'can_delete': can_delete, 'reason': reason},
                reason
            )
        except Exception as e:
            return Result.error('DELETE_CHECK_ERROR', f'Failed to check delete permissions: {str(e)}')

    # =====================
    # QUERIES (делегира на DocumentQuery)
    # =====================

    @staticmethod
    def get_pending_approval_documents(model_class=None, queryset=None):
        """Get pending approval documents - делегира на DocumentQuery"""
        return DocumentQuery.get_pending_approval_documents(model_class, queryset)

    @staticmethod
    def get_ready_for_processing_documents(model_class=None, queryset=None):
        """Get ready for processing documents - делегира на DocumentQuery"""
        return DocumentQuery.get_ready_for_processing_documents(model_class, queryset)

    @staticmethod
    def get_active_documents(model_class=None, queryset=None):
        """Get active documents - делегира на DocumentQuery"""
        return DocumentQuery.get_active_documents(model_class, queryset)

    @staticmethod
    def get_available_actions(document, user: User) -> List[Dict]:
        """Get available actions - делегира на DocumentQuery"""
        return DocumentQuery.get_available_actions(document, user)

    # =====================
    # CONVENIENCE METHODS (wrappers)
    # =====================

    @staticmethod
    def submit_for_approval(document, user: User, comments: str = '') -> Result:
        """
        Submit document for approval - convenience wrapper

        Намира правилния status и прави transition
        """
        try:
            if not document.document_type.requires_approval:
                return Result.error(
                    'NO_APPROVAL_REQUIRED',
                    'This document type does not require approval'
                )

            # Find submission status
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_submission_status(document)

            if not target_status:
                return Result.error(
                    'NO_SUBMISSION_STATUS',
                    'No submission status found for current state'
                )

            return StatusManager.transition_document(
                document, target_status, user, comments
            )

        except ImportError:
            # Fallback to simple submission
            return StatusManager.transition_document(
                document, 'submitted', user, comments
            )

    @staticmethod
    def approve_document(document, user: User, notes: str = '') -> Result:
        """
        Approve document - convenience wrapper
        """
        try:
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_next_approval_status(document)

            if not target_status:
                # Default approval status
                target_status = 'approved'

            return StatusManager.transition_document(
                document, target_status, user, notes
            )

        except ImportError:
            return StatusManager.transition_document(
                document, 'approved', user, notes
            )

    @staticmethod
    def reject_document(document, user: User, reason: str) -> Result:
        """
        Reject document - convenience wrapper
        """
        try:
            from .approval_service import ApprovalService
            target_status = ApprovalService.find_rejection_status(document)

            if not target_status:
                # Default rejection status
                target_status = 'rejected'

            return StatusManager.transition_document(
                document, target_status, user, reason
            )

        except ImportError:
            return StatusManager.transition_document(
                document, 'rejected', user, reason
            )

    # =====================
    # PRIVATE HELPERS (за backward compatibility)
    # =====================

    @staticmethod
    def _get_document_type_for_model(model_class):
        """За backward compatibility - делегира на DocumentCreator"""
        return DocumentCreator._get_document_type_for_model(model_class)

    @staticmethod
    def _get_initial_status(document_type) -> str:
        """За backward compatibility - делегира на DocumentCreator"""
        return DocumentCreator._get_initial_status(document_type)

    # =====================
    # UNIVERSAL DOCUMENT OPERATIONS - ДОБАВЕНИ ОТ DocumentProcessingService
    # =====================

    @classmethod
    @transaction.atomic
    def recalculate_document_lines(cls, document, user=None, recalc_vat=True, update_pricing=True) -> Result:
        """Universal line recalculation with service integration"""
        try:
            lines_processed = 0
            pricing_updates = 0
            original_total = getattr(document, 'total_amount', Decimal('0'))

            for line in document.lines.select_related('product').all():
                # PRICING UPDATE
                if update_pricing and hasattr(line, 'unit_price'):
                    try:
                        from pricing.services import PricingService
                        pricing_result = PricingService.get_product_pricing(
                            document.location, line.product, quantity=getattr(line, 'quantity', Decimal('1'))
                        )
                        if pricing_result.ok:
                            new_price = pricing_result.data.get('final_price')
                            if new_price and new_price != line.unit_price:
                                line.unit_price = new_price
                                pricing_updates += 1
                    except ImportError:
                        pass

                # VAT CALCULATION
                if recalc_vat:
                    try:
                        from nomenclatures.services import VATCalculationService
                        vat_result = VATCalculationService.calculate_line_vat(line)
                        if vat_result.ok:
                            vat_data = vat_result.data
                            if 'line_total_with_vat' in vat_data:
                                line.line_total = vat_data['line_total_with_vat']
                            if 'vat_amount_per_line' in vat_data:
                                line.vat_amount = vat_data['vat_amount_per_line']
                    except ImportError:
                        pass

                line.save()
                lines_processed += 1

            # Recalculate document totals
            document.total_amount = document.lines.aggregate(Sum('line_total'))['line_total__sum'] or Decimal('0')
            document.updated_by = user
            document.save()

            return Result.success({
                'lines_processed': lines_processed,
                'pricing_updates': pricing_updates,
                'new_total': float(document.total_amount)
            }, f'Recalculated {lines_processed} lines for {document.document_number}')

        except Exception as e:
            return Result.error('LINE_RECALCULATION_ERROR', f'Failed to recalculate lines: {str(e)}')

    @classmethod
    def validate_document_integrity(cls, document, deep_validation=True) -> Result:
        """Universal document validation"""
        try:
            validation_issues = []

            # Basic validation
            if not document.lines.exists():
                validation_issues.append({
                    'type': 'no_lines', 'severity': 'error',
                    'message': 'Document has no lines'
                })

            # Line validation
            for line in document.lines.all():
                if hasattr(line, 'quantity') and line.quantity <= 0:
                    validation_issues.append({
                        'type': 'invalid_quantity', 'severity': 'error',
                        'line': line.line_number, 'message': f'Line {line.line_number}: Invalid quantity'
                    })

            error_count = len([i for i in validation_issues if i['severity'] == 'error'])
            is_valid = error_count == 0

            return Result.success({
                'is_valid': is_valid, 'error_count': error_count,
                'validation_issues': validation_issues, 'document_number': document.document_number
            }, f'Validation: {"VALID" if is_valid else "INVALID"}')

        except Exception as e:
            return Result.error('VALIDATION_ERROR', f'Validation failed: {str(e)}')

    @classmethod
    def analyze_document_financial_impact(cls, document, compare_to_budget=True) -> Result:
        """Universal financial analysis"""
        try:
            analysis = {
                'document_number': document.document_number,
                'total_amount': float(getattr(document, 'total_amount', 0)),
                'line_count': document.lines.count()
            }

            # Add cost analysis if possible
            total_cost = Decimal('0')
            for line in document.lines.select_related('product').all():
                try:
                    from pricing.services import PricingService
                    cost_result = PricingService.get_product_pricing(
                        document.location, line.product, include_cost=True
                    )
                    if cost_result.ok:
                        cost_price = cost_result.data.get('cost_price', Decimal('0'))
                        total_cost += cost_price * getattr(line, 'quantity', Decimal('0'))
                except ImportError:
                    pass

            analysis['total_cost'] = float(total_cost)
            analysis['total_profit'] = analysis['total_amount'] - float(total_cost)

            return Result.success(analysis, f'Financial analysis completed for {document.document_number}')

        except Exception as e:
            return Result.error('FINANCIAL_ANALYSIS_ERROR', f'Analysis failed: {str(e)}')

    # =====================
    # LEGACY COMPATIBILITY WRAPPERS
    # =====================

    @staticmethod
    def can_edit(document, user=None):
        """LEGACY: Returns bool for backward compatibility"""
        result = DocumentService.can_edit_document(document, user)
        return result.data.get('can_edit', False) if result.ok else False

    @staticmethod
    def can_delete(document, user=None):
        """LEGACY: Returns bool for backward compatibility"""
        result = DocumentService.can_delete_document(document, user)
        return result.data.get('can_delete', False) if result.ok else False

    # =====================
    # BULK OPERATIONS
    # =====================

    @classmethod
    @transaction.atomic
    def bulk_process_documents(cls, document_queryset, operation, user=None, **kwargs) -> Result:
        """
        Bulk process multiple documents with specified operation.

        OPERATIONS:
        - 'recalculate': Recalculate all lines
        - 'validate': Validate document integrity
        - 'financial_analysis': Analyze financial impact

        Args:
            document_queryset: QuerySet of documents to process
            operation: Operation to perform
            user: User performing operation
            **kwargs: Operation-specific parameters

        Returns:
            Result with bulk operation summary
        """
        try:
            total_documents = document_queryset.count()
            successful_operations = 0
            failed_operations = []
            operation_results = []

            for document in document_queryset:
                try:
                    if operation == 'recalculate':
                        result = cls.recalculate_document_lines(
                            document, user,
                            recalc_vat=kwargs.get('recalc_vat', True),
                            update_pricing=kwargs.get('update_pricing', True)
                        )

                    elif operation == 'validate':
                        result = cls.validate_document_integrity(
                            document, deep_validation=kwargs.get('deep_validation', True)
                        )

                    elif operation == 'financial_analysis':
                        result = cls.analyze_document_financial_impact(
                            document,
                            compare_to_budget=kwargs.get('compare_to_budget', True)
                        )

                    else:
                        result = Result.error(
                            'UNKNOWN_OPERATION',
                            f'Unknown operation: {operation}'
                        )

                    if result.ok:
                        successful_operations += 1
                        operation_results.append({
                            'document': document.document_number,
                            'success': True,
                            'data': result.data
                        })
                    else:
                        failed_operations.append({
                            'document': document.document_number,
                            'error': result.code,
                            'message': result.msg
                        })
                        operation_results.append({
                            'document': document.document_number,
                            'success': False,
                            'error': result.code
                        })

                except Exception as e:
                    logger.error(f"Bulk operation failed for {document.document_number}: {str(e)}")
                    failed_operations.append({
                        'document': document.document_number,
                        'error': 'PROCESSING_EXCEPTION',
                        'message': str(e)
                    })

            success_rate = (successful_operations / total_documents * 100) if total_documents > 0 else 0

            return Result.success(
                {
                    'total_documents': total_documents,
                    'successful_operations': successful_operations,
                    'failed_operations': len(failed_operations),
                    'success_rate': round(success_rate, 2),
                    'operation': operation,
                    'failed_details': failed_operations,
                    'operation_results': operation_results
                },
                f'Bulk {operation} completed: {successful_operations}/{total_documents} successful'
            )

        except Exception as e:
            logger.error(f"Bulk processing failed: {str(e)}")
            return Result.error(
                'BULK_PROCESSING_ERROR',
                f'Bulk processing failed: {str(e)}',
                {'exception': str(e)}
            )