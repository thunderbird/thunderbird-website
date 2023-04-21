// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    const BetaAppeal = {};

    /**
     * Hides the appeal, shows the thank you.
     * @param {MouseEvent} evt
     * @constructor
     */
    BetaAppeal.Upgrade = function(evt) {
        document.getElementById('ba-step-1').classList.add('hidden');
        document.getElementById('ba-step-2').classList.remove('hidden');

        // Track this upgrade
        // Initialize the command queue if it's somehow not.
        const _paq = window._paq = window._paq || [];
        // TrackEvent: Category, Action
        _paq.push(['trackEvent', 'Beta Appeal', 'Upgrade']);
    }

    /**
     * Returns information to formulate the download link
     * @returns {{os: (string), channel: string, locale: string, version: string}}
     */
    BetaAppeal.GetDownloadInfo = function() {
        const url = new URL(window.location.href);

        const archMap = {
            'darwin': 'osx',
            'linux-32': 'linux',
            'linux-64': 'linux64',
            'winnt-32': 'win',
            'winnt-64': 'win64'
        }

        const archSize = window.site.archSize;
        const osParam = url.searchParams.get('os').toLowerCase();
        let archKey = osParam;

        // Don't add archSize to Mac (since it reports Mac as 32)
        if (osParam !== 'darwin') {
            archKey = `${osParam}-${archSize}`;
        }

        return {
            os: archMap[archKey] ?? null,
            locale: url.searchParams.get('locale') ?? window.siteLocale,
            channel: url.searchParams.get('channel'),
            version: url.searchParams.get('version'),
        }
    }

    /**
     * Initializes the event listener for the beta appeal button
     */
    BetaAppeal.Init = function() {
        if (document.getElementById('thunderbird-beta-appeal')) {
            const downloadInfo = BetaAppeal.GetDownloadInfo();
            const upgradeBtn = document.getElementById('tb-join-beta-btn');

            // Only replace the download link with our new direct one if they have a detectable operating system
            if (downloadInfo.os) {
                upgradeBtn.addEventListener('click', BetaAppeal.Upgrade);
                // Add our new download link to the anchor, and a tracking class
                upgradeBtn.href = `https://download.mozilla.org/?product=thunderbird-${window.latestBuild}-SSL&os=${downloadInfo.os}&lang=${downloadInfo.locale}`;
                upgradeBtn.classList.add('matomo-track-download');
            }
        }
    }

    window.Mozilla.BetaAppeal = BetaAppeal;

    BetaAppeal.Init();
})();