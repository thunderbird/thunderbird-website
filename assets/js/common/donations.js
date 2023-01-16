// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    Donation.ANIMATION_DURATION = 250;
    Donation.IsVisible = false;

    /**
     * Close the donation form
     */
    Donation.CloseForm = function() {
        $('#amount-modal').fadeOut(Donation.ANIMATION_DURATION);
        $('#modal-overlay').fadeOut(Donation.ANIMATION_DURATION);
        $(document.body).removeClass('overflow-hidden');
        Donation.IsVisible = false;
    }

    /**
     * Display the donation download modal for fundraise up
     * @param download_url - Link to the actual file download
     */
    Donation.DisplayDownloadForm = function(download_url) {
        // Show the donation form.
        $('#amount-modal').fadeIn(Donation.ANIMATION_DURATION);
        $('#modal-overlay').fadeIn(Donation.ANIMATION_DURATION);
        $(document.body).addClass('overflow-hidden');
        Donation.IsVisible = true;

        // Define cancel and close button on the donation form.
        $('#amount-cancel').click(function(e) {
            e.preventDefault();
            Donation.CloseForm();
            location.href = download_url;
        });
        $('#close-modal').click(function(e) {
            e.preventDefault();
            Donation.CloseForm();
        });

        // Close modal when clicking the overlay
        $('#modal-overlay').click(function(e) {
            e.preventDefault();
            Donation.CloseForm();
        });

        // Close modal when pressing escaoe
        $(document).keyup(function(e) {
            if (e.key === "Escape") {
                Donation.CloseForm();
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

        // Ensure we actually have the javascript loaded, so we can hook up our events.
        if (window.FundraiseUp) {
            const fundraiseUp = window.FundraiseUp;
            // Close our modal on open
            fundraiseUp.on('checkoutOpen', function() {
                // Don't start the download if we didn't come from the donation download modal
                if (!Donation.IsVisible) {
                    return;
                }

                Donation.CloseForm();

                // Timeout is here to prevent url collisions with fundraiseup form.
                window.setTimeout(function() {
                    location.href = download_url;
                },1000);
            });
        }
    };

    window.Mozilla.Donation = Donation;

})();
