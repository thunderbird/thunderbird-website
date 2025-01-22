/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */


/**
 * This script contains various other scripts that should be organized in the future...
 */

/**
 * Handle nav expandables / hamburgers
 */
document.addEventListener('DOMContentLoaded', function() {
  const hamburgerBtn = document.getElementById('mobile-hamburger-button');
  const navExpandables = document.getElementsByClassName("nav-expandable");

  if (!hamburgerBtn || !navExpandables) {
    return;
  }

  /**
   * HamburgerBtn On Click
   * Toggle the navigation when the hamburger button is clicked. This also affects the aria attributes.
   */
  hamburgerBtn.addEventListener('click', function(evt) {
    evt.preventDefault();

    const navMenu = document.getElementById('nav-menu');
    const isExpanded = hamburgerBtn.ariaExpanded === 'true';

    if (!isExpanded) {
      navMenu.classList.add('expanded');
    } else {
      navMenu.classList.remove('expanded');
    }

    // Flip the aria attr.
    hamburgerBtn.ariaExpanded = isExpanded ? 'false' : 'true';

  });

  /**
   * For each nav-expandable's button child: adjust the ariaExpanded attribute depending on hover/focus state
   */
  for (const item of navExpandables) {
    item.addEventListener('focusin', function(evt) {
      evt.target.ariaExpanded = "true";
    });
    item.addEventListener('mouseenter', function(evt) {
      evt.target.ariaExpanded = "true";
    });
    item.addEventListener('focusout', function(evt) {
      evt.target.ariaExpanded = "false";
    });
    item.addEventListener('mouseleave', function(evt) {
      evt.target.ariaExpanded = "false";
    });
  }

});

/**
 * Handle autoplaying videos, including detecting if the user is requesting reduced motion (in which case we don't autoplay.)
 */
document.addEventListener('DOMContentLoaded', function() {
  const autoplayVideos = document.querySelectorAll('video[autoplay]');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  for (const item of autoplayVideos) {
    // Disable autoplay and pause playback if they would like reduced motion
    if (reduceMotion) {
      item.autoplay = false;
      item.pause();
    }

    const togglePlayback = (evt) => {
      const target = evt.target;
      const isPaused = target.paused;
      if (isPaused) {
        target.play();
      } else {
        target.pause();
      }
    }

    // Allow toggling playback with a click
    item.addEventListener('click', togglePlayback);
    item.addEventListener('keyup', (evt) => {
      if (evt.key === 'Enter') {
        togglePlayback(evt);
      }
    })
  }
});

/**
 * Handle download redirects
 */
document.addEventListener('DOMContentLoaded', function() {
  const downloadButtons = document.querySelectorAll('[data-donate-link]');

  for (const downloadButton of downloadButtons) {
    downloadButton.addEventListener('click', (evt) => {
      const element = evt.currentTarget;
      const donate_url = element.getAttribute('data-donate-link') || null;

      if (!donate_url) {
        return;
      }

      // TODO: Unsure if this check is still needed.
      // MSIE and Edge cancel the download prompt on redirect, so just leave them out.
      if (!(/msie\s|trident\/|edge\//i.test(navigator.userAgent))) {
          setTimeout(function() {
              window.location.href = donate_url;
          }, 5000);
      }

    });
  }
});