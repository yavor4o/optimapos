from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.db import transaction, models
from django.utils import timezone
from django.core.paginator import Paginator

from .models.deliveries import DeliveryReceipt, DeliveryLine
from core.interfaces import ServiceResolverMixin


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


class DeliveryReceiptDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView, ServiceResolverMixin):
    """
    Delivery Receipt Detail View с inventory tracking
    
    Features:
    - Complete delivery information
    - Line items with quality status
    - Inventory movements tracking
    - Action buttons (approve, reject, edit)
    - Related documents links
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
            'source_order'
        ).prefetch_related(
            'lines__product',
            'lines__unit',
            'lines__source_order_line'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        delivery = self.object
        
        context.update({
            'page_title': f'Delivery Receipt {delivery.document_number}',
            'can_edit': self.request.user.has_perm('purchases.change_deliveryreceipt'),
            'can_approve': self.request.user.has_perm('purchases.approve_deliveryreceipt'),
            
            # Line items with enhanced data
            'delivery_lines': self.get_enhanced_lines(delivery),
            
            # Related information
            'inventory_movements': self.get_inventory_movements(delivery),
            'related_documents': self.get_related_documents(delivery),
            
            # Action availability
            'actions_available': self.get_available_actions(delivery),
        })
        return context
    
    def get_enhanced_lines(self, delivery):
        """Get delivery lines with calculated fields"""
        lines = []
        for line in delivery.lines.all():
            # Determine quality status display
            if line.quality_approved is True:
                quality_display = 'Approved'
            elif line.quality_approved is False:
                quality_display = 'Rejected'
            else:
                quality_display = 'Pending'
            
            line_data = {
                'line': line,
                'variance_quantity': line.received_quantity - (line.ordered_quantity or 0),
                'variance_percentage': self.calculate_variance_percentage(
                    line.received_quantity, 
                    line.ordered_quantity
                ),
                'quality_status_display': quality_display,
                'total_value': line.received_quantity * (line.unit_price or 0),
            }
            lines.append(line_data)
        return lines
    
    def calculate_variance_percentage(self, received, ordered):
        """Calculate delivery variance percentage"""
        if not ordered or ordered == 0:
            return 0
        return ((received - ordered) / ordered) * 100
    
    def get_inventory_movements(self, delivery):
        """Get related inventory movements"""
        # TODO: Integrate with InventoryService
        try:
            inventory_service = self.get_service('IInventoryService')
            return inventory_service.get_movements_for_delivery(delivery)
        except Exception:
            return []
    
    def get_related_documents(self, delivery):
        """Get related documents (PO, Invoices, etc.)"""
        related = {}
        if delivery.source_order:
            related['purchase_order'] = delivery.source_order
        return related
    
    def get_available_actions(self, delivery):
        """Determine which actions are available for this delivery using StatusResolver"""
        from nomenclatures.services._status_resolver import StatusResolver, can_edit_in_status, can_delete_in_status
        
        user = self.request.user
        actions = {
            'can_edit': False,
            'can_approve': False,
            'can_reject': False,
            'can_quality_check': False,
        }
        
        try:
            # Use StatusResolver for dynamic status checking
            if can_edit_in_status(delivery) and user.has_perm('purchases.change_deliveryreceipt'):
                actions['can_edit'] = True
            
            # Check if document is in editable status for approval actions
            editable_statuses = StatusResolver.get_editable_statuses(delivery.document_type)
            if delivery.status in editable_statuses:
                if user.has_perm('purchases.approve_deliveryreceipt'):
                    actions['can_approve'] = True
                    actions['can_reject'] = True
            
            # Quality check availability - keep quality status logic as is (business specific)
            if delivery.quality_status == 'pending':
                if user.has_perm('purchases.quality_check_deliveryreceipt'):
                    actions['can_quality_check'] = True
                    
        except Exception:
            # Fallback to hardcoded logic if StatusResolver fails
            if delivery.status == 'draft':
                if user.has_perm('purchases.change_deliveryreceipt'):
                    actions['can_edit'] = True
                if user.has_perm('purchases.approve_deliveryreceipt'):
                    actions['can_approve'] = True
                    actions['can_reject'] = True
            
            if delivery.quality_status == 'pending':
                if user.has_perm('purchases.quality_check_deliveryreceipt'):
                    actions['can_quality_check'] = True
        
        return actions


class DeliveryReceiptCreateView(LoginRequiredMixin, CreateView, ServiceResolverMixin):
    """
    Create new Delivery Receipt с inventory integration
    
    Features:
    - Link to Purchase Order (optional)
    - Product selection with autocomplete
    - Real-time calculations
    - Quality control setup
    - Inventory impact preview
    """
    model = DeliveryReceipt
    template_name = 'frontend/purchases/deliveries/create.html'
    # permission_required = 'purchases.add_deliveryreceipt'
    success_url = reverse_lazy('purchases:delivery_list')
    fields = ['document_date', 'delivery_date', 'supplier_delivery_reference', 'notes']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Load suppliers via service or fallback
        try:
            partner_service = self.get_service('IPartnerService')
            suppliers = partner_service.get_suppliers()
        except Exception:
            from partners.models import Supplier
            suppliers = Supplier.objects.filter(is_active=True).order_by('name')
        
        # Load locations via inventory service or fallback
        try:
            inventory_service = self.get_service('IInventoryService')
            locations = inventory_service.get_all_locations()
        except Exception:
            from inventory.models import InventoryLocation
            locations = InventoryLocation.objects.filter(is_active=True).order_by('name')
        
        # Load products via service or fallback
        try:
            product_service = self.get_service('IProductService')
            products = product_service.get_all_products()
        except Exception:
            from products.models import Product
            products = Product.objects.all().order_by('name')
        
        # Load units of measure
        try:
            from nomenclatures.models import UnitOfMeasure
            units = UnitOfMeasure.objects.filter(is_active=True).order_by('name')
        except Exception:
            units = []
        
        context.update({
            'page_title': 'New Delivery Receipt',
            'form_mode': 'create',
            'suppliers': suppliers,
            'locations': locations,
            'products': products,
            'units': units,
            'today': timezone.now().date(),
        })
        return context
    
    def form_valid(self, form):
        """Handle successful form submission using PurchaseDocumentService"""
        from .services.purchase_service import DeliveryReceiptService
        from core.utils.result import Result
        
        try:
            # Gather form data
            partner_id = self.request.POST.get('partner_id')
            location_id = self.request.POST.get('location_id')
            status = self.request.POST.get('status', 'draft')
            
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
            
            # Prepare line items data
            lines = self.prepare_lines_data()
            if not lines:
                messages.warning(self.request, 'At least one line item is required')
                # Create empty delivery to show form with errors
                lines = []  # Will create document without lines for now
            
            # Create delivery using service
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
            
            # Get created document and set document_type if missing
            self.object = result.data['document']
            
            # Ensure document_type is set for StatusResolver
            if not self.object.document_type:
                from nomenclatures.models import DocumentType
                delivery_doc_type = DocumentType.objects.filter(
                    models.Q(code='003') | models.Q(name__icontains='delivery')
                ).first()
                if delivery_doc_type:
                    self.object.document_type = delivery_doc_type
                    self.object.save(update_fields=['document_type'])
            
            # Handle status transitions using service and StatusResolver
            from nomenclatures.services._status_resolver import StatusResolver
            try:
                initial_status = StatusResolver.get_initial_status(self.object.document_type)
                if status != initial_status:
                    from .services.purchase_service import PurchaseDocumentService
                    doc_service = PurchaseDocumentService(self.object, self.request.user)
                    
                    # Get semantic statuses for proper transitions
                    approval_statuses = StatusResolver.get_statuses_by_semantic_type(self.object.document_type, 'approval')
                    processing_statuses = StatusResolver.get_statuses_by_semantic_type(self.object.document_type, 'processing')
                    
                    if status in approval_statuses:
                        transition_result = doc_service.submit_for_approval()
                    elif status in processing_statuses:
                        transition_result = doc_service.approve('Direct approval from creation')
                    else:
                        transition_result = Result.success()  # Stay as initial status
                    
                    if not transition_result.ok:
                        messages.warning(self.request, f'Document created but status change failed: {transition_result.msg}')
            except Exception:
                # Fallback to hardcoded logic if StatusResolver fails
                if status != 'draft':
                    from .services.purchase_service import PurchaseDocumentService
                    doc_service = PurchaseDocumentService(self.object, self.request.user)
                    
                    if status == 'pending':
                        transition_result = doc_service.submit_for_approval()
                    elif status == 'approved':
                        transition_result = doc_service.approve('Direct approval from creation')
                    else:
                        transition_result = Result.success()  # Stay as draft
                    
                    if not transition_result.ok:
                        messages.warning(self.request, f'Document created but status change failed: {transition_result.msg}')
            
            messages.success(
                self.request, 
                f'Delivery Receipt {self.object.document_number} created successfully.'
            )
            
            return redirect(self.get_success_url())
            
        except Exception as e:
            messages.error(self.request, f'Unexpected error: {str(e)}')
            return self.form_invalid(form)
    
    def prepare_lines_data(self):
        """Prepare line items data for service"""
        lines = []
        item_counter = 1
        
        while f'items-{item_counter}-product_id' in self.request.POST:
            product_id = self.request.POST.get(f'items-{item_counter}-product_id')
            received_quantity = self.request.POST.get(f'items-{item_counter}-received_quantity')
            unit_price = self.request.POST.get(f'items-{item_counter}-unit_price')
            unit_id = self.request.POST.get(f'items-{item_counter}-unit_id')
            quality_status = self.request.POST.get(f'items-{item_counter}-quality_status')
            quality_notes = self.request.POST.get(f'items-{item_counter}-quality_notes')
            
            # Skip empty items
            if not product_id or not received_quantity:
                item_counter += 1
                continue
                
            try:
                from products.models import Product
                from nomenclatures.models import UnitOfMeasure
                from decimal import Decimal
                
                product = Product.objects.get(pk=product_id)
                
                # Get unit
                if unit_id:
                    unit = UnitOfMeasure.objects.get(pk=unit_id)
                else:
                    # Use product's base unit or get a default unit
                    unit = getattr(product, 'base_unit', None)
                    if not unit:
                        unit = UnitOfMeasure.objects.filter(is_active=True).first()
                
                line_data = {
                    'product': product,
                    'quantity': Decimal(str(received_quantity)),  # Service expects 'quantity'
                    'unit': unit,
                    'unit_price': Decimal(str(unit_price or 0)),
                    'entered_price': Decimal(str(unit_price or 0)),  # For VAT calculations
                    # Add delivery-specific fields as extras
                    'quality_approved': quality_status == 'approved' if quality_status != 'pending' else None,
                    'quality_notes': quality_notes or '',
                }
                lines.append(line_data)
                
            except (Product.DoesNotExist, ValueError, UnitOfMeasure.DoesNotExist) as e:
                messages.warning(self.request, f'Skipped item {item_counter}: {e}')
            
            item_counter += 1
        
        return lines
    
    def form_invalid(self, form):
        """Handle form validation errors"""
        return super().form_invalid(form)
    


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


class DeliveryReceiptApproveView(LoginRequiredMixin, PermissionRequiredMixin, View, ServiceResolverMixin):
    """
    Approve/Reject Delivery Receipt using PurchaseDocumentService
    """
    permission_required = 'purchases.approve_deliveryreceipt'
    
    def post(self, request, pk):
        delivery = get_object_or_404(DeliveryReceipt, pk=pk)
        action = request.POST.get('action')  # Should be 'transition' 
        target_status = request.POST.get('status')  # The actual target status
        
        if action != 'transition' or not target_status:
            messages.error(request, 'Invalid transition request.')
            return redirect('purchases:delivery_detail', pk=pk)
        
        try:
            from .services.purchase_service import PurchaseDocumentService
            from nomenclatures.services._status_resolver import StatusResolver
            
            # Ensure document_type is set for StatusResolver
            if not delivery.document_type:
                from nomenclatures.models import DocumentType
                delivery_doc_type = DocumentType.objects.filter(
                    models.Q(code='003') | models.Q(name__icontains='delivery')
                ).first()
                if delivery_doc_type:
                    delivery.document_type = delivery_doc_type
                    delivery.save(update_fields=['document_type'])
            
            # Use PurchaseDocumentService for approve/reject actions
            doc_service = PurchaseDocumentService(delivery, request.user)
            
            # Handle semantic actions instead of hardcoded target statuses
            action_type = request.POST.get('action_type', target_status)  # 'approve', 'reject', or specific status
            comment = request.POST.get('comment', f'Action: {action_type} via web interface')
            
            if action_type == 'approve':
                # Let the service determine the next status for approval
                result = doc_service.approve(comment)
            elif action_type == 'reject':
                # Let the service determine the cancellation status  
                result = doc_service.reject(comment)
            else:
                # Direct status transition (for future extensibility)
                result = doc_service.transition_to(target_status, comment)
            
            if result.ok:
                new_status = result.data.get('new_status', target_status)
                messages.success(request, f'Delivery Receipt {delivery.document_number} status changed to {new_status}.')
            else:
                messages.error(request, f'Status transition failed: {result.msg}')
                
        except Exception as e:
            messages.error(request, f'Status transition failed: {e}')
        
        return redirect('purchases:delivery_detail', pk=pk)


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