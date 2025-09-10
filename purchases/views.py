import json
import logging
from typing import  List

from django.shortcuts import  get_object_or_404, redirect
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import  reverse
from django.http import JsonResponse
from django.db import  models
from django.utils import timezone


from core.utils.result import Result
from inventory.models import InventoryLocation
from nomenclatures.models import UnitOfMeasure
from nomenclatures.services import DocumentCreator
from nomenclatures.services._status_resolver import StatusResolver
from partners.models import Supplier
from products.models import Product
from .forms import DeliveryLineFormSet, DeliveryReceiptForm
from .models.deliveries import DeliveryReceipt, DeliveryLine
from core.interfaces import ServiceResolverMixin
from .services import PurchaseDocumentService, DeliveryReceiptService

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
    🆕 Enhanced delivery receipt creation with proper form layer
    
    ARCHITECTURE COMPLIANCE:
    ✅ Uses DeliveryReceiptForm for main fields (partner_id, location_id, etc.)
    ✅ Uses DeliveryLineFormSet for line items
    ✅ Clean delegation to service layer
    ✅ NO ad-hoc validation in view layer
    """
    model = DeliveryReceipt
    form_class = DeliveryReceiptForm  # 🆕 Use proper form class
    template_name = 'frontend/purchases/deliveries/create_form.html'
    
    def get_form_kwargs(self):
        """Remove instance parameter since we're using regular Form, not ModelForm"""
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)  # Remove instance parameter
        return kwargs

    def get_success_url(self):
        return reverse('purchases:delivery_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # 1. Зареждаме данните, нужни за JSON сериализация
            suppliers = self._get_optimized_supplier_list()
            locations = InventoryLocation.objects.filter(is_active=True).order_by('name')
            products = Product.objects.active().prefetch_related('packagings__unit').order_by('name')
            units = UnitOfMeasure.objects.filter(is_active=True).order_by('name')

            # 2. Логика за достъпните екшъни (остава същата)
            empty_delivery = DeliveryReceipt()
            document_type = DocumentCreator._get_document_type_for_model(DeliveryReceipt)
            empty_delivery.document_type = document_type
            if document_type:
                initial_status = StatusResolver.get_initial_status(document_type)
                empty_delivery.status = initial_status or 'draft'
            else:
                empty_delivery.status = 'draft'

            doc_service = PurchaseDocumentService(empty_delivery, self.request.user)
            raw_actions = doc_service.facade.get_creation_actions()
            available_actions = [
                {
                    'action_key': action.get('action', 'save_draft'),
                    'label': action.get('label', 'Запази'),
                    'button_class': action.get('button_style', 'btn-secondary'),
                    'icon': action.get('icon', 'ki-filled ki-document'),
                    'can_perform': action.get('can_perform', True),
                    'target_status': action.get('target_status'),
                    'semantic_type': action.get('semantic_type', 'creation')
                } for action in raw_actions
            ]

            # 3. Сериализираме данните в JSON за фронтенда
            context.update({
                'available_actions': available_actions,
                'available_actions_json': json.dumps(available_actions),
                'products_json': self.serialize_products(products),
                'units_json': json.dumps([{'pk': u.pk, 'code': u.code} for u in units]),
                'suppliers_json': json.dumps([{'pk': s.pk, 'name': s.name} for s in suppliers]),
                'locations_json': json.dumps([{'pk': l.pk, 'name': l.name} for l in locations]),
                'today': timezone.now().date().isoformat(),
            })

            # ✅ FIXED: Създаваме formset само веднъж
            context['line_formset'] = self.get_line_formset()

        except Exception as e:
            logger.error(f"Грешка при подготовка на контекста за DeliveryReceipt: {e}", exc_info=True)
            # В случай на грешка, задаваме празни стойности, за да не се счупи шаблона
            context['available_actions_json'] = '[]'
            context['products_json'] = '[]'
            context['units_json'] = '[]'
            context['suppliers_json'] = '[]'
            context['locations_json'] = '[]'
            context['line_formset'] = DeliveryLineFormSet(prefix='lines')

        return context

    def get_line_formset(self):
        """✅ FIXED: Централизирано създаване на formset"""
        if self.request.POST:
            return DeliveryLineFormSet(self.request.POST, prefix='lines')
        else:
            return DeliveryLineFormSet(prefix='lines')

    def form_valid(self, form):
        # ## ENHANCED: Подобрена formset валидация с structured error handling
        line_formset = DeliveryLineFormSet(self.request.POST, prefix='lines')

        if not line_formset.is_valid():
            # Enhanced formset error processing
            formatted_errors = self._process_formset_errors(line_formset)
            error_msg = "Моля, поправете грешките в редовете."
            
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {
                        'form_errors': form.errors.as_json() if form.errors else {},
                        'formset_errors': formatted_errors['line_errors'],
                        'formset_non_field_errors': formatted_errors['non_field_errors'],
                        'error_summary': self._generate_error_summary(form, line_formset)
                    },
                    'error_count': formatted_errors['total_count']
                }, status=400)

            # Add detailed error messages for non-AJAX requests
            for i, line_errors in enumerate(formatted_errors['line_errors']):
                if line_errors:
                    messages.error(self.request, f"Ред {i+1}: {', '.join(line_errors.values())}")
            
            messages.error(self.request, error_msg)
            return self.form_invalid(form)

        # Данните от редовете са вече валидирани и почистени!
        lines_data = line_formset.cleaned_data

        try:
            # 🆕 CLEAN DELEGATION - use form.cleaned_data (NO ad-hoc validation!)
            target_status = self.request.POST.get('action_type')
            if target_status == 'save_draft':
                target_status = None

            # ✅ Use validated form data - NO .objects.get() calls!
            partner = form.cleaned_data['partner_id']  # Already validated by form
            location = form.cleaned_data['location_id']  # Already validated by form

            result = DeliveryReceiptService.create(
                user=self.request.user,
                partner=partner,
                location=location,
                lines=lines_data,  # <-- Подаваме чистите, валидирани данни
                target_status=target_status,
                document_date=form.cleaned_data.get('document_date'),
                delivery_date=form.cleaned_data.get('delivery_date'),
                supplier_delivery_reference=form.cleaned_data.get('supplier_delivery_reference', ''),
                comments=form.cleaned_data.get('notes', '')
            )

            # Логиката за обработка на резултата си остава същата, защото е отлична
            if result.ok:
                self.object = result.data['document']
                final_status = result.data.get('final_status', self.object.status)
                message = f'Документ {self.object.document_number} е създаден със статус: {final_status}'

                if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True, 'message': message, 'redirect_url': self.get_success_url()
                    })
                messages.success(self.request, message)
                return redirect(self.get_success_url())
            else:
                # Връщаме грешката от service-а в същия формат като form errors
                if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': result.msg,
                        'errors': {
                            'errors': {
                                'error_count': 1,
                                'error_list': [f"Бизнес логика: {result.msg}"]
                            }
                        }
                    }, status=400)
                messages.error(self.request, f"Създаването на документ се провали: {result.msg}")
                return self.form_invalid(form)

        except Exception as e:
            logger.error(f"Неочаквана грешка при form_valid: {e}", exc_info=True)
            error_msg = f'Възникна неочаквана грешка: {str(e)}'
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            messages.error(self.request, error_msg)
            return self.form_invalid(form)

    def form_invalid(self, form):
        # Логиката тук е добра, само я правим по-чиста за AJAX
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # ✅ FIXED: Използваме централизираната get_line_formset метод
            line_formset = self.get_line_formset()
            line_formset.is_valid()  # За да се попълни .errors

            # ✅ FIXED: Match JavaScript expected structure with double nesting
            form_errors = dict(form.errors.items())
            formset_errors = [dict(line_form.errors.items()) for line_form in line_formset.forms]
            formset_non_field_errors = []
            if line_formset.non_form_errors():
                formset_non_field_errors = list(line_formset.non_form_errors())
                
            # ✅ Calculate error statistics
            form_error_count = sum(len(errors) for errors in form_errors.values())
            formset_error_count = sum(len(line_errors) for line_errors in formset_errors for line_errors in line_errors.values())
            total_errors = form_error_count + formset_error_count
            
            # ✅ Build error summary list
            error_list = []
            
            # Add form errors
            for field_name, messages in form_errors.items():
                field_label = form[field_name].label or field_name.replace('_', ' ').title()
                for message in messages:
                    error_list.append(f"{field_label}: {message}")
            
            # Add formset errors  
            for line_idx, line_errors in enumerate(formset_errors):
                if line_errors:  # Only if line has errors
                    for field_name, messages in line_errors.items():
                        field_label = field_name.replace('_', ' ').title()
                        for message in messages:
                            error_list.append(f"Ред {line_idx + 1} - {field_label}: {message}")
            
            # Add formset non-field errors
            for error in formset_non_field_errors:
                error_list.append(f"Формсет: {error}")

            return JsonResponse({
                'success': False,
                'message': 'Моля, попълнете правилно всички задължителни полета.',
                'errors': {
                    'errors': {  # ✅ Match JavaScript expectation
                        'form_errors': form_errors,
                        'formset_errors': formset_errors,
                        'formset_non_field_errors': formset_non_field_errors,
                        'error_count': total_errors,
                        'error_list': error_list
                    }
                }
            }, status=400)

        return super().form_invalid(form)

    def _process_formset_errors(self, formset) -> dict:
        """
        🆕 Enhanced formset error processing with structured output
        
        Args:
            formset: Django formset instance
            
        Returns:
            dict: Structured error data with counts and formatted messages
        """
        line_errors = []
        non_field_errors = []
        total_count = 0
        
        # Process individual form errors
        for i, form in enumerate(formset.forms):
            form_errors = {}
            
            # Field-specific errors
            for field_name, error_list in form.errors.items():
                if field_name != '__all__':
                    form_errors[field_name] = [str(error) for error in error_list]
                    total_count += len(error_list)
                else:
                    # Non-field errors for this form
                    non_field_errors.extend([f"Ред {i+1}: {error}" for error in error_list])
                    total_count += len(error_list)
            
            line_errors.append(form_errors)
        
        # Process formset-level non-field errors
        if formset.non_form_errors():
            non_field_errors.extend([str(error) for error in formset.non_form_errors()])
            total_count += len(formset.non_form_errors())
        
        return {
            'line_errors': line_errors,
            'non_field_errors': non_field_errors,
            'total_count': total_count
        }
    
    def _generate_error_summary(self, form, formset) -> str:
        """
        🆕 Generate user-friendly error summary
        
        Args:
            form: Main form instance
            formset: Formset instance
            
        Returns:
            str: Human-readable error summary
        """
        error_parts = []
        
        # Count form errors
        form_error_count = sum(len(errors) for errors in form.errors.values())
        if form_error_count > 0:
            error_parts.append(f"{form_error_count} грешки в основната форма")
        
        # Count formset errors
        formset_error_count = 0
        for form_instance in formset.forms:
            formset_error_count += sum(len(errors) for errors in form_instance.errors.values())
        
        if formset_error_count > 0:
            error_parts.append(f"{formset_error_count} грешки в редовете")
        
        if not error_parts:
            return "Неизвестни грешки във формата"
            
        return "Намерени " + " и ".join(error_parts) + "."

    def _get_optimized_supplier_list(self):
        """
        🆕 OPTIMIZED: Get smart supplier list (recent + popular, ~100 items)
        
        Strategy:
        1. Get suppliers used in recent deliveries (last 90 days) 
        2. Get most frequently used suppliers (all time)
        3. Combine and dedupe, prioritize recent usage
        4. Limit to ~100 items for performance
        
        Returns:
            QuerySet: Optimized supplier list
        """
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Q
        
        try:
            # Define time window for "recent" activity
            recent_cutoff = timezone.now() - timedelta(days=90)
            
            # 1. Get suppliers from recent deliveries (last 90 days)
            recent_supplier_ids = DeliveryReceipt.objects.filter(
                created_at__gte=recent_cutoff,
                partner_content_type__model='supplier'
            ).values_list('partner_object_id', flat=True).distinct()[:50]
            
            # 2. Get most popular suppliers (by delivery count, all time)
            popular_supplier_ids = DeliveryReceipt.objects.filter(
                partner_content_type__model='supplier'
            ).values('partner_object_id').annotate(
                delivery_count=Count('id')
            ).order_by('-delivery_count').values_list('partner_object_id', flat=True)[:30]
            
            # 3. Combine recent and popular, remove duplicates
            priority_supplier_ids = list(recent_supplier_ids) + [
                sid for sid in popular_supplier_ids if sid not in recent_supplier_ids
            ]
            
            # 4. Build final queryset with priority ordering (PostgreSQL compatible)
            if priority_supplier_ids:
                # Get priority suppliers first (converted to list for ordering)
                priority_suppliers = list(Supplier.objects.filter(
                    pk__in=priority_supplier_ids,
                    is_active=True
                ))
                
                # Sort by the priority_supplier_ids order
                priority_dict = {supplier_id: index for index, supplier_id in enumerate(priority_supplier_ids)}
                priority_suppliers.sort(key=lambda s: priority_dict.get(s.pk, 999))
                
                # Add other active suppliers (alphabetically) to fill to ~100
                remaining_count = 100 - len(priority_supplier_ids)
                if remaining_count > 0:
                    other_suppliers = list(Supplier.objects.filter(
                        is_active=True
                    ).exclude(
                        pk__in=priority_supplier_ids
                    ).order_by('name')[:remaining_count])
                    
                    # Combine lists
                    combined_suppliers = priority_suppliers + other_suppliers
                    
                    # Convert back to queryset IDs for consistent processing
                    all_ids = [s.pk for s in combined_suppliers]
                    final_queryset = Supplier.objects.filter(pk__in=all_ids)
                else:
                    # Convert to queryset IDs
                    all_ids = [s.pk for s in priority_suppliers]
                    final_queryset = Supplier.objects.filter(pk__in=all_ids)
            else:
                # Fallback: just get alphabetical active suppliers if no usage data
                final_queryset = Supplier.objects.filter(is_active=True).order_by('name')[:100]
            
            logger.info(f"Optimized supplier list: {final_queryset.count()} suppliers (recent: {len(recent_supplier_ids)}, popular: {len(popular_supplier_ids)})")
            return final_queryset
            
        except Exception as e:
            logger.error(f"Error getting optimized supplier list: {e}", exc_info=True)
            # Fallback to simple active suppliers
            return Supplier.objects.filter(is_active=True).order_by('name')[:100]

    def serialize_products(self, products_queryset):
        """Хелпър метод за сериализация на продуктите, за да е по-чист get_context_data."""
        products_data = []
        for p in products_queryset:
            products_data.append({
                'pk': p.pk,
                'name': p.name,
                'code': p.code,
                'base_unit': {
                    'pk': p.base_unit.pk, 'name': p.base_unit.name, 'symbol': p.base_unit.symbol
                } if p.base_unit else None,
                'packagings': [
                    {
                        'unit_id': pkg.unit.pk,
                        'unit_name': pkg.unit.name,
                        'unit_symbol': pkg.unit.symbol,
                        'conversion_factor': float(pkg.conversion_factor)
                    } for pkg in p.packagings.filter(allow_purchase=True)
                ]
            })
        return json.dumps(products_data)


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
                # Handle 'generic' actions - use target status instead of semantic type
                if action_type == 'generic':
                    # For generic actions, get target status from request data
                    target_status = self.request.POST.get('target_status')
                    if target_status:
                        logger.info(f"Processing generic action to target status: '{target_status}'")
                        return doc_service.facade.transition_to(target_status, comments)
                    else:
                        logger.error("Generic action without target_status")
                        return Result.error('MISSING_TARGET_STATUS', 'Generic action requires target_status')
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


