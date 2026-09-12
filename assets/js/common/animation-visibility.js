/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * Toggles a `tab-inactive` class on the <html> element whenever the tab is
 * hidden (Page Visibility API) or the window loses focus (e.g. the user
 * switched to another application). CSS can key off this class to pause
 * decorative animations (e.g. `animation-play-state: paused`) and avoid
 * burning CPU/battery while the page isn't actually being looked at.
 */
(() => {
  const root = document.documentElement;

  const updateAnimationVisibility = () => {
    const isInactive = document.hidden || !document.hasFocus();
    root.classList.toggle('tab-inactive', isInactive);
  };

  document.addEventListener('visibilitychange', updateAnimationVisibility);
  window.addEventListener('blur', updateAnimationVisibility);
  window.addEventListener('focus', updateAnimationVisibility);

  updateAnimationVisibility();
})();
