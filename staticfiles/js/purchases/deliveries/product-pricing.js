/**
 * Product Pricing Management
 * Handles dynamic pricing, price variance indicators, and auto-pricing
 */

export class ProductPricing {
    constructor() {
        this.init();
    }
    
    init() {
        // Make pricing functions globally available for backward compatibility
        window.loadProductPricing = this.loadProductPricing.bind(this);
        window.updatePriceVarianceIndicator = this.updatePriceVarianceIndicator.bind(this);
    }
    
    loadProductPricing(lineElement) {
        const productSelect = lineElement.querySelector('.product-select');
        const priceInput = lineElement.querySelector('.price-input');
        const productId = productSelect.value;
        
        if (!productId) return;
        
        const partnerId = document.getElementById('partner_id')?.value;
        const locationId = document.getElementById('location_id')?.value;
        
        if (!partnerId || !locationId) return;
        
        // Show loading
        priceInput.style.backgroundColor = '#f8f9fa';
        priceInput.disabled = true;
        
        fetch('/purchases/deliveries/ajax-product-pricing/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: new URLSearchParams({
                'product_id': productId,
                'partner_id': partnerId,
                'location_id': locationId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                priceInput.value = data.recommended_price;
                priceInput.setAttribute('data-suggested-price', data.recommended_price);
                priceInput.setAttribute('data-has-suggestion', 'true');
                
                const indicator = priceInput.parentElement.querySelector('.price-indicator');
                indicator.classList.remove('hidden');
                indicator.innerHTML = '<i class="ki-outline ki-check text-success"></i>';
                indicator.title = `Auto-suggested: ${data.recommended_price}`;
                
                // Trigger total calculation
                this.calculateLineTotal(lineElement);
            }
        })
        .catch(error => {
            console.error('Pricing error:', error);
        })
        .finally(() => {
            priceInput.disabled = false;
            priceInput.style.backgroundColor = '';
        });
    }
    
    updatePriceVarianceIndicator(priceInput) {
        const hasSuggestion = priceInput.getAttribute('data-has-suggestion') === 'true';
        const suggestedPrice = parseFloat(priceInput.getAttribute('data-suggested-price'));
        const currentPrice = parseFloat(priceInput.value);
        
        if (!hasSuggestion || isNaN(suggestedPrice) || isNaN(currentPrice)) return;
        
        const indicator = priceInput.parentElement.querySelector('.price-indicator');
        
        if (Math.abs(currentPrice - suggestedPrice) < 0.01) {
            indicator.innerHTML = '<i class="ki-outline ki-check text-success"></i>';
            indicator.title = `Auto-suggested: ${suggestedPrice}`;
            return;
        }
        
        const variance = ((currentPrice - suggestedPrice) / suggestedPrice) * 100;
        const isHigher = variance > 0;
        const arrow = isHigher ? '↗' : '↙';
        const colorClass = isHigher ? 'text-danger' : 'text-success';
        
        indicator.innerHTML = `<span class="${colorClass}">${arrow}${Math.abs(variance).toFixed(1)}%</span>`;
        indicator.title = `${Math.abs(variance).toFixed(1)}% ${isHigher ? 'higher' : 'lower'} than suggested (${suggestedPrice})`;
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
    
    static formatPrice(price, currency = '€') {
        return `${currency}${parseFloat(price).toFixed(2)}`;
    }
    
    static calculateDiscount(originalPrice, currentPrice) {
        if (!originalPrice || !currentPrice) return 0;
        return ((originalPrice - currentPrice) / originalPrice) * 100;
    }
    
    static validatePrice(price, min = 0, max = 999999) {
        const numPrice = parseFloat(price);
        return !isNaN(numPrice) && numPrice >= min && numPrice <= max;
    }
}

// Auto-initialize when module loads
export const pricingManager = new ProductPricing();