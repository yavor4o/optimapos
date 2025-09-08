/**
 * Delivery Form Management
 * Handles form validation, line items management, and form submission
 */

export class DeliveryForm {
    constructor(formId = 'delivery-form') {
        this.form = document.getElementById(formId);
        this.actionTypeInput = document.getElementById('action_type');
        this.lineIndex = 0;
        this.productPackagingData = {};
        this.productOptionsHtml = '<option value="">Select Product...</option>';
        this.unitOptionsHtml = '<option value="">Auto</option>';
        
        this.init();
    }
    
    init() {
        if (!this.form) return;
        
        this.setupEventListeners();
        this.prepareProductData();
        this.addInitialLineItem();
    }
    
    setupEventListeners() {
        // Semantic action buttons
        document.addEventListener('click', (e) => {
            if (e.target.matches('.semantic-action-btn')) {
                this.handleActionButton(e);
            }
        });
        
        // Add line item button
        document.addEventListener('click', (e) => {
            if (e.target.matches('#add-line-btn') || e.target.closest('#add-line-btn')) {
                e.preventDefault();
                this.addLineItem();
            }
        });
        
        // Form validation
        this.form.addEventListener('submit', (e) => {
            this.validateForm(e);
        });
    }
    
    handleActionButton(e) {
        e.preventDefault();
        const button = e.target.closest('.semantic-action-btn');
        const targetStatus = button.value;
        
        this.actionTypeInput.value = targetStatus;
        
        if (targetStatus === 'reject') {
            const comments = prompt('Please provide a reason for rejection:');
            if (!comments || comments.trim() === '') {
                this.showAlert('Rejection reason is required.', 'danger');
                return;
            }
            
            const commentsField = document.createElement('input');
            commentsField.type = 'hidden';
            commentsField.name = 'comments';
            commentsField.value = comments.trim();
            this.form.appendChild(commentsField);
        }
        
        // Show loading state
        button.disabled = true;
        button.innerHTML = '<i class="ki-outline ki-loading animate-spin"></i> Processing...';
        
        this.form.submit();
    }
    
    prepareProductData() {
        // This will be populated by Django template variables
        // Products data should be passed from the template
        if (window.productPackagingData) {
            this.productPackagingData = window.productPackagingData;
        }
        
        if (window.productOptionsHtml) {
            this.productOptionsHtml = window.productOptionsHtml;
        }
        
        if (window.unitOptionsHtml) {
            this.unitOptionsHtml = window.unitOptionsHtml;
        }
    }
    
    addLineItem() {
        const container = document.getElementById('line-items-container');
        const noLinesMessage = document.getElementById('no-lines-message');
        
        if (noLinesMessage) {
            noLinesMessage.remove();
        }
        
        const lineHtml = this.generateLineItemHtml();
        container.insertAdjacentHTML('beforeend', lineHtml);
        
        const newLine = container.lastElementChild;
        this.attachLineEventListeners(newLine);
        this.updateLineCount();
        this.initializeKtUIComponents(newLine);
        
        this.lineIndex++;
    }
    
    generateLineItemHtml() {
        return `
            <tr class="hover:bg-gray-50 transition-colors line-item" data-index="${this.lineIndex}">
                <td class="p-4">
                    <select name="line_product_${this.lineIndex}" class="kt-select product-select w-full" data-kt-select="{}" required>
                        ${this.productOptionsHtml}
                    </select>
                </td>
                <td class="p-4 text-right">
                    <input type="number"
                           name="line_quantity_${this.lineIndex}"
                           class="quantity-input w-20 text-right"
                           min="0.001"
                           step="0.001"
                           placeholder="0"
                           required>
                </td>
                <td class="p-4 text-right">
                    <select name="line_unit_${this.lineIndex}" class="kt-select unit-select w-20" data-kt-select="{}">
                        ${this.unitOptionsHtml}
                    </select>
                </td>
                <td class="p-4 text-right">
                    <div class="relative">
                        <input type="number"
                               name="line_unit_price_${this.lineIndex}"
                               class="price-input w-24 text-right"
                               min="0"
                               step="0.01"
                               placeholder="Auto">
                        <span class="price-indicator absolute right-1 top-1 hidden"></span>
                    </div>
                </td>
                <td class="p-4 text-right">
                    <input type="text"
                           name="line_total_${this.lineIndex}"
                           class="total-display w-24 text-right bg-gray-100 font-mono font-semibold"
                           readonly
                           placeholder="0.00">
                </td>
                <td class="p-4 text-center">
                    <button type="button" class="btn btn-icon btn-danger btn-sm remove-line-btn" title="Remove line">
                        <i class="ki-outline ki-trash"></i>
                    </button>
                </td>
                <input type="hidden" name="line_notes_${this.lineIndex}" value="">
            </tr>
        `;
    }
    
