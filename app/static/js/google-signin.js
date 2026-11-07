/* "Continue with Google", loaded only on a page that asked for it.
 *
 * The button is rendered by Google's own library, which is the only way to get One Tap and the official
 * mark; our part is to hand it the client id, take the credential it returns, and post that to our own
 * endpoint - which is where the token is actually checked. NOTHING here decides whether somebody is
 * signed in: a credential that reaches this file is just a string until the server has verified its
 * audience, its issuer, its expiry and that Google says the address is verified.
 *
 * The third-party script is injected from here rather than written into the page so that it loads only
 * where the flag put the placeholder - and the Content-Security-Policy that allows it is widened only
 * while the same flag is on, so turning the flag off closes both doors at once.
 */
(function () {
  "use strict";

  var holder = document.getElementById("google-signin");
  if (!holder || !holder.dataset.clientId) return;
  var problem = document.getElementById("google-error");

  function failed() {
    if (!problem) return;
    problem.hidden = false;
  }

  function onCredential(response) {
    if (!response || !response.credential) { failed(); return; }
    fetch("/api/auth/google", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ credential: response.credential })
    }).then(function (result) {
      if (!result.ok) { failed(); return; }
      /* Where the e-mail code would have gone: back to whatever they were doing. */
      var next = holder.dataset.next;
      window.location.assign(next && next.charAt(0) === "/" ? next : "/");
    }).catch(failed);
  }

  function start() {
    if (!window.google || !window.google.accounts || !window.google.accounts.id) { failed(); return; }
    window.google.accounts.id.initialize({
      client_id: holder.dataset.clientId,
      callback: onCredential,
      /* One Tap is offered, never forced: somebody with no Google session sees the ordinary button and
         the e-mail code sitting next to it. */
      auto_select: false,
      cancel_on_tap_outside: true
    });
    window.google.accounts.id.renderButton(holder, {
      type: "standard", theme: "outline", size: "large", width: 280,
      text: "continue_with", shape: "rectangular"
    });
  }

  var tag = document.createElement("script");
  tag.src = "https://accounts.google.com/gsi/client";
  tag.async = true;
  tag.defer = true;
  tag.onload = start;
  tag.onerror = failed;
  document.head.appendChild(tag);
})();
