/**
 * UI Components Management
 * Handles Metronic component initialization, alerts, and UI utilities
 */

export class UIComponents {
    constructor() {
        this.init();
    }
    
    init() {
        this.initializeExistingComponents();
        this.setupGlobalFunctions();
        this.autoHideMessages();
    }
    
    initializeExistingComponents() {
        // Initialize all Metronic select components on page load
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeSelects(document);
        });
    }
    
    initializeSelects(container = document) {
        const selects = container.querySelectorAll('[data-kt-select]');
        selects.forEach(select => {
            if (window.KtSelect && !select.ktSelect) {
                try {
                    select.ktSelect = new window.KtSelect(select);
                } catch (error) {
                    console.warn('Failed to initialize KtSelect:', error);
                }
            }
        });
    }
    
    initializeModal(modalElement) {
        if (window.KTModal && modalElement) {
            try {
                return window.KTModal.getInstance(modalElement) || new window.KTModal(modalElement);
            } catch (error) {
                console.warn('Failed to initialize KTModal:', error);
                return null;
            }
        }
        return null;
    }
    
    initializeDrawer(drawerElement) {
        if (window.KTDrawer && drawerElement) {
            try {
                return window.KTDrawer.getInstance(drawerElement) || new window.KTDrawer(drawerElement);
            } catch (error) {
                console.warn('Failed to initialize KTDrawer:', error);
                return null;
            }
        }
        return null;
    }
    
    showAlert(message, type = 'info', container = document.body, duration = 5000) {
        const alertId = 'alert-' + Date.now();
        const alertHtml = `
            <div id="${alertId}" class="alert alert-${type} alert-dismissible mb-4">
                <div class="alert-icon">
                    ${this.getAlertIcon(type)}
                </div>
                <div class="alert-text">${message}</div>
                <button type="button" class="btn btn-icon btn-xs alert-close" onclick="this.closest('.alert').remove()">
                    <i class="ki-outline ki-cross"></i>
                </button>
            </div>
        `;
        
        const alertContainer = document.createElement('div');
        alertContainer.innerHTML = alertHtml;
        const alertElement = alertContainer.firstElementChild;
        
        if (container.tagName === 'FORM') {
            container.insertBefore(alertElement, container.firstElementChild);
        } else {
            container.appendChild(alertElement);
        }
        
        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => {
                if (alertElement && alertElement.parentNode) {
                    alertElement.remove();
                }
            }, duration);
        }
        
        return alertElement;
    }
    
    getAlertIcon(type) {
        const icons = {
            'success': '<i class="ki-outline ki-check-circle"></i>',
            'danger': '<i class="ki-outline ki-information-4"></i>',
            'warning': '<i class="ki-outline ki-notification-bing"></i>',
            'info': '<i class="ki-outline ki-information-4"></i>',
            'primary': '<i class="ki-outline ki-check-circle"></i>'
        };
        return icons[type] || icons['info'];
    }
    
    showToast(message, type = 'success', duration = 3000) {
        const toastId = 'toast-' + Date.now();
        const toastHtml = `
            <div id="${toastId}" class="fixed top-4 right-4 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-4 transition-all duration-300 transform translate-x-full">
                <div class="flex items-center gap-3">
                    <div class="flex-shrink-0">
                        ${this.getToastIcon(type)}
                    </div>
                    <div class="flex-1">
                        <p class="text-sm font-medium text-gray-900">${message}</p>
                    </div>
                    <button type="button" class="flex-shrink-0 text-gray-400 hover:text-gray-600" onclick="this.closest('[id^=toast-]').remove()">
                        <i class="ki-outline ki-cross text-xs"></i>
                    </button>
                </div>
            </div>
        `;
        
        const toastContainer = document.createElement('div');
        toastContainer.innerHTML = toastHtml;
        const toastElement = toastContainer.firstElementChild;
        
        document.body.appendChild(toastElement);
        
        // Animate in
        setTimeout(() => {
            toastElement.classList.remove('translate-x-full');
        }, 100);
        
        // Auto-hide
        setTimeout(() => {
            toastElement.classList.add('translate-x-full');
            setTimeout(() => {
                if (toastElement && toastElement.parentNode) {
                    toastElement.remove();
                }
            }, 300);
        }, duration);
        
        return toastElement;
    }
    
    getToastIcon(type) {
        const icons = {
            'success': '<div class="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center"><i class="ki-outline ki-check text-green-600 text-sm"></i></div>',
            'error': '<div class="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center"><i class="ki-outline ki-cross text-red-600 text-sm"></i></div>',
            'warning': '<div class="w-6 h-6 rounded-full bg-yellow-100 flex items-center justify-center"><i class="ki-outline ki-notification-bing text-yellow-600 text-sm"></i></div>',
            'info': '<div class="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center"><i class="ki-outline ki-information-4 text-blue-600 text-sm"></i></div>'
        };
        return icons[type] || icons['info'];
    }
    
    showLoading(element, message = 'Loading...') {
        if (element) {
            element.innerHTML = `
                <div class="d-flex align-items-center justify-content-center h-100">
                    <div class="spinner-border text-primary"></div>
                    <div class="text-muted ms-3">${message}</div>
                </div>
            `;
        }
    }
    
    hideLoading(element, content = '') {
        if (element) {
            element.innerHTML = content;
        }
    }
    
    setupGlobalFunctions() {
        // Make functions globally available for backward compatibility
        window.showAlert = this.showAlert.bind(this);
        window.showToast = this.showToast.bind(this);
        window.initializeKtUIComponents = (container) => {
            this.initializeSelects(container);
        };
    }
    
    autoHideMessages() {
        // Auto-hide success messages that exist on page load
        document.addEventListener('DOMContentLoaded', () => {
            const successAlerts = document.querySelectorAll('.alert-primary, .alert-success');
            successAlerts.forEach(alert => {
                setTimeout(() => {
                    alert.style.opacity = '0';
                    setTimeout(() => {
                        if (alert.parentNode) {
                            alert.remove();
                        }
                    }, 300);
                }, 5000);
            });
        });
    }
    
    createConfirmDialog(message, title = 'Confirm', callback) {
        // For now, use browser confirm dialog
        // Later this can be enhanced with custom modal
        const result = confirm(`${title}\n\n${message}`);
        if (callback) {
            callback(result);
        }
        return result;
    }
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    throttle(func, limit) {
        let lastFunc;
        let lastRan;
        return function executedFunction(...args) {
            if (!lastRan) {
                func(...args);
                lastRan = Date.now();
            } else {
                clearTimeout(lastFunc);
                lastFunc = setTimeout(() => {
                    if ((Date.now() - lastRan) >= limit) {
                        func(...args);
                        lastRan = Date.now();
                    }
                }, limit - (Date.now() - lastRan));
            }
        };
    }
}

// Auto-initialize when module loads
export const uiComponents = new UIComponents();