    attachLineEventListeners(lineElement) {
        const productSelect = lineElement.querySelector('.product-select');
        const priceInput = lineElement.querySelector('.price-input');
        const unitSelect = lineElement.querySelector('.unit-select');
        const quantityInput = lineElement.querySelector('.quantity-input');
        const removeBtn = lineElement.querySelector('.remove-line-btn');
        
        // Product selection change
        productSelect.addEventListener('change', () => {
            this.handleProductChange(lineElement, productSelect.value);
        });
        
        // Quantity and price changes
        quantityInput.addEventListener('input', () => this.calculateLineTotal(lineElement));
        priceInput.addEventListener('input', () => {
            this.calculateLineTotal(lineElement);
            if (window.updatePriceVarianceIndicator) {
                window.updatePriceVarianceIndicator(priceInput);
            }
        });
        
        // Remove line
        removeBtn.addEventListener('click', () => {
            lineElement.remove();
            this.updateLineCount();
            
            if (document.querySelectorAll('.line-item').length === 0) {
                this.showEmptyState();
            }
        });
    }
    
    handleProductChange(lineElement, productId) {
        if (productId && this.productPackagingData[productId]) {
            const productData = this.productPackagingData[productId];
            const unitSelect = lineElement.querySelector('.unit-select');
            
            // Update unit dropdown
            unitSelect.innerHTML = '';
            
            // Add base unit
            const baseOption = document.createElement('option');
            baseOption.value = productData.base_unit.id;
            baseOption.textContent = `${productData.base_unit.name} (${productData.base_unit.symbol})`;
            unitSelect.appendChild(baseOption);
            
            // Add packaging units
            productData.packagings.forEach(packaging => {
                if (packaging.allow_purchase) {
                    const option = document.createElement('option');
                    option.value = packaging.unit_id;
                    option.textContent = `${packaging.unit_name} (${packaging.conversion_factor} x ${productData.base_unit.symbol})`;
                    unitSelect.appendChild(option);
                }
            });
            
            unitSelect.value = productData.base_unit.id;
        }
        
        this.calculateLineTotal(lineElement);
        
        // Load pricing if available
        if (window.loadProductPricing) {
            window.loadProductPricing(lineElement);
        }
    }
    
    calculateLineTotal(lineElement) {
        const quantity = parseFloat(lineElement.querySelector('.quantity-input').value) || 0;
        const price = parseFloat(lineElement.querySelector('.price-input').value) || 0;
        const total = quantity * price;
        
        const totalDisplay = lineElement.querySelector('.total-display');
        totalDisplay.value = total.toFixed(2);
        
        // Update styling
        if (total > 0) {
            totalDisplay.classList.remove('text-danger');
            totalDisplay.classList.add('text-success');
        } else {
            totalDisplay.classList.remove('text-success');
            totalDisplay.classList.add('text-danger');
        }
    }
    
    updateLineCount() {
        const lineItems = document.querySelectorAll('.line-item').length;
        const lineCountElement = document.getElementById('line-count');
        const validationStatus = document.getElementById('validation-status');
        
        if (lineCountElement) {
            lineCountElement.textContent = `${lineItems} item${lineItems !== 1 ? 's' : ''}`;
        }
        
        if (validationStatus) {
            if (lineItems > 0) {
                validationStatus.textContent = `Ready with ${lineItems} item${lineItems !== 1 ? 's' : ''}`;
                validationStatus.className = 'kt-timeline-text text-sm font-semibold text-success';
            } else {
                validationStatus.textContent = 'No items added';
                validationStatus.className = 'kt-timeline-text text-sm font-semibold text-warning';
            }
        }
    }
    
    showEmptyState() {
        const container = document.getElementById('line-items-container');
        container.innerHTML = `
            <tr id="no-lines-message">
                <td colspan="6" class="p-8 text-center">
                    <div class="kt-empty-state">
                        <div class="kt-empty-state-icon">
                            <i class="ki-outline ki-element-plus text-4xl text-gray-400"></i>
                        </div>
                        <div class="kt-empty-state-content">
                            <div class="kt-empty-state-title">No line items added</div>
                            <div class="kt-empty-state-description">Click "Add Item" to start adding products</div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }
    
    validateForm(e) {
        const partnerId = document.getElementById('partner_id').value;
        if (!partnerId) {
            e.preventDefault();
            this.showAlert('Please select a supplier.', 'danger');
            return;
        }
        
        const lineItems = document.querySelectorAll('.line-item');
        const actionType = this.actionTypeInput.value;
        
        if (lineItems.length === 0 && actionType !== 'save_draft') {
            const proceed = confirm('No line items added. Continue with empty delivery?');
            if (!proceed) {
                e.preventDefault();
                return;
            }
        }
    }
    
    addInitialLineItem() {
        // Add one line item by default
        setTimeout(() => {
            this.addLineItem();
        }, 100);
    }
    
    initializeKtUIComponents(container) {
        const selects = container.querySelectorAll('[data-kt-select]');
        selects.forEach(select => {
            if (window.KtSelect) {
                new window.KtSelect(select);
            }
        });
    }
    
    showAlert(message, type = 'info') {
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible">
                <div class="alert-icon">
                    <i class="ki-outline ki-information-4"></i>
                </div>
                <div class="alert-text">${message}</div>
                <button type="button" class="btn btn-icon btn-xs alert-close">
                    <i class="ki-outline ki-cross"></i>
                </button>
            </div>
        `;
        
        const alertContainer = document.createElement('div');
        alertContainer.innerHTML = alertHtml;
        this.form.insertBefore(alertContainer.firstElementChild, this.form.firstElementChild);
        
        setTimeout(() => {
            alertContainer.remove();
        }, 5000);
    }
}