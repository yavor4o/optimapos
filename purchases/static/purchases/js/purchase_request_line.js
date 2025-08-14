// purchases/static/purchases/js/purchase_request_line.js - COMPLETE FIXED VERSION

(function() {
    'use strict';

    // Helper function for DOM ready
    function whenReady(fn) {
        if (document.readyState !== 'loading') {
            fn();
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    }

    function initializePriceAutoFill() {
        const $ = window.django.jQuery;

        if (!$) {
            console.error('Django jQuery not available');
            return;
        }

        // Initialize calculations
        initializeCalculations($);

        // Функция за добавяне на listener към product field
        function attachProductListener(productField) {
            const row = productField.closest('.form-row, tr, .dynamic-form');
            const enteredPriceField = row.find('input[name*="entered_price"], input[id*="entered_price"]');

            if (enteredPriceField.length > 0) {
                productField.off('change.priceAutofill');
                productField.on('change.priceAutofill', function() {
                    const productId = $(this).val();

                    if (productId && (!enteredPriceField.val() || enteredPriceField.val() === '0.00' || enteredPriceField.val() === '')) {
                        console.log('🔍 Product selected:', productId);
                        fetchLastPurchasePrice(productId, enteredPriceField, $);
                    }
                });
            }
        }

        // Обработи съществуващите product fields
        const productFields = $('select[name*="product"], select[id*="product"]');
        productFields.each(function() {
            attachProductListener($(this));
        });

        // За динамично добавяни редове
        $(document).on('formset:added', function(event, $row) {
            const productField = $row.find('select[name*="product"], select[id*="product"]');
            if (productField.length > 0) {
                attachProductListener(productField);
            }
            // Re-attach calculation listeners to new row
            attachCalculationListeners($row, $);
        });

        console.log('🎯 Purchase Request auto-calculations initialized!');
    }

    function initializeCalculations($) {
        // Attach listeners to all calculation fields
        attachCalculationListeners($(document), $);

        // Initial calculation
        setTimeout(() => calculateTotals($), 500);
    }

    function attachCalculationListeners(container, $) {
        // Listen for changes in quantity, price, discount fields
        container.off('input.calculations change.calculations');

        container.on('input.calculations change.calculations',
            'input[name*="requested_quantity"], input[name*="entered_price"], input[name*="unit_price"], input[name*="discount_percent"], input[name*="discount_amount"], select[name*="vat_rate"]',
            function() {
                console.log('🧮 Field changed, recalculating...');
                setTimeout(() => calculateTotals($), 100);
            }
        );

        // Also listen for line removal
        container.on('click', '.delete-row, .remove-form-row', function() {
            setTimeout(() => calculateTotals($), 200);
        });
    }

    function calculateTotals($) {
        let subtotal = 0;
        let vatTotal = 0;
        let discountTotal = 0;

        // Find all line rows
        const lineRows = $('.dynamic-form:visible, .form-row:visible').filter(function() {
            return $(this).find('input[name*="requested_quantity"], input[name*="entered_price"]').length > 0;
        });

        console.log('📊 Calculating totals for', lineRows.length, 'rows');

        // Calculate line totals
        lineRows.each(function() {
            const row = $(this);

            // Skip deleted rows
            if (row.find('input[name*="DELETE"]').is(':checked')) {
                return;
            }

            const quantity = parseFloat(row.find('input[name*="requested_quantity"]').val()) || 0;
            const unitPrice = parseFloat(row.find('input[name*="entered_price"], input[name*="unit_price"]').val()) || 0;
            const discountPercent = parseFloat(row.find('input[name*="discount_percent"]').val()) || 0;
            const discountAmount = parseFloat(row.find('input[name*="discount_amount"]').val()) || 0;

            if (quantity > 0 && unitPrice > 0) {
                let lineTotal = quantity * unitPrice;

                // Apply line discount
                if (discountPercent > 0) {
                    lineTotal = lineTotal * (1 - discountPercent / 100);
                } else if (discountAmount > 0) {
                    lineTotal = Math.max(0, lineTotal - discountAmount);
                }

                subtotal += lineTotal;

                // Update line total display (if exists)
                const lineTotalField = row.find('input[name*="line_total"], .line-total-display');
                if (lineTotalField.length > 0) {
                    if (lineTotalField.is('input')) {
                        lineTotalField.val(lineTotal.toFixed(2));
                    } else {
                        lineTotalField.text(formatCurrency(lineTotal));
                    }
                }

                console.log(`📊 Line: ${quantity} × ${unitPrice} = ${lineTotal.toFixed(2)}`);
            }
        });

        // Get document-level VAT rate
        const documentVatRate = parseFloat($('input[name*="vat_rate"], select[name*="vat_rate"]').val()) || 0;

        // Calculate VAT
        if (documentVatRate > 0) {
            vatTotal = subtotal * (documentVatRate / 100);
        }

        // Get document-level discount
        const documentDiscountPercent = parseFloat($('input[name*="discount_percent"]').val()) || 0;
        const documentDiscountAmount = parseFloat($('input[name*="discount_amount"]').val()) || 0;

        if (documentDiscountPercent > 0) {
            discountTotal = subtotal * (documentDiscountPercent / 100);
        } else if (documentDiscountAmount > 0) {
            discountTotal = documentDiscountAmount;
        }

        // Final total
        const finalTotal = subtotal + vatTotal - discountTotal;

        // Update display fields
        updateTotalFields($, {
            subtotal: subtotal,
            vatTotal: vatTotal,
            discountTotal: discountTotal,
            finalTotal: finalTotal
        });

        console.log(`💰 Totals: Subtotal=${subtotal.toFixed(2)}, VAT=${vatTotal.toFixed(2)}, Final=${finalTotal.toFixed(2)}`);
    }

    function updateTotalFields($, totals) {
        // Update subtotal fields
        const subtotalFields = $('input[name*="subtotal"], .subtotal-display, #id_subtotal');
        subtotalFields.each(function() {
            const field = $(this);
            if (field.is('input')) {
                field.val(totals.subtotal.toFixed(2));
            } else {
                field.text(formatCurrency(totals.subtotal));
            }
        });

        // Update VAT total
        const vatFields = $('input[name*="vat_amount"], input[name*="vat_total"], .vat-total-display, #id_vat_amount');
        vatFields.each(function() {
            const field = $(this);
            if (field.is('input')) {
                field.val(totals.vatTotal.toFixed(2));
            } else {
                field.text(formatCurrency(totals.vatTotal));
            }
        });

        // Update discount total
        const discountFields = $('input[name*="discount_total"], .discount-total-display');
        discountFields.each(function() {
            const field = $(this);
            if (field.is('input')) {
                field.val(totals.discountTotal.toFixed(2));
            } else {
                field.text(formatCurrency(totals.discountTotal));
            }
        });

        // Update final total
        const totalFields = $('input[name*="total_amount"], input[name*="grand_total"], .final-total-display, #id_total_amount');
        totalFields.each(function() {
            const field = $(this);
            if (field.is('input')) {
                field.val(totals.finalTotal.toFixed(2));
            } else {
                field.text(formatCurrency(totals.finalTotal));
            }
        });

        // Visual feedback
        totalFields.addClass('total-updated');
        setTimeout(() => {
            totalFields.removeClass('total-updated');
        }, 1000);
    }

    function formatCurrency(amount) {
        return amount.toFixed(2) + ' лв';
    }

    function fetchLastPurchasePrice(productId, priceField, $) {
        console.log('🌐 Fetching price for product:', productId);

        const originalPlaceholder = priceField.attr('placeholder');
        priceField.attr('placeholder', '💰 Loading...');
        priceField.addClass('loading-price');

        $.ajax({
            url: '/purchases/api/last-purchase-price/',
            type: 'GET',
            data: {
                'product_id': productId
            },
            success: function(response) {
                console.log('📡 API Response:', response);

                if (response.success && response.last_price) {
                    if (!priceField.val() || priceField.val() === '0.00' || priceField.val() === '') {
                        priceField.val(response.last_price);

                        priceField.addClass('price-auto-filled');
                        setTimeout(() => {
                            priceField.removeClass('price-auto-filled');
                        }, 3000);

                        const info = `💰 Last price: ${response.last_price}
📅 Date: ${response.last_date || 'Unknown'}
🏪 Source: ${response.supplier || 'Unknown'}`;
                        priceField.attr('title', info);

                        // Trigger calculation update
                        priceField.trigger('input.calculations');

                        console.log('✅ Price auto-filled:', response.last_price);
                    }
                } else {
                    console.log('💡 No price found for this product');
                    priceField.attr('title', '💡 No previous purchase price found');
                }
            },
            error: function(xhr, status, error) {
                console.error('❌ AJAX Error:', error);
                priceField.attr('title', '❌ Error loading price data');
            },
            complete: function() {
                priceField.attr('placeholder', originalPlaceholder);
                priceField.removeClass('loading-price');
            }
        });
    }

    // Initialize when ready
    whenReady(function() {
        if (window.location.pathname.includes('/admin/purchases/purchaserequest/')) {
            setTimeout(function() {
                initializePriceAutoFill();

                const style = document.createElement('style');
                style.textContent = `
                    .price-auto-filled {
                        background-color: #e8f5e8 !important;
                        border-color: #28a745 !important;
                        transition: all 0.3s ease;
                        box-shadow: 0 0 5px rgba(40, 167, 69, 0.3);
                    }
                    .loading-price {
                        background-color: #fff3cd !important;
                        border-color: #ffc107 !important;
                    }
                    .total-updated {
                        background-color: #cce5ff !important;
                        border-color: #007bff !important;
                        transition: all 0.3s ease;
                    }
                `;
                document.head.appendChild(style);

                console.log('🚀 System ready with auto-calculations!');
            }, 1000);
        }
    });

})();