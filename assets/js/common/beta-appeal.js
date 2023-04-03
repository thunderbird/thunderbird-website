// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    const BetaAppeal = {};

    /**
     *
     * @param {MouseEvent} evt
     * @constructor
     */
    BetaAppeal.Join = function (evt) {
        if (evt.currentTarget.dataset.joined) {
            return;
        }

        const joinBtn = evt.currentTarget;

        // Don't run this again
        joinBtn.setAttribute('data-joined', true);
    }

    /**
     * Initializes the event listener for the beta appeal button
     */
    BetaAppeal.Init = function() {
        if (document.getElementById('thunderbird-beta-appeal')) {
            const joinBtn = document.getElementById('tb-join-beta-btn');
            joinBtn.addEventListener('click', BetaAppeal.Join);
        }
    }

    window.Mozilla.BetaAppeal = BetaAppeal;

    BetaAppeal.Init();
})();