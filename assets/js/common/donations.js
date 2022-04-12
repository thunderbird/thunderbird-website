// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    var braintree_URL = 'https://chaos.thunderbird.net'

    Donation.BuildForm = function(client_token, amount) {
        var button = document.querySelector('#submit-button');
        braintree.dropin.create({
            authorization: client_token,
            container: '#dropin-container'
        }, function(createErr, instance) {
            $('#submit-button').show();
            button.addEventListener('click', function() {
                instance.requestPaymentMethod(function(requestPaymentMethodErr, payload) {
                    $.ajax({
                        type: 'POST',
                        url: braintree_URL +'/checkout',
                        data: {
                            'payment_method_nonce': payload.nonce,
                            'amount': amount
                        }
                    }).done(function(result) {
                        // Tear down the Drop-In UI.
                        instance.teardown(function(teardownErr) {
                            if (teardownErr) {
                                console.error('Could not tear down Drop-in UI!');
                            } else {
                                console.info('Drop-in UI has been torn down!');
                                // Remove the 'Submit payment' button.
                                $('#submit-button').remove();
                            }
                        });

                        // TODO: The success and failure responses need user-friendly display.
                        // TODO: On success, we should trigger the Thunderbird download immediately.
                        if (result.success) {
                            $('#checkout-message').html('<h1>'+result.message+'</h1><p>Refresh to try again.</p>');
                        } else {
                            console.log(result);
                            $('#checkout-message').html('<h1>Error:'+result.message+'</h1><p>Check your console.</p>');
                        }
                    });
                });
            });
        });
    };

    Donation.InitForm = function(amount) {
        $.ajax({
            type: 'GET',
            url: braintree_URL + '/verify_client',
            success: function(result) {
                if (result.success) {
                    Donation.BuildForm(result.client_token, amount)
                }
            }
        });
    };

    Donation.DisplayAmountForm = function() {
        // 
        const DURATION = 250;
        
        // Show the donation form.
        $('#amount-modal').fadeIn(DURATION);
        $('#modal-overlay').fadeIn(DURATION);

        // Define close button on the donation form.
        $('#amount-cancel').click(function(e) {
            e.preventDefault();
            $('#amount-modal').fadeOut(DURATION);
            $('#modal-overlay').fadeOut(DURATION);
            // TODO: Start Thunderbird download if they close the donation form.
        });
        $('#close-modal').click(function(e) {
            e.preventDefault();
            $('#amount-modal').fadeOut(DURATION);
            $('#modal-overlay').fadeOut(DURATION);
        });

        // Define submit button on the donation form.
        $('#amount-submit').click(function(e) {
            e.preventDefault();
            $('#amount-modal').fadeOut(DURATION);
            $('#checkout-modal').fadeIn(DURATION);
            // TODO: This needs to check the textbox for the "other" value as well.
            // TODO: The checkout page should display the chosen amount for user confirmation.
            // TODO: Hookup the currency switcher as well.
            let amount = $("input[name='amount']:checked").val();
            Donation.InitForm(amount)
        });
    };

    window.Mozilla.Donation = Donation;

})();
