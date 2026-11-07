/* Start a NUMEROLOGY consultation from a name and a date of birth.
 *
 * WHY THIS EXISTS AS ITS OWN FILE. Every numerology CTA used to open the chart chat, which asked
 * for a birth time and a city those pages never collect, and lost the reader's numbers and the
 * question they had just tapped. The server half is POST /api/consultation/start-numerology.
 *
 * IT DOES NOT TOUCH app.js OR chat.js. app.js posts the birth form and fires `tool:result`; this
 * posts the two-field form and fires THE SAME EVENT, so chat.js opens the conversation without
 * knowing which form produced it. The chart chat is a live paid feature and its scripts are left
 * exactly as they were.
 *
 * The question from the chip is a PREFILL: it is typed into the box for the reader and nothing is
 * sent until they press send.
 */
(function () {
  "use strict";

  var form = document.getElementById("tool-form");
  if (!form || form.getAttribute("data-numerology") !== "1") return;

  var status = document.getElementById("form-status");
  var endpoint = form.getAttribute("data-endpoint");
  var lang = form.getAttribute("data-lang") || "en";
  var pending = false;

  function say(message) {
    if (!status) return;
    status.textContent = message;
    status.hidden = !message;
  }

  function value(id) {
    var el = document.getElementById(id);
    return el ? el.value.trim() : "";
  }

  function isoDate() {
    var day = parseInt(value("num-chat-day"), 10);
    var month = parseInt(value("num-chat-month"), 10);
    var year = parseInt(value("num-chat-year"), 10);
    if (!day || !month || !year) return null;
    // THE DATE IS CHECKED HERE TOO, not only on the server. Date() rolls 31 February over to
    // 2 March without complaining, so a reader would be given a reading for a day they did not
    // type. Comparing the parts back is what catches it.
    var made = new Date(Date.UTC(year, month - 1, day));
    if (made.getUTCFullYear() !== year || made.getUTCMonth() !== month - 1 ||
        made.getUTCDate() !== day) return null;
    return year + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0");
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (pending) return;
    var date = isoDate();
    if (!date) {
      say(form.getAttribute("data-bad-date") ||
          "That date does not exist. Check the day and the month.");
      return;
    }
    pending = true;
    say("");
    var body = {date: date, language: lang, name: value("num-chat-name") || null};
    var question = (document.getElementById("ask-first") || {}).value;
    if (question && question.trim()) body.question = question.trim();

    fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      credentials: "same-origin",
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (data) { return {ok: response.ok, data: data}; });
    }).then(function (result) {
      pending = false;
      if (!result.ok || !result.data || !result.data.session_id) {
        var detail = result.data && result.data.detail;
        say((detail && (detail.message || detail)) || "Could not start the consultation.");
        return;
      }
      // The same event app.js fires. chat.js opens the conversation from it.
      document.dispatchEvent(new CustomEvent("tool:result", {
        detail: {response: result.data}
      }));
      // The chip's question, typed into the box and not sent. chat.js has just rebuilt the input,
      // so this runs after it rather than before.
      var prefill = result.data.prefill;
      if (prefill) {
        window.setTimeout(function () {
          var input = document.getElementById("chat-input") ||
                      document.querySelector("#chat textarea, #chat input[type=text]");
          if (input && !input.value) {
            input.value = prefill;
            input.focus();
          }
        }, 0);
      }
    }).catch(function () {
      pending = false;
      say("Could not reach the server. Please try again.");
    });
  });
})();
