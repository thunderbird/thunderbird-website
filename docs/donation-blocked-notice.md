# Donation Blocked Notice

Controlled by: `settings.SHOW_DONATION_BLOCKED_NOTICE`.

This feature checks to see if the user is on the Donate page, or if they've clicked on a donate button (determined by
`[data-donate-btn]` attribute except for inclusion of `[data-dont-show-donation-blocked-notice]`.) If this check fails a
medium-sized banner will appear the bottom of the screen notifying the user that they have an extension or browser that 
is blocking Fundraise Up. 

This check is done in `assets/js/common/donation-notice.js`, and simply sees if the user is on the Donate page and for 
the existence of the embed donation form widget, or more commonly if they've clicked on a donation button and we don't 
receive a Fundraise Up `checkoutOpen` event within 7.5 seconds.

Important to note that if someone's internet is so slow that the checkout modal doesn't load and send that 
`checkoutOpen` event within the 7.5 seconds the notice will still show up. However, it will auto-close once we receive 
that event.
