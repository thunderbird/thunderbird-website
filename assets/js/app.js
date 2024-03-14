/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */


document.addEventListener('DOMContentLoaded', function() {
  const hamburgerBtn = document.getElementById('mobile-hamburger-button');
  const navExpandables = document.getElementsByClassName("nav-expandable");

  /**
   * HamburgerBtn On Click
   * Toggle the navigation when the hamburger button is clicked. This also affects the aria attributes.
   */
  hamburgerBtn.addEventListener('click', function(evt) {
    evt.preventDefault();

    const navMenu = document.getElementById('nav-menu');
    const isExpanded = hamburgerBtn.ariaExpanded;

    if (!isExpanded) {
      navMenu.classList.add('expanded');
    } else {
      navMenu.classList.remove('expanded');
    }

    // Flip the data attr.
    hamburgerBtn.ariaExpanded = isExpanded ? 'false' : 'true';
  });

  /**
   * For each nav-expandable's button child: adjust the ariaExpanded attribute depending on hover/focus state
   */
  for (const item of navExpandables) {
    const children = item.children;
    const button = children[0];

    item.addEventListener('focusin', function(evt) {
      button.ariaExpanded = "true";
    });
    item.addEventListener('mouseenter', function(evt) {
      button.ariaExpanded = "true";
    });
    item.addEventListener('focusout', function(evt) {
      button.ariaExpanded = "false";
    });
    item.addEventListener('mouseleave', function(evt) {
      button.ariaExpanded = "false";
    });
  }

});