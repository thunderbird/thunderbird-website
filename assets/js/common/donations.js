// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    Donation.BraintreeDropin = null;

    // configuration
    var braintreeUrl = 'https://chaos.thunderbird.net'; // base url for braintree
    var duration = 250;                                 // transition duration for fade effects

    /**
     * Init modal and show step 1: selection of donation amount
     * @param {downloadLink} string direct link to download URL
     */
    Donation.DisplayDonateModal = function(downloadLink) {
        // Show the donation modal.
        $('#donate-modal').fadeIn(duration);
        $('#modal-overlay').fadeIn(duration);
        $(document.body).addClass('overflow-hidden');

        // Start with showing the amount selection
        $('#checkout-container').hide();
        $('#result-container').hide();
        $('#amount-container').show();

        // Close modal with button (clicking cancel donation or direct download button)
        $('#amount-cancel, .donation-direct-download').click(function(e) {
            e.preventDefault();
            Donation.CloseDonateModal(downloadLink);
        });
        // Close modal without download (clicking close/finish button or overlay)
        $('#close-modal, #modal-overlay, #finish-modal').click(function(e) {
            e.preventDefault();
            Donation.CloseDonateModal();
        });
        // Close modal when pressing ESC
        $(document).keyup(function(e) {
            if (e.key === "Escape") {
                Donation.CloseDonateModal();
            }
        });

        // Define active amount in amount selection.
        $('#amount-selection > label').click(function() {
            $('#amount-selection > label.active').removeClass('active');
            $(this).addClass('active');
        });
        $('#amount-other-selection').click(function() {
            $('#amount-other').focus();
        });
        $('#amount-other').click(function() {
            $('#amount-other-selection').prop('checked', true);
        });
        $('#amount-other').on('input', function() {
            $('#amount-other-selection').val($(this).val());
        });

        // Define amount submit button on the donation form.
        $('#amount-submit').click(function(e) {
            e.preventDefault();
            $('#loading-container').fadeIn(duration);
            // TODO: Hookup the currency switcher as well.
            let amount = $("input[name='amount']:checked").val();
            Donation.InitPaymentForm(amount, downloadLink)
        });

        // Define go back / start again buttons to the donation amount selection (step 2 or 3 -> step 1)
        $('#checkout-back, #start-again').click(function(e) {
            e.preventDefault();
            Donation.DropinTeardown();
            Donation.DisplayDonateModal(downloadLink);
        });
    };

    /**
     * Init braintree payment form and build it on success
     * @param {amount} number the user wants to donate
     * @param {downloadLink} string direct link to download URL
     */
    Donation.InitPaymentForm = function(amount, downloadLink) {
        $.ajax({
            type: 'GET',
            url: braintreeUrl + '/verify_client',
            success: function(result) {
                if (result.success) {
                    Donation.BuildDropin(result.client_token, amount, downloadLink)
                }
            }
        });
    };

    
    /**
     * Create Braintree Dropin if it doesn't exist yet before step 2
     * @param {clientToken} string given token from client verification
     * @param {amount} number the user wants to donate
     * @param {downloadLink} string direct link to download URL
     */
     Donation.BuildDropin = function(clientToken, amount, downloadLink) {
        // show selected donation amount
        $('#amount-preview').text(amount);
        // create braintree dropin instance if necessary
        if (!Donation.BraintreeDropin) {
            braintree.dropin.create({
                authorization: clientToken,
                container: '#dropin-container'
            }, function(createErr, instance) {
                if (!createErr) {
                    Donation.BraintreeDropin = instance;
                    Donation.BuildPaymentForm(amount, downloadLink);
                } else {
                    console.error('Could not create Drop-in UI!', createErr);
                }
            });
        } else {
            Donation.BuildPaymentForm(amount, downloadLink);
        }
    };

    /**
     * Show step 2: payment form to checkout and submit
     * @param {amount} number the user wants to donate
     * @param {downloadLink} string direct link to download URL
     */
    Donation.BuildPaymentForm = function(amount, downloadLink) {
        $('#amount-container').hide();
        $('#checkout-container').show();
        $('#checkout-submit').show();
        $('#loading-container').hide();
        $('#checkout-submit').click(function() {
            Donation.BraintreeDropin.requestPaymentMethod(function(requestPaymentMethodErr, payload) {
                if (!requestPaymentMethodErr) {
                    $('#loading-container').fadeIn(duration);
                    $.ajax({
                        type: 'POST',
                        url: braintreeUrl +'/checkout',
                        data: {
                            'payment_method_nonce': payload.nonce,
                            'amount': amount
                        }
                    }).done(function(result) {
                        // Tear down the Drop-In UI while keeping event listeners
                        if (Donation.DropinTeardown(true)) {
                            // Remove the 'Submit payment' button.
                            $('#checkout-submit').remove();
                        }
                        Donation.ShowResult(result, downloadLink);
                    });
                } else {
                    console.error('Could not request Payment Method!', requestPaymentMethodErr);
                }
            });
        });
    };

    /**
     * Show step 3: payment result message and download
     * @param {result} object ajax request result
     * @param {downloadLink} string direct link to download URL
     */
    Donation.ShowResult = function(result, downloadLink) {
        $('#checkout-container').hide();
        $('#result-container').show();
        $('#loading-container').hide();
        // handle result
        if (result.success) {
            $('#donation-error-message').hide();
            $('#donation-success-message').show();
            // Automatically start Thunderbird download.
            window.Mozilla.Utils.doRedirect(downloadLink);
        } else {
            $('#donation-success-message').hide();
            $('#donation-error-message').show();
        }
    }
    /**
     * Reset Braintree dropin to be able to recreate it if necessary
     */
    Donation.DropinTeardown = function(keepEventListeners) {
        if (!keepEventListeners) {
            $('.donation-click-event').off('click');
        }
        if (Donation.BraintreeDropin) {
            Donation.BraintreeDropin.teardown(function(teardownErr) {
                if (!teardownErr) {
                    Donation.BraintreeDropin = null;
                    return true;
                } else {
                    console.error('Could not tear down Drop-in UI!', teardownErr);
                    return false;
                }
            });
        }
    };

    /**
     * CLose modal and start download if necessary
     * @param {downloadLink} string direct link to download URL
     */
    Donation.CloseDonateModal = function(downloadLink) {
        $('#donate-modal').fadeOut(duration);
        $('#modal-overlay').fadeOut(duration);
        $('#checkout-container').fadeOut(duration);
        $('#result-container').fadeOut(duration);
        setTimeout(function() {
            $('#amount-container').show();
        }, duration);
        $(document.body).removeClass('overflow-hidden');
        // Reset Braintree dropin if existing
        Donation.DropinTeardown();
        // Start Thunderbird download if requested.
        if (downloadLink) {
            window.Mozilla.Utils.doRedirect(downloadLink);
        }
    }

    // append instance
    window.Mozilla.Donation = Donation;

})();
