/* The blog index's category filter.
 *
 * A FILE, NOT AN INLINE SCRIPT: the Content-Security-Policy here is `script-src 'self'`, and an inline
 * version is blocked outright - which costs the feature silently, with nothing but a console line.
 *
 * It hides cards rather than fetching anything. A round trip to show four posts is slower than showing
 * all four, and without this file every post is listed and nothing is hidden - which is the honest
 * no-JavaScript state rather than a control that cannot work.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var bar = document.getElementById("blog-filter");
  var list = document.getElementById("blog-cards");
  var none = document.getElementById("blog-none");
  if (!bar || !list) return;

  var cards = [].slice.call(list.querySelectorAll("[data-categories]"));

  bar.addEventListener("click", function (event) {
    var chip = event.target.closest("[data-filter]");
    if (!chip) return;

    var wanted = chip.getAttribute("data-filter") || "";
    var shown = 0;
    cards.forEach(function (card) {
      var categories = (card.getAttribute("data-categories") || "").split(" ");
      var match = !wanted || categories.indexOf(wanted) !== -1;
      card.hidden = !match;
      if (match) shown += 1;
    });

    [].slice.call(bar.querySelectorAll("[data-filter]")).forEach(function (other) {
      var on = other === chip;
      other.classList.toggle("is-on", on);
      other.setAttribute("aria-pressed", String(on));
    });

    // Said out loud rather than left as an empty page, which reads as a broken filter.
    if (none) none.hidden = shown !== 0;
  });
})();
