// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};

    // configuration
    var braintree_URL = 'https://chaos.thunderbird.net'
    const DURATION = 250;

    Donation.BraintreeDropin = null;

    Donation.BuildPaymentForm = function(client_token, amount, download_link) {
        // show selected donation amount
        $('#amount-preview').text(amount);
        // load braintree content
        braintree.dropin.create({
            authorization: client_token,
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
                                url: braintree_URL +'/checkout',
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
        
                                // TODO: The success and failure responses need user-friendly display.
                                // TODO: On success, we should trigger the Thunderbird download immediately.
                                if (result.success) {
                                    $('#checkout-message').html('<h1>'+result.message+'</h1><p>Your contributing helps to ensure Thunderbird stays free for business and personal use and supports future development.</p>');
                                    // Start Thunderbird download.
                                    window.Mozilla.Utils.doRedirect(download_link);
                                } else {
                                    console.log(result);
                                    $('#checkout-message').html('<h1>Error:'+result.message+'</h1><p>Check your console.</p>');
                                }
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


    Donation.InitPaymentForm = function(amount, download_link) {
        $.ajax({
            type: 'GET',
            url: braintree_URL + '/verify_client',
            success: function(result) {
                if (result.success) {
                    Donation.BuildPaymentForm(result.client_token, amount, download_link)
                }
            }
        });
    };

    Donation.DisplayDonateModal = function(download_link) {
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
            window.Mozilla.Utils.doRedirect(download_link);
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
            Donation.InitPaymentForm(amount, download_link)
        });

        // Define go back button to the donation amount selection.
        $('#checkout-back').click(function(e) {
            e.preventDefault();
            Donation.DropinTeardown();
            $('#checkout-container').hide();
            $('#amount-container').show();
        });
    };

    window.Mozilla.Donation = Donation;

})();
