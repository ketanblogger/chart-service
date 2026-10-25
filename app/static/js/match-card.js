/* The shareable match card: "Name ❤ Name: N/36 gun".
 *
 * THE CARD IS DRAWN IN THE BROWSER, on a canvas, and the names never leave it. That is not a
 * convenience - it is the whole design. A server-rendered card would need the two names in a URL or a
 * request body, which puts them in an access log, and these are the names of two people somebody is
 * considering a marriage between.
 *
 * NAMES ARE OFF BY DEFAULT. The box is unticked; without it the card says the score and nothing else.
 * Somebody sharing a match into a family group has not necessarily decided to put both names in it.
 *
 * NO BIRTH DETAIL EVER REACHES IT. The card is built from two strings the reader typed as names and
 * one number this page computed. There is no code path from a date, a time or a place to this file,
 * and tests/test_match_card.py asserts the fields it reads are exactly those three.
 *
 * The site's existing share shares the TOOL rather than a result, for good reasons written down in
 * app/web/sharing.py. This is the deliberate exception the proprietor asked for, and it is narrow:
 * two names the reader chose to include, and a score out of 36.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var WIDTH = 1200, HEIGHT = 630;
  var FAMILY = '"RK Devanagari Fallback", system-ui, -apple-system, "Segoe UI", sans-serif';

  /* A canvas draws with the fonts the DOCUMENT has loaded, and a webfont the page has not painted
     yet is not among them. Without this the Devanagari came out as boxes. */
  function fontsReady() {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    var wanted = ["700 64px", "700 150px", "700 190px", "400 40px", "700 34px"].map(function (size) {
      return document.fonts.load(size + ' "RK Devanagari Fallback"', "अआकखगघ");
    });
    return Promise.all(wanted).then(function () { return document.fonts.ready; }).catch(function () {});
  }

  function send(step) {
    try {
      var url = "/api/funnel?step=" + encodeURIComponent(step) + "&w=" + (window.innerWidth || 0);
      if (navigator.sendBeacon) navigator.sendBeacon(url);
      else fetch(url, { method: "POST", keepalive: true, credentials: "same-origin" });
    } catch (e) { /* measurement is never a reason to break a share */ }
  }

  /* The names come from the two inputs the reader filled, read at the moment the button is pressed.
     They are deliberately NOT in the page's markup and never in a request: the only copy of these two
     names is in the reader's own form. */
  /* THE SITE'S NAME IS CONFIGURATION, never a string in a script - tests/test_seo.py enforces that,
     and it is right: the brand belongs in one place. The card takes it from the address the reader is
     already on. */
  function siteName() {
    try {
      return (location.hostname || "").replace(/^www\./, "");
    } catch (e) {
      return "";
    }
  }

  function typedName(which) {
    var input = document.getElementById(which + "-name");
    return input && input.value ? input.value.trim().slice(0, 40) : "";
  }

  function draw(left, right, score, max, words) {
    var canvas = document.createElement("canvas");
    canvas.width = WIDTH; canvas.height = HEIGHT;
    var c = canvas.getContext("2d");

    c.fillStyle = "#2E2660"; c.fillRect(0, 0, WIDTH, HEIGHT);
    c.strokeStyle = "rgba(224,168,46,.22)"; c.lineWidth = 2;
    c.beginPath(); c.arc(1050, 150, 280, 0, Math.PI * 2); c.stroke();
    c.beginPath(); c.arc(1160, 560, 210, 0, Math.PI * 2); c.stroke();

    // THE FAMILY THE PAGE ACTUALLY HAS. The first version of this named "Noto Sans Devanagari",
    // which the site does not declare, so every Devanagari name and the word for "gunas" drew as
    // empty boxes - visible only by looking at the PNG, which is why it is shot.
    var family = FAMILY;
    c.textBaseline = "alphabetic";

    // The headline: the two names with a heart between them, or just the score when they opted out.
    if (left && right) {
      c.fillStyle = "#FFFFFF";
      c.font = "700 64px " + family;
      var line = left + "  ❤  " + right;
      // Shrink rather than overflow: two long names must not run off the card.
      while (c.measureText(line).width > WIDTH - 140 && parseInt(c.font, 10) > 32) {
        c.font = "700 " + (parseInt(c.font, 10) - 4) + "px " + family;
      }
      c.fillText(line, 70, 250);
    }

    c.fillStyle = "#E0A82E";
    c.font = "700 " + (left && right ? "150" : "190") + "px " + family;
    c.fillText(score + " / " + max, 70, left && right ? 430 : 400);

    c.fillStyle = "#B9B2E0";
    c.font = "400 40px " + family;
    c.fillText(words.gunaLabel, 70, left && right ? 490 : 470);

    c.strokeStyle = "rgba(224,168,46,.45)"; c.lineWidth = 2;
    c.beginPath(); c.moveTo(70, 540); c.lineTo(WIDTH - 70, 540); c.stroke();
    c.fillStyle = "#FFFFFF"; c.font = "700 34px " + family;
    c.fillText(siteName(), 70, 590);
    return canvas;
  }

  function wire() {
    var holder = document.querySelector("[data-match-card]");
    if (!holder || holder.getAttribute("data-wired")) return;
    holder.setAttribute("data-wired", "1");
    send("match_card_seen");

    var tick = holder.querySelector("[data-match-names]");
    var button = holder.querySelector("[data-match-share]");
    if (!button) return;

    if (tick) {
      tick.addEventListener("change", function () { if (tick.checked) send("match_card_named"); });
    }

    button.addEventListener("click", function () {
      fontsReady().then(function () { drawAndShare(); });
    });

    function drawAndShare() {
      var words = {
        gunaLabel: holder.getAttribute("data-label-gunas") || "",
      };
      var named = !!(tick && tick.checked);
      var left = named ? typedName("boy") : "";
      var right = named ? typedName("girl") : "";
      var canvas = draw(
        left, right,
        holder.getAttribute("data-score") || "0",
        holder.getAttribute("data-max") || "36",
        words);
      send("match_card_shared");

      var text = (named && left && right ? left + " ❤ " + right + ": " : "") +
        holder.getAttribute("data-score") + "/" + holder.getAttribute("data-max") + " " +
        words.gunaLabel + " - " + (holder.getAttribute("data-share-url") || "");

      // A FILE SHARE WHERE THE BROWSER HAS ONE, a WhatsApp text where it does not. The text carries
      // the same two names and nothing else; app/web/sharing.py's rule that no third-party URL
      // appears in the markup still holds, because this is assembled on the tap.
      canvas.toBlob(function (blob) {
        var file = blob && window.File ? new File([blob], "match.png", { type: "image/png" }) : null;
        if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
          navigator.share({ files: [file], text: text }).catch(function () {});
          return;
        }
        // analytics.js owns the wa.me URL - see the whitelist in tests/test_payments.py.
        if (window.RKShare && window.RKShare.openWhatsApp) window.RKShare.openWhatsApp(text);
      }, "image/png");
    }
  }

  if (window.MutationObserver) {
    var body = document.getElementById("result-body");
    if (body) new MutationObserver(wire).observe(body, { childList: true, subtree: true });
  }
  wire();
})();
