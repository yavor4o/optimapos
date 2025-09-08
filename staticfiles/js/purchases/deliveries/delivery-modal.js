// static/js/purchases/deliveries/delivery-modal.js

import { DeliveryFormManager } from './delivery-form-manager.js';

export class DeliveryModal {
    constructor(modalId = 'createDeliveryModal') {
        this.modalElement = document.getElementById(modalId);
        this.modal = null;
        this.loadingState = document.getElementById('loadingState');
        this.contentState = document.getElementById('contentState');
        this.actionButtons = document.getElementById('modal-action-buttons');
        this.formManager = null;
        this.init();
    }

    init() {
        if (this.modalElement && typeof KTModal !== 'undefined') {
            this.modal = KTModal.getInstance(this.modalElement) || new KTModal(this.modalElement);
        }
    }

    async show() {
        if (!this.modal) return false;
        this.modal.show();
        await this.loadContent();
        return true;
    }

    hide() {
        if (this.modal) this.modal.hide();
    }

    async loadContent() {
        this.showLoading();
        this.clearActionButtons();

        try {
            const response = await fetch('/purchases/deliveries/create/', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (!response.ok) throw new Error(`Server responded with ${response.status}`);

            const html = await response.text();
            this.processContent(html);
        } catch (error) {
            console.error('Error loading modal content:', error);
            this.showError('Error loading form. Please try again.');
        }
    }

    processContent(html) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;

        const contentContainer = tempDiv.querySelector('[data-form-context="modal-create"]');
        if (!contentContainer) {
            this.showError('Invalid form content received.');
            return;
        }

        // 1. Инжектираме HTML-а в модала
        this.contentState.innerHTML = contentContainer.outerHTML;
        this.showContent();

        // 2. Зареждаме екшън бутоните от данните в HTML-а
        this.loadActionButtons(tempDiv);

        // 3. ИНИЦИАЛИЗИРАМЕ ФОРМАТА - най-важната стъпка
        try {
            const dataElement = this.contentState.querySelector('#delivery-form-data');
            if (!dataElement) throw new Error('#delivery-form-data script tag not found.');

            const initialData = JSON.parse(dataElement.textContent);

            // Създаваме инстанция на мениджъра. Вече сме сигурни, че HTML-ът е в DOM-a.
            this.formManager = new DeliveryFormManager('delivery-form', initialData);

            console.log('✅ Delivery form initialized successfully by DeliveryModal.');
        } catch (error) {
            console.error('❌ Failed to initialize DeliveryFormManager:', error);
            this.showError('Error initializing form scripts.');
        }
    }

    loadActionButtons(container) {
        const actionScript = container.querySelector('script[data-available-actions]');
        if (!actionScript) return;

        try {
            const actions = JSON.parse(actionScript.dataset.availableActions);
            actions.forEach(action => {
                const button = document.createElement('button');
                button.type = 'button'; // Важно: типът е button, за да не събмитва формата директно
                button.className = `btn ${action.button_class || 'btn-secondary'} semantic-action-btn`;
                button.innerHTML = `<i class="${action.icon || ''} text-sm me-2"></i> ${action.label}`;

                // Запазваме данните в `dataset` атрибути
                button.dataset.action = action.action_key;
                button.dataset.targetStatus = action.target_status;

                this.actionButtons.appendChild(button);
            });
        } catch (error) {
            console.error('Error parsing actions data:', error);
        }
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
        this.contentState.innerHTML = `<div class="text-danger text-center py-4">${message}</div>`;
        this.showContent();
    }

    clearActionButtons() {
        this.actionButtons.innerHTML = '';
    }
}

// Глобална функция за `onclick` атрибута
export function showCreateDeliveryModal() {
    // Добра практика е да се създава нова инстанция всеки път,
    // за да се избегнат проблеми със състоянието.
    const modalInstance = new DeliveryModal();
    modalInstance.show();
}