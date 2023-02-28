// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    /**
     * Super simple ABTest module, it puts you in one of the buckets.
     * Bucket === 0 - A
     * Bucket === 1 - B
     */
    const ABTest = {};
    ABTest.bucket = null;

    ABTest.RandomInt = function(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * Pick a random int between 0 - 1.
     * Once a bucket has been chosen, this function does nothing.
     */
    ABTest.Choose = function() {
        /*
        if (ABTest.bucket !== null) {
            return;
        }

        ABTest.bucket = ABTest.RandomInt(0, 1);
        */
    }

    /**
     * Tracks our bucket choice.
     * Called from matomo.js, registers a bucket if no bucket has been chosen.
     */
    ABTest.Track = function() {
        /*
        if (ABTest.bucket === null) {
            ABTest.Choose();
        }

        // Initialize the command queue if it's somehow not.
        const _paq = window._paq = window._paq || [];

        // TrackEvent: Category, Action, Name
        _paq.push(['trackEvent', 'AB-Test - Test Name Here', 'Bucket Registration', ABTest.bucket === 0 ? 'a' : 'b']);
        */
    }

    /**
     * Are we in the FundraiseUp bucket?
     * @returns {boolean}
     */
    ABTest.IsInBucketA = function() {
        return ABTest.bucket === 0;
    }

    /**
     * Are we in the legacy give.thunderbird.net bucket?
     * @returns {boolean}
     */
    ABTest.IsInBucketB = function() {
        return ABTest.bucket === 1;
    }

    /**
     * Replaces a 'HTMLAnchorElement' href tag with the bucket's (only FRU right now) equivalent url.
     * @param element : HTMLAnchorElement
     */
    ABTest.ReplaceDonateLinks = function(element) {
        /*
        if (ABTest.IsInBucketA()) {
            // If we somehow don't have an element, we can exit and still start any redirects.
            if (!element) {
                return;
            }

            // Falsey fallback check to transform '' => null
            const utmContent = element.getAttribute('data-donate-content') || null;
            const utmSource = element.getAttribute('data-donate-source') || 'thunderbird.net';
            const utmMedium = element.getAttribute('data-donate-medium') || 'fru';
            const utmCampaign = element.getAttribute('data-donate-campaign') || 'donation_flow_2023';
            const redirect = element.getAttribute('data-donate-redirect') || null;

            element.href = window.Mozilla.Donation.MakeDonateUrl(utmContent, utmSource, utmMedium, utmCampaign, redirect);
        }
        */
    }

    /**
     * Any required initializations for our ABTest should go here
     * Called after ABTest is added to the Mozilla namespace.
     */
    ABTest.Init = function() {
        // Pick one!
        ABTest.Choose();
    }

    window.Mozilla.ABTest = ABTest;

    ABTest.Init();
})();