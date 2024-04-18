// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Donation = {};
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
     * Stateful copy of the location.href value on page load. Used to fix tracking url after donation checkout close
     * @type {string}
     */
    Donation.OriginalHref = '';

    /**
     * Setups our FRU javascript events
     */
    Donation.Init = function() {
        if (!window.FundraiseUp) {
            return;
        }

        const searchParams = new URLSearchParams(window.location.search);
        const utmSourceNewsletter = 'newsletter';
        const utmSource = searchParams.get('utm_source');

        // If a user clicks on a donate button, track the donate link click goal
        const donateButtons = document.querySelectorAll('[data-donate-btn]');
        donateButtons.forEach(function(element) {
            // Correct the utmSource
            if (utmSource === utmSourceNewsletter) {
                const href = new URL(element.href);
                // Adjust the utm source to newsletter
                href.searchParams.set('utm_source', utmSourceNewsletter);
                // Set the new href
                element.href = href.toString();
            }

            element.addEventListener('click', function() {
                window._paq = window._paq || [];
                window._paq.push(['trackGoal', 1]);
            });
        });

        // Ensure we actually have the javascript loaded, so we can hook up our events.
        const fundraiseUp = window.FundraiseUp;

        // Note: This won't play well this any location history adjustments!
        Donation.OriginalHref = location.href;

        /**
         * Event fires when the FRU checkout modal opens
         * @param details - See https://fundraiseup.com/docs/parameters/
         */
        fundraiseUp.on('checkoutOpen', function(details) {
            window._paq = window._paq || [];
            window._paq.push(['setCustomUrl', location.href]);
            window._paq.push(['trackEvent', 'Donation', 'Started']);

            // Reset any stateful variables
            Donation.NeedsNewsletterRedirect = false;

            // Retrieve the current download link before we close the form (as that clears it)
            const download_link = Donation.CurrentDownloadLink;

            // No download link? Exit.
            if (!download_link) {
                return;
            }

            // Send off the download event
            window._paq.push(['trackLink', download_link, 'download']);

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
                // Set the tracking url the original page load url
                window._paq.push(['setCustomUrl', Donation.OriginalHref]);
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
            if (!details) {
                return;
            }

            window._paq = window._paq || [];

            // TrackEvent: Category, Action, Name
            window._paq.push(['trackEvent', 'Donation', 'Completed']);
            window._paq.push(['trackGoal', 7]); // Donation Completed Goal

            if (details.supporter) {
                const hasSubscribedToNewsletter = details.supporter.mailingListSubscribed || false;

                if (hasSubscribedToNewsletter) {
                    const state = window.open(Donation.NEWSLETTER_URL, '_blank');

                    // If a browser doesn't want us to open a new tab (due to a pop-up blocker, or chrome's 'user must click once on a page before we allow redirect') then just redirect them.
                    Donation.NeedsNewsletterRedirect = state === null;
                }
            }
        });
    }

    /**
     * Display FRUs donation form - This is just for donations, not the download form.
     * @param utmContent {?string}
     * @param utmSource {?string}
     * @param utmMedium {?string}
     * @param utmCampaign {?string}
     * @param redirect {?string} - Whether we should redirect the user to another page
     * @deprecated Donation url code has been migrated to static build process. This is left here in case of further AB tests.
     */
    Donation.MakeDonateUrl = function(utmContent = null, utmSource = 'thunderbird.net', utmMedium = 'fru', utmCampaign = 'donation_2023', redirect = null) {
        /*
        const is_donate_redirect = redirect === 'donate';
        const is_download_redirect = redirect && redirect.indexOf('download-') !== -1;

        // en-US gets converted to en, so fix that if needed.
        const lang = document.documentElement.lang === 'en' ? 'en-US': document.documentElement.lang;

        let params = {
            // Don't open the form automatically if we're redirecting to donate
            'form': is_donate_redirect ? null : 'support',
            'utm_content': utmContent,
            'utm_source': utmSource,
            'utm_medium': utmMedium,
            'utm_campaign': utmCampaign,
            // Split off our download-(esr|beta|daily) query param
            'download_channel': is_download_redirect ? redirect.split('-')[1] : null,
        };

        // Filter nulls from the object (this mutates)
        Object.keys(params).forEach((k) => params[k] == null && delete params[k]);

        params = new URLSearchParams(params);

        const query_params = `?${params.toString()}`;

        if (is_donate_redirect) {
            // We don't have a good way to get the current environment in javascript right now..
            return `https://www.thunderbird.net/${lang}/donate/${query_params}#donate`;
        } else if (is_download_redirect) {
            return `/${lang}/download/${query_params}`;
        }

        return query_params;
        */
    }

    window.Mozilla.Donation = Donation;
    Donation.Init();
})();
