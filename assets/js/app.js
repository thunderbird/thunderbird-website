/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */


document.addEventListener('DOMContentLoaded', function () {
  const hamburgerBtn = document.getElementById('mobile-hamburger-button');

  /**
   * HamburgerBtn On Click
   * Toggle the navigation when the hamburger button is clicked. This also affects the aria attributes.
   */
  hamburgerBtn.addEventListener('click', function(evt) {
    evt.preventDefault();

    const navMenu = document.getElementById('nav-menu');
    const isExpanded = hamburgerBtn.dataset['expanded'] === 'true';

    console.log(navMenu, isExpanded);

    if (!isExpanded) {
      navMenu.classList.add('expanded');
    } else {
      navMenu.classList.remove('expanded');
    }

    // Flip the data attr.
    hamburgerBtn.dataset['expanded'] = isExpanded ? 'false' : 'true';
    hamburgerBtn.ariaExpanded = hamburgerBtn.dataset['expanded'];
  });
});