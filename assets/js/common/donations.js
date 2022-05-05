// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    Donation.BraintreeDropin = null;

    // configuration
    var braintreeUrl = 'https://chaos.thunderbird.net';
    const DURATION = 250;

    /**
     * Init modal and show step 1: selection of donation amount
     * @param {downloadLink} string direct link to download URL
     */
    Donation.DisplayDonateModal = function(downloadLink) {
        // Show the donation form.
        $('#donate-modal').fadeIn(DURATION);
        $('#modal-overlay').fadeIn(DURATION);
        $(document.body).addClass('overflow-hidden');

        // Define cancel and close button on the donation form.
        $('#amount-cancel').click(function(e) {
            e.preventDefault();
            $('#donate-modal').fadeOut(DURATION);
            $('#modal-overlay').fadeOut(DURATION);
            $(document.body).removeClass('overflow-hidden');
            // Start Thunderbird download if they close the donation form.
            window.Mozilla.Utils.doRedirect(downloadLink);
        });
        $('#close-modal').click(function(e) {
            e.preventDefault();
            $('#donate-modal').fadeOut(DURATION);
            $('#modal-overlay').fadeOut(DURATION);
            $(document.body).removeClass('overflow-hidden');
        });

        // Close modal when clicking the overlay
        $('#modal-overlay').click(function(e) {
            e.preventDefault();
            $('#donate-modal').fadeOut(DURATION);
            $('#modal-overlay').fadeOut(DURATION);
            $(document.body).removeClass('overflow-hidden');
        });

        // Close modal when pressing ESC
        $(document).keyup(function(e) {
            if (e.key === "Escape") {
                $('#donate-modal').fadeOut(DURATION);
                $('#modal-overlay').fadeOut(DURATION);
                $(document.body).removeClass('overflow-hidden');
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
            $('#loading-container').fadeIn(DURATION);
            // TODO: Hookup the currency switcher as well.
            let amount = $("input[name='amount']:checked").val();
            Donation.InitPaymentForm(amount, downloadLink)
        });

        // Define go back button to the donation amount selection.
        $('#checkout-back').click(function(e) {
            e.preventDefault();
            Donation.DropinTeardown();
            $('#checkout-container').hide();
            $('#amount-container').show();
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
                    Donation.BuildPaymentForm(result.client_token, amount, downloadLink)
                }
            }
        });
    };

    /**
     * Show step 2: payment form to checkout and submit
     * @param {clientToken} string given token from client verification
     * @param {amount} number the user wants to donate
     * @param {downloadLink} string direct link to download URL
     */
    Donation.BuildPaymentForm = function(clientToken, amount, downloadLink) {
        // show selected donation amount
        $('#amount-preview').text(amount);
        // load braintree content
        braintree.dropin.create({
            authorization: clientToken,
            container: '#dropin-container'
        }, function(createErr, instance) {
            if (!createErr) {
                Donation.BraintreeDropin = instance;
                $('#amount-container').hide();
                $('#checkout-container').show();
                $('#checkout-submit').show();
                $('#loading-container').hide();
                $('#checkout-submit').click(function() {
                    instance.requestPaymentMethod(function(requestPaymentMethodErr, payload) {
                        if (!requestPaymentMethodErr) {
                            $.ajax({
                                type: 'POST',
                                url: braintreeUrl +'/checkout',
                                data: {
                                    'payment_method_nonce': payload.nonce,
                                    'amount': amount
                                }
                            }).done(function(result) {
                                // Tear down the Drop-In UI.
                                if (Donation.DropinTeardown()) {
                                    // Remove the 'Submit payment' button.
                                    $('#checkout-submit').remove();
                                }
                                Donation.Result(result, downloadLink);
                            });
                        } else {
                            console.error('Could not request Payment Method!');
                        }
                    });
                });
            } else {
                console.error('Could not create Drop-in UI!');
            }
        });
    };

    /**
     * Show step 3: payment result message and download
     * @param {result} object ajax request result
     * @param {downloadLink} string direct link to download URL
     */
    Donation.Result = function(result, downloadLink) {
        $('#checkout-container').hide();
        $('#message-container').show();
        if (result.success) {
            $('#donation-success-message').show();
            // Start Thunderbird download.
            window.Mozilla.Utils.doRedirect(downloadLink);
        } else {
            $('#donation-error-message').show();
        }
    }
    /**
     * Reset Braintree dropin to be able to recreate it if necessary
     */
    Donation.DropinTeardown = function() {
        var instance = Donation.BraintreeDropin;
        if (instance) {
            instance.teardown(function(teardownErr) {
                if (!teardownErr) {
                    Donation.BraintreeDropin = null;
                    return true;
                } else {
                    console.error('Could not tear down Drop-in UI!');
                    return false;
                }
            });
        }
    };

    window.Mozilla.Donation = Donation;

})();
