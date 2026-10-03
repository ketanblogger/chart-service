/* DOM wiring for the tool pages: city combobox, validation, fetch() to the JSON API, and
 * handing the response to the pure renderers in render.js. No frameworks, no AI calls.
 *
 * Payment hook (Phase 6): clicking a [data-product] button dispatches a cancelable
 * `product:purchase` CustomEvent on document with
 *   detail = { product, priceInr, request, name, endpoint, sessionId }
 * where `request` is the exact JSON body that produced the result on screen and `sessionId` is the
 * consultation session (only on /consultation, from the button's data-session-id). A payment script
 * should listen for it and call event.preventDefault(); until then a "coming soon" note shows
 * (the button's data-notice, or a default).
 *
 * Other scripts on the page (static/js/chat.js) learn about a new result from the `tool:result`
 * CustomEvent on document: detail = { request, response, ctx }.
 *
 * Language: the form's data-lang ("en" | "hi" | "mr") picks the labels and messages of render.js, and the
 * consultation is started in that language. This file contains no page paths: links are rendered by the server
 * from the URL registry (app/web/i18n.py).
 *
 * Matching by name (the matching page only): a [data-mode] toggle switches the same form between birth details and
 * names. In name mode only the two names are sent (R.buildNamePayload) to the same endpoint; when a name's first
 * sound is ambiguous the result carries a candidate list, render.js shows it as a small picker, and a click
 * resubmits with the chosen `syllable`. Deep link: ?mode=name or #by-name (the canonical URL is unchanged).
 */
