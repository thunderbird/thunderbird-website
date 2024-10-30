var u="//thunderbird.innocraft.cloud/";
var _paq = _paq || [];
_paq.push(["setDocumentTitle", document.domain + "/" + document.title]);
_paq.push(['setTrackerUrl', u+'piwik.php']);
_paq.push(['setSiteId', '1']);
_paq.push(["setCookieDomain", "*.thunderbird.net"]);
_paq.push(['setDownloadClasses', "matomo-track-download"]);
_paq.push(['trackPageView']);
_paq.push(['enableLinkTracking']);
// Disable cookies needs to be set _after_ trackPageView for it to actually work.
_paq.push(["disableCookies"]);
if (window.Mozilla.ABTest) {
  window.Mozilla.ABTest.Track();
}