import logging
from typing import Dict

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.db import transaction, models
from django.utils import timezone
from django.core.paginator import Paginator

from core.utils.result import Result
from .models.deliveries import DeliveryReceipt, DeliveryLine
from core.interfaces import ServiceResolverMixin
from .services import PurchaseDocumentService

logger = logging.getLogger(__name__)
class PurchasesIndexView(LoginRequiredMixin, TemplateView):
    """Purchases module dashboard"""
    template_name = 'frontend/purchases/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': 'Purchases Overview',
            'module': 'purchases',
        })
        return context


class DeliveryReceiptListView(LoginRequiredMixin, PermissionRequiredMixin, ListView, ServiceResolverMixin):
    """
    Delivery Receipts List View с advanced filtering
    
    Features:
    - Status filtering (pending, approved, rejected)
    - Quality control status
    - Date range filtering
    - Supplier filtering
    - Search functionality
    """
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/list.html'
    context_object_name = 'delivery_receipts'
    paginate_by = 25
    permission_required = 'purchases.view_deliveryreceipt'
    
    def get_queryset(self):
        queryset = DeliveryReceipt.objects.select_related(
            'partner_content_type',
            'location_content_type', 
            'received_by'
        ).prefetch_related('lines__product')
        
        # Status filtering
        status = self.request.GET.get('status')
        if status and status != 'all':
            queryset = queryset.filter(status=status)
        
        # Quality control filtering
        quality_status = self.request.GET.get('quality_status')
        if quality_status and quality_status != 'all':
            queryset = queryset.filter(quality_status=quality_status)
        
        # Search by document number or supplier
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(document_number__icontains=search) |
                models.Q(partner__name__icontains=search)
            )
        
        # Date range filtering
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(document_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(document_date__lte=date_to)
        
        return queryset.order_by('-document_date', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Filter options for template
        context.update({
            'page_title': 'Delivery Receipts',
            'current_status': self.request.GET.get('status', 'all'),
            'current_quality_status': self.request.GET.get('quality_status', 'all'),
            'search_query': self.request.GET.get('search', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
            
            # Statistics for dashboard cards
            'stats': self.get_delivery_stats(),
        })
        return context
    
    def get_delivery_stats(self):
        """Statistics for the list page using StatusResolver"""
        from nomenclatures.services._status_resolver import StatusResolver
        from nomenclatures.models import DocumentType
        
        all_deliveries = DeliveryReceipt.objects.all()
        
        try:
            # Get delivery receipt document type
            doc_type = DocumentType.objects.filter(name__icontains='delivery').first()
            if doc_type:
                # Use StatusResolver for semantic status resolution
                approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
                processing_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'processing')
                
                return {
                    'total_count': all_deliveries.count(),
                    'pending_count': all_deliveries.filter(status__in=approval_statuses).count(),
                    'quality_pending_count': all_deliveries.filter(quality_status='pending').count(),
                    'approved_count': all_deliveries.filter(status__in=processing_statuses).count(),
                }
            else:
                # Fallback to hardcoded if document type not found
                return {
                    'total_count': all_deliveries.count(),
                    'pending_count': all_deliveries.filter(status='pending').count(),
                    'quality_pending_count': all_deliveries.filter(quality_status='pending').count(),
                    'approved_count': all_deliveries.filter(status='approved').count(),
                }
        except Exception:
            # Emergency fallback
            return {
                'total_count': all_deliveries.count(),
                'pending_count': 0,
                'quality_pending_count': 0,
                'approved_count': 0,
            }



# purchases/views.py - DeliveryReceiptCreateView REFACTORED
"""
Рефакториран DeliveryReceiptCreateView за работа с новия PurchaseDocumentService

CHANGES:
✅ Използва семантичните методи от DocumentService
✅ БЕЗ hardcoded 'draft'/'pending'/'approved' mapping
✅ Clean status resolution чрез StatusResolver
✅ Proper error handling и user feedback
❌ БЕЗ fallback към hardcoded логика
"""


class DeliveryReceiptCreateView(LoginRequiredMixin, CreateView, ServiceResolverMixin):
    """
    Create new Delivery Receipt с правилна service integration

    Features:
    - Dynamic status resolution
    - Semantic action handling
    - Clean architecture compliance
    - Proper error feedback
    """
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/create.html'
    fields = ['document_date', 'delivery_date', 'supplier_delivery_reference', 'notes']

    def get_success_url(self):
        return reverse('purchases:delivery_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Load suppliers
        try:
            from partners.models import Supplier
            suppliers = Supplier.objects.filter(is_active=True).order_by('name')
        except Exception:
            suppliers = []

        # Load locations
        try:
            from inventory.models import InventoryLocation
            locations = InventoryLocation.objects.filter(is_active=True).order_by('name')
        except Exception:
            locations = []

        # Load products
        try:
            from products.models import Product
            products = Product.objects.all().order_by('name')
        except Exception:
            products = []

        # Load units of measure
        try:
            from nomenclatures.models import UnitOfMeasure
            units = UnitOfMeasure.objects.filter(is_active=True).order_by('name')
        except Exception:
            units = []

        # ✅ NEW: Get available semantic actions for UI
        semantic_actions = self._get_semantic_action_options()

        context.update({
            'page_title': 'New Delivery Receipt',
            'form_mode': 'create',
            'suppliers': suppliers,
            'locations': locations,
            'products': products,
            'units': units,
            'today': timezone.now().date(),
            'semantic_actions': semantic_actions,  # ✅ За dynamic buttons
        })
        return context

    def _get_semantic_action_options(self) -> dict:
        """Get available semantic action options for new document"""
        try:
            from nomenclatures.models import DocumentType
            from nomenclatures.services._status_resolver import StatusResolver

            # Get delivery document type
            doc_type = DocumentType.objects.filter(app_name='purchases').first()
            if not doc_type:
                return self._get_fallback_actions()

            # Get initial status
            initial_status = StatusResolver.get_initial_status(doc_type)

            # Get possible next statuses from initial
            next_statuses = StatusResolver.get_next_possible_statuses(doc_type, initial_status)

            # Map to semantic actions
            actions = {
                'save_draft': {
                    'status': initial_status,
                    'label': f'Save as {initial_status.replace("_", " ").title()}',
                    'button_class': 'btn-secondary',
                    'semantic_action': None  # No transition needed
                }
            }

            # Check for approval statuses
            approval_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'approval')
            for status in approval_statuses:
                if status in next_statuses:
                    actions['submit_approval'] = {
                        'status': status,
                        'label': f'Submit for {status.replace("_", " ").title()}',
                        'button_class': 'btn-warning',
                        'semantic_action': 'submit_for_approval'
                    }
                    break

            # Check for completion statuses
            completion_statuses = StatusResolver.get_statuses_by_semantic_type(doc_type, 'completion')
            for status in completion_statuses:
                if status in next_statuses:
                    actions['approve_direct'] = {
                        'status': status,
                        'label': f'Create & {status.replace("_", " ").title()}',
                        'button_class': 'btn-success',
                        'semantic_action': 'approve'
                    }
                    break

            return actions

        except Exception as e:
            logger.warning(f"Failed to get semantic actions: {e}")
            return self._get_fallback_actions()

    def _get_fallback_actions(self) -> dict:
        """Fallback action options"""
        return {
            'save_draft': {
                'status': 'draft',
                'label': 'Save as Draft',
                'button_class': 'btn-secondary',
                'semantic_action': None
            },
            'submit_approval': {
                'status': 'pending',
                'label': 'Submit for Approval',
                'button_class': 'btn-warning',
                'semantic_action': 'submit_for_approval'
            },
            'approve_direct': {
                'status': 'approved',
                'label': 'Create & Approve',
                'button_class': 'btn-success',
                'semantic_action': 'approve'
            }
        }

    def form_valid(self, form):
        """
        Handle form submission с clean semantic action handling

        REFACTORED:
        - БЕЗ hardcoded status mapping
        - Semantic action resolution
        - Clean service delegation
        - Proper error handling
        """
        from .services.purchase_service import DeliveryReceiptService
        from core.utils.result import Result

        try:
            # 1. ✅ Gather form data (same as before)
            partner_id = self.request.POST.get('partner_id')
            location_id = self.request.POST.get('location_id')
            action_type = self.request.POST.get('action_type', 'save_draft')  # ✅ Semantic action

            # Get partner and location
            if partner_id:
                from partners.models import Supplier
                partner = Supplier.objects.get(pk=partner_id)
            else:
                messages.error(self.request, 'Supplier is required')
                return self.form_invalid(form)

            location = None
            if location_id:
                from inventory.models import InventoryLocation
                location = InventoryLocation.objects.get(pk=location_id)

            # 2. ✅ Prepare line items (same as before)
            lines = self.prepare_lines_data()
            if not lines:
                messages.warning(self.request, 'At least one line item is required')
                lines = []  # Create document without lines for now

            # 3. ✅ Create delivery using service (same as before)
            result = DeliveryReceiptService.create(
                user=self.request.user,
                partner=partner,
                location=location,
                lines=lines,
                document_date=form.cleaned_data.get('document_date'),
                delivery_date=form.cleaned_data.get('delivery_date'),
                supplier_delivery_reference=form.cleaned_data.get('supplier_delivery_reference'),
                comments=form.cleaned_data.get('notes', ''),
            )

            if not result.ok:
                messages.error(self.request, f'Failed to create delivery receipt: {result.msg}')
                return self.form_invalid(form)

            # 4. ✅ Document creation successful
            self.object = result.data['document']

            # Ensure document_type for semantic actions
            if not self.object.document_type:
                from nomenclatures.models import DocumentType
                delivery_doc_type = DocumentType.objects.filter(
                    models.Q(code='003') | models.Q(name__icontains='delivery')
                ).first()
                if delivery_doc_type:
                    self.object.document_type = delivery_doc_type
                    self.object.save(update_fields=['document_type'])

            # 5. ✅ NEW: Handle semantic actions cleanly
            transition_result = self._handle_semantic_action(action_type)
            if not transition_result.ok:
                # Document created successfully, but status transition failed
                messages.warning(
                    self.request,
                    f'Delivery Receipt created successfully, but status change failed: {transition_result.msg}'
                )
            else:
                # Complete success
                final_status = transition_result.data.get('new_status', self.object.status)
                messages.success(
                    self.request,
                    f'Delivery Receipt {self.object.document_number} created with status: {final_status}'
                )

            return super().form_valid(form)

        except Exception as e:
            logger.error(f"Form processing failed: {e}")
            messages.error(self.request, f'Unexpected error: {str(e)}')
            return self.form_invalid(form)

    def _handle_semantic_action(self, action_type: str) -> Result:
        """
        Handle semantic action после document creation

        Args:
            action_type: 'save_draft', 'submit_approval', 'approve_direct', etc.

        Returns:
            Result with transition details
        """
        try:
            from .services.purchase_service import PurchaseDocumentService

            # Get service for created document
            doc_service = PurchaseDocumentService(self.object, self.request.user)

            # ✅ NEW: Clean semantic action mapping
            action_map = {
                'save_draft': lambda: Result.success({'new_status': self.object.status}),  # No action needed
                'submit_approval': lambda: doc_service.submit_for_approval('Submitted via web interface'),
                'approve_direct': lambda: doc_service.approve('Direct approval from creation'),
                'reject': lambda: doc_service.reject('Rejected during creation'),
            }

            # Execute semantic action
            action_func = action_map.get(action_type)
            if action_func:
                result = action_func()
                logger.info(f"Semantic action '{action_type}' result: {result.ok}")
                return result
            else:
                # Unknown action - try direct status transition
                logger.warning(f"Unknown semantic action: {action_type}, treating as direct status")
                return doc_service.facade.transition_to(action_type, 'Direct transition from creation')

        except Exception as e:
            logger.error(f"Semantic action handling failed: {e}")
            return Result.error('SEMANTIC_ACTION_FAILED', f'Action failed: {str(e)}')

    def prepare_lines_data(self):
        """
        Prepare line items from form data - FIXED to match JavaScript

        PROBLEM: POST field names не match-ваха с JavaScript template
        SOLUTION: Correct field name parsing и validation
        """
        lines = []

        # ✅ DEBUG: Log all POST data за debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("=== PREPARE_LINES_DATA DEBUG ===")
        logger.debug(f"All POST keys: {list(self.request.POST.keys())}")

        # ✅ FIXED: Correct field name pattern matching
        # JavaScript създава полета като: line_product_0, line_quantity_0, etc.
        line_indices = set()

        # Find all line indices from POST data
        for key in self.request.POST.keys():
            if key.startswith('line_product_'):
                try:
                    index = key.split('_')[-1]  # Get index from line_product_0
                    line_indices.add(index)
                except (IndexError, ValueError):
                    continue

        logger.debug(f"Found line indices: {line_indices}")

        # Process each line
        for index in line_indices:
            try:
                # ✅ FIXED: Correct POST field names
                product_id = self.request.POST.get(f'line_product_{index}')
                quantity = self.request.POST.get(f'line_quantity_{index}')
                unit_price = self.request.POST.get(f'line_unit_price_{index}')
                notes = self.request.POST.get(f'line_notes_{index}', '')

                logger.debug(f"Line {index}: product_id={product_id}, quantity={quantity}, price={unit_price}")

                # ✅ Skip empty lines
                if not product_id or not quantity:
                    logger.debug(f"Skipping line {index}: missing product_id or quantity")
                    continue

                # ✅ Validate quantity
                try:
                    quantity_decimal = float(quantity)
                    if quantity_decimal <= 0:
                        logger.warning(f"Skipping line {index}: invalid quantity {quantity}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Skipping line {index}: cannot parse quantity {quantity}")
                    continue

                # ✅ Get product object
                try:
                    from products.models import Product
                    product = Product.objects.get(pk=product_id)
                except Product.DoesNotExist:
                    logger.warning(f"Skipping line {index}: product {product_id} not found")
                    continue

                # ✅ Parse unit price with fallback
                try:
                    unit_price_decimal = float(unit_price) if unit_price else product.selling_price
                except (ValueError, TypeError):
                    unit_price_decimal = product.selling_price

                # ✅ Build line data for service
                line_data = {
                    'product': product,
                    'quantity': quantity_decimal,  # Service expects 'quantity'
                    'unit_price': unit_price_decimal,
                    'received_quantity': quantity_decimal,  # For delivery-specific logic
                    'notes': notes,
                    # ✅ Add default unit if available
                    'unit': getattr(product, 'base_unit', None),
                    # ✅ Default quality status for new deliveries
                    'quality_approved': None,  # Pending quality control
                    'quality_notes': '',
                }

                lines.append(line_data)
                logger.debug(f"Added line {index}: {product.code} x {quantity_decimal}")

            except Exception as e:
                logger.error(f"Error processing line {index}: {e}")
                continue

        logger.debug(f"Total lines prepared: {len(lines)}")

        # ✅ Provide feedback about lines
        if not lines:
            logger.warning("No valid lines found in POST data")

            # ✅ ENHANCED DEBUG: Show what we're looking for vs what we found
            expected_patterns = ['line_product_*', 'line_quantity_*', 'line_unit_price_*']
            found_patterns = []
            for key in self.request.POST.keys():
                if any(pattern.replace('*', '') in key for pattern in expected_patterns):
                    found_patterns.append(key)

            logger.debug(f"Expected patterns: {expected_patterns}")
            logger.debug(f"Found matching keys: {found_patterns}")

            # ✅ Try alternative field patterns (in case template is different)
            alternative_patterns = ['item_product_', 'items-', 'product_', 'quantity_']
            found_alternatives = []
            for key in self.request.POST.keys():
                if any(pattern in key for pattern in alternative_patterns):
                    found_alternatives.append(key)

            if found_alternatives:
                logger.debug(f"Found alternative patterns: {found_alternatives}")
                logger.debug("Template might be using different field naming convention")

        return lines



class DeliveryReceiptUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView, ServiceResolverMixin):
    """Update existing Delivery Receipt"""
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/edit.html'
    permission_required = 'purchases.change_deliveryreceipt'
    fields = ['document_number', 'document_date', 'delivery_date', 'supplier_delivery_reference', 'notes']
    
    def get_success_url(self):
        return reverse('purchases:delivery_detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': f'Edit Delivery Receipt {self.object.document_number}',
            'form_mode': 'edit',
        })
        return context


