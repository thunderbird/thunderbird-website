// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    /**
     * Super simple ABTest module, it puts you in one of the buckets.
     * Bucket === 0 - FundraiseUp
     * Bucket === 1 - give.thunderbird.net
     */
    const ABTest = {};
    ABTest.bucket = 0;

    ABTest.RandomInt = function(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * Pick a random int between 0 - 1.
     */
    ABTest.Choose = function() {
        ABTest.bucket = ABTest.RandomInt(0, 1);
    }

    /**
     * Are we in the FundraiseUp bucket?
     * @returns {boolean}
     */
    ABTest.IsInFundraiseUpBucket = function() {
        return ABTest.bucket === 0;
    }

    /**
     * Are we in the legacy give.thunderbird.net bucket?
     * @returns {boolean}
     */
    ABTest.IsInGiveBucket = function() {
        return ABTest.bucket === 1;
    }

    /**
     * FundraiseUp's download functionality. This will simply raise the Donation form.
     * @param download_url
     * @private
     */
    ABTest._FundraiseUpDownload = function(download_url) {
        window.Mozilla.Donation.DisplayDownloadForm(download_url);
    }

    /**
     * Legacy give.thunderbird.net download functionality.
     * This will redirect them to the donation url, which will start the download.
     * @param download_url
     * @param donate_url
     * @private
     */
    ABTest._GiveDownload = function(download_url, donate_url) {
        // Don't redirect if we're on the failed download page.
        if ($("body").attr('id') !== 'thunderbird-download') {
            // MSIE and Edge cancel the download prompt on redirect, so just leave them out.
            if (!(/msie\s|trident\/|edge\//i.test(navigator.userAgent))) {
                setTimeout(function() {
                    window.location.href = donate_url;
                }, 5000);
            }
        }
        window.Mozilla.Utils.triggerIEDownload(download_url);
    }

    /**
     * Start the Download, it will handle determining what bucket we're in and what download path we need to go down.
     * @param event : Event
     */
    ABTest.Download = function(event) {
        const element = event.target;
        const download_url = element.href;
        const donate_url = element.dataset.donateLink || null;

        if (ABTest.IsInFundraiseUpBucket()) {
            event.preventDefault();
            ABTest._FundraiseUpDownload(download_url);
        } else {
            ABTest._GiveDownload(download_url, donate_url);
        }
    }

    /**
     * Replaces a 'HTMLAnchorElement' href tag with the bucket's (only FRU right now) equivalent url.
     * @param element : HTMLAnchorElement
     */
    ABTest.ReplaceDonateLinks = function(element) {
        if (ABTest.IsInFundraiseUpBucket()) {
            // If we somehow don't have an element, we can exit and still start any redirects.
            if (!element) {
                return;
            }

            // Falsey fallback check to transform '' => null
            const utmContent = element.getAttribute('data-donate-content') || null;
            const utmSource = element.getAttribute('data-donate-source') || 'thunderbird.net';
            const utmMedium = element.getAttribute('data-donate-medium') || 'fru';
            const utmCampaign = element.getAttribute('data-donate-campaign') || 'donation_flow_2023';

            element.href = window.Mozilla.Donation.MakeDonateUrl(utmContent, utmSource, utmMedium, utmCampaign);
        }
    }

    /**
     * Any required initializations for our ABTest should go here
     * Called after ABTest is added to the Mozilla namespace.
     */
    ABTest.Init = function() {
        // Pick one!
        ABTest.Choose();

        // Replace the donation button's links with the correct one.
        const donate_buttons = document.querySelectorAll('[data-donate-btn]');
        for (const donate_button of donate_buttons) {
            ABTest.ReplaceDonateLinks(donate_button);
        }
        // Replace the download and donate button's link with the correct one.
        const download_and_donate_button = document.getElementById('amount-submit');
        ABTest.ReplaceDonateLinks(download_and_donate_button);
    }

    window.Mozilla.ABTest = ABTest;

    ABTest.Init();
})();