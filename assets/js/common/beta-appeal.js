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
        document.getElementById('ba-step-1').classList.add('hidden');
        document.getElementById('ba-step-2').classList.remove('hidden');
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