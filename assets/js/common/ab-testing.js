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
        console.log("Bucket: ", ABTest.bucket);
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

    // Pick one!
    ABTest.Choose();

    window.ABTest = ABTest;
})();