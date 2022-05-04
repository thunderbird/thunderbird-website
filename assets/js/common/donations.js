// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    var braintree_URL = 'https://chaos.thunderbird.net'

    Donation.BuildPaymentForm = function(client_token, amount, download_link) {
        // show selected donation amount
        $('#amount-preview').text(amount);
        // load braintree content
        var button = document.querySelector('#checkout-submit');
        braintree.dropin.create({
            authorization: client_token,
            container: '#dropin-container'
        }, function(createErr, instance) {
            $('#amount-container').hide();
            $('#checkout-container').show();
            $('#checkout-submit').show();
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
                                $('#checkout-submit').remove();
                            }
                        });

                        // TODO: The success and failure responses need user-friendly display.
                        // TODO: On success, we should trigger the Thunderbird download immediately.
                        if (result.success) {
                            $('#checkout-message').html('<h1>'+result.message+'</h1><p>Refresh to try again.</p>');
                            // Start Thunderbird download.
                            window.Mozilla.Utils.doRedirect(download_link);
                        } else {
                            console.log(result);
                            $('#checkout-message').html('<h1>Error:'+result.message+'</h1><p>Check your console.</p>');
                        }
                    });
                });
            });
        });
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
        // form configuration
        const DURATION = 250;
        
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
            // TODO: Hookup the currency switcher as well.
            let amount = $("input[name='amount']:checked").val();
            Donation.InitPaymentForm(amount, download_link)
        });

        // Define go back button to the donation amount selection.
        $('#checkout-back').click(function(e) {
            e.preventDefault();
            $('#checkout-container').hide();
            $('#amount-container').show();
        });
    };

    window.Mozilla.Donation = Donation;

})();
