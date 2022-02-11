// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    var braintree_URL = 'https://chaos.thunderbird.net'

    Donation.BuildForm = function(client_token) {
        var button = document.querySelector('#submit-button');
        braintree.dropin.create({
            // Insert your tokenization key here
            authorization: client_token,
            container: '#dropin-container'
        }, function(createErr, instance) {
            $('#submit-button').show();
            button.addEventListener('click', function() {
                instance.requestPaymentMethod(function(requestPaymentMethodErr, payload) {
                    // When the user clicks on the 'Submit payment' button this code will send the
                    // encrypted payment information in a variable called a payment method nonce
                    $.ajax({
                        type: 'POST',
                        url: braintree_URL +'/checkout',
                        data: {
                            'payment_method_nonce': payload.nonce,
                            'amount': 10
                        }
                    }).done(function(result) {
                        // Tear down the Drop-in UI
                        instance.teardown(function(teardownErr) {
                            if (teardownErr) {
                                console.error('Could not tear down Drop-in UI!');
                            } else {
                                console.info('Drop-in UI has been torn down!');
                                // Remove the 'Submit payment' button
                                $('#submit-button').remove();
                            }
                        });

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

    Donation.InitForm = function() {
        $.ajax({
            type: 'GET',
            url: braintree_URL + '/verify_client',
            success: function(result) {
                if (result.success) {
                    console.log(result)
                    Donation.BuildForm(result.client_token)
                }
            }
        });
    };

    window.Mozilla.Donation = Donation;

})();
