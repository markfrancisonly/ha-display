/* Display boot shim — applies the cached correction at FIRST PAINT, before
   the frontend has even connected. Loaded via extra_js_url (part of the app
   shell), so it runs at logo time; the main module (lovelace resource) takes
   over once live state arrives. DELIBERATELY FROZEN: the service worker may
   serve the app shell (and this file) stale across releases, so this shim
   must never carry logic that needs updating — it only replays the last
   matrix the main module cached in localStorage. */
(() => {
  try {
    // iOS is unsupported (renders native) — see display.js
    if (
      /iPhone|iPad|iPod/.test(navigator.userAgent) ||
      (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1)
    )
      return;
    const m = JSON.parse(localStorage.getItem("display_matrix") || "null");
    if (!Array.isArray(m) || m.length !== 9) return;
    const I = [1, 0, 0, 0, 1, 0, 0, 0, 1];
    if (m.every((v, i) => Math.abs(v - I[i]) < 0.002)) return;
    const NS = "http://www.w3.org/2000/svg";
    const f = (v) => Number(v).toFixed(4);
    const values =
      `${f(m[0])} ${f(m[1])} ${f(m[2])} 0 0  ` +
      `${f(m[3])} ${f(m[4])} ${f(m[5])} 0 0  ` +
      `${f(m[6])} ${f(m[7])} ${f(m[8])} 0 0  0 0 0 1 0`;
    const put = () => {
      if (!document.body) return;
      if (!document.getElementById("display-svg")) {
        const svg = document.createElementNS(NS, "svg");
        svg.id = "display-svg";
        svg.setAttribute("width", "0");
        svg.setAttribute("height", "0");
        svg.style.position = "fixed";
        const filter = document.createElementNS(NS, "filter");
        filter.id = "display-filter";
        filter.setAttribute("color-interpolation-filters", "sRGB");
        const fe = document.createElementNS(NS, "feColorMatrix");
        fe.setAttribute("type", "matrix");
        fe.setAttribute("values", values);
        filter.appendChild(fe);
        svg.appendChild(filter);
        document.body.appendChild(svg);
      }
      if (!document.body.style.filter)
        document.body.style.filter = "url(#display-filter)";
    };
    // The frontend boot can clear body inline styles after a one-shot apply,
    // leaving the page bare until the main module loads (slow on phones) —
    // keep re-asserting until the module (window.__displayLive) takes over.
    let n = 0;
    const tick = () => {
      if (window.__displayLive || n++ > 100) return;
      put();
      setTimeout(tick, 150);
    };
    tick();
  } catch (e) {}
})();