class SupplierSearchAPIView(LoginRequiredMixin, View):
    """
    🆕 API endpoint for advanced supplier search with filters and pagination
    
    Features:
    - Text search (name, code, contact person)
    - Division filtering
    - Status filtering (active/inactive)
    - Pagination support
    - Smart relevance ordering
    """
    
    def post(self, request):
        """Advanced supplier search with filters"""
        try:
            import json
            data = json.loads(request.body)
            
            # Extract search parameters
            search_term = data.get('search', '').strip()
            division = data.get('division', '').strip()
            status = data.get('status', 'active')
            page = int(data.get('page', 1))
            page_size = int(data.get('page_size', 10))
            
            # Build base queryset
            queryset = Supplier.objects.select_related().prefetch_related('divisions')
            
            # Apply status filter
            if status == 'active':
                queryset = queryset.filter(is_active=True)
            elif status == 'inactive':
                queryset = queryset.filter(is_active=False)
            # 'all' means no status filter
            
            # Apply text search
            if search_term:
                queryset = queryset.filter(
                    models.Q(name__icontains=search_term) |
                    models.Q(code__icontains=search_term) |
                    models.Q(contact_person__icontains=search_term) |
                    models.Q(vat_number__icontains=search_term) |
                    models.Q(phone__icontains=search_term) |
                    models.Q(email__icontains=search_term)
                )
            
            # Apply division filter
            if division:
                queryset = queryset.filter(divisions__name__icontains=division)
            
            # Apply ordering (relevance + name)
            if search_term:
                # Prioritize exact name matches, then partial matches
                queryset = queryset.extra(
                    select={
                        'name_exact': f"CASE WHEN LOWER(name) = LOWER('{search_term}') THEN 1 ELSE 0 END",
                        'name_starts': f"CASE WHEN LOWER(name) LIKE LOWER('{search_term}%') THEN 1 ELSE 0 END"
                    }
                ).order_by('-name_exact', '-name_starts', 'name')
            else:
                queryset = queryset.order_by('name')
            
            # Apply pagination
            from django.core.paginator import Paginator
            paginator = Paginator(queryset, page_size)
            
            try:
                suppliers_page = paginator.page(page)
            except:
                suppliers_page = paginator.page(1)
                page = 1
            
            # Serialize suppliers
            suppliers_data = []
            for supplier in suppliers_page:
                # Get primary division
                primary_division = supplier.divisions.first()
                division_name = primary_division.name if primary_division else ''
                
                suppliers_data.append({
                    'id': supplier.pk,
                    'name': supplier.name,
                    'code': supplier.code,
                    'vat_number': supplier.vat_number,
                    'contact_person': supplier.contact_person,
                    'phone': supplier.phone,
                    'email': supplier.email,
                    'is_active': supplier.is_active,
                    'division': division_name,
                    'city': supplier.city,
                    'address': supplier.address,
                })
            
            # Build pagination info
            pagination_info = {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'page_size': page_size,
                'has_previous': suppliers_page.has_previous(),
                'has_next': suppliers_page.has_next(),
                'start_index': suppliers_page.start_index(),
                'end_index': suppliers_page.end_index(),
            }
            
            return JsonResponse({
                'success': True,
                'suppliers': suppliers_data,
                'pagination': pagination_info,
                'search_info': {
                    'search_term': search_term,
                    'division': division,
                    'status': status,
                    'results_count': len(suppliers_data)
                }
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'message': f'Invalid parameters: {str(e)}'
            }, status=400)
        except Exception as e:
            logger.error(f"Supplier search API error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': 'Internal server error'
            }, status=500)


