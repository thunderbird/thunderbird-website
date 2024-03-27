/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */


// Create namespace
if (typeof Mozilla === 'undefined') {
  var Mozilla = {};
}

(function() {
  'use strict';

  const DownloadInfo = {};

  const isDownloadPage = document.getElementsByClassName('page-download').length > 0;
  const localeSelect = document.getElementById('download-language-select');
  const channelSelect = document.getElementById('download-browser-select');
  const platformSelect = document.getElementById('download-platform-select');
  const installerSelect = document.getElementById('download-advanced-platform-select');
  const downloadButton = document.getElementById('download-btn');

  /**
   * Hooks up onChange event handlers, and sets the installer dropdown options / download link
   */
  DownloadInfo.Init = function() {
    if (!isDownloadPage) {
      return;
    }

    platformSelect.addEventListener('change', function(event) {
      DownloadInfo.OnPlatformSelection(event.currentTarget.value);
    });
    [localeSelect, channelSelect, platformSelect, installerSelect].forEach(function(element) {
      element.addEventListener('change', function(event) {
        DownloadInfo.SetDownloadLink();
      });
    });

    // Setup download link
    DownloadInfo.OnPlatformSelection(platformSelect.value);
    DownloadInfo.SetDownloadLink();
  }

  /**
   * Hides the non-relevant installer options, and selects the first one that's relevant.
   * @param platform {string}
   */
  DownloadInfo.OnPlatformSelection = function(platform) {
    document.querySelectorAll(`[data-for-os]`).forEach((element) => {
      element.classList.add('hidden');
      element.removeAttribute('selected');
    });
    document.querySelectorAll(`[data-for-os=${platform}]`).forEach((os) => os.classList.remove('hidden'));
    const firstItem = document.querySelector(`[data-for-os=${platform}]`);
    firstItem.setAttribute('selected', 'true')
  }

  /**
   * Actually set the download link from the current options
   * @constructor
   */
  DownloadInfo.SetDownloadLink = function() {
    downloadButton.href = DownloadInfo.DownloadLink(localeSelect.value, channelSelect.value, platformSelect.value, installerSelect.value);
  }

  /**
   * Generate the download link from the given parameters
   * @param locale {string} - Locale code (e.g. 'fr' or 'en-CA')
   * @param channel {string} - Channel code for the build (e.g. 'release' or 'beta')
   * @param platform {string} - OS Platform for the build. Only used for android.
   * @param installer {string} - Platform code for the build (e.g. 'win64' or 'linux64')
   * @returns {string} - Formulated download link or redirect link depending on the platform vs options
   */
  DownloadInfo.DownloadLink = function(locale, channel, platform, installer) {
    if (platform === 'android') {
      return 'https://play.google.com/store/apps/details?id=com.fsck.k9';
    }

    const channelVersion = channel === 'release' ? `latest` : `${channel}-latest`;
    return `https://download.mozilla.org/?product=thunderbird-${channelVersion}-SSL&os=${installer}&lang=${locale}`
  }

  window.Mozilla.DownloadInfo = DownloadInfo;

  document.addEventListener('DOMContentLoaded', function() {
    DownloadInfo.Init();
  });
})();