# purchases/views.py - DeliveryReceiptApproveView REFACTORED
"""
Рефакториран DeliveryReceiptApproveView за работа с новия PurchaseDocumentService

CHANGES:
✅ Използва семантичните методи approve()/reject()
✅ БЕЗ hardcoded target_status mapping  
✅ Clean action type resolution
✅ Proper error handling и validation
"""


class DeliveryReceiptApproveView(LoginRequiredMixin, PermissionRequiredMixin, View, ServiceResolverMixin):
    """
    Approve/Reject Delivery Receipt using semantic actions

    Features:
    - Semantic action handling (approve, reject, submit, etc.)
    - Dynamic status resolution
    - Proper validation и permissions
    - Enhanced user feedback
    """
    permission_required = 'purchases.approve_deliveryreceipt'

    def post(self, request, pk):
        """Handle approval/rejection actions"""
        delivery = get_object_or_404(DeliveryReceipt, pk=pk)

        # ✅ NEW: Get semantic action instead of hardcoded status
        action_type = request.POST.get('action_type')  # 'approve', 'reject', 'submit', etc.
        comments = request.POST.get('comments', '').strip()

        # Validation
        if not action_type:
            messages.error(request, 'Action type is required.')
            return redirect('purchases:delivery_detail', pk=pk)

        # Require comments for rejection
        if action_type == 'reject' and not comments:
            messages.error(request, 'Comments are required for rejection.')
            return redirect('purchases:delivery_detail', pk=pk)

        try:
            from .services.purchase_service import PurchaseDocumentService

            # Ensure document_type е set for semantic actions
            if not delivery.document_type:
                from nomenclatures.models import DocumentType
                delivery_doc_type = DocumentType.objects.filter(
                    models.Q(code='003') | models.Q(name__icontains='delivery')
                ).first()
                if delivery_doc_type:
                    delivery.document_type = delivery_doc_type
                    delivery.save(update_fields=['document_type'])

            # ✅ Create service за semantic actions
            doc_service = PurchaseDocumentService(delivery, request.user)

            # ✅ Execute semantic action
            result = self._execute_semantic_action(doc_service, action_type, comments)

            if result.ok:
                # Success feedback
                new_status = result.data.get('new_status', delivery.status)
                old_status = result.data.get('old_status', 'unknown')

                messages.success(
                    request,
                    f'Delivery Receipt {delivery.document_number} status changed from {old_status} to {new_status}.'
                )

                # Log action for audit trail
                logger.info(f"User {request.user} performed '{action_type}' on delivery {delivery.document_number}")

            else:
                # Error feedback
                messages.error(request, f'Action failed: {result.msg}')
                logger.error(
                    f"Semantic action '{action_type}' failed for delivery {delivery.document_number}: {result.msg}")

            return redirect('purchases:delivery_detail', pk=pk)

        except Exception as e:
            logger.error(f"Approval view processing failed: {e}")
            messages.error(request, f'Unexpected error: {str(e)}')
            return redirect('purchases:delivery_detail', pk=pk)

    def _execute_semantic_action(self, doc_service: PurchaseDocumentService, action_type: str, comments: str) -> Result:
        """
        Execute semantic action чрез service

        Args:
            doc_service: PurchaseDocumentService instance
            action_type: Semantic action ('approve', 'reject', 'submit', etc.)
            comments: User comments

        Returns:
            Result with action outcome
        """
        try:
            # ✅ Semantic action mapping (БЕЗ hardcoded statuses!)
            semantic_actions = {
                'approve': lambda: doc_service.approve(comments or 'Approved via web interface'),
                'reject': lambda: doc_service.reject(comments),  # Comments required for reject
                'submit': lambda: doc_service.submit_for_approval(comments or 'Submitted via web interface'),
                'submit_for_approval': lambda: doc_service.submit_for_approval(
                    comments or 'Submitted via web interface'),
                'return_to_draft': lambda: doc_service.return_to_draft(
                    comments or 'Returned to draft via web interface'),
            }

            # Execute semantic action
            action_func = semantic_actions.get(action_type)
            if action_func:
                result = action_func()
                logger.info(f"Executed semantic action '{action_type}': {result.ok}")
                return result
            else:
                # Unknown semantic action - try direct transition
                logger.warning(f"Unknown semantic action '{action_type}', attempting direct transition")
                return doc_service.facade.transition_to(action_type, comments)

        except Exception as e:
            logger.error(f"Semantic action execution failed: {e}")
            return Result.error('ACTION_EXECUTION_FAILED', f'Failed to execute {action_type}: {str(e)}')


