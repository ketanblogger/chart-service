/* Header navigation (every page, deferred, no dependencies).
 *
 * The nav used to be a horizontal scroller. That put a visible scrollbar under it on every desktop that does
 * not use overlay scrollbars, and a scrolling child also hides its own overflow from any document-width
 * check - so the bar could sit there while every width test passed. It is a wrapping list now.
 *
 * Wrapping alone would cost a second row of header on a phone, so below the breakpoint the list is
 * collapsed behind a disclosure button. THAT STATE IS DECIDED BY A MEDIA QUERY IN site.css, not here.
 * It used to be decided here - this file added `is-collapsed` and revealed the button after it ran -
 * and on a phone that meant the header painted as a wrapped list 347px tall and snapped to 122px when
 * this deferred script executed, roughly a second in on a slow connection. Every page's content moved
 * up 128px with it: 0.13 CLS, the largest shift on the site, and on every page.
 *
 * So this file no longer decides anything structural. It opens and closes, and that is all. The
 * no-JavaScript path is kept honest by a <noscript> block in base.html, which restores the full list
 * and hides a button that could not open anything - the same guarantee this comment used to describe,
 * moved to where it costs nothing.
 *
 * Nothing here touches the page's scroll position, and it contains no page paths.
 */
(function () {
  "use strict";
  var nav = document.querySelector(".site-nav");
  var toggle = nav && nav.querySelector(".site-nav__toggle");
  var list = nav && nav.querySelector("ul");
  if (!nav || !toggle || !list) return;

  function close() {
    nav.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
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

  // Crossing the breakpoint with the menu open would otherwise leave `is-open` set on a desktop
  // layout, where it has no meaning. The media query is read only for that, never to decide structure.
  var narrow = window.matchMedia("(max-width: 899px)");
  function forget() { if (!narrow.matches) close(); }
  if (narrow.addEventListener) narrow.addEventListener("change", forget);
  else if (narrow.addListener) narrow.addListener(forget);
})();
