/* The admin draft editor's live checks.
 *
 * A FILE RATHER THAN AN INLINE SCRIPT because the site's Content-Security-Policy is `script-src
 * 'self'`: an inline version is blocked outright, which is exactly what happened the first time - the
 * checks never ran and the only sign was a console line nobody was reading.
 *
 * Debounced, because a check runs the whole safety pipeline and a keystroke is not a reason to. The
 * form posts normally without any of this; live feedback is the enhancement, not the mechanism.
 *
 * Urlencoded, not FormData: FormData sends multipart and this project deliberately does not install
 * python-multipart (app/blog/admin.py says why). The server refuses anything else.
 */
(function () {
  "use strict";
  var box = document.getElementById("body-md");
  var out = document.getElementById("live-checks");
  var state = document.getElementById("edit-state");
  if (!box || !out) return;

  var timer = null;
  box.addEventListener("input", function () {
    if (state) state.textContent = "unsaved";
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      var body = new URLSearchParams();
      body.append("body_md", box.value);
      fetch(box.getAttribute("data-check-url"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString()
      }).then(function (response) {
        return response.text();
      }).then(function (html) {
        out.innerHTML = html;
      }).catch(function () {
        out.textContent = "checks could not run - save and reload";
      });
    }, 700);
  });
})();
