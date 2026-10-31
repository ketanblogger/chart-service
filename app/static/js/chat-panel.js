/* The chart panel beside the AI astrologer (?design=v2 shell only).
 *
 * EVERYTHING HERE IS THE ENGINE'S. It reads the `summary` that /api/consultation/start already returned -
 * the same object the chat itself opened with - so the panel costs no extra request, cannot disagree with
 * the reading beside it, and contains not one word the AI wrote. If the shapes below are ever missing the
 * panel simply stays hidden: a wrong lagna beside a reading would be worse than no panel.
 *
 * It listens for `tool:result`, which app.js already dispatches for chat.js. No change to either.
 */
(function () {
  "use strict";

  var panel = document.getElementById("chat-chart-panel");
  if (!panel) return;

  function set(name, text) {
    var cell = panel.querySelector('[data-panel="' + name + '"]');
    if (cell) cell.textContent = text;
  }

  function signName(sign) {
    if (!sign) return "";
    /* The reader's own tree names it: Devanagari on /hi and /mr, the Sanskrit name on /en. */
    var deva = document.documentElement.lang !== "en";
    return (deva && sign.devanagari) ? sign.devanagari : (sign.name || sign.key || "");
  }

  function drawKundali(summary) {
    /* THE SAME PICTURE AS THE FREE CHART PAGE, from the same numbers: render.js owns the geometry and
       this panel only asks it to draw. A second copy of the diamond would be a second thing to get
       wrong, and the one that disagreed would be the one nobody noticed. */
    var holder = panel.querySelector('[data-panel="kundali"]');
    if (!holder || !window.AstroRender || !window.AstroRender.chartSvg) return;
    if (!summary.houses || !summary.houses.length) return;
    var script = document.documentElement.lang === "en" ? "en" : "deva";
    try {
      holder.innerHTML = window.AstroRender.chartSvg(summary, script);
    } catch (err) {
      holder.innerHTML = "";          /* a panel with no diamond beats a panel with a wrong one */
    }
  }

  /* The nine lords, as the sprite names them. A lord with no glyph simply shows no glyph. */
  var GLYPH = {
    Sun: "g-surya", Moon: "g-chandra", Mars: "g-mangal", Mercury: "g-budh", Jupiter: "g-guru",
    Venus: "g-shukra", Saturn: "g-shani", Rahu: "g-rahu", Ketu: "g-ketu"
  };

  function fraction(start, end) {
    /* How much of this period has gone. Dates are ISO from the engine; anything unparseable gives null
       and the bar is left out rather than drawn at a guess. */
    var from = Date.parse(start), to = Date.parse(end), now = Date.now();
    if (!from || !to || to <= from) return null;
    return Math.max(0, Math.min(1, (now - from) / (to - from)));
  }

  function fillDashaCard(dasha, lordName) {
    var card = panel.querySelector('[data-panel="dasha-card"]');
    if (!card) return;
    var use = panel.querySelector('[data-panel="dasha-glyph"]');
    var id = GLYPH[(dasha.lord && dasha.lord.key) || ""];
    if (use && id) use.setAttribute("href", (panel.dataset.sprite || "") + "#" + id);
    var lordEl = panel.querySelector('[data-panel="dasha-lord"]');
    if (lordEl) lordEl.textContent = lordName;

    var done = fraction(dasha.start, dasha.end);
    var fill = panel.querySelector('[data-panel="dasha-fill"]');
    if (fill) fill.style.width = done === null ? "0%" : (done * 100).toFixed(1) + "%";

    var ends = panel.querySelector('[data-panel="dasha-ends"]');
    if (ends && dasha.end) {
      /* ONE DATE FORMAT, from the server, in the reader's language. The wording goes either side of the
         date rather than through it - no placeholder is ever left in the page, and Hindi and Marathi can
         put their word after the date where it belongs. */
      ends.textContent = (panel.dataset.endsBefore || "") + humanDate(dasha.end) +
                         (panel.dataset.endsAfter || "");
    }
    card.hidden = false;
  }

  function humanDate(iso) {
    /* render.js's own formatter, which the result page and the consultation cards already use. One date
       format on the site means exactly one function that writes one. */
    if (window.AstroRender && window.AstroRender.fmtDate) return window.AstroRender.fmtDate(iso);
    return String(iso).slice(0, 10);
  }

  function fill(summary) {
    if (!summary || !summary.lagna || !summary.moon_rashi) return;
    drawKundali(summary);
    var lagna = summary.lagna;
    set("lagna", signName(lagna.sign) + (lagna.degree_dms ? " " + lagna.degree_dms : ""));
    set("rashi", signName(summary.moon_rashi));

    var nak = summary.janma_nakshatra;
    if (nak) {
      var name = (document.documentElement.lang !== "en" && nak.devanagari) ? nak.devanagari : nak.name;
      set("nakshatra", name + (nak.pada ? " · " + nak.pada : ""));
    }

    var dasha = summary.dasha && summary.dasha.mahadasha;
    if (dasha && dasha.lord) {
      var lord = (document.documentElement.lang !== "en" && dasha.lord.devanagari) ? dasha.lord.devanagari
                                                                                  : (dasha.lord.name || dasha.lord.key);
      fillDashaCard(dasha, lord);
    }

    var list = panel.querySelector('[data-panel="transits"]');
    var heading = panel.querySelector('[data-panel="transits-heading"]');
    var events = (summary.transits && summary.transits.events) || summary.events || [];
    if (list && events.length) {
      list.textContent = "";
      events.slice(0, 4).forEach(function (event) {
        var item = document.createElement("li");
        item.textContent = (event.date ? event.date + " · " : "") + (event.text || event.summary || "");
        list.appendChild(item);
      });
      if (heading) heading.hidden = false;
    }
    panel.hidden = false;
    fillStrip(summary, lagna);
  }

  function fillStrip(summary, lagna) {
    /* The phone's one line: lagna, rashi, and the running dasha with its end date. The same three figures
       the panel shows, in the order someone would say them aloud. The full panel moves into the strip's
       body when it opens, so there is ONE panel on the page and never two that can disagree. */
    var strip = document.getElementById("chat-strip");
    if (!strip) return;
    var line = strip.querySelector('[data-panel="strip"]');
    var dasha = summary.dasha && summary.dasha.mahadasha;
    if (line) {
      var bits = [signName(lagna.sign), signName(summary.moon_rashi)];
      if (dasha && dasha.lord) {
        var lord = (document.documentElement.lang !== "en" && dasha.lord.devanagari)
          ? dasha.lord.devanagari : (dasha.lord.name || dasha.lord.key);
        bits.push(dasha.end ? lord + " \u00b7 " + humanDate(dasha.end) : lord);
      }
      line.textContent = bits.filter(Boolean).join(" \u00b7 ");
    }
    strip.hidden = false;
  }

  function moveThePanel() {
    /* ONE panel, two places. Below 1100px it belongs inside the strip; above, back in the rail. Moving the
       element rather than rendering a second copy is what keeps the kundali from being drawn twice and the
       two drifting apart - and it keeps the diamond out of the phone's first screen until it is asked for. */
    var strip = document.getElementById("chat-strip");
    var body = strip && strip.querySelector('[data-panel="strip-body"]');
    var rail = document.querySelector(".v2-chat__side");
    if (!strip || !body || !rail || !panel) return;
    var onPhone = window.matchMedia("(max-width: 1100px)").matches;
    var wanted = onPhone ? body : rail;
    if (panel.parentNode !== wanted) wanted.insertBefore(panel, wanted.firstChild);
  }

  window.addEventListener("resize", moveThePanel);
  document.addEventListener("DOMContentLoaded", moveThePanel);
  moveThePanel();

  /* A RESUMED CHAT HAS A CHART TOO. `tool:result` fires when the birth form is submitted, so the panel
     filled on a new consultation and stayed empty on one reopened from the sidebar or after a reload -
     which, now that chats persist, is most of the times anybody sees this page. chat.js announces an
     opened conversation on `consultation:opened`, and its view carries the same `summary`. */
  document.addEventListener("consultation:opened", function (event) {
    var view = event.detail;
    if (view && view.summary) fill(view.summary);
  });

  document.addEventListener("tool:result", function (event) {
    var response = event.detail && event.detail.response;
    if (response) fill(response.summary);
  });
})();
