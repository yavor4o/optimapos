import logging
from typing import Dict, List

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.db import transaction, models
from django.utils import timezone


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
        """ОПРОСТЕНО: Statistics без semantic типове"""
        all_deliveries = DeliveryReceipt.objects.all()
        
        # Просто броим по конкретни статуси без сложни семантици
        return {
            'total_count': all_deliveries.count(),
            'pending_count': all_deliveries.filter(status='pending').count(),
            'quality_pending_count': all_deliveries.filter(quality_status='pending').count(),
            'approved_count': all_deliveries.filter(status='approved').count(),
        }

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

        # ✅ OPTIMIZED: Single try-except block with specific exception handling
        try:
            from partners.models import Supplier
            from inventory.models import InventoryLocation  
            from products.models import Product
            from nomenclatures.models import UnitOfMeasure
            from .services.purchase_service import PurchaseDocumentService

            # ✅ OPTIMIZED: Load all data with proper error handling
            suppliers = Supplier.objects.filter(is_active=True).order_by('name')
            locations = InventoryLocation.objects.filter(is_active=True).order_by('name')
            
         
            products = Product.objects.active().prefetch_related(
                'packagings__unit'
            ).order_by('name')
            
            units = UnitOfMeasure.objects.filter(is_active=True).order_by('name')


            from purchases.models import DeliveryReceipt
            from nomenclatures.services.creator import DocumentCreator
            
            # Create empty document instance (not saved to DB)
            empty_delivery = DeliveryReceipt()
            
            # Set document_type from model class
            document_type = DocumentCreator._get_document_type_for_model(DeliveryReceipt)
            empty_delivery.document_type = document_type
            
            # Set initial status for new documents
            if document_type:
                from nomenclatures.services._status_resolver import StatusResolver
                initial_status = StatusResolver.get_initial_status(document_type)
                empty_delivery.status = initial_status or 'draft'
            else:
                empty_delivery.status = 'draft'
            
            # Get CREATION actions through service facade (different from DetailView)
            doc_service = PurchaseDocumentService(empty_delivery, self.request.user)
            raw_actions = doc_service.facade.get_creation_actions()
            
            logger.info(f"🔥 get_creation_actions() returned: {raw_actions}")
            logger.info(f"🔥 empty_delivery.document_type: {empty_delivery.document_type}")
            logger.info(f"🔥 empty_delivery status: {empty_delivery.status}")
            
            # ✅ NEW: Convert to template-compatible format for CREATION actions
            available_actions = []
            for action in raw_actions:
                template_action = {
                    'action_key': action.get('action', 'save_draft'),
                    'label': action.get('label', 'Запази'),
                    'button_class': action.get('button_style', 'btn-secondary'),
                    'icon': action.get('icon', 'ki-filled ki-document'),
                    'can_perform': action.get('can_perform', True),
                    'target_status': action.get('target_status'),  # Creation-specific
                    'semantic_type': action.get('semantic_type', 'creation')
                }
                available_actions.append(template_action)
                
            logger.info(f"🔥 Final available_actions count: {len(available_actions)}")

        except ImportError as e:
            logger.error(f"Failed to import required models: {e}")
            suppliers, locations, products, units, available_actions = [], [], [], [], []
            
        except Exception as e:
            logger.error(f"Failed to load form context data: {e}")
            suppliers, locations, products, units, available_actions = [], [], [], [], []

        context.update({
            'page_title': 'New Delivery Receipt',
            'form_mode': 'create',
            'is_create_mode': True,  # Flag for creation vs transition actions
            'suppliers': suppliers,
            'locations': locations,
            'products': products,
            'units': units,
            'today': timezone.now().date(),
            'available_actions': available_actions,
        })
        return context

    def form_valid(self, form):
        """
        OPTIMIZED VIEW: Само data extraction и service delegation
        
        ✅ OPTIMIZED:
        - БЕЗ business логика в VIEW
        - БЕЗ manual document_type assignment (DocumentCreator го прави)  
        - БЕЗ дублираща се валидация
        - БЕЗ unused variables
        - САМО делегация към PurchaseService
        """
        try:
            from .services.purchase_service import DeliveryReceiptService
            
            # ✅ OPTIMIZED: Extract form data including target_status from creation buttons
            target_status = self.request.POST.get('target_status')
            logger.info(f"Extracted target_status from POST: '{target_status}'")
            
            form_data = {
                'partner_id': self.request.POST.get('partner_id'),
                'location_id': self.request.POST.get('location_id'),
                'target_status': target_status,  # From creation action buttons
                **form.cleaned_data
            }

            # ✅ OPTIMIZED: Early validation return
            if not form_data['partner_id']:
                messages.error(self.request, 'Supplier is required')
                return self.form_invalid(form)

            # ✅ ЧИСТА ДЕЛЕГАЦИЯ - Използвай съществуващия create метод
            from partners.models import Supplier
            from inventory.models import InventoryLocation
            
            # Convert form data to service parameters
            try:
                partner = Supplier.objects.get(id=form_data['partner_id'])
                location = InventoryLocation.objects.get(id=form_data['location_id']) if form_data.get('location_id') else None
            except (Supplier.DoesNotExist, InventoryLocation.DoesNotExist) as e:
                messages.error(self.request, f'Invalid partner or location: {e}')
                return self.form_invalid(form)
            
            # Extract lines from POST data
            lines = self._extract_lines_from_post(self.request.POST)
            
            target_status_param = form_data.get('target_status')
            logger.info(f"🔥 Calling DeliveryReceiptService.create with target_status='{target_status_param}'")
            logger.info(f"🔥 Complete form_data: {form_data}")
            
            result = DeliveryReceiptService.create(
                user=self.request.user,
                partner=partner,
                location=location,
                lines=lines,
                target_status=target_status_param,
                document_date=form_data.get('document_date'),
                delivery_date=form_data.get('delivery_date'),
                supplier_delivery_reference=form_data.get('supplier_delivery_reference', ''),
                comments=form_data.get('notes', '')
            )

            # ✅ OPTIMIZED: Handle result with EXACT error messages
            if result.ok:
                self.object = result.data['document']
                final_status = result.data.get('final_status', self.object.status)
                
                messages.success(
                    self.request,
                    f'Delivery Receipt {self.object.document_number} created with status: {final_status}'
                )
                return redirect(self.get_success_url())
            else:
                # ✅ SHOW EXACT ERROR from service - no generic messages
                messages.error(self.request, result.msg)
                logger.error(f"DeliveryReceiptService.create() failed: {result.msg}")
                return self.form_invalid(form)

        except ImportError as e:
            import traceback
            full_traceback = traceback.format_exc()
            logger.error(f"Failed to import DeliveryReceiptService: {e}\nFull traceback: {full_traceback}")
            messages.error(self.request, f'Import failed: {str(e)}')
            return self.form_invalid(form)
            
        except Exception as e:
            logger.error(f"Form processing failed: {e}")
            messages.error(self.request, f'Unexpected error: {str(e)}')
            return self.form_invalid(form)

    def _extract_lines_from_post(self, post_data):
        """
        Extract product lines from POST data
        
        Expected form fields:
        - line_product_0, line_product_1, etc.
        - line_quantity_0, line_quantity_1, etc.  
        - line_unit_price_0, line_unit_price_1, etc.
        - line_unit_0, line_unit_1, etc.
        """
        lines = []
        from products.models import Product
        from decimal import Decimal
        
        # Find all line indices by looking for line_product_* fields
        line_indices = []
        for key in post_data.keys():
            if key.startswith('line_product_') and post_data[key]:
                try:
                    index = int(key.split('_')[-1])
                    line_indices.append(index)
                except ValueError:
                    continue
        
        # Process each line
        for index in sorted(line_indices):
            try:
                product_id = post_data.get(f'line_product_{index}')
                quantity_str = post_data.get(f'line_quantity_{index}', '0')
                price_str = post_data.get(f'line_unit_price_{index}', '0')
                unit_id = post_data.get(f'line_unit_{index}')
                
                # Skip empty lines
                if not product_id or not quantity_str:
                    continue
                
                # Get product object
                product = Product.objects.get(id=product_id)
                quantity = Decimal(quantity_str)
                unit_price = Decimal(price_str) if price_str else Decimal('0')
                
                line_data = {
                    'product': product,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'notes': post_data.get(f'line_notes_{index}', ''),
                }
                
                # Add unit if selected
                if unit_id:
                    from nomenclatures.models import UnitOfMeasure
                    try:
                        unit = UnitOfMeasure.objects.get(id=unit_id)
                        line_data['unit'] = unit
                    except UnitOfMeasure.DoesNotExist:
                        logger.warning(f"Unit {unit_id} not found for line {index}")
                
                lines.append(line_data)
                
            except (Product.DoesNotExist, ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid line {index}: {e}")
                continue
        
        logger.info(f"Extracted {len(lines)} valid lines from POST data")
        return lines


class DeliveryReceiptUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView, ServiceResolverMixin):
    """Update existing Delivery Receipt"""
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/edit.html'
    permission_required = 'purchases.change_deliveryreceipt'
    fields = ['document_number', 'document_date', 'delivery_date', 'supplier_delivery_reference', 'notes']
    
    def get_success_url(self):
        return reverse('purchases:delivery_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        """
        ✅ ENHANCED: Auto-reactivate cancelled documents when edited and saved
        
        Only reactivates if there are actual changes to prevent unnecessary status transitions.
        Uses official return_to_draft method for proper audit trail and StatusManager integration.
        """
        old_status = self.object.status
        
        # ✅ Check if there are actual changes before reactivation
        has_changes = form.has_changed()
        
        # Call parent to save the form changes
        response = super().form_valid(form)
        
        # ✅ Auto-reactivation logic - only if there are changes
        if old_status == 'cancelled' and has_changes:
            try:
                from .services.purchase_service import PurchaseDocumentService
                
                # Get list of changed fields for audit trail
                changed_fields = form.changed_data if hasattr(form, 'changed_data') else []
                change_summary = f"Fields changed: {', '.join(changed_fields)}" if changed_fields else "Form data modified"
                
                # Use official return_to_draft method
                doc_service = PurchaseDocumentService(self.object, self.request.user)
                reactivation_result = doc_service.return_to_draft(
                    f'Document automatically reactivated after edit by {self.request.user.get_full_name() or self.request.user.username}. {change_summary}'
                )
                
                if reactivation_result.ok:
                    messages.success(
                        self.request, 
                        f'✅ Document updated and automatically reactivated from cancelled status. Status changed to draft - you can now continue editing.'
                    )
                    logger.info(f"Auto-reactivated document {self.object.document_number} from cancelled to draft after edit by {self.request.user}. Changed fields: {changed_fields}")
                else:
                    messages.warning(
                        self.request,
                        f'⚠️ Document was updated but auto-reactivation failed: {reactivation_result.msg}. Status remains cancelled.'
                    )
                    logger.warning(f"Auto-reactivation failed for {self.object.document_number}: {reactivation_result.msg}")
                    
            except Exception as e:
                messages.error(
                    self.request,
                    f'❌ Document was updated but auto-reactivation encountered an error: {str(e)}. Please manually reactivate if needed.'
                )
                logger.error(f"Auto-reactivation error for {self.object.document_number}: {e}")
                
        elif old_status == 'cancelled' and not has_changes:
            # No changes - inform user but don't reactivate
            messages.info(
                self.request,
                'ℹ️ No changes detected. Document remains in cancelled status. Make changes to automatically reactivate it.'
            )
            logger.debug(f"No changes detected for cancelled document {self.object.document_number} - skipping auto-reactivation")
                
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # ✅ Add status context for template notification
        status_notice = ''
        if self.object.status == 'cancelled':
            status_notice = 'ℹ️ Note: Editing a cancelled document will automatically reactivate it to draft status when saved.'
            
        context.update({
            'page_title': f'Edit Delivery Receipt {self.object.document_number}',
            'form_mode': 'edit',
            'status_notice': status_notice,  # ✅ For template notification
            'current_status': self.object.status,
        })
        return context

class DeliveryReceiptActionView(LoginRequiredMixin, PermissionRequiredMixin, View, ServiceResolverMixin):
    """
    Handle all semantic actions for Delivery Receipts

    Supported Actions:
    - approve: Complete/approve the delivery
    - reject: Reject the delivery with reason
    - cancel: Cancel the delivery with reason
    - submit: Submit for approval workflow
    - return_to_draft: Return to editable draft state

    Features:
    - Dynamic comment requirements per action
    - Configurable document type resolution
    - Clean semantic action delegation
    - Enhanced user feedback and audit logging
    """
    permission_required = 'purchases.change_deliveryreceipt'

    def get_actions_requiring_comments(self) -> List[str]:
        """
        Get actions that require comments (configurable)
        
        Returns:
            List of action types that must have comments provided
        """
        return ['reject', 'cancel', 'return_to_draft']

    def _get_action_message(self, action_type: str, comments: str) -> str:
        """
        Generate appropriate message for action
        
        Args:
            action_type: The semantic action being performed
            comments: User-provided comments
            
        Returns:
            Final message to use for the action
        """
        if comments.strip():
            return comments
            
        default_messages = {
            'approve': 'Approved via web interface',
            'reject': 'Rejected via web interface', 
            'cancel': 'Cancelled via web interface',
            'submit': 'Submitted via web interface',
            'return_to_draft': 'Returned to draft via web interface'
        }
        
        return default_messages.get(action_type, f'{action_type.title()} via web interface')

    def _ensure_document_type(self, delivery) -> bool:
        """
        Ensure delivery has document_type set using smart resolution
        
        Args:
            delivery: DeliveryReceipt instance
            
        Returns:
            bool: True if document_type is set (or successfully set), False otherwise
        """
        if delivery.document_type:
            return True
            
        try:
            from nomenclatures.models import DocumentType
            
            # Try app-based lookup first (from CLAUDE.md architecture)
            doc_type = DocumentType.objects.filter(
                app_name='purchases',
                is_active=True
            ).filter(
                models.Q(type_key__icontains='delivery') |
                models.Q(name__icontains='delivery')
            ).first()
            
            # Fallback to legacy lookup if app-based fails
            if not doc_type:
                logger.warning("App-based document type lookup failed, falling back to legacy method")
                doc_type = DocumentType.objects.filter(
                    models.Q(code='003') | models.Q(name__icontains='delivery')
                ).first()
            
            if doc_type:
                delivery.document_type = doc_type
                delivery.save(update_fields=['document_type'])
                logger.info(f"Auto-assigned document_type '{doc_type.name}' to delivery {delivery.document_number}")
                return True
            else:
                logger.error("Could not find suitable document type for delivery receipts")
                return False
                
        except Exception as e:
            logger.error(f"Failed to resolve document type: {e}")
            return False

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

        # Dynamic comment requirements based on action type
        if action_type in self.get_actions_requiring_comments() and not comments:
            messages.error(request, f'Comments are required for {action_type}.')
            return redirect('purchases:delivery_detail', pk=pk)

        try:
            from .services.purchase_service import PurchaseDocumentService

            # Ensure document_type is set for semantic actions using smart resolution
            if not self._ensure_document_type(delivery):
                messages.error(request, 'Failed to determine document type for this delivery receipt.')
                return redirect('purchases:delivery_detail', pk=pk)

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
                'approve': lambda: doc_service.approve(self._get_action_message('approve', comments)),
                'reject': lambda: doc_service.reject(comments),  # Comments required for reject
                'submit': lambda: doc_service.submit_for_approval(self._get_action_message('submit', comments)),
                'submit_for_approval': lambda: doc_service.submit_for_approval(
                    self._get_action_message('submit', comments)),
                'return_to_draft': lambda: doc_service.return_to_draft(
                    self._get_action_message('return_to_draft', comments)),
                'return_draft': lambda: doc_service.return_to_draft(
                    self._get_action_message('return_draft', comments)),  # ✅ ADDED: alias for compatibility
                'cancel': lambda: doc_service.cancel(comments),  # Comments required for cancel
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

        # ✅ FIXED: Use PurchaseDocumentService facade for configuration-driven actions
        from .services.purchase_service import PurchaseDocumentService
        doc_service = PurchaseDocumentService(delivery, self.request.user)
        available_actions = doc_service.facade.get_available_actions()  # ✅ NEW: Direct configuration-driven actions

        # Calculate VAT breakdown grouped by rates
        vat_breakdown = self._calculate_vat_breakdown(delivery)
        
        # Calculate EUR conversion (total ÷ 1.95583)
        eur_total = None
        if delivery.total:
            from decimal import Decimal
            eur_rate = Decimal('1.95583')
            eur_total = round(delivery.total / eur_rate, 2)

        context.update({
            'page_title': f'Delivery Receipt {delivery.document_number}',
            'can_edit': doc_service.can_edit(),  # ✅ Uses DocumentValidator via facade
            'can_approve': self.request.user.has_perm('purchases.change_deliveryreceipt'),

            # Enhanced data - FIXED: Use direct lines instead of processed version
            'delivery_lines': delivery.lines.all(),
            'inventory_movements': self.get_inventory_movements(delivery),
            'related_documents': self.get_related_documents(delivery),

            # Financial calculations
            'vat_breakdown': vat_breakdown,
            'eur_total': eur_total,

            # ✅ NEW: Configuration-driven actions (NO MORE semantic_actions mapping!)
            'available_actions': available_actions,
            
            # ✅ PROFESSIONAL: Status classes using StatusResolver
            'status_class': self._get_status_css_class(delivery),
            'semantic_status_info': self._get_semantic_status_info(delivery),
            
            # ✅ DEBUG INFO for badge troubleshooting
            'debug_status_info': {
                'current_status': delivery.status,
                'document_type': delivery.document_type,
                'calculated_status_class': self._get_status_css_class(delivery),
                'has_document_type': bool(delivery.document_type),
            },
        })
        return context

    def _get_status_css_class(self, delivery) -> str:
        """
        ПРОФЕСИОНАЛНО: Директно от базата чрез badge_class поле
        
        Ако няма конфигуриран клас - без клас и толкова
        """
        try:
            if delivery.document_type:
                from nomenclatures.models import DocumentTypeStatus
                
                # Намери конфигурацията за този статус
                config = DocumentTypeStatus.objects.filter(
                    document_type=delivery.document_type,
                    status__code=delivery.status,
                    is_active=True
                ).select_related('status').first()
                
                if config and config.status.badge_class:
                    # Конвертирай Bootstrap → Metronic класове
                    bootstrap_class = config.status.badge_class
                    metronic_class = self._convert_bootstrap_to_metronic(bootstrap_class)
                    return metronic_class
            
            # Няма конфигурация - просто neutral клас
            return 'kt-badge-light'
                
        except Exception:
            # При грешка - просто neutral клас
            return 'kt-badge-light'

    def _convert_bootstrap_to_metronic(self, bootstrap_class: str) -> str:
        """
        Конвертирай Bootstrap badge класове към Metronic kt-badge класове
        """
        mapping = {
            'badge-secondary': 'kt-badge-secondary',
            'badge-success': 'kt-badge-success', 
            'badge-warning': 'kt-badge-warning',
            'badge-danger': 'kt-badge-destructive',  # FIXED: Metronic uses destructive not danger
            'badge-info': 'kt-badge-info',
            'badge-light': 'kt-badge-light',
            'badge-dark': 'kt-badge-mono',  # FIXED: Metronic uses mono for dark
            'badge-primary': 'kt-badge-primary',
            
            # Support for both forms
            'kt-badge-secondary': 'kt-badge-secondary',
            'kt-badge-success': 'kt-badge-success',
            'kt-badge-warning': 'kt-badge-warning',
            'kt-badge-danger': 'kt-badge-destructive',  # FIXED: Metronic uses destructive
            'kt-badge-destructive': 'kt-badge-destructive',
            'kt-badge-info': 'kt-badge-info',
            'kt-badge-light': 'kt-badge-light',
            'kt-badge-dark': 'kt-badge-mono',
            'kt-badge-mono': 'kt-badge-mono',
            'kt-badge-primary': 'kt-badge-primary',
        }
        
        # Clean the class name (remove extra spaces, kt-badge-sm etc.)
        clean_class = bootstrap_class.strip().split()[0] if bootstrap_class else ''
        
        converted = mapping.get(clean_class, 'kt-badge-light')
        logger.debug(f"Converted badge class '{bootstrap_class}' -> '{converted}'")
        return converted
    
    
    def _get_semantic_status_info(self, delivery) -> dict:
        """
        ОПРОСТЕНО: Използва само database конфигурация без semantic gluposti
        """
        try:
            if not delivery.document_type:
                return {
                    'is_initial': False,
                    'is_final': False, 
                    'is_cancellation': False,
                    'can_edit': False,
                    'can_delete': False,
                    'available_transitions': []
                }
                
            from nomenclatures.services._status_resolver import (
                is_initial_status, is_final_status, is_cancellation_status,
                can_edit_in_status, can_delete_in_status
            )
            from nomenclatures.services._status_resolver import StatusResolver
            
            return {
                'is_initial': is_initial_status(delivery),
                'is_final': is_final_status(delivery),
                'is_cancellation': is_cancellation_status(delivery),
                'can_edit': can_edit_in_status(delivery),
                'can_delete': can_delete_in_status(delivery),
                'available_transitions': StatusResolver.get_next_possible_statuses(
                    delivery.document_type, delivery.status
                ) if delivery.document_type else []
            }
            
        except Exception as e:
            logger.error(f"Failed to get semantic status info: {e}")
            return {
                'is_initial': False,
                'is_final': False,
                'is_cancellation': False,
                'can_edit': False,
                'can_delete': False,
                'available_transitions': [],
                'error': str(e)
            }

    def _calculate_vat_breakdown(self, delivery):
        """
        Calculate VAT breakdown grouped by rates - სუმარისა (group) by rate
        """
        from decimal import Decimal
        vat_breakdown = {}
        
        for line in delivery.lines.all():
            if not line.vat_rate or not line.vat_amount:
                continue
                
            # Convert VAT rate to percentage for display (0.20 -> 20)
            vat_rate_percent = int(line.vat_rate * 100)
            
            if vat_rate_percent not in vat_breakdown:
                vat_breakdown[vat_rate_percent] = Decimal('0.00')
            
            # Get quantity for line total VAT calculation
            quantity = getattr(line, 'received_quantity', Decimal('0'))
            if not quantity:
                quantity = Decimal('1')  # Fallback
            
            # Sum VAT amounts by rate (multiply by quantity for line total)
            line_vat_total = line.vat_amount * quantity
            vat_breakdown[vat_rate_percent] += line_vat_total
        
        # Sort by rate for consistent display
        return dict(sorted(vat_breakdown.items()))

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

            if available_actions.get('can_approve') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['approve'] = True

            if available_actions.get('can_submit') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['submit'] = True

            if available_actions.get('can_reject') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['reject'] = True

            if available_actions.get('can_return_to_draft') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['return_to_draft'] = True

            if available_actions.get('can_cancel') and user.has_perm('purchases.change_deliveryreceipt'):
                final_actions['cancel'] = True

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