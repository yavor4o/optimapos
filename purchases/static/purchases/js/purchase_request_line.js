// purchases/static/purchases/js/purchase_request_line.js - SAFE VERSION

(function() {
    'use strict';

    let isInitialized = false;

    function safeInit() {
        // Предотврати двойна инициализация
        if (isInitialized) return;

        // Провери дали сме в правилната страница
        if (!window.location.pathname.includes('/admin/purchases/purchaserequest/')) {
            return;
        }

        // Провери дали Django jQuery е налично
        if (!window.django || !window.django.jQuery) {
            console.warn('Django jQuery not available, retrying...');
            setTimeout(safeInit, 500);
            return;
        }

        const $ = window.django.jQuery;
        isInitialized = true;

        console.log('🎯 Price auto-fill initializing...');

        // САМО auto-fill функционалност, БЕЗ real-time calculations
        initializePriceAutoFill($);
    }

    function initializePriceAutoFill($) {
        // Attach к съществуващи полета
        attachToExistingFields($);

        // За нови редове
        $(document).on('formset:added', function(event, $row) {
            setTimeout(() => attachToNewRow($row, $), 100);
        });
    }

    function attachToExistingFields($) {
        $('select[name*="product"]').each(function() {
            const $select = $(this);
            if (!$select.data('price-autofill-attached')) {
                attachPriceAutofill($select, $);
            }
        });
    }

    function attachToNewRow($row, $) {
        const $select = $row.find('select[name*="product"]');
        if ($select.length > 0) {
            attachPriceAutofill($select, $);
        }
    }

    function attachPriceAutofill($productSelect, $) {
        $productSelect.data('price-autofill-attached', true);

        $productSelect.on('change.priceAutofill', function() {
            const productId = $(this).val();
            if (!productId) return;

            const $row = $(this).closest('tr, .form-row');
            const $priceField = $row.find('input[name*="entered_price"]');

            if ($priceField.length === 0) return;

            // Само ако полето е празно
            const currentPrice = $priceField.val();
            if (currentPrice && currentPrice !== '0.00' && currentPrice !== '') {
                return;
            }

            fetchAndFillPrice(productId, $priceField, $);
        });
    }

    function fetchAndFillPrice(productId, $priceField, $) {
        // Визуален индикатор
        const originalPlaceholder = $priceField.attr('placeholder') || '';
        $priceField.attr('placeholder', 'Loading...');

        $.ajax({
            url: '/purchases/api/last-purchase-price/',
            type: 'GET',
            data: { product_id: productId },
            success: function(response) {
                if (response.success && response.last_price) {
                    $priceField.val(response.last_price);

                    // Визуален feedback
                    $priceField.css({
                        'background-color': '#e8f5e8',
                        'border-color': '#28a745'
                    });

                    setTimeout(() => {
                        $priceField.css({
                            'background-color': '',
                            'border-color': ''
                        });
                    }, 2000);

                    console.log('✅ Auto-filled price:', response.last_price);
                }
            },
            error: function(xhr, status, error) {
                console.error('❌ Price fetch error:', error);
            },
            complete: function() {
                $priceField.attr('placeholder', originalPlaceholder);
            }
        });
    }

    // Безопасно стартиране
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', safeInit);
    } else {
        safeInit();
    }

    // Backup ако DOMContentLoaded не се изпълни
    setTimeout(safeInit, 1000);

})();