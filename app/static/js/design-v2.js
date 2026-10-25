/* PROTOTYPE (?design=v2). Two things: collapse the long prose sections ON A PHONE, and pair the kundali
 * with the positions table on a wide screen.
 *
 * Why it is JavaScript at all. The sections ship as `<details open>`, so the content is in the HTML and
 * expanded for a crawler, for a reader with JavaScript off, and on every screen with the room for it. There
 * is no way in CSS to say "closed below 700px, open above it": `open` is markup state, not a style, and the
 * alternatives - rendering the section twice, or clamping it with a height and faking a control - either
 * duplicate content or leave a reader unable to get at it.
 *
 * So: three lines, no dependency, no inline script (the CSP is `self` only), and it runs once. If it never
 * runs, the page is the whole page, which is the right way for this to fail.
 */
(function () {
  "use strict";
  if (!window.matchMedia || !window.matchMedia("(max-width: 700px)").matches) return;
  var sections = document.querySelectorAll("details.v2-readmore[open]");
  for (var i = 0; i < sections.length; i++) sections[i].removeAttribute("open");
})();

/* THE CHART AND THE POSITIONS TABLE, SIDE BY SIDE. A rendered kundali is a 480px square and the table beside
 * it is the thing a reader checks it against, so on a wide screen they belong on one row - that is most of
 * what the extra width on a result page is for.
 *
 * It is done here, in the prototype's own script, because render.js emits a FLAT list of <section class=
 * "block"> and pairing two of them needs a wrapper element that no CSS can create. render.js is shared with
 * the live page, so adding the wrapper there would change the live result for everyone; adding it here
 * changes it only under the flag. `.chart-block` is the renderer's own class, and the table is the block
 * that follows it - the same adjacency the renderer has always produced.
 *
 * A MutationObserver rather than a hook, because the result arrives when the fetch does and app.js offers
 * nothing to listen to. It re-pairs after every submit, and does nothing on a page with no result.
 */
(function () {
  "use strict";
  var body = document.getElementById("result-body");
  if (!body || !window.MutationObserver) return;

  function pair() {
    var chart = body.querySelector(".chart-block");
    if (!chart || !chart.parentNode) return;
    if (chart.parentNode.className === "v2-chartpair") return;      // already paired
    var table = chart.nextElementSibling;
    if (!table || table.className.indexOf("block") === -1) return;
    var wrapper = document.createElement("div");
    wrapper.className = "v2-chartpair";
    chart.parentNode.insertBefore(wrapper, chart);
    wrapper.appendChild(chart);
    wrapper.appendChild(table);
  }

  new window.MutationObserver(pair).observe(body, {childList: true});
  pair();
})();