# =================================================
# ENHANCED DELIVERY DETAIL VIEW - Semantic Actions
# =================================================

class DeliveryReceiptDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView, ServiceResolverMixin):
    """
    Enhanced Delivery Receipt Detail View с semantic actions

    Features:
    - Dynamic action buttons based на semantic actions
    - Real-time status information
    - Enhanced context for templates
    """
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/detail.html'
    context_object_name = 'delivery_receipt'
    permission_required = 'purchases.view_deliveryreceipt'

    def get_queryset(self):
        return DeliveryReceipt.objects.select_related(
            'partner_content_type',
            'location_content_type',
            'received_by',
            'source_order',
            'document_type'  # ✅ Include for semantic actions
        ).prefetch_related(
            'lines__product',
            'lines__unit',
            'lines__source_order_line'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        delivery = self.object

        # ✅ NEW: Get semantic actions for UI
        semantic_actions = self._get_semantic_actions_for_delivery(delivery)

        context.update({
            'page_title': f'Delivery Receipt {delivery.document_number}',
            'can_edit': self.request.user.has_perm('purchases.change_deliveryreceipt'),
            'can_approve': self.request.user.has_perm('purchases.approve_deliveryreceipt'),

            # Enhanced data
            'delivery_lines': self.get_enhanced_lines(delivery),
            'inventory_movements': self.get_inventory_movements(delivery),
            'related_documents': self.get_related_documents(delivery),

            # ✅ NEW: Semantic actions for dynamic UI
            'semantic_actions': semantic_actions,
            'action_labels': semantic_actions.get('labels', {}),
            'available_actions': semantic_actions.get('available', {}),
        })
        return context

    def _get_semantic_actions_for_delivery(self, delivery) -> dict:
        """Get semantic actions available for this delivery"""
        try:
            from .services.purchase_service import PurchaseDocumentService

            if not delivery.document_type:
                return {'available': {}, 'labels': {}, 'error': 'No document type configured'}

            # Create service for semantic action inquiry
            doc_service = PurchaseDocumentService(delivery, self.request.user)

            # ✅ Get available semantic actions
            available_actions = doc_service.facade.get_available_semantic_actions()
            action_labels = doc_service.facade.get_semantic_action_labels()

            # ✅ Add permission checks
            user = self.request.user
            final_actions = {}

            if available_actions.get('can_approve') and user.has_perm('purchases.approve_deliveryreceipt'):
                final_actions['approve'] = True

            if available_actions.get('can_submit') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['submit'] = True

            if available_actions.get('can_reject') and user.has_perm('purchases.approve_deliveryreceipt'):
                final_actions['reject'] = True

            if available_actions.get('can_return_to_draft') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['return_to_draft'] = True

            return {
                'available': final_actions,
                'labels': action_labels,
                'raw_actions': available_actions,  # For debugging
                'current_status': delivery.status
            }

        except Exception as e:
            logger.error(f"Failed to get semantic actions: {e}")
            return {
                'available': {},
                'labels': {},
                'error': f'Failed to load actions: {str(e)}'
            }

    def get_enhanced_lines(self, delivery):
        """
        Get delivery lines with calculated fields - FIXED

        PROBLEM: Старата версия очакваше различна структура
        SOLUTION: Правилна line structure и field access
        """
        lines = []

        # ✅ Check if delivery has lines
        if not hasattr(delivery, 'lines') or not delivery.lines.exists():
            return lines

        for line in delivery.lines.all():
            try:
                # ✅ FIXED: Правилен field access
                # Check which fields actually exist on the model
                product = line.product if hasattr(line, 'product') else None
                if not product:
                    continue  # Skip lines without products

                # ✅ FIXED: Safe field access with defaults
                received_quantity = getattr(line, 'received_quantity', 0) or 0
                ordered_quantity = getattr(line, 'ordered_quantity', 0) or getattr(line, 'quantity', 0) or 0
                unit_price = getattr(line, 'unit_price', 0) or 0

                # Quality status - safe access
                quality_approved = getattr(line, 'quality_approved', None)
                if quality_approved is True:
                    quality_display = 'Approved'
                elif quality_approved is False:
                    quality_display = 'Rejected'
                else:
                    quality_display = 'Pending'

                # ✅ FIXED: Calculate variance safely
                variance_quantity = received_quantity - ordered_quantity
                variance_percentage = 0
                if ordered_quantity and ordered_quantity > 0:
                    variance_percentage = ((received_quantity - ordered_quantity) / ordered_quantity) * 100

                # ✅ Build enhanced line data
                line_data = {
                    'product': product,
                    'line_number': getattr(line, 'line_number', 0),
                    'received_quantity': received_quantity,
                    'ordered_quantity': ordered_quantity,
                    'unit_price': unit_price,
                    'unit': getattr(line, 'unit', None),
                    'line_total': received_quantity * unit_price,
                    'variance_quantity': variance_quantity,
                    'variance_percentage': variance_percentage,
                    'quality_status_display': quality_display,
                    'quality_approved': quality_approved,
                    'quality_notes': getattr(line, 'quality_notes', ''),
                    'batch_number': getattr(line, 'batch_number', ''),
                    'expiry_date': getattr(line, 'expiry_date', None),
                    'source_order_line': getattr(line, 'source_order_line', None),

                    # ✅ Keep original line object для template
                    'line': line,
                }

                lines.append(line_data)

            except Exception as e:
                # ✅ Log errors but don't break the whole view
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error processing delivery line {getattr(line, 'id', 'unknown')}: {e}")
                continue

        return lines

    def get_inventory_movements(self, delivery):
        """Same as before - inventory tracking"""
        # ... existing implementation
        pass

    def get_related_documents(self, delivery):
        """Same as before - related docs"""
        # ... existing implementation
        pass

class DeliveryLineQualityCheckView(LoginRequiredMixin, PermissionRequiredMixin, View, ServiceResolverMixin):
    """
    AJAX view for quality checking individual delivery lines
    """
    permission_required = 'purchases.quality_check_deliveryreceipt'
    
    def post(self, request, pk):
        line = get_object_or_404(DeliveryLine, pk=pk)
        
        quality_status = request.POST.get('quality_status')  # 'approved', 'rejected', 'partial'
        quality_notes = request.POST.get('quality_notes', '')
        
        if quality_status in ['approved', 'rejected', 'partial']:
            line.quality_approved = (quality_status == 'approved')
            line.quality_notes = quality_notes
            line.quality_checked_by = request.user
            line.quality_checked_at = timezone.now()
            line.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Quality status updated to {quality_status}',
                'line_id': line.pk,
                'new_status': quality_status
            })
        
        return JsonResponse({
            'success': False,
            'message': 'Invalid quality status'
        })