// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function () {
    'use strict';

    var Donation = {};
    var braintree_URL = 'https://chaos.thunderbird.net'
    Donation.ANIMATION_DURATION = 250;

    Donation.BuildForm = function (client_token, amount) {
        var button = document.querySelector('#submit-button');
        braintree.dropin.create({
            authorization: client_token,
            container: '#dropin-container'
        }, function (createErr, instance) {
            $('#submit-button').show();
            button.addEventListener('click', function () {
                instance.requestPaymentMethod(function (requestPaymentMethodErr, payload) {
                    $.ajax({
                        type: 'POST',
                        url: braintree_URL + '/checkout',
                        data: {
                            'payment_method_nonce': payload.nonce,
                            'amount': amount
                        }
                    }).done(function (result) {
                        // Tear down the Drop-In UI.
                        instance.teardown(function (teardownErr) {
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
                            $('#checkout-message').html('<h1>' + result.message + '</h1><p>Refresh to try again.</p>');
                        } else {
                            console.log(result);
                            $('#checkout-message').html('<h1>Error:' + result.message + '</h1><p>Check your console.</p>');
                        }
                    });
                });
            });
        });
    };

    Donation.InitForm = function (amount) {
        $.ajax({
            type: 'GET',
            url: braintree_URL + '/verify_client',
            success: function (result) {
                if (result.success) {
                    Donation.BuildForm(result.client_token, amount)
                }
            }
        });
    };

    Donation.CloseForm = function () {
        $('#amount-modal').fadeOut(Donation.ANIMATION_DURATION);
        $('#modal-overlay').fadeOut(Donation.ANIMATION_DURATION);
        $(document.body).removeClass('overflow-hidden');
    }

    /**
     * Display the donation modal for fundraise up
     * @param download_url - Link to the actual file download
     */
    Donation.DisplayAmountForm = function (download_url) {
        // Show the donation form.
        $('#amount-modal').fadeIn(Donation.ANIMATION_DURATION);
        $('#modal-overlay').fadeIn(Donation.ANIMATION_DURATION);
        $(document.body).addClass('overflow-hidden');

        // Define cancel and close button on the donation form.
        $('#amount-cancel').click(function (e) {
            e.preventDefault();
            Donation.CloseForm();
            location.href = download_url;
        });
        $('#close-modal').click(function (e) {
            e.preventDefault();
            Donation.CloseForm();
        });

        // Close modal when clicking the overlay
        $('#modal-overlay').click(function (e) {
            e.preventDefault();
            Donation.CloseForm();
        });

        // Close modal when pressing escaoe
        $(document).keyup(function (e) {
            if (e.key === "Escape") {
                Donation.CloseForm();
            }
        });

        // Define active amount in amount selection.
        $('#amount-selection > label').click(function () {
            $('#amount-selection > label.active').removeClass('active');
            $(this).addClass('active');
        });
        $('#amount-other-selection').click(function () {
            $('#amount-other').focus();
        });
        $('#amount-other').click(function () {
            $('#amount-other-selection').prop('checked', true);
        });
        $('#amount-other').on('input', function () {
            $('#amount-other-selection').val($(this).val());
        });

        // Ensure we actually have the javascript loaded, so we can hook up our events.
        if (window.FundraiseUp) {
            const fundraiseUp = window.FundraiseUp;
            // Close our modal on open
            fundraiseUp.on('checkoutOpen', function () {
                Donation.CloseForm();
            });
            // Start the download on completion
            fundraiseUp.on('donationComplete', function () {
                location.href = download_url;
            })
        }
    };

    window.Mozilla.Donation = Donation;

})();
