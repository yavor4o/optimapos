# purchases/services/request_service.py - ПОЧИСТЕН

from typing import Dict, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from purchases.models.requests import PurchaseRequest, PurchaseRequestLine


class RequestService:
    """Service for Purchase Request business operations (NO WORKFLOW)"""

    # =====================
    # REQUEST CREATION
    # =====================

    @staticmethod
    @transaction.atomic
    def create_request(
            requested_by,
            supplier,
            location,
            request_type: str = 'regular',
            urgency_level: str = 'normal',
            business_justification: str = '',
            expected_usage: str = '',
            lines_data: Optional[List[Dict]] = None,
            **kwargs
    ) -> PurchaseRequest:
        """Create new purchase request with optional lines"""

        try:
            # Create the request
            request = PurchaseRequest.objects.create(
                requested_by=requested_by,
                supplier=supplier,
                location=location,
                request_type=request_type,
                urgency_level=urgency_level,
                business_justification=business_justification,
                expected_usage=expected_usage,
                status='draft',
                **kwargs
            )

            # Add lines if provided
            if lines_data:
                for line_data in lines_data:
                    RequestService.add_line_to_request(
                        request=request,
                        product=line_data['product'],
                        requested_quantity=line_data['requested_quantity'],
                        estimated_price=line_data.get('estimated_price'),
                        usage_description=line_data.get('usage_description', ''),
                        suggested_supplier=line_data.get('suggested_supplier'),
                        user=requested_by
                    )

            return request

        except Exception as e:
            raise ValidationError(f'Error creating request: {str(e)}')

    @staticmethod
    @transaction.atomic
    def duplicate_request(
            original_request: PurchaseRequest,
            requested_by,
            modifications: Optional[Dict] = None
    ) -> PurchaseRequest:
        """Create copy of existing request"""

        try:
            # Copy basic fields
            new_request = PurchaseRequest.objects.create(
                requested_by=requested_by,
                supplier=original_request.supplier,
                location=original_request.location,
                request_type=original_request.request_type,
                urgency_level=modifications.get('urgency_level', original_request.urgency_level),
                business_justification=modifications.get('business_justification',
                                                         original_request.business_justification),
                expected_usage=modifications.get('expected_usage', original_request.expected_usage),
                status='draft'
            )

            # Copy lines
            for original_line in original_request.lines.all():
                RequestService.add_line_to_request(
                    request=new_request,
                    product=original_line.product,
                    requested_quantity=original_line.requested_quantity,
                    estimated_price=original_line.estimated_price,
                    usage_description=original_line.usage_description,
                    suggested_supplier=original_line.suggested_supplier,
                    user=requested_by
                )

            return new_request

        except Exception as e:
            raise ValidationError(f'Error duplicating request: {str(e)}')

    # =====================
    # LINE MANAGEMENT
    # =====================

    @staticmethod
    @transaction.atomic
    def add_line_to_request(
            request: PurchaseRequest,
            product,
            requested_quantity: Decimal,
            estimated_price: Decimal = None,
            usage_description: str = '',
            suggested_supplier=None,
            user=None
    ) -> Dict:
        """Add line to purchase request"""

        if request.status != 'draft':
            raise ValidationError("Cannot modify non-draft requests")

        try:
            # Автоматично генерираме line_number
            next_line_number = (request.lines.count() + 1)

            line = PurchaseRequestLine.objects.create(
                document=request,
                line_number=next_line_number,
                product=product,
                requested_quantity=requested_quantity,
                estimated_price=estimated_price,
                usage_description=usage_description,
                suggested_supplier=suggested_supplier,
                unit=product.default_purchase_unit  # Вземи от продукта
            )

            return {
                'success': True,
                'message': f'Line added: {product.name}',
                'line': line
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error adding line: {str(e)}',
                'line': None
            }

    @staticmethod
    @transaction.atomic
    def update_line_quantity(
            line: PurchaseRequestLine,
            new_quantity: Decimal,
            user=None
    ) -> Dict:
        """Update line quantity"""

        if line.document.status != 'draft':
            raise ValidationError("Cannot modify non-draft requests")

        try:
            old_quantity = line.requested_quantity
            line.requested_quantity = new_quantity
            line.save()

            return {
                'success': True,
                'message': f'Quantity updated: {old_quantity} → {new_quantity}',
                'line': line
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error updating quantity: {str(e)}',
                'line': line
            }

    @staticmethod
    @transaction.atomic
    def remove_line_from_request(
            line: PurchaseRequestLine,
            user=None
    ) -> Dict:
        """Remove line from request"""

        if line.document.status != 'draft':
            raise ValidationError("Cannot modify non-draft requests")

        try:
            request = line.document
            product_name = line.product.name
            line.delete()

            # Reorder line numbers
            RequestService._reorder_line_numbers(request)

            return {
                'success': True,
                'message': f'Line removed: {product_name}',
                'request': request
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Error removing line: {str(e)}',
                'line': line
            }

    @staticmethod
    def _reorder_line_numbers(request: PurchaseRequest):
        """Reorder line numbers after deletion"""
        lines = request.lines.order_by('line_number')
        for idx, line in enumerate(lines, 1):
            if line.line_number != idx:
                line.line_number = idx
                line.save(update_fields=['line_number'])

    # =====================
    # ANALYTICS & REPORTING
    # =====================

    @staticmethod
    def get_request_analytics(request: PurchaseRequest) -> Dict:
        """Get comprehensive analytics for specific request"""

        return {
            'basic_info': {
                'document_number': request.document_number,
                'status': request.status,
                'request_type': request.request_type,
                'urgency_level': request.urgency_level,
                'created_at': request.created_at,
                'requested_by': request.requested_by.get_full_name() if request.requested_by else None
            },
            'workflow_timing': {
                'time_to_submit': RequestService._calculate_time_to_submit(request),
                'time_to_approve': RequestService._calculate_time_to_approve(request),
                'time_to_convert': RequestService._calculate_time_to_convert(request),
                'total_processing_time': RequestService._calculate_total_processing_time(request)
            },
            'content_analysis': {
                'total_lines': request.lines.count(),
                'total_items': sum(line.requested_quantity for line in request.lines.all()),
                'estimated_total': RequestService._calculate_estimated_total(request),
                'lines_with_estimates': request.lines.filter(estimated_price__isnull=False).count(),
                'lines_with_suppliers': request.lines.filter(suggested_supplier__isnull=False).count(),
                'high_priority_lines': request.lines.filter(priority__gt=0).count(),
            },
            'supplier_analysis': RequestService._analyze_suppliers(request),
            'product_categories': RequestService._analyze_product_categories(request)
        }

    # =====================
    # BUSINESS CALCULATIONS
    # =====================

    @staticmethod
    def calculate_request_totals(request: PurchaseRequest) -> Dict:
        """Calculate various totals for the request"""

        lines = request.lines.all()

        total_items = sum(line.requested_quantity for line in lines)
        estimated_total = sum(
            line.estimated_price * line.requested_quantity
            for line in lines
            if line.estimated_price
        ) or Decimal('0.00')

        lines_with_estimates = lines.filter(estimated_price__isnull=False).count()
        estimate_coverage = (lines_with_estimates / lines.count() * 100) if lines.count() > 0 else 0

        return {
            'total_lines': lines.count(),
            'total_items': total_items,
            'estimated_total': estimated_total,
            'lines_with_estimates': lines_with_estimates,
            'estimate_coverage_percent': round(estimate_coverage, 1),
            'average_item_value': (estimated_total / total_items) if total_items > 0 else Decimal('0.00')
        }

    @staticmethod
    def validate_request_completeness(request: PurchaseRequest) -> Dict:
        """Validate if request is complete enough for submission"""

        issues = []
        warnings = []

        # Check lines
        if not request.lines.exists():
            issues.append("Request has no lines")

        # Check justification
        if not request.business_justification:
            issues.append("Business justification is required")

        # Check estimates for high-value requests
        lines_without_estimates = request.lines.filter(estimated_price__isnull=True).count()
        if lines_without_estimates > 0:
            warnings.append(f"{lines_without_estimates} lines missing price estimates")

        # Check urgency justification
        if request.urgency_level in ['high', 'critical'] and not request.expected_usage:
            warnings.append("High/critical requests should have detailed usage description")

        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'completeness_score': RequestService._calculate_completeness_score(request)
        }

    # =====================
    # HELPER METHODS
    # =====================

    @staticmethod
    def _calculate_time_to_submit(request: PurchaseRequest) -> Optional[int]:
        """Calculate days from creation to submission"""
        if request.status in ['submitted', 'approved', 'converted', 'rejected']:
            # Approximate submit time as creation time if not tracked separately
            return 0  # Same day submission assumed
        return None

    @staticmethod
    def _calculate_time_to_approve(request: PurchaseRequest) -> Optional[int]:
        """Calculate days from submission to approval"""
        if request.approved_at and request.created_at:
            return (request.approved_at.date() - request.created_at.date()).days
        return None

    @staticmethod
    def _calculate_time_to_convert(request: PurchaseRequest) -> Optional[int]:
        """Calculate days from approval to conversion"""
        if request.converted_at and request.approved_at:
            return (request.converted_at.date() - request.approved_at.date()).days
        return None

    @staticmethod
    def _calculate_total_processing_time(request: PurchaseRequest) -> Optional[int]:
        """Calculate total processing time"""
        if request.converted_at and request.created_at:
            return (request.converted_at.date() - request.created_at.date()).days
        elif request.approved_at and request.created_at:
            return (request.approved_at.date() - request.created_at.date()).days
        return None

    @staticmethod
    def _calculate_estimated_total(request: PurchaseRequest) -> Decimal:
        """Calculate estimated total value"""
        return sum(
            line.estimated_price * line.requested_quantity
            for line in request.lines.all()
            if line.estimated_price
        ) or Decimal('0.00')

    @staticmethod
    def _analyze_suppliers(request: PurchaseRequest) -> Dict:
        """Analyze suggested suppliers"""
        lines_with_suppliers = request.lines.filter(suggested_supplier__isnull=False)

        supplier_breakdown = {}
        for line in lines_with_suppliers:
            supplier_name = line.suggested_supplier.name
            if supplier_name not in supplier_breakdown:
                supplier_breakdown[supplier_name] = {
                    'lines': 0,
                    'total_quantity': Decimal('0'),
                    'estimated_value': Decimal('0')
                }

            supplier_breakdown[supplier_name]['lines'] += 1
            supplier_breakdown[supplier_name]['total_quantity'] += line.requested_quantity
            if line.estimated_price:
                supplier_breakdown[supplier_name]['estimated_value'] += (
                        line.estimated_price * line.requested_quantity
                )

        return {
            'total_suppliers': len(supplier_breakdown),
            'lines_with_suppliers': lines_with_suppliers.count(),
            'supplier_breakdown': supplier_breakdown
        }

    @staticmethod
    def _analyze_product_categories(request: PurchaseRequest) -> Dict:
        """Analyze product categories in request"""
        lines = request.lines.select_related('product', 'product__group')

        category_breakdown = {}
        for line in lines:
            category = line.product.group.name if line.product.group else 'Uncategorized'
            if category not in category_breakdown:
                category_breakdown[category] = {
                    'lines': 0,
                    'total_quantity': Decimal('0'),
                    'estimated_value': Decimal('0')
                }

            category_breakdown[category]['lines'] += 1
            category_breakdown[category]['total_quantity'] += line.requested_quantity
            if line.estimated_price:
                category_breakdown[category]['estimated_value'] += (
                        line.estimated_price * line.requested_quantity
                )

        return {
            'total_categories': len(category_breakdown),
            'category_breakdown': category_breakdown
        }

    @staticmethod
    def _calculate_completeness_score(request: PurchaseRequest) -> int:
        """Calculate completeness score (0-100)"""
        score = 0

        # Basic info (40 points)
        if request.lines.exists():
            score += 20
        if request.business_justification:
            score += 20

        # Detail completeness (30 points)
        total_lines = request.lines.count()
        if total_lines > 0:
            lines_with_estimates = request.lines.filter(estimated_price__isnull=False).count()
            lines_with_suppliers = request.lines.filter(suggested_supplier__isnull=False).count()

            score += int((lines_with_estimates / total_lines) * 15)
            score += int((lines_with_suppliers / total_lines) * 15)

        # Additional details (30 points)
        if request.expected_usage:
            score += 15
        if request.urgency_level != 'normal':
            if request.expected_usage:  # Justified urgency
                score += 15
            else:
                score += 5  # Unjustified urgency
        else:
            score += 10  # Normal urgency

        return min(score, 100)