// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    Donation.ANIMATION_DURATION = 250;
    Donation.WINDOW_POS_KEY = '_tb_donation_position';
    Donation.NEWSLETTER_URL = `/${window.siteLocale}/newsletter`;
    /**
     * Is the download form visible?
     * @type {boolean}
     */
    Donation.IsVisible = false;
    /**
     * Stateful download link to be retrieved by the FRU on.checkoutOpen event
     * @type {?string}
     */
    Donation.CurrentDownloadLink = null;
    /**
     * Stateful check to determine if the supporter needs to be redirected after the FRU on.checkoutClose event
     * @type {boolean}
     */
    Donation.NeedsNewsletterRedirect = false;

    /**
     * Setups our FRU javascript events
     */
    Donation.Init = function() {
        if (!window.FundraiseUp) {
            console.error("Could not find FundraiseUp");
            return;
        }

        // Ensure we actually have the javascript loaded, so we can hook up our events.
        const fundraiseUp = window.FundraiseUp;

        /**
         * Event fires when the FRU checkout modal opens
         * @param details - See https://fundraiseup.com/docs/parameters/
         */
        fundraiseUp.on('checkoutOpen', function(details) {
            // Reset any stateful variables
            Donation.NeedsNewsletterRedirect = false;

            // Retrieve the current download link before we close the form (as that clears it)
            const download_link = Donation.CurrentDownloadLink;

            Donation.CloseForm();

            // No download link? Exit.
            if (!download_link) {
                return;
            }

            // Timeout is here to prevent url collisions with fundraiseup form.
            window.setTimeout(function() {
                window.open(download_link, '_self');
            }, 1000);
        });
        /**
         * Event fires when the FRU checkout is closed.
         * @param details - See https://fundraiseup.com/docs/parameters/
         */
        fundraiseUp.on('checkoutClose', function (details) {
            if (!Donation.NeedsNewsletterRedirect) {
                return;
            }

            // Redirect them to the newsletter landing page
            location.href = Donation.NEWSLETTER_URL;
        });
        /**
         * Event fires when the FRU conversion is completed successfully.
         * @param details - See https://fundraiseup.com/docs/parameters/
         */
        fundraiseUp.on('donationComplete', function(details) {
            if (!details || !details.supporter) {
                return;
            }

            const hasSubscribedToNewsletter = details.supporter.mailingListSubscribed || false;

            if (hasSubscribedToNewsletter) {
                const state = window.open(Donation.NEWSLETTER_URL, '_blank');

                // If a browser doesn't want us to open a new tab (due to a pop-up blocker, or chrome's 'user must click once on a page before we allow redirect') then just redirect them.
                Donation.NeedsNewsletterRedirect = state === null;
            }
        });
    }

    /**
     * Display FRUs donation form - This is just for donations, not the download form.
     * @param utmContent {?string}
     * @param utmSource {?string}
     * @param utmMedium {?string}
     * @param utmCampaign {?string}
     */
    Donation.MakeDonateUrl = function(utmContent = null, utmSource = 'thunderbird.net', utmMedium = 'fru', utmCampaign = 'donation_flow_2023') {
        let params = {
            'form': 'support',
            'utm_content': utmContent,
            'utm_source': utmSource,
            'utm_medium': utmMedium,
            'utm_campaign': utmCampaign
        };
        // Filter nulls from the object (this mutates)
        Object.keys(params).forEach((k) => params[k] == null && delete params[k]);

        params = new URLSearchParams(params);

        return `?${params.toString()}`;
    }

    /**
     * Close the donation form
     * This will clear any currently set download link.
     */
    Donation.CloseForm = function() {
        $('#amount-modal').fadeOut(Donation.ANIMATION_DURATION);
        $('#modal-overlay').fadeOut(Donation.ANIMATION_DURATION);
        $(document.body).removeClass('overflow-hidden');
        Donation.IsVisible = false;
        Donation.CurrentDownloadLink = null;
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
        Donation.CurrentDownloadLink = download_url;

        // Set the "No thanks, just download" button's link
        if ($("#amount-cancel")[0]) {
            $("#amount-cancel")[0].href = download_url;
        }

        // Define cancel and close button on the donation form.
        $('#amount-cancel').click(function(e) {
            // No prevent default
            Donation.CloseForm();
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
    };

    window.Mozilla.Donation = Donation;
    Donation.Init();
})();
