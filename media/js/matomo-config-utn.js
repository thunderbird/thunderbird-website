var _paq = window._paq = window._paq || [];
var u="https://thunderbird.innocraft.cloud/";
/* tracker methods like "setCustomDimension" should be called before "trackPageView" */
_paq.push(['trackPageView']);
_paq.push(['enableLinkTracking']);
_paq.push(['setTrackerUrl', u+'matomo.php']);
_paq.push(["setCookieDomain", "*.thunderbird.net"]);
_paq.push(['setDownloadClasses', "matomo-track-download"]);
_paq.push(['setSiteId', `${window._utn.matomoSiteId || 3}`]);
_paq.push(["setDocumentTitle", window.location.hostname + "/" + document.title]);
if (window.Mozilla.ABTest) {
  window.Mozilla.ABTest.Track();
}
