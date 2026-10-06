/* The sign-in form, and the sign-out button. No framework, no inline script (the CSP is `self` only).
 *
 * Two steps in one <form>: ask for a code, then verify it. The <form> submit handler decides which, so the
 * Enter key does the obvious thing at both steps and a password manager sees one flow rather than two.
 *
 * Without JavaScript the page says so (the <noscript> line) rather than half-working: a sign-in that posts
 * and reloads would need its own CSRF handling and a second set of server-rendered error states, for a
 * feature whose whole audience has already run app.js to get a chart.
 */
(function () {
  "use strict";

  /* Two sign-out buttons: the header chip on a wide screen and the nav entry on a phone. Only one is
     visible at a time, but both are in the document, so both are wired. */
  ["sign-out", "sign-out-nav"].forEach(function (id) {
    var button = document.getElementById(id);
    if (!button) return;
    button.addEventListener("click", function () {
      fetch("/api/auth/sign-out", {method: "POST"}).then(function () { location.href = "/"; });
    });
  });

  var form = document.getElementById("login-form");
  if (!form) return;

  var status = document.getElementById("login-status");
  var request = form.querySelector('[data-step="request"]');
  var verify = form.querySelector('[data-step="verify"]');
  var sent = document.getElementById("login-sent");
  var emailField = document.getElementById("login-email");
  var nameField = document.getElementById("login-name");
  var codeField = document.getElementById("login-code");
  var messages = {
    err_invalid: form.dataset.errInvalid, err_disposable: form.dataset.errDisposable,
    err_rate: form.dataset.errRate, err_code: form.dataset.errCode,
    err_accounts: form.dataset.errAccounts, code_sent: form.dataset.codeSent
  };

  function say(text) {
    status.textContent = text || "";
    status.hidden = !text;
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        return {ok: response.ok, status: response.status, data: data};
      });
    });
  }

  function reason(result) {
    var detail = (result.data && result.data.detail) || {};
    if (result.status === 429) return detail.reason === "too_many_accounts" ? messages.err_accounts : messages.err_rate;
    if (detail.reason === "disposable") return messages.err_disposable;
    if (detail.reason === "invalid") return messages.err_invalid;
    return messages.err_code;
  }

  function showVerify() {
    request.hidden = true;
    verify.hidden = false;
    sent.textContent = (messages.code_sent || "").replace("{email}", emailField.value.trim());
    codeField.focus();
  }

  function sendCode() {
    say("");
    return post(form.dataset.request, {
      email: emailField.value.trim(), name: (nameField && nameField.value.trim()) || "", language: form.dataset.lang
    }).then(function (result) {
      if (!result.ok) { say(reason(result)); return false; }
      showVerify();
      return true;
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!verify.hidden) {
      say("");
      post(form.dataset.verify, {email: emailField.value.trim(), code: codeField.value.trim()})
        .then(function (result) {
          if (!result.ok) { say(reason(result)); return; }
          /* Back to where they were going: the chat if they came from it, else their orders. */
          var next = new URLSearchParams(location.search).get("next");
          location.href = next && next.charAt(0) === "/" ? next : form.dataset.next;
        });
      return;
    }
    if (!emailField.value.trim()) { say(messages.err_invalid); return; }
    sendCode();
  });

  form.querySelector("[data-resend]").addEventListener("click", function () { sendCode(); });
  form.querySelector("[data-change]").addEventListener("click", function () {
    verify.hidden = true;
    request.hidden = false;
    say("");
    emailField.focus();
  });
})();
