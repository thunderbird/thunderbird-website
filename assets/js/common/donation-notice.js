/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * Donation Blocker Detector
 */
// The widget id on the donate page, should be the same as the 'href' value (minus the hash.)
const FRU_FORM_WIDGET = 'XVFNMBAK';
const FRU_TIMEOUT_IN_MS = 7_500;

let donationCountdownHandle = null;
let donationCheckoutSuccess = false;

/**
 * Display the dialog element #donation-blocked-notice only if the element exists, and a FRU element hasn't been detected.
 */
const showDonationNotice = () => {
  const notice = document.getElementById('donation-blocked-notice');
  const donatePageEmbeddedWidget = document.getElementById(FRU_FORM_WIDGET);
  const isFRULoaded = donationCheckoutSuccess || donatePageEmbeddedWidget;

  // Clear our state variables now
  donationCountdownHandle = null;
  donationCheckoutSuccess = false;

  // Exit early if the notice doesn't exist, or FRU is loaded.
  if (!notice || isFRULoaded) {
    return;
  }

  notice.showModal();
};

/**
 * Simply checks if there isn't a countdown in progress before starting a new one.
 */
const startDonationNoticeCountdown = () => {
  if (donationCountdownHandle !== null) {
    return;
  }
  donationCountdownHandle = window.setTimeout(() => showDonationNotice(), FRU_TIMEOUT_IN_MS);
};

document.addEventListener('DOMContentLoaded', () => {
  // Don't set anything up if notice doesn't exist
  const notice = document.getElementById('donation-blocked-notice');
  if (!notice) {
    return;
  }

  // Hook up notice's close button
  const noticeCloseButton = document.querySelector('#donation-blocked-notice .close-btn');
  if (noticeCloseButton) {
    noticeCloseButton.addEventListener('click', () => {
      notice.close()
    });
  }

  // Conditions for the countdown
  const donationButtons = document.querySelectorAll('[data-donate-btn]');
  for (const donationButton of donationButtons) {
    // Any donation button that redirects should be skipped as that's not where the modal will show up.
    // Ref: [data-dont-show-donation-blocked-notice]
    if ('dontShowDonationBlockedNotice' in donationButton.dataset) {
      continue;
    }
    donationButton.addEventListener('click', () => {
      startDonationNoticeCountdown();
    });
  }

  // If they've clicked on a donation button (adds ?form=<form_id> to searchparams) or if they're on the donations page.
  if (window.location.search.includes('form=') || document.getElementsByClassName('page-donations').length > 0) {
    startDonationNoticeCountdown();
  }

  // Finally setup a event handler for FRU checkoutOpen
  // This will only trigger once the checkout is fully loaded,
  // which can cause some issues with slower internet speeds.
  window.FundraiseUp.on('checkoutOpen', function() {
    // If we opened after the countdown fires then close the notice.
    if (notice.open) {
      notice.close();
    }

    donationCheckoutSuccess = true;
  });
});