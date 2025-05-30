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
  let pageContainer = document.getElementById('select-download');
  let localeSelect = document.getElementById('download-language-select');
  let channelSelect = document.getElementById('download-release-select');
  let osSelect = document.getElementById('download-os-select');
  let installerSelect = document.getElementById('download-advanced-platform-select');
  let downloadButton = document.getElementById('download-btn');
  let defaultOS = 'Windows';
  let defaultReleaseChannel = window._desktop_product.defaultChannel ?? 'esr';

  // Platform map
  const platformMap = {
    'windows': 'Windows',
    'windows-7-8': 'Windows (7/8.1)',
    'linux64': 'Linux',
    'linux': 'Linux',
    'osx': 'macOS',
  };


  /**
   * Sets the page container's data attributes so it can be used for conditional css/other means
   * @param elementName {string}
   * @param elementValue {string}
   */
  DownloadInfo.SetDataAttributes = function(elementName, elementValue) {
    // Capitalize the name
    const name = elementName.charAt(0).toUpperCase() + elementName.slice(1);
    pageContainer.dataset[`desktop${name}`] = elementValue;
  }

  /**
   * Hooks up onChange event handlers, and sets the installer dropdown options / download link
   */
  DownloadInfo.Init = function() {
    // We only have to check for one of these dropdowns.
    if (!isDownloadPage || !channelSelect) {
      return;
    }

    // Check to see if we want to show a different release channel on load
    const regex = /\/download\/(release|esr|beta|daily)\/?$/gm;
    const url = new URL(location.href);
    const overrideReleasePath = regex.exec(url.pathname)

    // Check for ?release=<channel> or /download/<channel>
    let overrideRelease = url.searchParams.get('release');
    if (!overrideRelease && overrideReleasePath) {
      overrideRelease = overrideReleasePath[1];
    }

    if (['esr', 'release', 'beta', 'daily'].indexOf(overrideRelease) !== -1) {
      defaultReleaseChannel = overrideRelease;
      DownloadInfo.ToggleWarning(defaultReleaseChannel);
    }

    channelSelect.addEventListener('change', function(event) {
      DownloadInfo.ToggleWarning(event.currentTarget.value);
    });
    osSelect.addEventListener('change', function(event) {
      DownloadInfo.OnOSSelection(event.currentTarget.value);
    });
    [localeSelect, channelSelect, osSelect, installerSelect].forEach(function(element) {
      element.addEventListener('change', function(event) {
        DownloadInfo.SetDataAttributes(event.currentTarget.name, event.currentTarget.value);
        DownloadInfo.SetDownloadLink();
      });
    });


    // Set some defaults
    DownloadInfo.SetDefaults();
  }

  DownloadInfo.SetDefaults = function () {
    const platform = window.site.getPlatform();
    const version = window.site.getPlatformVersion();

    // Setup download link
    DownloadInfo.Update();

    // If they're on windows and within the NT 6.1 - NT 10.0 then force windows-7-8 to display
    if (platform === 'windows' && version >= 6.1 && version < 10.0) {
      defaultOS = platformMap['windows-7-8'] ?? defaultOS;
    } else {
      defaultOS = platformMap[platform] ?? defaultOS;
    }
    channelSelect.value = defaultReleaseChannel;

    // Channel Selection calls OS Selection
    DownloadInfo.OnOSSelection(defaultOS);
    DownloadInfo.SetDownloadLink();

    // Set the data attribute defaults
    [localeSelect, channelSelect, osSelect, installerSelect].forEach(function(element) {
      DownloadInfo.SetDataAttributes(element.name, element.value);
    });
  }

  /**
   * We could keep state here which can get tricky, or just rely on values.
   */
  DownloadInfo.Update = function() {
    localeSelect = document.getElementById('download-language-select');
    channelSelect = document.getElementById('download-release-select');
    osSelect = document.getElementById('download-os-select');
    installerSelect = document.getElementById('download-advanced-platform-select');
    downloadButton = document.getElementById('download-btn');
  };

  /**
   * Selects a specific entry from the OS Selection
   * @param os {string}
   */
  DownloadInfo.OnOSSelection = function(os) {
    osSelect.value = os;

    let firstInstaller = null;

    document.querySelectorAll('[data-for-os]').forEach(function (element) {
      if (element.dataset.forOs === os) {
        element.classList.remove('hidden');
        if (!firstInstaller) {
          firstInstaller = element.value;
        }
      } else {
        element.classList.add('hidden');
      }
    });

    if (firstInstaller) {
      installerSelect.value = firstInstaller;
      // Also have to update the data attributes
      DownloadInfo.SetDataAttributes(installerSelect.name, installerSelect.value);
    }

    // Hack: We need to hide beta and daily for Windows 7/8.1 builds, and force the release channel.
    if (os === platformMap['windows-7-8']) {
      document.querySelector('#download-release-select [value="beta"]').classList.add('hidden');
      document.querySelector('#download-release-select [value="daily"]').classList.add('hidden');
      document.querySelector('#download-release-select [value="release"]').classList.add('hidden');
      // Force esr build
      channelSelect.value = 'esr';
      DownloadInfo.SetDataAttributes(channelSelect.name, channelSelect.value);
    } else {
      document.querySelector('#download-release-select [value="beta"]').classList.remove('hidden');
      document.querySelector('#download-release-select [value="daily"]').classList.remove('hidden');
      document.querySelector('#download-release-select [value="release"]').classList.remove('hidden');
    }

    DownloadInfo.ToggleWarning(channelSelect.value);
  }

  /**
   * Hides/Shows daily warning
   * @param channel {string}
   */
  DownloadInfo.ToggleWarning = function(channel) {
    const dailyWarning = document.getElementById('daily-warning');
    const betaWarning = document.getElementById('beta-warning');
    const esrNotice = document.getElementById('esr-notice');
    const releaseNotice = document.getElementById('release-notice');

    dailyWarning.classList.add('hidden');
    betaWarning.classList.add('hidden');
    esrNotice.classList.add('hidden');
    releaseNotice.classList.add('hidden');

    let element = null;
    switch (channel) {
      case 'daily':
        element = dailyWarning;
        break;
      case 'beta':
        element = betaWarning;
        break;
      case 'esr':
        element = esrNotice;
        break;
      case 'release':
        element = releaseNotice;
        break;
      default:
        break;
    }

    if (element) {
      element.classList.remove('hidden');
    }
  }

  /**
   * Actually set the download link from the current options
   * @constructor
   */
  DownloadInfo.SetDownloadLink = function() {
    downloadButton.href = DownloadInfo.DownloadLink(localeSelect.value, channelSelect.value, osSelect.value, installerSelect.value);
  }

  /**
   * Generate the download link from the given parameters
   * @param locale {string} - Locale code (e.g. 'fr' or 'en-CA')
   * @param channel {string} - Channel code for the build (e.g. 'release' or 'beta')
   * @param os {string} - OS for the build.
   * @param installer {string} - Platform code for the build (e.g. 'win64' or 'linux64')
   * @returns {string} - Formulated download link or redirect link depending on the platform vs options
   */
  DownloadInfo.DownloadLink = function(locale, channel, os, installer) {
    let downloadLink = window._desktop_product.channels[channel]?.platforms[installer]?.url;
    if (!downloadLink) {
      console.warn(`[DownloadInfo.DownloadLink] Could not generate downloadLink for: locale=${locale}, channel=${channel}, os=${os}, installer=${installer}`);
      return '#';
    }

    // Only options that pass "has_localized_download" are allowed to be selected which makes this safe!
    // Note: The Japanese mac version is an exception here.
    if (locale === 'ja' && installer === 'osx') {
      downloadLink = downloadLink.replace('en-US', 'ja-JP-mac');
    } else if (locale !== 'en-US') {
      downloadLink = downloadLink.replace('en-US', locale);
    }

    return downloadLink;
  }

  window.Mozilla.DownloadInfo = DownloadInfo;

  document.addEventListener('DOMContentLoaded', function() {
    DownloadInfo.Init();
  });
})();