/* Carry a reader's name and date of birth between numerology pages WITHOUT putting them in a URL.
 *
 * WHY. These values used to ride in the query string - ?name=...&date=... to the chat, and
 * ?name=...&day=... to the report form. A name and a date of birth together identify somebody, and
 * a URL is the worst place to keep them: it lands in the access log of every hop, goes to third
 * parties in the Referer header, stays in browser history, and is copied intact by anybody who
 * shares the link. The report form posts them in a body now; the chat reads them from here.
 *
 * sessionStorage, NOT localStorage. This is a handover between two pages of one visit, so it should
 * die with the tab rather than sit on a shared computer until something clears it.
 *
 * IT ALSO SCRUBS THE URL. Links of the old shape exist - in history, in anything already shared -
 * so on load any of these parameters is removed from the address bar with replaceState. The page
 * has already been rendered from them server-side; this stops them being re-shared, bookmarked, or
 * sent onward in a Referer.
 *
 * Everything here is an enhancement. Without JavaScript the report form still posts (it is a real
 * form) and the consultation simply asks for the name and date, which is the form it shows anyway.
 */
(function () {
  "use strict";

  var KEY = "numerology-subject";
  //: The parameters that must never remain in a visible URL.
  var PRIVATE = ["name", "date", "day", "month", "year"];

  function store(value) {
    try {
      window.sessionStorage.setItem(KEY, JSON.stringify(value));
    } catch (ignore) { /* private mode, blocked storage: the reader types it again */ }
  }

  function read() {
    try {
      return JSON.parse(window.sessionStorage.getItem(KEY) || "null");
    } catch (ignore) {
      return null;
    }
  }

  function scrubUrl() {
    if (!window.history || !window.history.replaceState || !window.URL) return;
    try {
      var url = new URL(window.location.href);
      var had = false;
      PRIVATE.forEach(function (key) {
        if (url.searchParams.has(key)) { url.searchParams.delete(key); had = true; }
      });
      if (had) window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (ignore) { /* an address bar we cannot rewrite is not worth an error */ }
  }

  // ---- the calculator: remember what this reader just worked out ---------------------------
  var subject = document.getElementById("numerology-subject");
  if (subject) {
    store({name: subject.getAttribute("data-name") || "",
           born: subject.getAttribute("data-born") || ""});
  }

  // ---- the consultation page in numerology mode: fill the form from it ---------------------
  var form = document.getElementById("tool-form");
  if (form && form.getAttribute("data-numerology") === "1") {
    var held = read();
    if (held && held.born) {
      var parts = String(held.born).split("-");
      var fill = {"num-chat-name": held.name, "num-chat-year": parts[0],
                  "num-chat-month": String(Number(parts[1])), "num-chat-day": String(Number(parts[2]))};
      Object.keys(fill).forEach(function (id) {
        var el = document.getElementById(id);
        // Never overwrite something the reader has already typed, and never write "undefined".
        if (el && !el.value && fill[id]) el.value = fill[id];
      });
    }
  }

  scrubUrl();
}());

/* The sticky bar on a phone, after a calculation.
 *
 * RENDERED HIDDEN AND SHOWN HERE, so a reader with JavaScript off never gets a bar with a dismiss
 * button that cannot work. While it is up the page carries bottom padding equal to its height
 * (body.has-report-bar), because a bar that covers the last line of a free calculator to advertise
 * a paid report is a worse page, not a better-converting one.
 *
 * DISMISSAL STICKS for the rest of the tab. Someone who has said no once should not be asked again
 * on the next calculation in the same visit.
 */
(function () {
  "use strict";

  var DISMISSED = "numerology-bar-dismissed";
  var bar = document.getElementById("report-bar");
  if (!bar) return;

  try {
    if (window.sessionStorage.getItem(DISMISSED) === "1") return;
  } catch (ignore) { /* storage blocked: show it, and dismissal lasts this page */ }

  // The bar's own link must carry the reader's entry the same way the card does - but a link
  // cannot POST, so it submits the card's form instead of navigating with a query string.
  var go = document.getElementById("report-bar-go");
  var form = document.querySelector(".report-card__form");
  if (go && form) {
    go.addEventListener("click", function (event) {
      event.preventDefault();
      form.submit();
    });
  }

  bar.hidden = false;
  document.body.classList.add("has-report-bar");

  var dismiss = document.getElementById("report-bar-dismiss");
  if (dismiss) {
    dismiss.addEventListener("click", function () {
      bar.hidden = true;
      document.body.classList.remove("has-report-bar");
      try { window.sessionStorage.setItem(DISMISSED, "1"); } catch (ignore) { /* fine */ }
    });
  }
}());
