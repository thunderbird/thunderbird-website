// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
    Donation.ANIMATION_DURATION = 250;
    Donation.WINDOW_POS_KEY = '_tb_donation_position';
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
     * Setups our FRU javascript events
     */
    Donation.Init = function() {
        if (!window.FundraiseUp) {
            console.error("Could not find FundraiseUp");
            return;
        }

        // Ensure we actually have the javascript loaded, so we can hook up our events.
        const fundraiseUp = window.FundraiseUp;

        // An initial check for our donate buttons
        Donation.CheckForPosition();

        /**
         * @param details - See https://fundraiseup.com/docs/parameters/
         */
        fundraiseUp.on('checkoutOpen', function(details) {
            // Don't start the download if we didn't come from the donation download modal
            // The absence of Download & Donate element button should handle this
            if (!details.element || !details.element.id) {
                return;
            }

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

    }

    /**
     * Returns the stored position if available, otherwise returns null.
     * @returns {number|null}
     */
    Donation.GetScrollPosition = function() {
        const pos = window.sessionStorage.getItem(Donation.WINDOW_POS_KEY);

        if (pos) {
            return parseFloat(pos);
        }
        return null;
    }

    /**
     * Set our current position, so we can fix it on page reload.
     * @see Donation.CheckForPosition
     */
    Donation.SetScrollPosition = function() {
        window.sessionStorage.setItem(Donation.WINDOW_POS_KEY, window.scrollY.toString());
    }

    /**
     * Removes our current position.
     */
    Donation.RemoveScrollPosition = function() {
        window.sessionStorage.removeItem(Donation.WINDOW_POS_KEY);
    }

    /**
     * Display FRUs donation form - This is just for donations, not the download form.
     * @param utmContent {?string}
     * @param utmSource {?string}
     * @param utmMedium {?string}
     * @param utmCampaign {?string}
     */
    Donation.Donate = function(utmContent = null, utmSource = 'thunderbird.net', utmMedium = 'fru', utmCampaign = 'donation_flow_2023') {
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

        Donation.SetScrollPosition();

        // Display the FRU form
        location.href = `?${params.toString()}`;
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
        Donation.RemoveScrollPosition();
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

        Donation.SetScrollPosition();
    };

    /**
     * Checks and applies any position parameter to the window's scrollY
     * This makes the silly page refresh on the donation modal look less jarring
     */
    Donation.CheckForPosition = function() {
        const pos = Donation.GetScrollPosition();
        if (pos) {
            window.scrollTo(0, pos);
            window.sessionStorage.removeItem(Donation.WINDOW_POS_KEY)
        }
    }

    window.Mozilla.Donation = Donation;
    Donation.Init();
})();
