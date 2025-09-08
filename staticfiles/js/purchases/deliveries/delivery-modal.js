/**
 * Delivery Modal Management
 * Handles modal show/hide, content loading, and AJAX integration
 */

export class DeliveryModal {
    constructor(modalId = 'createDeliveryModal') {
        this.modalElement = document.getElementById(modalId);
        this.modal = null;
        this.loadingState = document.getElementById('loadingState');
        this.contentState = document.getElementById('contentState');
        this.actionButtons = document.getElementById('modal-action-buttons');
        
        this.init();
    }
    
    init() {
        if (this.modalElement && typeof KTModal !== 'undefined') {
            this.modal = KTModal.getInstance(this.modalElement);
        }
    }
    
    async show() {
        if (!this.modal) return false;
        
        this.modal.show();
        await this.loadContent();
        return true;
    }
    
    hide() {
        if (this.modal) {
            this.modal.hide();
        }
    }
    
    async loadContent() {
        // Reset modal state
        this.showLoading();
        this.clearActionButtons();
        
        try {
            const response = await fetch('/purchases/deliveries/create/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/html, */*'
                },
                credentials: 'same-origin'
            });
            
            if (!response.ok) {
                throw new Error('Failed to load create form');
            }
            
            const html = await response.text();
            await this.processContent(html);
            
        } catch (error) {
            console.error('Error loading modal content:', error);
            this.showError('Error loading form. Please try again.');
        }
    }
    
    async processContent(html) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        
        // Get content container
        const contentContainer = tempDiv.querySelector('.w-full.h-full');
        if (!contentContainer) {
            throw new Error('Content container not found');
        }
        
        // Load content
        this.contentState.innerHTML = contentContainer.outerHTML;
        
        // Load action buttons from context data (already in HTML)
        this.loadActionButtonsFromContext(tempDiv);
        
        // Execute scripts
        this.executeScripts(tempDiv);
        
        this.showContent();
    }
    
    loadActionButtonsFromContext(tempDiv) {
        // Look for available_actions data in the HTML context
        const actionScript = tempDiv.querySelector('script[data-available-actions]');
        if (actionScript) {
            try {
                const actionsData = JSON.parse(actionScript.dataset.availableActions);
                if (actionsData && actionsData.length > 0) {
                    actionsData.forEach(action => {
                        const button = document.createElement('button');
                        button.type = 'submit';
                        button.name = 'target_status';
                        button.value = action.target_status;
                        button.className = `btn ${action.button_class || 'btn-secondary'} semantic-action-btn`;
                        button.setAttribute('form', 'delivery-form');
                        
                        button.innerHTML = `
                            <i class="${action.icon || 'ki-filled ki-check'} text-sm me-2"></i>
                            ${action.label}
                        `;
                        
                        this.actionButtons.appendChild(button);
                    });
                    return; // Success, no need for fallback
                }
            } catch (error) {
                console.error('Error parsing actions data from context:', error);
            }
        }
        
        // Fallback: Add default button
        const fallbackButton = document.createElement('button');
        fallbackButton.type = 'submit';
        fallbackButton.className = 'btn btn-primary semantic-action-btn';
        fallbackButton.setAttribute('form', 'delivery-form');
        fallbackButton.innerHTML = `
            <i class="ki-filled ki-check text-sm me-2"></i>
            Save Draft
        `;
        this.actionButtons.appendChild(fallbackButton);
    }
    
    async loadActionButtons() {
        try {
            // Request JSON data for available actions
            const response = await fetch('/purchases/deliveries/create/?actions_only=true', {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.available_actions && data.available_actions.length > 0) {
                    data.available_actions.forEach(action => {
                        const button = document.createElement('button');
                        button.type = 'submit';
                        button.name = 'target_status';
                        button.value = action.target_status;
                        button.className = `btn ${action.button_class || 'btn-secondary'} semantic-action-btn`;
                        button.setAttribute('form', 'delivery-form');
                        
                        button.innerHTML = `
                            <i class="ki-filled ki-check text-sm me-2"></i>
                            ${action.label}
                        `;
                        
                        this.actionButtons.appendChild(button);
                    });
                } else {
                    // Fallback button
                    const fallbackButton = document.createElement('button');
                    fallbackButton.type = 'submit';
                    fallbackButton.className = 'btn btn-primary semantic-action-btn';
                    fallbackButton.setAttribute('form', 'delivery-form');
                    fallbackButton.innerHTML = `
                        <i class="ki-filled ki-check text-sm me-2"></i>
                        Save Draft
                    `;
                    this.actionButtons.appendChild(fallbackButton);
                }
            }
        } catch (error) {
            console.error('Error loading action buttons:', error);
            // Add fallback button on error
            const fallbackButton = document.createElement('button');
            fallbackButton.type = 'submit';
            fallbackButton.className = 'btn btn-primary semantic-action-btn';
            fallbackButton.setAttribute('form', 'delivery-form');
            fallbackButton.innerHTML = `
                <i class="ki-filled ki-check text-sm me-2"></i>
                Save Draft
            `;
            this.actionButtons.appendChild(fallbackButton);
        }
    }
    
    executeScripts(tempDiv) {
        const scripts = tempDiv.querySelectorAll('script');
        
        setTimeout(() => {
            scripts.forEach(script => {
                const newScript = document.createElement('script');
                if (script.src) {
                    newScript.src = script.src;
                } else {
                    // Replace DOMContentLoaded with immediate execution
                    let scriptContent = script.textContent;
                    scriptContent = scriptContent.replace(
                        /document\.addEventListener\('DOMContentLoaded',\s*function\(\)\s*\{/g, 
                        '(function() {'
                    );
                    scriptContent = scriptContent.replace(/\}\);?\s*$/, '})();');
                    newScript.textContent = scriptContent;
                }
                document.body.appendChild(newScript);
                
                // Cleanup after execution
                setTimeout(() => {
                    if (newScript.parentNode) {
                        newScript.parentNode.removeChild(newScript);
                    }
                }, 2000);
            });
        }, 100);
    }
    
    showLoading() {
        this.loadingState.style.display = 'flex';
        this.contentState.style.display = 'none';
    }
    
    showContent() {
        this.loadingState.style.display = 'none';
        this.contentState.style.display = 'block';
    }
    
    showError(message) {
        this.loadingState.innerHTML = `<div class="text-danger text-center py-4">${message}</div>`;
    }
    
    clearActionButtons() {
        this.actionButtons.innerHTML = '';
    }
}

// Global function for backward compatibility
export function showCreateDeliveryModal() {
    const modal = new DeliveryModal();
    return modal.show();
}