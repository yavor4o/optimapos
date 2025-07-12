# purchases/services/document_service.py

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import PurchaseDocument, PurchaseDocumentLine, DocumentType


class DocumentService:
    """Сервис за работа с документи и техните workflow-и"""

    @staticmethod
    def get_document_status_info(document: PurchaseDocument) -> Dict:
        """Връща детайлна информация за статуса на документа"""

        status_info = {
            'current_status': document.status,
            'status_display': document.get_status_display(),
            'can_modify': document.can_be_modified(),
            'can_receive': document.can_be_received(),
            'can_cancel': document.can_be_cancelled(),
            'is_paid': document.is_paid,
            'payment_overdue': document.is_overdue_payment() if not document.is_paid else False,
            'days_until_payment': document.get_days_until_payment()
        }

        # Workflow възможности
        next_actions = []

        if document.status == document.DRAFT:
            next_actions.extend(['confirm', 'cancel', 'edit'])
        elif document.status == document.CONFIRMED:
            next_actions.extend(['receive', 'cancel'])
        elif document.status == document.RECEIVED:
            if not document.is_paid:
                next_actions.append('mark_paid')

        status_info['available_actions'] = next_actions

        return status_info

    @staticmethod
    def get_document_financial_summary(document: PurchaseDocument) -> Dict:
        """Финансово резюме на документа"""

        lines = document.lines.all()

        summary = {
            'lines_count': lines.count(),
            'total_products': lines.values('product').distinct().count(),
            'subtotal': document.subtotal,
            'discount_amount': document.discount_amount,
            'vat_amount': document.vat_amount,
            'grand_total': document.grand_total,
        }

        # Анализ на редовете
        if lines.exists():
            line_analysis = lines.aggregate(
                total_quantity=models.Sum('quantity'),
                total_received=models.Sum('received_quantity'),
                avg_discount=models.Avg('discount_percent'),
                max_discount=models.Max('discount_percent'),
                lines_with_discount=models.Count('id', filter=models.Q(discount_percent__gt=0)),
                quality_issues=models.Count('id', filter=models.Q(quality_approved=False))
            )

            summary.update({
                'line_analysis': line_analysis,
                'avg_line_value': summary['subtotal'] / summary['lines_count'] if summary['lines_count'] > 0 else 0,
                'discount_percentage': (summary['discount_amount'] / summary['subtotal'] * 100) if summary[
                                                                                                       'subtotal'] > 0 else 0
            })

        return summary

    @staticmethod
    def get_document_variance_report(document: PurchaseDocument) -> Dict:
        """Отчет за отклонения между поръчано и получено"""

        if document.status not in [document.RECEIVED, document.CLOSED]:
            return {'message': 'Document not yet received'}

        lines = document.lines.with_analysis()

        variance_summary = {
            'total_lines': lines.count(),
            'perfect_matches': lines.filter(quantity_variance=0).count(),
            'over_received': lines.filter(quantity_variance__gt=0).count(),
            'under_received': lines.filter(quantity_variance__lt=0).count(),
        }

        # Детайлен анализ
        variance_details = []
        for line in lines:
            if line.quantity_variance != 0:
                variance_details.append({
                    'line_number': line.line_number,
                    'product_code': line.product.code,
                    'ordered': line.quantity,
                    'received': line.received_quantity,
                    'variance_qty': line.quantity_variance,
                    'variance_percent': line.quantity_variance_percent,
                    'variance_value': line.variance_value
                })

        # Общи стойности
        total_variance_value = sum(detail['variance_value'] for detail in variance_details)

        return {
            'summary': variance_summary,
            'details': variance_details,
            'total_variance_value': total_variance_value,
            'accuracy_rate': (variance_summary['perfect_matches'] / variance_summary['total_lines'] * 100) if
            variance_summary['total_lines'] > 0 else 0
        }

    @staticmethod
    def get_document_pricing_analysis(document: PurchaseDocument) -> Dict:
        """Анализ на ценообразуването за документа"""

        lines = document.lines.with_pricing_suggestions()

        if not lines.exists():
            return {'message': 'No pricing suggestions available'}

        pricing_summary = {
            'lines_with_suggestions': lines.count(),
            'total_lines': document.lines.count(),
            'suggested_revenue_increase': Decimal('0.00'),
            'avg_markup': Decimal('0.00')
        }

        pricing_details = []
        total_revenue_increase = Decimal('0.00')
        markup_values = []

        for line in lines:
            if line.old_sale_price and line.new_sale_price:
                revenue_increase = (line.new_sale_price - line.old_sale_price) * line.received_quantity
                total_revenue_increase += revenue_increase

                if line.markup_percentage:
                    markup_values.append(line.markup_percentage)

                pricing_details.append({
                    'line_number': line.line_number,
                    'product_code': line.product.code,
                    'current_price': line.old_sale_price,
                    'suggested_price': line.new_sale_price,
                    'price_increase': line.new_sale_price - line.old_sale_price,
                    'markup_percentage': line.markup_percentage,
                    'quantity': line.received_quantity,
                    'revenue_impact': revenue_increase
                })

        pricing_summary['suggested_revenue_increase'] = total_revenue_increase
        pricing_summary['avg_markup'] = sum(markup_values) / len(markup_values) if markup_values else 0

        return {
            'summary': pricing_summary,
            'details': pricing_details
        }

    @staticmethod
    def get_document_quality_report(document: PurchaseDocument) -> Dict:
        """Отчет за качеството на получените стоки"""

        lines = document.lines.all()

        quality_summary = {
            'total_lines': lines.count(),
            'approved_lines': lines.filter(quality_approved=True).count(),
            'rejected_lines': lines.filter(quality_approved=False).count(),
            'lines_with_notes': lines.exclude(quality_notes='').count()
        }

        quality_summary['approval_rate'] = (
                quality_summary['approved_lines'] / quality_summary['total_lines'] * 100
        ) if quality_summary['total_lines'] > 0 else 0

        # Issues details
        quality_issues = []
        for line in lines.filter(quality_approved=False):
            quality_issues.append({
                'line_number': line.line_number,
                'product_code': line.product.code,
                'quantity': line.received_quantity,
                'notes': line.quality_notes,
                'value_impact': line.line_total
            })

        total_rejected_value = sum(issue['value_impact'] for issue in quality_issues)

        return {
            'summary': quality_summary,
            'issues': quality_issues,
            'total_rejected_value': total_rejected_value,
            'rejection_rate': (quality_summary['rejected_lines'] / quality_summary['total_lines'] * 100) if
            quality_summary['total_lines'] > 0 else 0
        }

    @staticmethod
    def get_document_expiry_analysis(document: PurchaseDocument) -> Dict:
        """Анализ на сроковете на годност"""

        lines_with_expiry = document.lines.filter(expiry_date__isnull=False)

        if not lines_with_expiry.exists():
            return {'message': 'No products with expiry dates'}

        today = timezone.now().date()

        expiry_categories = {
            'expired': lines_with_expiry.filter(expiry_date__lt=today).count(),
            'expires_week': lines_with_expiry.filter(
                expiry_date__range=[today, today + timedelta(days=7)]
            ).count(),
            'expires_month': lines_with_expiry.filter(
                expiry_date__range=[today + timedelta(days=8), today + timedelta(days=30)]
            ).count(),
            'good_expiry': lines_with_expiry.filter(
                expiry_date__gt=today + timedelta(days=30)
            ).count()
        }

        # Детайли за критичните продукти
        critical_items = []
        for line in lines_with_expiry.filter(expiry_date__lte=today + timedelta(days=30)):
            days_to_expiry = (line.expiry_date - today).days

            critical_items.append({
                'line_number': line.line_number,
                'product_code': line.product.code,
                'batch_number': line.batch_number,
                'expiry_date': line.expiry_date,
                'days_to_expiry': days_to_expiry,
                'quantity': line.received_quantity,
                'status': 'expired' if days_to_expiry < 0 else 'critical'
            })

        return {
            'total_with_expiry': lines_with_expiry.count(),
            'categories': expiry_categories,
            'critical_items': sorted(critical_items, key=lambda x: x['days_to_expiry'])
        }

    @staticmethod
    @transaction.atomic
    def mark_document_paid(document: PurchaseDocument, payment_date=None, user=None) -> bool:
        """Маркира документ като платен"""

        if document.is_paid:
            raise ValidationError("Document is already marked as paid")

        if document.status not in [document.RECEIVED, document.CLOSED]:
            raise ValidationError("Can only mark received documents as paid")

        document.is_paid = True
        document.payment_date = payment_date or timezone.now().date()

        if document.status == document.RECEIVED:
            document.status = document.CLOSED

        if user:
            document.updated_by = user

        document.save()

        # Логваме действието
        from ..models import PurchaseAuditLog
        PurchaseAuditLog.log_action(
            document=document,
            action='PAYMENT',
            user=user,
            notes=f"Marked as paid on {document.payment_date}"
        )

        return True

    @staticmethod
    def get_document_audit_trail(document: PurchaseDocument) -> List[Dict]:
        """Връща audit trail за документа"""

        audit_logs = document.audit_logs.order_by('-timestamp')

        trail = []
        for log in audit_logs:
            trail.append({
                'timestamp': log.timestamp,
                'action': log.get_action_display(),
                'user': log.user.username if log.user else 'System',
                'field_name': log.field_name,
                'old_value': log.old_value,
                'new_value': log.new_value,
                'notes': log.notes
            })

        return trail

    @staticmethod
    def validate_document_data(document_data: Dict, lines_data: List[Dict]) -> List[str]:
        """Валидира данни за документ преди създаване"""
        errors = []

        # Валидация на основния документ
        required_fields = ['supplier', 'location', 'document_type', 'document_date']
        for field in required_fields:
            if field not in document_data or not document_data[field]:
                errors.append(f"Field '{field}' is required")

        # Валидация на редовете
        if not lines_data:
            errors.append("Document must have at least one line")

        for i, line_data in enumerate(lines_data, 1):
            line_errors = DocumentService.validate_line_data(line_data, i)
            errors.extend(line_errors)

        return errors

    @staticmethod
    def validate_line_data(line_data: Dict, line_number: int) -> List[str]:
        """Валидира данни за ред"""
        errors = []

        required_fields = ['product', 'quantity', 'unit', 'unit_price']
        for field in required_fields:
            if field not in line_data or line_data[field] is None:
                errors.append(f"Line {line_number}: Field '{field}' is required")

        # Валидация на стойности
        if 'quantity' in line_data and line_data['quantity'] <= 0:
            errors.append(f"Line {line_number}: Quantity must be positive")

        if 'unit_price' in line_data and line_data['unit_price'] < 0:
            errors.append(f"Line {line_number}: Unit price cannot be negative")

        if 'discount_percent' in line_data and (
                line_data['discount_percent'] < 0 or line_data['discount_percent'] > 100):
            errors.append(f"Line {line_number}: Discount percent must be between 0 and 100")

        return errors