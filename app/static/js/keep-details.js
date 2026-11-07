/* Birth details, kept across the trip to the sign-in page and back.
 *
 * WHY. The funnel showed several people signing up and then never asking a question. On a 390px phone the
 * reason is plain: fill in name, date of birth, exact time and city; the page says the chat needs a free
 * account; tap Sign in; the browser LEAVES for /login; sign in; come back - and every field is empty. Four
 * things to type again, one of them a birth time most people have to look up. They did the hard part and
 * were met with a blank form.
 *
 * WHAT IS KEPT, AND WHERE. The values that are already in this form, in this tab's sessionStorage, on this
 * device. Nothing is sent anywhere to achieve it; the data never leaves the browser, and the tab closing
 * is the end of it. That is deliberately the weakest storage that solves the problem: these are somebody's
 * birth details, so they are kept for as long as the errand takes and not one moment longer.
 */
(function () {
  "use strict";

  var KEY = "rk.birth.v1";
  var FIELDS = ["name", "date", "time", "city", "lat", "lon", "tz", "timezone"];
  var ASK = "ask-first";

  function form() {
    return document.getElementById("self-name") ? document : null;
  }

  function field(suffix) {
    return document.getElementById("self-" + suffix);
  }

  function save() {
    try {
      var values = {};
      var any = false;
      FIELDS.forEach(function (suffix) {
        var el = field(suffix);
        if (el && el.value) { values[suffix] = el.value; any = true; }
      });
      /* The QUESTION rides with them. Somebody who typed one before signing in should come back to an
         answer, not to an empty box and the memory of what they meant to ask. */
      var asked = document.getElementById(ASK);
      if (asked && asked.value.trim()) { values.question = asked.value.trim(); any = true; }
      if (any) sessionStorage.setItem(KEY, JSON.stringify(values));
    } catch (ignore) { /* private mode, storage off: the form simply behaves as it did before */ }
  }

  function pending() {
    try {
      var saved = JSON.parse(sessionStorage.getItem(KEY) || "{}");
      return saved && saved.question ? saved : null;
    } catch (ignore) { return null; }
  }

  function restore() {
    try {
      var saved = sessionStorage.getItem(KEY);
      if (!saved) return;
      var values = JSON.parse(saved);
      Object.keys(values).forEach(function (suffix) {
        var el = field(suffix);
        /* Never overwrite something the person has already typed in this tab. */
        if (el && !el.value) {
          el.value = values[suffix];
          /* The city box has a hidden pair of coordinates and a listener that sets them; telling it the
             value changed is what keeps the three in step. */
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    } catch (ignore) { /* a bad blob is not worth a broken page */ }
  }

  function forget() {
    try { sessionStorage.removeItem(KEY); } catch (ignore) { /* nothing to do */ }
  }

  if (!form()) return;
  restore();

  /* ---- ask first, sign in second ------------------------------------------------------------------
   *
   * Pressing Send with no account does NOT start a consultation and does not call anything: it writes
   * the question down beside the birth details and says so. Everything that costs money still happens
   * on the other side of the sign-in, where the allowance and the rate limits already live.
   */
  var sendFirst = document.getElementById("ask-first-send");
  var status = document.getElementById("ask-first-status");
  if (sendFirst && status) {
    sendFirst.addEventListener("click", function () {
      var asked = document.getElementById(ASK);
      if (!asked || !asked.value.trim()) { if (asked) asked.focus(); return; }
      save();
      status.textContent = status.dataset.preparing || "";
      status.hidden = false;
      var link = document.getElementById("chat-signin-link");
      if (link) link.focus();
    });
  }

  /* ...and on the way back, with a session now in hand, the question is asked for them. chat.js owns
     the conversation, so this only hands it the details and the words and lets it do its own work. */
  var waiting = pending();
  if (waiting && document.body.dataset.signedIn === "1") {
    document.addEventListener("DOMContentLoaded", resume);
    resume();
  }

  function resume() {
    if (resume.done) return;
    resume.done = true;
    FIELDS.forEach(function (suffix) {
      var el = field(suffix);
      if (el && waiting[suffix] && !el.value) el.value = waiting[suffix];
    });
    document.dispatchEvent(new CustomEvent("consultation:ask", { detail: { question: waiting.question } }));
  }

  /* Saved as they type, because the trip to the sign-in page can start from the header menu as well as
     from the gate's own button, and neither is worth special-casing. */
  FIELDS.forEach(function (suffix) {
    var el = field(suffix);
    if (el) el.addEventListener("change", save);
  });
  document.addEventListener("input", function (event) {
    if (event.target && /^self-/.test(event.target.id || "")) save();
  });
  window.addEventListener("pagehide", save);

  /* Once a consultation has actually started, the details are in the session and this copy is clutter. */
  document.addEventListener("tool:result", forget);
  document.addEventListener("consultation:opened", forget);
})();
