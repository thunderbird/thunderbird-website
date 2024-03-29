/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Create namespace
if (typeof Mozilla === 'undefined') {
    var Mozilla = {};
}

(function() {
    'use strict';

    var Utils = {};
    var bouncerURL = 'download.mozilla.org'

    /**
     * Bug 393263 A special function for IE < 9.
     * Without this hack there is no prompt to download after they click. sigh.
     * @param {link} direct link to download URL
     * @param {userAgent} optional UA string for testing purposes.
     */

    Utils.triggerIEDownload = function(link, userAgent) {
        'use strict';
        var ua = userAgent !== undefined ? userAgent : navigator.userAgent;
        // Only open if we got a link and this is IE < 9.
        if (link && window.site.platform === 'windows' && /MSIE\s[1-8]\./.test(ua)) {
            window.open(link, 'download_window', 'toolbar=0,location=no,directories=0,status=0,scrollbars=0,resizeable=0,width=1,height=1,top=0,left=0');
            window.focus();
        }
    };

    // Add target="_blank" to all external links so they open in a new tab by default.
    Utils.externalLinks = function() {
        for (var c = document.getElementsByTagName("a"), a = 0; a < c.length; a++) {
            var b = c[a];
            b.getAttribute("href") && b.hostname !== location.hostname && b.hostname !== bouncerURL && (b.target = "_blank")
        }
    };

    /**
     * Redirects the user to a donation url. This should be triggered after a download.
     * @param {HTMLAnchorElement} element
     */
    Utils.redirectAfterDownload = function(element) {
        const download_url = element.href;
        const donate_url = element.getAttribute('data-donate-link') || null;

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

    // attach an event to all the download buttons to trigger the special
    // ie functionality if on ie
    Utils.initDownloadLinks = function() {
        $('#submit-button').hide();
        $('.download-link').each(function() {
            var $el = $(this);
            $el.click(function(e) {
                Utils.redirectAfterDownload(e.currentTarget);
            });
        });
        $('.download-list').attr('role', 'presentation');
    };

    // Replace Google Play and Apple App Store links on Android and iOS devices to
    // let them open the native marketplace app
    Utils.initMobileDownloadLinks = function() {
        if (site.platform === 'android') {
            $('a[href^="https://play.google.com/store/apps/"]').each(function() {
                $(this).attr('href', $(this).attr('href')
                    .replace('https://play.google.com/store/apps/', 'market://'));
            });
        }

        if (site.platform === 'ios') {
            $('a[href^="https://itunes.apple.com/"]').each(function() {
                $(this).attr('href', $(this).attr('href')
                    .replace('https://', 'itms-apps://'));
            });
        }
    };

    // Bug 1264843: link to China build of Fx4A, for display within Fx China repack
    Utils.maybeSwitchToDistDownloadLinks = function(client) {
        if (!client.distribution || client.distribution === 'default') {
            return;
        }

        var distribution = client.distribution.toLowerCase();
        $('a[data-' + distribution + '-link]').each(function() {
            $(this).attr('href', $(this).data(distribution + 'Link'));
        });
    };

    Utils.switchPathLanguage = function(location, newLang) {
        // get path without locale
        var urlpath = location.pathname.slice(1).split('/').slice(1).join('/');
        return '/' + newLang + '/' + urlpath + location.search;
    };

    // language switcher
    Utils.initLangSwitcher = function() {
        var $language = $('#page-language-select');
        var previousLanguage = $language.val();
        $language.on('change', function() {
            var newLanguage = $language.val();
            window.dataLayer.push({
                'event': 'change-language',
                'languageSelected': $language.val(),
                'languageSelected': newLanguage,
                'previousLanguage': previousLanguage
            });
            $('#lang_form').attr('action', window.location.hash || '#').submit();
            Utils.doRedirect(Utils.switchPathLanguage(window.location, newLanguage));
        });
    };

    // client-side redirects (handy for testing)
    Utils.doRedirect = function(destination) {
        if (destination) {
            window.location.href = destination;
        }
    };

    // Create text translation function using #strings element.
    // TODO: Move to docs
    // In order to use it, you need a block string_data bit inside your template,
    // then, each key name needs to be preceeded by data- as this uses data attributes
    // to work. After this, you can access all strings defined inside the
    // string_data block in JS using Mozilla.Utils.trans('keyofstring'); Thank @mkelly
    var _$strings = $('#strings');
    Utils.trans = function(stringId) {
        return _$strings.data(stringId);
    };

    window.Mozilla.Utils = Utils;

})();
