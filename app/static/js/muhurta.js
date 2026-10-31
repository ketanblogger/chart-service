/* The muhurta finder's form. Engine only: this posts a purpose, a range and a place and renders what comes
   back. It invents nothing - every value in the table is a value the server computed, and when the server
   finds no day this says so rather than showing the nearest miss. */
(function () {
  "use strict";
  var form = document.getElementById("muhurta-form");
  if (!form) return;

  var result = document.getElementById("m-result");
  var count = document.getElementById("m-count");
  var table = document.getElementById("m-table");
  var none = document.getElementById("m-none");
  var submit = document.getElementById("m-submit");
  var city = document.getElementById("m-city");
  var list = document.getElementById("m-city-list");
  var chosen = null;
  var lastToken = null;          /* handed back by the search; the PDF will not print without it */
  var lastFilename = null;
  var lang = document.documentElement.lang || "en";

  /* The same city index the chart form uses, so a place means the same thing on both pages. */
  function lookup(term) {
    return fetch("/api/cities?q=" + encodeURIComponent(term) + "&lang=" + encodeURIComponent(lang))
      .then(function (r) { return r.ok ? r.json() : {cities: []}; })
      .then(function (data) { return data.cities || []; })
      .catch(function () { return []; });
  }

  function showCities(cities) {
    list.innerHTML = "";
    cities.slice(0, 8).forEach(function (place) {
      var li = document.createElement("li");
      li.textContent = place.label || place.name;
      li.addEventListener("mousedown", function () {
        chosen = place;
        city.value = li.textContent;
        city.setAttribute("data-chosen", "1");
        list.hidden = true;
      });
      list.appendChild(li);
    });
    list.hidden = cities.length === 0;
    city.setAttribute("aria-expanded", String(!list.hidden));
  }

  var timer = null;
  city.addEventListener("input", function () {
    chosen = null;
    city.removeAttribute("data-chosen");
    clearTimeout(timer);
    var term = city.value.trim();
    if (term.length < 2) { list.hidden = true; return; }
    timer = setTimeout(function () { lookup(term).then(showCities); }, 180);
  });
  city.addEventListener("blur", function () { setTimeout(function () { list.hidden = true; }, 150); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!chosen) { city.focus(); return; }
    submit.disabled = true;
    var body = {
      purpose: document.getElementById("m-purpose").value,
      from_date: document.getElementById("m-from").value,
      to_date: document.getElementById("m-to").value,
      lat: chosen.lat, lon: chosen.lon,
      timezone: chosen.timezone || "Asia/Kolkata",
      city: chosen.label || chosen.name,
      language: lang
    };
    fetch("/api/muhurta/search", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (data) { return {ok: response.ok, data: data}; });
    }).then(function (answer) {
      submit.disabled = false;
      result.hidden = false;
      var tbody = table.querySelector("tbody");
      tbody.innerHTML = "";
      if (!answer.ok) {
        count.textContent = (answer.data && answer.data.detail && answer.data.detail.error === "refused")
          ? (result.getAttribute("data-refused") || "") : "";
        none.hidden = false;
        table.hidden = true;
        return;
      }
      var data = answer.data;
      table.hidden = data.found === 0;
      none.hidden = data.found !== 0;
      /* The sentence, in the reader's language - "7 dates found in 31 days searched" rather than "7 / 31".
         The count is only half the answer: how many days were LOOKED AT is what tells a reader whether a
         small number means few good days or a short search. */
      var template = data.found === 1
        ? result.getAttribute("data-found-one") : result.getAttribute("data-found-many");
      count.textContent = data.found === 0 ? "" : (template || "")
        .replace("{found}", data.found).replace("{searched}", data.searched_days);
      /* The report is only offered once there is something in it to sell. */
      lastToken = data.token || null;
      var buy = document.getElementById("m-buy");
      if (buy) {
        buy.hidden = data.found === 0;
        /* `language` MUST be in here: the token is signed over the search INCLUDING the language, so a
           PDF asked for without it is a different search and is correctly refused. That is the token
           doing its job - it was this object that was wrong. */
        buy.setAttribute("data-search", JSON.stringify({
          purpose: body.purpose, from_date: body.from_date, to_date: body.to_date,
          lat: body.lat, lon: body.lon, timezone: body.timezone, city: body.city,
          language: body.language
        }));
      }
      setAskLink(data, document.getElementById("m-purpose").selectedOptions[0].textContent.trim());
      data.days.forEach(function (day) {
        var tr = document.createElement("tr");
        [day.date, day.weekday, day.sunrise, day.paksha + " " + day.tithi, day.nakshatra, day.rahu_kaal]
          .forEach(function (cell) {
            var td = document.createElement("td");
            td.textContent = cell;
            tr.appendChild(td);
          });
        tbody.appendChild(tr);
      });
    }).catch(function () {
      submit.disabled = false;
      result.hidden = false;
      none.hidden = false;
      table.hidden = true;
    });
  });
  /* The PDF. FREE, and it asks for nothing: no payment, no account, no e-mail. The search hands back a
     token with its results and the download sends it straight back, which is what ties a PDF to a search
     that was actually run. */
  var pdfBtn = document.getElementById("m-pdf-btn");
  var pdfNote = document.getElementById("m-pdf-note");

  function say(message) {
    if (!pdfNote) return;
    pdfNote.textContent = message || "";
    pdfNote.hidden = !message;
  }

  if (pdfBtn) {
    pdfBtn.addEventListener("click", function () {
      var holder = document.getElementById("m-buy");
      var search = holder && holder.getAttribute("data-search");
      if (!search) return;
      if (!lastToken) return;
      pdfBtn.disabled = true;
      say(pdfBtn.getAttribute("data-working") || "");
      fetch("/api/muhurta/pdf", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(Object.assign(JSON.parse(search), {token: lastToken}))
      }).then(function (response) {
        pdfBtn.disabled = false;
        /* The server names the file after the purpose and the date; keep that rather than inventing one. */
        var disposition = response.headers.get("Content-Disposition") || "";
        var named = /filename="([^"]+)"/.exec(disposition);
        if (named) lastFilename = named[1];
        if (!response.ok) {
          return response.json().then(function (body) {
            say((body && body.detail && body.detail.message) || "");
            return null;
          }, function () { say(""); return null; });
        }
        return response.blob();
      }).then(function (blob) {
        if (!blob) return;
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = lastFilename || "muhurta.pdf";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        say("");
      }).catch(function () { pdfBtn.disabled = false; say(""); });
    });
  }

  /* "Ask the AI Astrologer about these dates". The dates travel in the QUESTION, so the astrologer is
     explaining figures the engine computed rather than working any of them out - which is the whole
     division of labour here. */
  function setAskLink(data, purposeLabel) {
    var ask = document.getElementById("m-ask-ai");
    if (!ask || !data.days || !data.days.length) return;
    var lines = data.days.slice(0, 5).map(function (d) {
      return d.date + " (" + d.weekday + "), " + d.paksha + " " + d.tithi + ", " + d.nakshatra;
    });
    var question = (ask.getAttribute("data-prompt") || "About these dates") + " - " + purposeLabel + ": "
      + lines.join("; ") + ".";
    ask.href = ask.getAttribute("data-chat") + "?ask=" + encodeURIComponent(question);
  }
})();