(function () {
  "use strict";

  var R = window.AstroRender;
  var form = document.getElementById("tool-form");
  if (!R || !form) return;

  var formType = form.getAttribute("data-form");
  var lang = form.getAttribute("data-lang") || "en"; // page language: result labels + messages (render.js normalises it)
  var M = R.messages(lang);
  var endpoint = form.getAttribute("data-endpoint");
  var renderer = R.renderers[form.getAttribute("data-renderer")];
  var rendererKey = form.getAttribute("data-renderer");
  var people = formType === "pair" ? ["boy", "girl"] : ["self"];
  var mode = "birth"; // "birth" | "name" (matching page only)
  var nameChoices = {}; // person -> candidate picked for an ambiguous first syllable
  var statusEl = document.getElementById("form-status");
  var submitBtn = document.getElementById("submit-btn");
  var submitLabel = submitBtn.textContent;
  var resultEl = document.getElementById("result");
  var resultBody = document.getElementById("result-body");
  var STORE_KEY = "birth-details";
  var requestCounter = 0;
  /* A `fetch` with no signal waits for ever, and that is not a theoretical shape: measured on a real page,
   * a chart request that HANGS leaves the submit button disabled, reading "Calculating…", with aria-busy
   * set, no error text and no result - permanently, with a page reload as the only way out. A reset
   * connection and an HTTP 500 are both handled correctly and say so; the hang was the one unhandled
   * branch, and it is the worst of the three because it looks to the customer like a slow site rather than
   * a broken one. They wait, and then they leave, on the path to a paid product.
   *
   * TWENTY SECONDS, and the number is chosen rather than round: this endpoint answers in well under a
   * second, so twenty only fires on a connection that is genuinely broken, while still leaving headroom
   * for a slow 2G round trip carrying a JSON payload. Short enough that nobody stares at a dead button,
   * long enough that we never cut off a request that was going to succeed.
   *
   * DO NOT COPY THIS TO THE REMAINING FETCHES WITHOUT READING THIS PARAGRAPH. /api/cities and
   * /api/chart/pdf in this file are now bounded too, each with its own note saying why it was safe. Two
   * are deliberately NOT: chat.js for the paid consultation, and pay.js for the purchase.
   *
   * The test is NOT "is this a pure read" - that was the first formulation and it is too weak. The test is
   * whether an abort can leave the customer WORSE OFF THAN NEVER HAVING TRIED. A chart or a city list
   * costs them nothing to retry. A PDF leaves a rendered file they can fetch again for free. But an abort
   * after the server created an order leaves an order that exists and a browser that does not know its
   * reference - a charge they cannot name - and an abort mid-message on the consultation spends a message
   * credit and hides the answer it bought. Those two need idempotency and recovery, not an
   * AbortController, and a timeout on either would manufacture the loss it appears to prevent.
   * pay.js does already bound its POLL, by a deadline taken from the order's own promised wait, so the
   * path that matters most was thought about; it is the request itself that is unguarded. */
  var REQUEST_TIMEOUT_MS = 20000;
  var inFlight = null;          // the AbortController of the request currently running, if any
  var last = null; // {request, response, ctx} of the result on screen

  function el(person, field) {
    return document.getElementById(person + "-" + field);
  }

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
  }

  /* ---------- cities + combobox ---------- */

  var cities = [];
  /* The same deadline as the chart request, for a different failure. This fetch is a pure read and
   * aborting it loses nothing - but the promise is AWAITED by two features, and an unsettled promise is
   * not a slow list, it is a dead control. The "use my location" button says "searching..." and then
   * waits on this before it ever asks for a position, so a hung connection leaves that sentence on
   * screen for good, with no error and nothing to press. The .catch below already settles a network
   * ERROR; it is a HANG that never settles, which is exactly what a deadline is for.
   *
   * On abort `cities` stays empty and the callers' existing empty-list paths run: the combobox never
   * opens, and the locate button reports that it could not find a place, which is true and actionable.
   *
   * What this does NOT do is block the form, and the earlier claim that it did was wrong. Client
   * validation asks only that the city field be non-empty (render.js), and the server resolves the name
   * case-insensitively, so typing "pune" produces a chart with no list at all. Losing the list degrades
   * the form; it does not stop it. The stuck sentence was the defect. */
  var citiesAbort = typeof AbortController === "function" ? new AbortController() : null;
  var citiesTimer = citiesAbort && window.setTimeout(function () { citiesAbort.abort(); }, REQUEST_TIMEOUT_MS);
  var citiesPromise = fetch("/api/cities", {
    headers: { Accept: "application/json" },
    signal: citiesAbort ? citiesAbort.signal : undefined
  })
    .then(function (response) { return response.ok ? response.json() : { cities: [] }; })
    .then(function (data) { cities = data.cities || []; return cities; })
    .catch(function () { return cities; }) // the API still validates the city on submit
    // Settled either way, so the timer is cancelled either way: a deadline that outlives the request it
    // bounds is the leak the skeleton timer taught us to look for.
    .then(function (list) { if (citiesTimer) { window.clearTimeout(citiesTimer); citiesTimer = null; } return list; });

  function initCombo(input) {
    var list = document.getElementById(input.getAttribute("aria-controls"));
    var options = [], active = -1;

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function setActive(index) {
      if (active >= 0 && list.children[active]) list.children[active].setAttribute("aria-selected", "false");
      active = index;
      if (active >= 0 && list.children[active]) {
        var node = list.children[active];
        node.setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", node.id);
        if (node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function open() {
      options = R.filterCities(cities, input.value, 200);
      if (!options.length) {
        list.innerHTML = cities.length ? '<li class="combo__empty" role="presentation">' + R.esc(M.noMatch) + "</li>" : "";
        list.hidden = !cities.length;
      } else {
        list.innerHTML = options.map(function (city, i) {
          return '<li role="option" id="' + input.id + "-opt-" + i + '" aria-selected="false" data-index="' + i + '">' +
            R.esc(city.name) + ' <span class="combo__state">' + R.esc(city.state || "") + "</span></li>";
        }).join("");
        list.hidden = false;
      }
      list.scrollTop = 0;
      active = -1;
      input.setAttribute("aria-expanded", String(!list.hidden));
    }

    function choose(index) {
      if (!options[index]) return;
      input.value = options[index].name;
      clearFieldError(input);
      close();
    }

    input.addEventListener("focus", function () {
      // Focus that the reader did not ask for - the step nav moving them to the place step - must not drop a
      // list of 124 cities over the submit button the moment they arrive. Typing or a tap still opens it.
      if (input.hasAttribute("data-quiet-focus")) return;
      citiesPromise.then(function () { if (document.activeElement === input) open(); });
    });
    input.addEventListener("input", open);
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (list.hidden) { open(); return; }
        if (!options.length) return;
        var next = active + (event.key === "ArrowDown" ? 1 : -1);
        setActive(next < 0 ? options.length - 1 : next >= options.length ? 0 : next);
      } else if (event.key === "Enter") {
        if (!list.hidden && options.length) {
          event.preventDefault(); // pick the city instead of submitting the form
          choose(active >= 0 ? active : 0);
        }
      } else if (event.key === "Escape") {
        close();
      }
    });
    input.addEventListener("blur", function () {
      // Normalise "pune" -> "Pune"; if one city matches what was typed, take it.
      var typed = input.value.trim().toLowerCase();
      if (typed) {
        var exact = cities.filter(function (city) { return city.name.toLowerCase() === typed; })[0];
        var matches = exact ? [exact] : R.filterCities(cities, typed, 2);
        if (exact || matches.length === 1) input.value = matches[0].name;
      }
      close();
    });
    // pointerdown + preventDefault keeps focus in the input, so blur does not close the list before the click lands.
    list.addEventListener("pointerdown", function (event) { event.preventDefault(); });
    list.addEventListener("mousedown", function (event) { event.preventDefault(); });
    list.addEventListener("click", function (event) {
      var option = event.target.closest ? event.target.closest('[role="option"]') : null;
      if (option) choose(Number(option.getAttribute("data-index")));
    });
  }

  /* ---------- errors ---------- */

  function clearFieldError(input) {
    var error = document.getElementById(input.id + "-error");
    input.removeAttribute("aria-invalid");
    if (error) { error.hidden = true; error.textContent = ""; }
  }

  function clearErrors() {
    people.forEach(function (person) {
      ["name", "date", "time", "city"].forEach(function (field) { clearFieldError(el(person, field)); });
    });
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.className = "form-status";
  }

  /* ---------- the date must be confirmed, not merely displayed ----------
   * The year jump invents 1 January so the native picker can open in the year that was chosen (the block
   * further down explains why it has to write a whole date). Echoing that back is necessary and is not
   * sufficient: a reader can skim a sentence, and the failure it guards - a chart cast, paid for and
   * printed for a date nobody ever entered - cannot be undone once it is a PDF in somebody's hand. So the
   * invented date cannot be SUBMITTED. The form refuses until the date field has been touched by
   * something the visitor themselves did.
   *
   * It rests entirely on `data-supplied-year`, which the jump sets ONLY when the field was empty and which
   * any trusted event removes. There is no second flag to keep in step with the first, and no comparison
   * against 1 January: somebody genuinely born on 1 January must be able to submit, and they can, the
   * moment they touch the field. That is why the discriminator is the event's own `isTrusted` and not a
   * value we remember writing.
   *
   * THE FRICTION IS THE POINT, AND IT IS NOT A FAILURE. Someone who has picked a year and nothing else has
   * not made a mistake - they have not finished. So the sentence asks them to confirm rather than telling
   * them something is wrong, and it is written as an instruction in all three trees. It travels through
   * showErrors because that is what puts it beside the field, moves focus to it and announces it; the
   * mechanism is an error channel, the message is not an accusation. */
  function unconfirmedDates() {
    var pending = [];
    people.forEach(function (person) {
      var input = el(person, "date");
      if (input && input.hasAttribute("data-supplied-year")) {
        pending.push({ person: person, field: "date", message: M.confirmDate });
      }
    });
    return pending;
  }

  /** errors: [{person, field, message}] - shows them next to fields (or in the form status) and focuses the first. */
  function showErrors(errors) {
    var general = [], first = null;
    errors.forEach(function (error) {
      var input = error.person && error.field ? el(error.person, error.field) : null;
      var target = input ? document.getElementById(input.id + "-error") : null;
      if (!input || !target) { general.push(error.message); return; }
      input.setAttribute("aria-invalid", "true");
      target.textContent = error.message;
      target.hidden = false;
      first = first || input;
    });
    if (general.length) {
      statusEl.textContent = general.join(" ");
      statusEl.className = "form-status form-status--error";
      statusEl.hidden = false;
    }
    if (first) first.focus();
  }

  /* ---------- submit ---------- */

  function readValues() {
    var values = {};
    people.forEach(function (person) {
      values[person] = {
        name: el(person, "name").value.trim(),
        date: el(person, "date").value,
        time: el(person, "time").value,
        city: el(person, "city").value.trim()
      };
    });
    return values;
  }

  var busyRow = document.getElementById("form-busy");
  var busyText = busyRow && busyRow.querySelector("[data-busy-text]");
  var skeleton = document.getElementById("result-skeleton");
  /* Half a second. Below it nobody sees the skeleton, which is the normal case - the endpoint answers in
   * well under a second and a placeholder that flashes and vanishes is worse than none. Above it, the
   * people who are actually waiting are the ones who get something to look at. */
  var REVEAL_SKELETON_MS = 500;
  var skeletonTimer = null;

  function setBusy(busy) {
    submitBtn.disabled = busy;
    // The BUTTON keeps the short label. The engine line goes in the row below it, because the button is
    // width:100% on a phone: a longer label wraps, the button grows a line, and everything under it moves -
    // at the exact moment the visitor clicks. A busy state that shifts the page is a worse trade than a
    // shorter word on a button.
    submitBtn.textContent = busy ? M.calculating : submitLabel;
    form.setAttribute("aria-busy", String(busy));
    if (busyRow) {
      if (busyText) busyText.textContent = busy ? (M.calculatingEngine || M.calculating) : "";
      busyRow.hidden = !busy;
    }
    /* The skeleton's timer is cancelled HERE, at the top of the only function that changes the busy state,
     * rather than on each exit path of the request. That matters more than it looks: a delayed reveal is a
     * third timer on one request, and "cancel it everywhere the request can end" is exactly the bookkeeping
     * that left the busy state stuck for ever before the deadline existed. Riding on setBusy instead means
     * it inherits an invariant that is already guaranteed - setBusy(false) runs on success, on failure and
     * on abort - so there is no path where the skeleton can outlive the request that showed it. */
    if (skeletonTimer) { window.clearTimeout(skeletonTimer); skeletonTimer = null; }
    if (!skeleton) return;
    if (!busy) { skeleton.hidden = true; return; }
    skeletonTimer = window.setTimeout(function () { skeleton.hidden = false; }, REVEAL_SKELETON_MS);
  }

  function showResult(request, response, values) {
    var ctx = formType === "pair"
      ? { names: { boy: values.boy.name, girl: values.girl.name }, lang: lang, mode: mode }
      : { name: values.self.name, lang: lang };
    ctx.approxTime = form.getAttribute("data-approx-time") === "1";
    last = { request: request, response: response, ctx: ctx };
    resultBody.innerHTML = renderer(response, ctx);
    var notice = document.getElementById("cta-notice");
    if (notice) notice.hidden = true;
    var cta = document.getElementById("cta");
    if (cta) cta.hidden = mode === "name"; // the paid report is written from two birth charts
    resultEl.hidden = false;
    revealInSequence();
    document.dispatchEvent(new CustomEvent("tool:result", { detail: last }));
    resultEl.focus({ preventScroll: true });
    resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearErrors();
    var values = readValues();
    var byName = mode === "name";
    var errors = byName ? R.validateNames(values, lang) : R.validate(formType, values, todayIso(), lang);
    // By-name mode has no birth date to confirm. Appended rather than checked first so that a reader with
    // two problems is told about both at once instead of being sent round the form twice.
    if (!byName) errors = errors.concat(unconfirmedDates());
    if (errors.length) {
      showErrors(errors);
      form.dispatchEvent(new CustomEvent("tool:invalid", { detail: errors }));
      return;
    }

    var request = byName ? R.buildNamePayload(values, nameChoices) : R.buildPayload(formType, values);
    if (rendererKey === "consultation") request.language = lang; // the astrologer answers in the page language
    var ticket = ++requestCounter;
    /* One request in flight, ever. A new submit aborts its predecessor, so a superseded response cannot
     * arrive at all - which is what makes the stale-ticket check below belt-and-braces rather than
     * load-bearing, and means the busy state is always cleared by the single live request.
     *
     * The alternative considered and rejected: having the stale branch call setBusy(false). That would
     * re-enable the form while a NEWER request is still running, letting someone fire a third into a form
     * already waiting - a new defect rather than a safety net. Aborting removes the case instead of
     * handling it, so the cleanup depends on no argument about how many requests can be in flight. */
    if (inFlight) inFlight.abort();
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    inFlight = controller;
    var timer = controller && window.setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
    function settled() {
      if (timer) window.clearTimeout(timer);
      if (inFlight === controller) inFlight = null;
    }
    setBusy(true);
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(request),
      signal: controller ? controller.signal : undefined
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (body) {
        return { ok: response.ok, status: response.status, body: body };
      });
    }).then(function (result) {
      settled();
      if (ticket !== requestCounter) return; // a newer submit is in flight
      setBusy(false);
      if (!result.ok || !result.body) { showErrors(R.parseApiError(result.status, result.body, formType, lang)); return; }
      if (!byName) try {
        var stored = JSON.parse(window.sessionStorage.getItem(STORE_KEY) || "{}") || {};
        people.forEach(function (person) { stored[person] = values[person]; });
        window.sessionStorage.setItem(STORE_KEY, JSON.stringify(stored));
      } catch (ignore) { /* storage unavailable - only a convenience */ }
      showResult(request, result.body, values);
    }).catch(function () {
      settled();
      // An abort lands here too. If it was OUR abort because a newer submit started, that submit owns the
      // busy state and this one must not touch it; if it was the timeout, this is the newest request and
      // the customer gets the same state a reset connection already gives them - form back, message shown,
      // retry works. The ticket check separates the two without needing to ask why we aborted.
      if (ticket !== requestCounter) return;
      setBusy(false);
      showErrors([{ person: null, field: null, message: M.offline }]);
    });
  });

  /* ---------- matching by name ---------- */

  var modeButtons = document.querySelectorAll("[data-mode][type=button]");
  var headingEl = document.getElementById("form-heading");

  function setMode(next, fromUser) {
    mode = next === "name" && modeButtons.length ? "name" : "birth";
    var byName = mode === "name";
    form.setAttribute("data-mode", mode);
    Array.prototype.forEach.call(modeButtons, function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-mode") === mode));
    });
    Array.prototype.forEach.call(form.querySelectorAll(".birth-only"), function (node) { node.hidden = byName; });
    Array.prototype.forEach.call(form.querySelectorAll(".name-only"), function (node) {
      node.hidden = !byName;
    });
    Array.prototype.forEach.call(form.querySelectorAll(".optional"), function (node) { node.hidden = byName; });
    people.forEach(function (person) {
      var input = el(person, "name");
      input.placeholder = byName ? (input.getAttribute("data-name-placeholder") || "") : "";
      if (byName) input.setAttribute("aria-required", "true"); else input.removeAttribute("aria-required");
    });
    var nameNote = document.getElementById("name-note"), formNote = document.getElementById("form-note");
    if (nameNote) nameNote.hidden = !byName;
    if (formNote) formNote.hidden = byName;
    submitLabel = submitBtn.getAttribute(byName ? "data-label-name" : "data-label-birth") || submitLabel;
    submitBtn.textContent = submitLabel;
    // The staged form listens: by-name mode hides every birth field, so its steps would be empty shells.
    document.dispatchEvent(new CustomEvent("tool:mode", { detail: mode }));
    if (headingEl) headingEl.textContent = headingEl.getAttribute(byName ? "data-heading-name" : "data-heading-birth") || headingEl.textContent;
    nameChoices = {};
    clearErrors();
    resultEl.hidden = true;
    if (fromUser && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname + (byName ? "?mode=name" : ""));
    }
  }

  Array.prototype.forEach.call(modeButtons, function (button) {
    button.addEventListener("click", function () { setMode(button.getAttribute("data-mode"), true); });
  });

  // Ambiguous first sound ("Tina": ती or टी?): the API scored the first reading and lists the others; the result
  // shows them as chips (render.js). Picking one resubmits the same names with that `syllable`.
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-name-candidate]") : null;
    if (!button || !last || mode !== "name") return;
    var person = button.getAttribute("data-person");
    var match = (last.response[person] || {}).name_match || {};
    var choice = (match.candidates || [])[Number(button.getAttribute("data-index"))];
    if (!choice || choice.syllable === match.syllable) return;
    nameChoices[person] = choice;
    if (form.requestSubmit) form.requestSubmit(); else submitBtn.click();
  });

  /* ---------- progressive reveal ----------
   * The free result is long: birth facts, then the chart, then positions, then the dasha timeline, and only
   * then the free PDF and the paid tiers. Each block settles in as it reaches the viewport so it reads as a
   * sequence rather than a wall. Nothing is hidden: without IntersectionObserver, or with reduced motion, or
   * with JavaScript off entirely, every block is simply there. Order comes from the DOM, not from here.
   */
  function revealInSequence() {
    if (!window.IntersectionObserver) return;
    var blocks = Array.prototype.slice.call(resultBody.querySelectorAll(":scope > .block, :scope > .score, :scope > .people"))
      .concat(Array.prototype.slice.call(document.querySelectorAll("#chart-download, #cta")));
    if (!blocks.length) return;
    var watcher = new window.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        watcher.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    blocks.forEach(function (block, index) {
      block.classList.add("reveal");
      if (index === 0) { block.classList.add("is-in"); return; } // the first answer is never delayed
      watcher.observe(block);
    });
  }

  /* ---------- staged form ----------
   * The steps are already in the page as <fieldset data-step>. Without JavaScript they are all visible and the
   * form submits as one, which is what the <noscript> block promises. Here we show one at a time. Nothing is
   * removed from the DOM, `hidden` is the only mechanism, and the form is novalidate so a required field on a
   * step you have not reached yet cannot block submission - app.js validates the lot on submit either way.
   */
  var steps = Array.prototype.slice.call(form.querySelectorAll("[data-step]"));
  var stepNav = form.querySelector("[data-step-nav]");
  if (steps.length > 1 && stepNav) (function () {
    var backBtn = stepNav.querySelector("[data-step-back]");
    var nextBtn = stepNav.querySelector("[data-step-next]");
    var counter = stepNav.querySelector("[data-step-count]");
    var at = 0;

    function fieldsOf(step) {
      return Array.prototype.slice.call(step.querySelectorAll("input[required]"))
        .filter(function (input) { return input.offsetParent !== null || !input.disabled; });
    }

    function show(index, moveFocus) {
      at = Math.max(0, Math.min(steps.length - 1, index));
      steps.forEach(function (step, i) {
        step.hidden = i !== at;
        if (i === at) step.setAttribute("aria-current", "step");
        else step.removeAttribute("aria-current");
      });
      backBtn.hidden = at === 0;
      nextBtn.hidden = at === steps.length - 1;
      submitBtn.hidden = at !== steps.length - 1;
      if (counter) counter.textContent = (counter.getAttribute("data-label") || "") + " " + (at + 1) + " / " + steps.length;
      if (moveFocus) {
        var first = steps[at].querySelector("input, select, textarea, button");
        if (first && first.focus) {
          first.setAttribute("data-quiet-focus", "1");   // see the combobox focus handler
          first.focus({ preventScroll: true });
          window.setTimeout(function () { first.removeAttribute("data-quiet-focus"); }, 0);
        }
      }
    }

    /** Validate only the step being left, so a reader is not sent back for a field they have not reached. */
    function stepIsValid() {
      var values = readValues(), errors = R.validate(formType, values, todayIso(), lang);
      var mine = fieldsOf(steps[at]).map(function (input) { return input.name; });
      // A single-person form puts the steps INSIDE the person fieldset; the matching page puts a person
      // fieldset inside each step. So look up and then down, or step 1 of a pair form validates the other
      // person's empty fields and nobody can ever leave it.
      var owner = steps[at].closest("[data-person]") || steps[at].querySelector("[data-person]");
      var person = owner && owner.getAttribute("data-person");
      var relevant = errors.filter(function (error) {
        return mine.indexOf(error.field) !== -1 && (!person || error.person === person);
      });
      clearErrors();
      if (relevant.length) showErrors(relevant);
      return !relevant.length;
    }

    function enterStaging() {
      form.classList.add("is-staged");
      stepNav.hidden = false;
      show(0, false);
    }

    nextBtn.addEventListener("click", function () { if (stepIsValid()) show(at + 1, true); });
    backBtn.addEventListener("click", function () { show(at - 1, true); });
    // A validation failure on submit has to be visible: jump to the step that owns the first error.
    form.addEventListener("tool:invalid", function (event) {
      // By-name mode un-stages the form and shows the whole of it, so there is no step to jump to - and
      // jumping anyway would hide the second name field the reader was just told to fill in.
      if (!form.classList.contains("is-staged")) return;
      var first = (event.detail || [])[0];
      if (!first) return;
      for (var i = 0; i < steps.length; i++) {
        var owner = steps[i].closest("[data-person]") || steps[i].querySelector("[data-person]");
        var person = owner && owner.getAttribute("data-person");
        if (steps[i].querySelector("[name='" + first.field + "']") && (!person || person === first.person)) {
          show(i, true);
          return;
        }
      }
    });
    // By-name mode on the matching page hides every birth field; staging would then show empty steps.
    document.addEventListener("tool:mode", function (event) {
      if (event.detail === "name") {
        form.classList.remove("is-staged");
        steps.forEach(function (step) { step.hidden = false; step.removeAttribute("aria-current"); });
        stepNav.hidden = true;
        submitBtn.hidden = false;
      } else {
        enterStaging();
      }
    });
    enterStaging();
  }());

  /* ---------- the date, read back in words ----------
   * <input type="date"> is drawn by the browser in the BROWSER's locale, not the document's: a Chrome set to
   * en-US shows mm/dd/yyyy to a reader in India, and lang="en-IN" does not reliably change it. Nobody can fix
   * that from here, but the mis-entry it causes is catchable - so the parsed value is read straight back in
   * words, in the page's language, using the same formatter the result uses. "03/04" becoming "3 April" or
   * "4 March" is visible before it becomes a chart.
   */
  function bindEcho(selector, type, pattern, format) {
    Array.prototype.forEach.call(form.querySelectorAll(selector), function (echo) {
      var input = echo.parentNode.querySelector("input[type='" + type + "']");
      if (!input) return;

      function show(event) {
        var value = input.value;
        // `isTrusted` is the discriminator: false for the events the year jump dispatches, true for
        // anything the visitor actually did. A property of the event cannot desynchronise from what caused
        // it, so the sentence about the app supplying a date cannot outlive the moment it was true - where
        // a flag we clear by hand can, and a comparison against the value we wrote mis-fires on a visitor
        // genuinely born on 1 January of the year they picked.
        //
        // Measured, on this page, because a first attempt at testing this concluded the opposite:
        //     page.fill(...)        -> isTrusted false     (sets the value programmatically: same as us)
        //     keyboard.type(...)    -> isTrusted TRUE
        //     the jump's dispatch   -> isTrusted false
        // So the rule IS reachable by a test; the test has to type rather than fill. Filling asks the
        // mechanism to separate two things that really are the same thing.
        if (event && event.isTrusted) {
          input.removeAttribute("data-supplied-year");
        }
        if (!pattern.test(value)) { echo.hidden = true; return; }
        var supplied = input.getAttribute("data-supplied-year");
        // The template lives in render.js's message tables rather than in a data- attribute, because an
        // attribute would have to carry "{year}" into the served HTML - and an unsubstituted placeholder
        // reaching a page is exactly what tests/test_pages_i18n.py forbids, for the good reason that it is
        // otherwise how a missing server-side substitution ships. Client-filled copy belongs with the rest
        // of the client-filled copy.
        if (supplied && echo.hasAttribute("data-supplied") && M.yearSet) {
          echo.innerHTML = R.esc(M.yearSet).replace("{year}", "<b>" + R.esc(supplied) + "</b>");
        } else {
          var words = R.withLang(lang, function () { return format(value); });
          echo.innerHTML = R.esc(echo.getAttribute("data-label") || "") + " <b>" + words + "</b>";
        }
        echo.hidden = false;
      }

      input.addEventListener("input", show);
      input.addEventListener("change", show);
      show();  // a value restored from the last visit is echoed too
    });
  }

  bindEcho("[data-date-echo]", "date", /^\d{4}-\d{2}-\d{2}$/, R.fmtDate);

  /* ---------- fast year selection ----------
   * A birth in the 1950s is a long crawl backwards through a month-at-a-time picker, so the year gets a
   * control of its own. Three things about it are deliberate:
   *
   * IT HOLDS NO VALUE. It writes the year into the date input and dispatches the events a keystroke would,
   * so the echo, the validation and the submitted payload all see one source of truth. A second control
   * holding half a date is a second thing to keep in step, and the half it would hold is the half nobody
   * can check by eye.
   *
   * ITS RANGE COMES FROM THE FIELD. The options are read off the input's own min and max, so it can never
   * offer a year the form would then refuse - and app.js sets that max to today during init, which is what
   * keeps a birth date in the future out of the picker as well as out of the validator.
   *
   * ON AN EMPTY FIELD IT LANDS ON 1 JANUARY, and the echo does NOT then say "you entered" it. The point
   * of the control is that the native picker opens on whatever the field holds, so writing a date is the
   * only way to make it open in 1955 - `<input type="date">` has no partial value to set, and anything
   * short of a full date yields the empty string. So a day and a month get invented, which is defensible
   * only if we never claim the visitor chose them. The echo says the year was set and the day and month
   * are still to choose, until the first real edit, after which it reports normally.
   *
   * That distinction is the whole of it. This echo's worth is that it is a faithful mirror; the first time
   * it reports an action the visitor did not take, it teaches them it is not one - and it teaches them
   * that here, in the cheap case, so that in the expensive one, a genuinely mistyped year, they have
   * already learned to skim it.
   *
   * Without that distinction in the copy, this control should not exist. */
  Array.prototype.forEach.call(form.querySelectorAll("[data-year-jump]"), function (slot) {
    var input = slot.parentNode.querySelector("input[type='date']");
    if (!input) return;
    var first = Number((input.getAttribute("min") || "1800-01-01").slice(0, 4));
    // Capped by TODAY as well as by the field, and not because the field is untrustworthy: the init block
    // further down is what narrows `max` from the markup's far-future bound to today, and it runs after
    // this. Reading the attribute alone built a list reaching 2399 - every year of it a birth date the
    // validator rejects - and the test caught it. Taking the tighter of the two makes the control correct
    // whatever order these two blocks end up in, which is worth more than moving one below the other.
    var last = Math.min(Number((input.getAttribute("max") || todayIso()).slice(0, 4)),
                        Number(todayIso().slice(0, 4)));
    if (!(last >= first)) return;

    var select = document.createElement("select");
    select.className = "field__jump-select";
    select.setAttribute("aria-label", slot.getAttribute("data-label") || "");
    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = slot.getAttribute("data-label") || "";
    select.appendChild(blank);
    for (var y = last; y >= first; y--) {
      var option = document.createElement("option");
      option.value = String(y);
      option.textContent = String(y);
      select.appendChild(option);
    }

    function sync() {                       // the field is the truth; the control only reflects it
      select.value = /^\d{4}-\d{2}-\d{2}$/.test(input.value) ? input.value.slice(0, 4) : "";
    }

    select.addEventListener("change", function () {
      if (!select.value) return;
      var full = /^\d{4}-\d{2}-\d{2}$/.test(input.value);
      var month = full ? input.value.slice(5, 7) : "01", day = full ? input.value.slice(8, 10) : "01";
      // If the day and month came from here rather than from the visitor, the echo has to say so instead
      // of claiming they entered them. Marked on the field, cleared by the first real edit.
      if (full) input.removeAttribute("data-supplied-year");
      // 29 February carried into a year that has no 29th must not become 1 March - a silently shifted date
      // is the whole failure class this form guards. Clamp to the last day the month actually has.
      var last_day = new Date(Number(select.value), Number(month), 0).getDate();
      if (Number(day) > last_day) day = ("0" + last_day).slice(-2);
      input.value = select.value + "-" + month + "-" + day;
      if (!full) input.setAttribute("data-supplied-year", select.value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    slot.appendChild(select);
    sync();
  });
  /* The time echo exists for one failure: a birth time entered as morning when the visitor meant evening.
   * It moves the lagna by half the zodiac and nothing after this point can detect it - the chart, the dasha
   * and the report are all internally consistent and all wrong. The echo is the only place it is visible,
   * so it is printed in the words this language uses for the time of day rather than as a 24-hour clock,
   * and by the same formatter the result uses so the two cannot drift apart. */
  bindEcho("[data-time-echo]", "time", /^\d{1,2}:\d{2}/, R.fmtTime);

  /* ---------- "not sure of the exact time?" presets ----------
   * Each preset is up to three hours wide and the lagna turns over about every two hours, so using one sets
   * data-approx-time on the form. That flag rides into the renderer (ctx.approxTime), which prints the caveat
   * in the result's existing caveat block, and into the free PDF request as `approximate_time`.
   */
  Array.prototype.forEach.call(form.querySelectorAll("[data-presets]"), function (group) {
    var toggle = group.querySelector("[data-preset-toggle]");
    var panel = group.querySelector(".presets__panel");
    var chips = Array.prototype.slice.call(group.querySelectorAll("[data-preset]"));
    var input = group.closest(".field").querySelector("input[type='time']");

    toggle.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        input.value = chip.getAttribute("data-preset");
        chips.forEach(function (other) { other.setAttribute("aria-pressed", String(other === chip)); });
        form.setAttribute("data-approx-time", "1");
        clearFieldError(input);
      });
    });
    // Typing a real time is the reader taking the caveat back off.
    input.addEventListener("input", function () {
      if (chips.every(function (chip) { return chip.getAttribute("data-preset") !== input.value; })) {
        chips.forEach(function (chip) { chip.setAttribute("aria-pressed", "false"); });
        if (!form.querySelector("[data-preset][aria-pressed='true']")) form.removeAttribute("data-approx-time");
      }
    });
  });

  /* ---------- "use my location" ----------
   * The coordinates never leave the browser. navigator.geolocation gives a position, the nearest of the cities
   * already fetched from /api/cities is picked HERE, and only that city's name goes into the field - so the
   * request that follows is the same request typing the city would have made. No new endpoint, nothing to log.
   */
  var locate = form.querySelector("[data-locate]");
  if (locate && navigator.geolocation) (function () {
    var status = form.querySelector("[data-locate-status]");
    var input = locate.closest(".field").querySelector("input[name='city']");
    locate.hidden = false;

    function say(key, extra) {
      status.textContent = (status.getAttribute("data-" + key) || "") + (extra ? " " + extra : "");
      status.hidden = !status.textContent;
    }

    function nearest(lat, lon) {
      var best = null, bestScore = Infinity;
      cities.forEach(function (city) {
        // Equirectangular distance is plenty for "which of 124 cities is closest"; no trigonometry library.
        var dy = city.lat - lat, dx = (city.lon - lon) * Math.cos(lat * Math.PI / 180);
        var score = dy * dy + dx * dx;
        if (score < bestScore) { bestScore = score; best = city; }
      });
      return best;
    }

    locate.querySelector("[data-locate-go]").addEventListener("click", function () {
      say("searching");
      citiesPromise.then(function () {
        navigator.geolocation.getCurrentPosition(function (position) {
          var city = cities.length && nearest(position.coords.latitude, position.coords.longitude);
          if (!city) { say("unavailable"); return; }
          input.value = city.name;
          clearFieldError(input);
          say("found", city.name);
        }, function (error) {
          say(error && error.code === 1 ? "denied" : "unavailable");
        }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 });
      });
    });
  }());

  /* ---------- result interactions ---------- */

  // Janam kundali: switch chart labels between English and Devanagari without refetching.
  resultBody.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-chart-script]") : null;
    var holder = document.getElementById("chart-holder");
    if (!button || !holder || !last) return;
    var script = button.getAttribute("data-chart-script");
    last.ctx.script = script;
    holder.innerHTML = R.chartSvg(last.response, script) + R.chartLegend(script, lang);
    Array.prototype.forEach.call(resultBody.querySelectorAll("[data-chart-script]"), function (chip) {
      chip.setAttribute("aria-pressed", String(chip === button));
    });
  });

  /* ---------- free Basic Chart PDF (janam kundali page only) ----------
   * POST /api/chart/pdf with the SAME body that produced the chart on screen, plus the page language, the
   * chart script the reader is currently looking at, and the optional name. It answers with the file itself
   * rather than JSON, so this is fetch -> blob -> a temporary <a download>; a plain link cannot do it because
   * the route is a POST (it recomputes the chart server-side instead of trusting a chart from the browser).
   *
   * Every failure here is a NOTE, not an error: the chart is already on the page and stays free to read. The
   * 429 in particular will land on people who did nothing wrong - India's mobile carriers put thousands of
   * subscribers behind one public IP - so it must never read like an accusation. Wording comes from the
   * server-rendered data-* attributes, so all three languages are the content modules' words, not JS strings.
   */
  // Which note a refusal shows. 429 = the hourly render limit (app/pdf/routes.py), 503 = busy or unavailable;
  // anything else, including a dead connection, falls through to the generic one. The server's own `message` is
  // English, so it is never shown - the wording comes from the page, in the page's language.
  var NOTE_FOR_STATUS = { 429: "limit", 503: "busy" };

  var pdfButton = document.getElementById("chart-pdf-btn");
  if (pdfButton) (function () {
    var status = document.getElementById("chart-pdf-status");
    var idleLabel = pdfButton.textContent;
    var pending = false;

    function note(key) {
      if (!status) return;
      status.textContent = status.getAttribute("data-" + key) || "";
      status.hidden = !status.textContent;
    }

    function done() {
      pending = false;
      pdfButton.disabled = false;
      pdfButton.removeAttribute("aria-busy");
      pdfButton.textContent = idleLabel;
    }

    function save(blob, filename) {
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Revoking immediately can cancel the download in some browsers; a tick later is safe.
      window.setTimeout(function () { window.URL.revokeObjectURL(url); }, 30000);
    }

    /** `attachment; filename="..."` (or filename*=UTF-8''...), falling back to a sensible default. */
    function filenameFrom(header) {
      var star = /filename\*=UTF-8''([^;]+)/i.exec(header || "");
      if (star) try { return decodeURIComponent(star[1]); } catch (ignore) { /* fall through */ }
      var plain = /filename="?([^";]+)"?/i.exec(header || "");
      return (plain && plain[1]) || "kundali.pdf";
    }

    pdfButton.addEventListener("click", function () {
      if (pending || !last || !last.request) return;
      pending = true;
      pdfButton.disabled = true;
      pdfButton.setAttribute("aria-busy", "true");
      pdfButton.textContent = pdfButton.getAttribute("data-label-working") || idleLabel;
      if (status) status.hidden = true;

      var body = {};
      Object.keys(last.request).forEach(function (key) { body[key] = last.request[key]; });
      body.language = lang;
      body.script = last.ctx.script || (lang === "en" ? "en" : "deva");
      if (last.ctx.approxTime) body.approximate_time = true;  // the sheet carries the same caveat
      if (last.ctx.name) body.name = last.ctx.name;

      /* Bounded, for the same reason as the chart request and NOT on the same argument. "Is this a pure
       * read" was the wrong question to ask about these call sites; the right one is whether an abort can
       * leave the customer worse off than never having pressed the button.
       *
       * Here it cannot. The route is sync, so a disconnect does not cancel it: Chromium finishes, the file
       * is written, and one unit of the IP's hourly render budget is spent. But the render was going to
       * complete either way - aborting does not cause that cost, it only stops somebody watching a dead
       * button - and the finished PDF is CACHED, so their retry is a cache hit: instant, free, charged
       * nothing, and it hands them the very file this attempt produced. Nothing is lost and nothing is
       * unreachable.
       *
       * Contrast the payment path, which is why that one stays unguarded: an aborted order creation leaves
       * something the customer cannot reach and may already have paid for. Same mechanism, opposite
       * consequence. An abort here leaves a file they can fetch for free; an abort there leaves a charge
       * they cannot name.
       *
       * The server is already quick or already honest - it queues for a bounded 2s and then answers 503 -
       * so twenty seconds fires only on a connection that has genuinely stopped answering. On abort the
       * catch below reports the existing "failed" copy, which is true, and the button comes back. */
      var pdfAbort = typeof AbortController === "function" ? new AbortController() : null;
      var pdfTimer = pdfAbort && window.setTimeout(function () { pdfAbort.abort(); }, REQUEST_TIMEOUT_MS);
      function pdfSettled() { if (pdfTimer) { window.clearTimeout(pdfTimer); pdfTimer = null; } }

      fetch("/api/chart/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/pdf" },
        body: JSON.stringify(body),
        signal: pdfAbort ? pdfAbort.signal : undefined
      }).then(function (response) {
        pdfSettled();
        if (!response.ok) { done(); note(NOTE_FOR_STATUS[response.status] || "failed"); return null; }
        return response.blob().then(function (blob) {
          done();
          save(blob, filenameFrom(response.headers.get("Content-Disposition")));
        });
      }).catch(function () {
        pdfSettled();
        done();
        note("failed");
      });
    });
  }());

  // Paid product hook - see the header comment.
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-product]") : null;
    if (!button) return;
    var detail = {
      product: button.getAttribute("data-product"),
      priceInr: Number(button.getAttribute("data-price-inr")),
      endpoint: endpoint,
      request: last ? last.request : null,
      name: last ? (last.ctx.name || last.ctx.names || null) : null,
      sessionId: button.getAttribute("data-session-id") || null
    };
    var purchase = new CustomEvent("product:purchase", { bubbles: true, cancelable: true, detail: detail });
    var unhandled = button.dispatchEvent(purchase);
    var notice = document.getElementById("cta-notice");
    if (unhandled && notice) {
      notice.textContent = button.getAttribute("data-notice") || M.comingSoon;
      notice.hidden = false;
    }
  });

  /* ---------- init ---------- */

  people.forEach(function (person) {
    el(person, "date").setAttribute("max", todayIso());
    initCombo(el(person, "city"));
    ["name", "date", "time", "city"].forEach(function (field) {
      el(person, field).addEventListener("input", function () {
        clearFieldError(el(person, field));
        if (field === "name") delete nameChoices[person]; // a changed name invalidates the syllable picked for it
      });
    });
  });

  if (modeButtons.length && (/[?&]mode=name\b/.test(window.location.search) || window.location.hash === "#by-name")) setMode("name", false);

  // Convenience: details entered on one single-person tool are prefilled on the others (this tab only).
  try {
    var saved = JSON.parse(window.sessionStorage.getItem(STORE_KEY) || "null");
    if (saved) {
      people.forEach(function (person) {
        var source = saved[person];
        if (!source) return;
        ["name", "date", "time", "city"].forEach(function (field) {
          if (source[field] && !el(person, field).value) el(person, field).value = source[field];
        });
      });
    }
  } catch (ignore) { /* no storage */ }
})();
