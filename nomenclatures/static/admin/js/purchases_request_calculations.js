// static/admin/js/purchase_request_calculations.js

(function($) {
    'use strict';
    
    // Wait for DOM to be ready
    $(document).ready(function() {
        console.log('Purchase Request Calculations JS loaded');
    });
    
    // Calculate single line via AJAX
    window.calculateLine = function(lineId) {
        console.log('Calculating line:', lineId);
        
        // Show loading indicator
        var button = $('button[onclick="calculateLine(' + lineId + ')"]');
        var originalText = button.text();
        button.text('Calculating...').prop('disabled', true);
        
        $.ajax({
            url: '/admin/purchases/purchaserequest/calculate-line/' + lineId + '/',
            type: 'POST',
            headers: {
                'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val()
            },
            success: function(data) {
                console.log('Calculation result:', data);
                if (data.success) {
                    // Show success message
                    button.text('✓ Calculated').removeClass('btn-success').addClass('btn-outline-success');
                    
                    // Refresh page after 1 second to show results
                    setTimeout(function() {
                        location.reload();
                    }, 1000);
                } else {
                    alert('Calculation failed: ' + (data.error || 'Unknown error'));
                    button.text(originalText).prop('disabled', false);
                }
            },
            error: function(xhr, status, error) {
                console.error('AJAX error:', error);
                alert('Request failed: ' + error);
                button.text(originalText).prop('disabled', false);
            }
        });
    };
    
    // Recalculate single line via AJAX
    window.recalculateLine = function(lineId) {
        console.log('Recalculating line:', lineId);
        
        // Show loading indicator
        var button = $('button[onclick="recalculateLine(' + lineId + ')"]');
        var originalText = button.text();
        button.text('Recalculating...').prop('disabled', true);
        
        $.ajax({
            url: '/admin/purchases/purchaserequest/recalculate-line/' + lineId + '/',
            type: 'POST',
            headers: {
                'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val()
            },
            success: function(data) {
                console.log('Recalculation result:', data);
                if (data.success) {
                    // Show success message
                    button.text('✓ Updated').removeClass('btn-outline-primary').addClass('btn-outline-success');
                    
                    // Refresh page after 1 second to show results
                    setTimeout(function() {
                        location.reload();
                    }, 1000);
                } else {
                    alert('Recalculation failed: ' + (data.error || 'Unknown error'));
                    button.text(originalText).prop('disabled', false);
                }
            },
            error: function(xhr, status, error) {
                console.error('AJAX error:', error);
                alert('Request failed: ' + error);
                button.text(originalText).prop('disabled', false);
            }
        });
    };
    
    // Batch calculate all lines
    window.calculateAllLines = function() {
        if (!confirm('Calculate VAT for all lines? This may take a moment.')) {
            return;
        }
        
        console.log('Calculating all lines...');
        
        // Disable all calculate buttons
        $('button[onclick*="calculateLine"]').prop('disabled', true).text('Processing...');
        
        // Get all line IDs from calculate buttons
        var lineIds = [];
        $('button[onclick*="calculateLine"]').each(function() {
            var onclick = $(this).attr('onclick');
            var match = onclick.match(/calculateLine\((\d+)\)/);
            if (match) {
                lineIds.push(parseInt(match[1]));
            }
        });
        
        console.log('Found line IDs:', lineIds);
        
        // Calculate each line sequentially
        var processedCount = 0;
        var errorCount = 0;
        
        function calculateNext() {
            if (processedCount >= lineIds.length) {
                // All done
                alert('Batch calculation complete! Processed: ' + processedCount + ', Errors: ' + errorCount);
                location.reload();
                return;
            }
            
            var lineId = lineIds[processedCount];
            processedCount++;
            
            $.ajax({
                url: '/admin/purchases/purchaserequest/calculate-line/' + lineId + '/',
                type: 'POST',
                headers: {
                    'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val()
                },
                success: function(data) {
                    if (!data.success) {
                        errorCount++;
                        console.error('Error calculating line ' + lineId + ':', data.error);
                    }
                    // Continue with next line
                    calculateNext();
                },
                error: function() {
                    errorCount++;
                    console.error('AJAX error for line ' + lineId);
                    // Continue with next line
                    calculateNext();
                }
            });
        }
        
        // Start processing
        calculateNext();
    };
    
    // Auto-calculation on field change (optional)
    $(document).on('blur', 'input[name*="estimated_price"], input[name*="requested_quantity"]', function() {
        var row = $(this).closest('tr');
        var lineId = row.find('button[onclick*="calculateLine"]').attr('onclick');
        
        if (lineId) {
            var match = lineId.match(/calculateLine\((\d+)\)/);
            if (match) {
                var id = match[1];
                
                // Check if both price and quantity are filled
                var price = row.find('input[name*="estimated_price"]').val();
                var quantity = row.find('input[name*="requested_quantity"]').val();
                
                if (price && quantity && parseFloat(price) > 0 && parseFloat(quantity) > 0) {
                    // Auto-trigger calculation after 2 seconds
                    setTimeout(function() {
                        if (confirm('Auto-calculate VAT for this line?')) {
                            calculateLine(id);
                        }
                    }, 2000);
                }
            }
        }
    });
    
})(django.jQuery || jQuery);

// Fallback for older Django versions
if (typeof django === 'undefined') {
    window.django = {
        jQuery: jQuery
    };
}