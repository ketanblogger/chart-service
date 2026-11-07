/* Google Analytics 4 bootstrap (every page, all three language trees).
 *
 * This is the snippet Google hands you, moved out of the page for one reason: the Content-Security-Policy in
 * app/hardening.py has no 'unsafe-inline' in script-src and no nonce machinery, so an inline <script> would be
 * refused by the browser and every pageview would be lost silently - the tag would still be in the HTML and the
 * property would simply stay empty. A file served from our own origin needs no exception to that policy.
 *
 * The measurement ID is spelled once, in templates/base.html, and arrives here on this tag's data-ga-id.
 *
 * THE LOADER IS NOW FETCHED BY THIS FILE, LATE, AND NOT BY A TAG IN THE HTML. It is 526 KB - measured, on
 * the rashifal page that was 75% of the whole page weight and more than triple all our own CSS, JS, fonts
 * and images together - so having the browser discover it in <head> put the heaviest thing on the page in
 * front of the content the reader came for. It is requested after load, once the browser is idle, or at the
 * reader's first interaction, whichever comes first.
 *
 * NO EVENT IS LOST BY WAITING. window.dataLayer is a plain array until the loader arrives and replaces its
 * push with its own processor, so everything queued before it lands is drained the moment it does, in order.
 * That property is what makes this safe, and it is the same property that already let the two tags race in
 * either order. Code elsewhere calls window.gtag() without knowing or caring whether Google has answered.
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

  /* Fetch Google's loader once, and never on the critical path. Whichever of these comes first wins:
   *   - the browser going idle after load, which is when nothing the reader is waiting for is pending;
   *   - the reader's first interaction, because somebody who has started using the page is a session
   *     worth measuring promptly and is also past first paint;
   *   - a hard timeout, so a page that never goes idle and is never touched still reports.
   */
  var started = false;
  var IDLE_TIMEOUT_MS = 3000;   /* requestIdleCallback's own deadline: report even on a busy page */
  var HARD_TIMEOUT_MS = 10000;  /* nothing idle, nothing touched - measure anyway */
  var FIRST_TOUCH = ["pointerdown", "keydown", "touchstart", "scroll", "wheel"];

  function load() {
    if (started) return;        /* five triggers, one request */
    started = true;
    FIRST_TOUCH.forEach(function (name) { window.removeEventListener(name, load, true); });
    var tag = document.createElement("script");
    tag.async = true;
    tag.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
    document.head.appendChild(tag);
  }

  function schedule() {
    if (window.requestIdleCallback) {
      window.requestIdleCallback(load, { timeout: IDLE_TIMEOUT_MS });
    } else {
      window.setTimeout(load, 200);   /* Safari has no requestIdleCallback; a task after load will do */
    }
    window.setTimeout(load, HARD_TIMEOUT_MS);
  }

  /* `passive` so a scroll listener cannot delay scrolling; capture so it fires whatever else handles it. */
  FIRST_TOUCH.forEach(function (name) {
    window.addEventListener(name, load, { capture: true, passive: true, once: false });
  });

  /* This file is async, so it can run either side of the load event: ask the document rather than assume. */
  if (document.readyState === "complete") {
    schedule();
  } else {
    window.addEventListener("load", schedule, { once: true });
  }
})();

/* OUR OWN "this is a browser" ping, independent of the Google tag above and of whether it is configured.
 *
 * WHY IT EXISTS. The server counts a page view for every HTML response that is not an obvious crawler, which
 * came to 450-580 "visitors" a day against about 7 Google clicks. Something fetches the HTML and stops. A
 * browser, by definition, runs this file - so reaching this line is the difference, and it is the only
 * honest way to tell the two apart from the server side.
 *
 * It carries nothing but the path, which the server already stored. No id is sent, none is issued: the
 * server recomputes the same daily-salted visitor hash it saved and marks that row. Nothing on the site is
 * gated on it, so a reader with JavaScript off loses nothing except being counted as proven.
 *
 * sendBeacon, so it never delays a paint and survives the page being closed; a no-op where it is missing.
 */
(function () {
  "use strict";
  try {
    if (!navigator.sendBeacon) return;
    var where = "/api/seen?path=" + encodeURIComponent(location.pathname);
    /* A tiny empty body: some browsers refuse a beacon with no payload at all. */
    navigator.sendBeacon(where, new Blob([], { type: "text/plain" }));
  } catch (ignore) {
    /* measurement is never a reason for a page to misbehave */
  }
})();


/* THE WHATSAPP SHARE BUTTON: revealed here, and the wa.me link assembled here.
 *
 * The page carries the text and the tagged URL as data attributes and no third-party URL at all. Four
 * separate guards in this repository forbid one in a page's markup, and they are right - a page should
 * reference nothing it does not own. Assembling the link at the moment of the tap keeps all four
 * satisfied and changes nothing a reader experiences.
 *
 * The button ships `hidden` and is revealed here, which is the honest no-JavaScript path: without this
 * file there is no button, rather than a button that cannot open anything. (The nav learned the
 * opposite lesson in the same batch - there, the CONTROL was the thing that needed to exist from the
 * first frame, because the content behind it was already on the page.)
 *
 * The tap is counted separately from the arrivals the link produces, because a share nobody opens and
 * a share nobody made are different facts.
 */
(function () {
  if (typeof document === "undefined") return;

  var buttons = document.querySelectorAll("[data-share]");
  for (var i = 0; i < buttons.length; i++) buttons[i].hidden = false;

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-share]");
    if (!button) return;
    var source = button.getAttribute("data-share") || "";
    var text = button.getAttribute("data-share-text") || "";
    var url = button.getAttribute("data-share-url") || "";

    try {
      var beacon = "/api/share?source=" + encodeURIComponent(source);
      if (navigator.sendBeacon) navigator.sendBeacon(beacon);
      else fetch(beacon, { method: "POST", keepalive: true });
    } catch (ignore) { /* counting never costs the reader their share */ }

    openWhatsApp(text + "\n" + url);
  });

  /* THE ONE PLACE THAT KNOWS THE wa.me URL. The guard in tests/test_payments.py is a whitelist per
     FILE, so a second file opening WhatsApp would mean a second entry in it - and the point of that
     guard is that the list stays short enough to read. match-card.js shares an image and calls this
     for its text fallback rather than spelling the URL again. */
  function openWhatsApp(message) {
    window.open("https://wa.me/?text=" + encodeURIComponent(message), "_blank", "noopener");
  }

  window.RKShare = { openWhatsApp: openWhatsApp };
})();
