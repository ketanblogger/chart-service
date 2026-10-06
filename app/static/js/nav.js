/* Header navigation (every page, deferred, no dependencies).
 *
 * The nav used to be a horizontal scroller. That put a visible scrollbar under it on every desktop that does
 * not use overlay scrollbars, and a scrolling child also hides its own overflow from any document-width
 * check - so the bar could sit there while every width test passed. It is a wrapping list now.
 *
 * Wrapping alone would cost a second row of header on a phone, so below the breakpoint this collapses the
 * list behind a disclosure button. The button ships `hidden` and is revealed here, which is what keeps the
 * no-JavaScript path honest: without this file the full list is visible and wrapped, never hidden behind a
 * control that cannot open. Nothing here touches the page's scroll position, and it contains no page paths.
 */
(function () {
  "use strict";
  var nav = document.querySelector(".site-nav");
  var toggle = nav && nav.querySelector(".site-nav__toggle");
  var list = nav && nav.querySelector("ul");
  if (!nav || !toggle || !list) return;

  var narrow = window.matchMedia("(max-width: 899px)");

  function close() {
    nav.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  }

  function apply() {
    if (narrow.matches) {
      nav.classList.add("is-collapsed");
      toggle.hidden = false;
      close();
    } else {
      nav.classList.remove("is-collapsed", "is-open");
      toggle.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  }

  toggle.addEventListener("click", function () {
    var open = !nav.classList.contains("is-open");
    nav.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  });

  // Following a link inside the collapsed menu leaves the page anyway; Escape is for changing your mind.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && nav.classList.contains("is-open")) {
      close();
      toggle.focus();
    }
  });

  if (narrow.addEventListener) narrow.addEventListener("change", apply);
  else if (narrow.addListener) narrow.addListener(apply);
  apply();
})();
