var _paq = window._paq = window._paq || [];
/* tracker methods like "setCustomDimension" should be called before "trackPageView" */
_paq.push(['trackPageView']);
_paq.push(['enableLinkTracking']);
(function() {
  var u="https://thunderbird.innocraft.cloud/";
  _paq.push(['setTrackerUrl', u+'matomo.php']);
  _paq.push(['setSiteId', `${window._utn.matomoSiteId || 3}`]);
  _paq.push(["setDocumentTitle", window.location.hostname + "/" + document.title]);

  var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
  g.async=true; g.src='https://cdn.matomo.cloud/thunderbird.innocraft.cloud/matomo.js'; s.parentNode.insertBefore(g,s);
})();

if (window.Mozilla.ABTest) {
  window.Mozilla.ABTest.Track();
}
