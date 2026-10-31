/* Where people stop filling in the birth-details form.
 *
 * WHY THIS FILE EXISTS. 6,372 people arrived on the kundli page in thirty days and 999 charts came out
 * of it. Five in six left without one, and nothing here could say at which field - so every explanation
 * was a guess, including the plausible ones.
 *
 * IT ONLY WATCHES. Every signal below is read from the DOM the form already produces - focus, change,
 * aria-invalid, the suggestion list emptying - so this file changes no behaviour and app.js does not
 * know it exists. Measurement must not be able to break the thing it measures, and the cheapest way to
 * guarantee that is to never touch it.
 *
 * IT CARRIES NO VALUES. A step name and a FIELD name: "city" says which box somebody left, never which
 * city. The server drops anything outside its own allowlist, so this is the second of two locks rather
 * than the only one.
 *
 * A FILE, NOT AN INLINE SCRIPT: `script-src 'self'` blocks inline, and an inline version would die
 * silently with nothing but a console line.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var form = document.querySelector("form");
  if (!form || !form.querySelector("input[name='city']")) return;   // not the birth-details form

  var sent = {};
  var width = window.innerWidth || 0;

  function send(step, field) {
    // ONCE PER STEP PER FIELD. A blur fires every time somebody tabs back through a field, and the
    // question is "did they ever complete it", not "how often did they revisit it".
    var key = step + ":" + (field || "");
    if (sent[key]) return;
    sent[key] = true;
    var url = "/api/funnel?step=" + encodeURIComponent(step) +
      (field ? "&field=" + encodeURIComponent(field) : "") + "&w=" + width;
    try {
      // sendBeacon survives the page being closed, which is exactly the moment worth recording: the
      // last step before somebody gave up is the one that matters most and the one a normal fetch
      // loses. fetch with keepalive is the fallback, and neither is awaited.
      if (navigator.sendBeacon) navigator.sendBeacon(url);
      else fetch(url, { method: "POST", keepalive: true, credentials: "same-origin" });
    } catch (e) { /* a beacon is never a reason to interrupt somebody filling in a form */ }
  }

  // ---- the form came into view: the denominator for everything below -------------------------------
  if (window.IntersectionObserver) {
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { send("form_seen"); seen.disconnect(); }
      });
    }, { threshold: 0.25 });
    seen.observe(form);
  } else {
    send("form_seen");
  }

  // ---- first touch, and each field actually completed -----------------------------------------------
  var FIELDS = ["name", "date", "time", "city"];

  form.addEventListener("focusin", function () { send("first_touch"); });

  FIELDS.forEach(function (name) {
    var input = form.querySelector("[name='" + name + "']");
    if (!input) return;
    input.addEventListener("change", function () {
      if (String(input.value || "").trim()) send("field_done", name);
    });
  });

  // ---- the place search, which is the field with the most ways to fail -------------------------------
  var city = form.querySelector("input[name='city']");
  if (city) {
    city.addEventListener("input", function () {
      if (String(city.value || "").trim().length >= 2) send("place_typed", "city");
    });

    // THE SUGGESTION LIST GOING EMPTY IS THE SIGNAL. A reader who types a town that is not in the list
    // sees nothing happen, which is indistinguishable from "still loading" - and is the one failure
    // this form cannot currently report on itself.
    var listId = city.getAttribute("aria-controls");
    var list = listId && document.getElementById(listId);
    if (list && window.MutationObserver) {
      new MutationObserver(function () {
        if (city.getAttribute("data-chosen")) { send("place_picked", "city"); return; }
        // COUNT THE OPTIONS, NOT THE CHILDREN. With nothing to offer, app.js puts a single "no match"
        // <li role="presentation"> in the list - so the list is NOT empty, and the first version of
        // this check never fired on the very case it exists to catch.
        var offered = list.querySelectorAll("[role='option']").length;
        if (offered === 0 && String(city.value || "").trim().length >= 3) send("place_none", "city");
      }).observe(list, { childList: true, attributes: true, attributeFilter: ["hidden"] });
    }
  }

  // ---- the paid report's offer: seen, and pressed ----------------------------------------------------
  // NOTHING RECORDED THIS. The chat's paywall was counted and the report offer under a free chart was
  // not, so the two steps between a free reader and a paying one were invisible - which is awkward when
  // the question being asked is why so few people buy.
  function watchOffer() {
    var cta = document.getElementById("cta");
    if (!cta || cta.hidden || cta.getAttribute("data-funnel-watched")) return;
    cta.setAttribute("data-funnel-watched", "1");
    if (window.IntersectionObserver) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) { send("offer_seen"); io.disconnect(); }
        });
      }, { threshold: 0.4 });
      io.observe(cta);
    } else {
      send("offer_seen");
    }
    cta.addEventListener("click", function (event) {
      if (event.target.closest("[data-product], .btn")) send("offer_click");
    });
  }

  // The offer is revealed with the result, so it is watched then rather than at load.
  if (window.MutationObserver) {
    var ctaEl = document.getElementById("cta");
    if (ctaEl) {
      new MutationObserver(watchOffer).observe(ctaEl, { attributes: true, attributeFilter: ["hidden"] });
      watchOffer();
    }
  }

  // ---- submitted, refused, or answered ---------------------------------------------------------------
  form.addEventListener("submit", function () { send("submit"); });

  if (window.MutationObserver) {
    // aria-invalid is what app.js puts on a field it is sending back, so the form tells us which field
    // it blamed without this file knowing a single validation rule.
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        var target = record.target;
        if (target.getAttribute && target.getAttribute("aria-invalid") === "true") {
          var name = target.getAttribute("name") || "unknown";
          send("invalid", FIELDS.indexOf(name) === -1 ? "unknown" : name);
        }
      });
    }).observe(form, { subtree: true, attributes: true, attributeFilter: ["aria-invalid"] });

    // THE RESULT BODY, WHICH EXISTS AT LOAD. #chart-holder does NOT: app.js builds it as part of the
    // result's own markup, so observing it at init found nothing and this step never fired even on a
    // chart that rendered perfectly well. The container it is written INTO is the thing to watch.
    var resultBody = document.getElementById("result-body");
    if (resultBody) {
      new MutationObserver(function () {
        if (resultBody.querySelector("svg.kundali, .kundali")) send("result");
      }).observe(resultBody, { childList: true, subtree: true });
    }
  }
})();