class ProductPricingAjaxView(LoginRequiredMixin, View):
    """Ajax endpoint for dynamic product pricing"""
    
    def post(self, request):
        """Get recommended pricing for product in delivery context"""
        try:
            product_id = request.POST.get('product_id')
            partner_id = request.POST.get('partner_id')
            location_id = request.POST.get('location_id')
            
            if not product_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Product ID is required'
                })
            
            # Get models
            from products.models import Product
            from partners.models import Supplier
            from inventory.models import InventoryLocation
            
            try:
                product = Product.objects.get(id=product_id)
                partner = Supplier.objects.get(id=partner_id) if partner_id else None
                location = InventoryLocation.objects.get(id=location_id) if location_id else None
            except (Product.DoesNotExist, Supplier.DoesNotExist, InventoryLocation.DoesNotExist) as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Invalid data: {str(e)}'
                })
            
            # Get last purchase price
            from pricing.services.pricing_service import PricingService
            pricing_result = PricingService.get_last_purchase_price(
                product=product,
                partner=partner, 
                location=location
            )
            
            if pricing_result.ok:
                data = pricing_result.data
                return JsonResponse({
                    'success': True,
                    'recommended_price': str(data['price']),
                    'pricing_info': {
                        'last_date': str(data.get('date', '')),
                        'last_partner': data.get('partner', ''),
                        'source': data.get('source', 'purchase_history'),
                        'match_type': data.get('match_type', ''),
                        'delivery_ref': data.get('delivery_ref', '')
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': pricing_result.msg,
                    'recommended_price': '0.00'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Pricing lookup failed: {str(e)}',
                'recommended_price': '0.00'
            })