/* Google Analytics 4 bootstrap (every page, all three language trees).
 *
 * This is the snippet Google hands you, moved out of the page for one reason: the Content-Security-Policy in
 * app/hardening.py has no 'unsafe-inline' in script-src and no nonce machinery, so an inline <script> would be
 * refused by the browser and every pageview would be lost silently - the tag would still be in the HTML and the
 * property would simply stay empty. A file served from our own origin needs no exception to that policy.
 *
 * The measurement ID is spelled once, in templates/base.html, and arrives here on this tag's data-ga-id. The
 * loader (https://www.googletagmanager.com/gtag/js) is the async tag next to it there: it is the third party,
 * so it stays visible in the HTML rather than being injected from here. Both tags are async and the order the
 * two run in does not matter: window.dataLayer is a plain array until the loader replaces its push with its
 * own processor, so a config pushed before it arrives is drained then, and one pushed after is handled at once.
 * That is also why this file is async rather than parser-blocking - measurement must not cost a page any paint.
 */
(function () {
  "use strict";
  var tag = document.currentScript || document.querySelector("script[data-ga-id]");
  var id = tag && tag.getAttribute("data-ga-id");
  if (!id) return;  // nothing configured: no dataLayer, no calls, no console noise

  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = gtag;
  gtag("js", new Date());
  gtag("config", id);
})();
