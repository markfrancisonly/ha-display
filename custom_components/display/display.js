/* Display — white-point, tint and brightness correction for displays that
   render wrong (e.g. Samsung tablets with no display WB control).

   Config entries are named PROFILES, each ONE light entity: color temp =
   white point (6500 K neutral, higher = bluer, lower = warmer), an hs color
   tints instead, brightness dims all the way down, OFF = black screen.
   Native = on at 6500 K full brightness. Tune profiles with the normal
   light UI anywhere in HA.

   On the bundled display-card every device picks the profile to bind to
   (stored in this browser's localStorage); no binding = native output.

   The correction is computed server-side (the light's rgb_matrix/rgb_gain
   attributes) and applied through an feColorMatrix filter on <body> — a real
   recolor of every rendered pixel, not an overlay. body, NOT html: a filter
   on the root element misses fixed/promoted compositing layers in Chromium
   (the sidebar escaped it); on a non-root element the filter is a containing
   block, so those layers paint inside it. Mobile WebView compositors promote
   fixed chrome out of any page-level filter (Android WebView the sidebar,
   iOS WKWebView the header AND sidebar; a backdrop-filter veil caught
   neither and WebKit never renders SVG backdrops) — those elements get the
   correction applied directly via per-shadow-root scoped filters, see
   CHROME_FIX. boot.js replays the cached matrix at first paint. */

const SVG_ID = "display-svg";
const FILTER_ID = "display-filter";
const SVGNS = "http://www.w3.org/2000/svg";
const PROFILE_KEY = "display_profile";
const LEGACY_PROFILE_KEY = "white_balance_profile";
const CHANGE_EVENT = "display-changed";
const NEUTRAL = 6500;

const entities = new Map(); // light entity_id -> {gains, on, kelvin, brightness, hs}

function storedProfile() {
  try {
    return localStorage.getItem(PROFILE_KEY) || "";
  } catch (e) {
    return "";
  }
}

function setProfile(id) {
  try {
    if (id) localStorage.setItem(PROFILE_KEY, id);
    else localStorage.removeItem(PROFILE_KEY);
  } catch (e) {}
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function matrixEl() {
  let svg = document.getElementById(SVG_ID);
  if (!svg) {
    svg = document.createElementNS(SVGNS, "svg");
    svg.id = SVG_ID;
    svg.setAttribute("width", "0");
    svg.setAttribute("height", "0");
    svg.style.position = "fixed";
    const filter = document.createElementNS(SVGNS, "filter");
    filter.id = FILTER_ID;
    // scale gamma-encoded values, like a display LUT (default is linearRGB)
    filter.setAttribute("color-interpolation-filters", "sRGB");
    const m = document.createElementNS(SVGNS, "feColorMatrix");
    m.setAttribute("type", "matrix");
    filter.appendChild(m);
    svg.appendChild(filter);
    document.body.appendChild(svg);
  }
  return svg.querySelector("feColorMatrix");
}

const IDENTITY9 = [1, 0, 0, 0, 1, 0, 0, 0, 1];

function diagonal([r, g, b]) {
  return [r, 0, 0, 0, g, 0, 0, 0, b];
}

function isIdentity(m) {
  return m.every((v, i) => Math.abs(v - IDENTITY9[i]) < 0.002);
}

// 3x3 row-major -> feColorMatrix 5x4 values
function matrixValues(m) {
  const f = (v) => v.toFixed(4);
  return (
    `${f(m[0])} ${f(m[1])} ${f(m[2])} 0 0  ` +
    `${f(m[3])} ${f(m[4])} ${f(m[5])} 0 0  ` +
    `${f(m[6])} ${f(m[7])} ${f(m[8])} 0 0  0 0 0 1 0`
  );
}

/* Mobile WebViews composite fixed chrome outside any page-level filter —
   Android WebView the sidebar, iOS WKWebView the header AND sidebar. Those
   elements get the same correction applied DIRECTLY. UA-gated: contained
   engines would double-apply. Selector walk mirrors lockdown.js. */
const CHROME_FIX = (() => {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return "ios";
  if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) return "ios"; // iPadOS
  if (/Android/.test(ua)) return "android";
  return null;
})();

const SCOPED_ID = "display-scoped";

// WebKit resolves url(#) strictly within the element's tree scope and does
// not render external (data-URI) filter documents at all — so every shadow
// root hosting corrected chrome gets its own copy of the filter definition.
function scopedFilter(root, m) {
  let svg = root.querySelector(`#${SCOPED_ID}`);
  if (!svg) {
    svg = document.createElementNS(SVGNS, "svg");
    svg.id = SCOPED_ID;
    svg.setAttribute("width", "0");
    svg.setAttribute("height", "0");
    svg.style.position = "fixed";
    const filter = document.createElementNS(SVGNS, "filter");
    filter.id = `${SCOPED_ID}-f`;
    filter.setAttribute("color-interpolation-filters", "sRGB");
    const fe = document.createElementNS(SVGNS, "feColorMatrix");
    fe.setAttribute("type", "matrix");
    filter.appendChild(fe);
    svg.appendChild(filter);
    root.appendChild(svg);
  }
  svg.querySelector("feColorMatrix").setAttribute("values", matrixValues(m));
  return `url(#${SCOPED_ID}-f)`;
}

// WebKit resolves url() on a SHADOW HOST against the host's own shadow tree,
// so hosts are filtered via their rendered inner elements instead (all
// non-empty children — e.g. card-mod injects zero-size style carriers).
function filterTargets(el) {
  if (!el) return [];
  if (!el.shadowRoot) return [el];
  const inner = [...el.shadowRoot.children].filter(
    (c) =>
      !/^(STYLE|LINK|SVG|TEMPLATE)$/.test(c.tagName) &&
      (c.offsetWidth || c.offsetHeight)
  );
  return inner.length ? inner : [el];
}

function chromeTargets() {
  const out = [];
  const main = document
    .querySelector("home-assistant")
    ?.shadowRoot?.querySelector("home-assistant-main")?.shadowRoot;
  if (!main) return out;
  out.push(...filterTargets(main.querySelector("ha-sidebar")));
  if (CHROME_FIX === "ios") {
    const huiRoot = main
      .querySelector("partial-panel-resolver")
      ?.firstElementChild?.shadowRoot?.querySelector("hui-root")?.shadowRoot;
    const header =
      huiRoot?.querySelector(".header") ||
      huiRoot?.querySelector("ha-top-app-bar-fixed") ||
      huiRoot?.querySelector("ha-header-bar");
    out.push(...filterTargets(header));
  }
  return out;
}

let lastMatrix = IDENTITY9;
let chromeTinted = new Set();

function applyChrome(m) {
  if (!CHROME_FIX) return;
  const want = isIdentity(m) ? [] : chromeTargets();
  for (const el of chromeTinted)
    if (!want.includes(el)) el.style.removeProperty("filter");
  chromeTinted = new Set(want);
  for (const el of want) {
    const url = scopedFilter(el.getRootNode(), m);
    if (el.style.filter !== url) el.style.filter = url;
  }
}

// panels remount on navigation, so the chrome set needs reconciling
if (CHROME_FIX) setInterval(() => applyChrome(lastMatrix), 1000);

function applyMatrix(m) {
  lastMatrix = m;
  if (isIdentity(m)) {
    document.body.style.removeProperty("filter");
  } else {
    matrixEl().setAttribute("values", matrixValues(m));
    document.body.style.filter = `url(#${FILTER_ID})`;
  }
  applyChrome(m);
  // a veil-era copy of this script may have left its overlay behind
  document.getElementById("display-veil")?.remove();
}

const MATRIX_CACHE_KEY = "display_matrix";

// the last correction is cached per browser so it applies at FIRST PAINT,
// before the backend connection is even up; the live state re-applies over it
try {
  const cached = JSON.parse(localStorage.getItem(MATRIX_CACHE_KEY) || "null");
  if (Array.isArray(cached) && cached.length === 9) applyMatrix(cached);
} catch (e) {}

// bindings written by the number-entity era point at number.<x>_white_point;
// rewrite them to the profile's light entity once it is seen
function migrateBinding() {
  const id = storedProfile();
  if (!id || entities.has(id)) return;
  const m = id.match(/^number\.(.+)_white_point$/);
  if (m && entities.has(`light.${m[1]}_display`)) {
    setProfile(`light.${m[1]}_display`);
  }
}

function recompute() {
  migrateBinding();
  const id = storedProfile();
  const bound = id ? entities.get(id) : null;
  const m = bound ? bound.matrix : IDENTITY9;
  try {
    localStorage.setItem(MATRIX_CACHE_KEY, JSON.stringify(m));
  } catch (e) {}
  applyMatrix(m);
}

function consider(state) {
  const a = state.attributes;
  if (!a || !Array.isArray(a.rgb_gain) || a.rgb_gain.length !== 3) {
    return entities.delete(state.entity_id);
  }
  entities.set(state.entity_id, {
    // full Bradford matrix when the backend provides it; older backends
    // fall back to the diagonal gains
    matrix:
      Array.isArray(a.rgb_matrix) && a.rgb_matrix.length === 9
        ? a.rgb_matrix.map(Number)
        : diagonal(a.rgb_gain.map(Number)),
    on: state.state === "on",
    kelvin: a.color_temp_kelvin ? Math.round(a.color_temp_kelvin) : null,
    brightness: a.brightness ? Math.round((a.brightness / 255) * 100) : null,
    hs: a.color_mode === "hs" ? a.hs_color : null,
  });
  return true;
}

function waitFor(fn) {
  return new Promise((resolve) => {
    const poll = () => {
      const v = fn();
      if (v) resolve(v);
      else setTimeout(poll, 100);
    };
    poll();
  });
}

window.addEventListener(CHANGE_EVENT, recompute);
// storage events only fire in OTHER tabs; same-tab changes use CHANGE_EVENT
window.addEventListener("storage", (ev) => {
  if (ev.key === PROFILE_KEY) recompute();
});
try {
  // migrate the white_balance-era key name (entity migration happens live)
  const legacy = localStorage.getItem(LEGACY_PROFILE_KEY);
  if (legacy && !localStorage.getItem(PROFILE_KEY))
    localStorage.setItem(PROFILE_KEY, legacy);
  localStorage.removeItem(LEGACY_PROFILE_KEY);
} catch (e) {}

(async () => {
  const haEl = await waitFor(() => document.querySelector("home-assistant"));
  const hass = await waitFor(() => haEl.hass);
  const conn = hass.connection;

  const refresh = async () => {
    const states = await conn.sendMessagePromise({ type: "get_states" });
    entities.clear();
    for (const s of states) {
      if (s.entity_id.startsWith("light.")) consider(s);
    }
    recompute();
  };

  await conn.subscribeEvents((ev) => {
    const { entity_id: id, new_state: ns } = ev.data;
    if (!id.startsWith("light.")) return;
    if (ns ? consider(ns) : entities.delete(id)) recompute();
  }, "state_changed");
  conn.addEventListener("ready", refresh); // re-sync after a reconnect
  await refresh();
})();

/* ---- the card: bind this device to a profile (tune via the light) ---- */

class DisplayCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 2;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) this._sync();
  }

  connectedCallback() {
    this._onChange = () => this._sync();
    window.addEventListener(CHANGE_EVENT, this._onChange);
    this._render();
  }

  disconnectedCallback() {
    window.removeEventListener(CHANGE_EVENT, this._onChange);
  }

  _profiles() {
    const states = (this._hass && this._hass.states) || {};
    const out = [];
    for (const id of Object.keys(states)) {
      if (!id.startsWith("light.")) continue;
      const a = states[id].attributes || {};
      if (Array.isArray(a.rgb_gain) && a.rgb_gain.length === 3) {
        out.push({
          id,
          name: (a.friendly_name || id).replace(/ Display$/, ""),
          on: states[id].state === "on",
          kelvin: a.color_temp_kelvin ? Math.round(a.color_temp_kelvin) : null,
          brightness: a.brightness ? Math.round((a.brightness / 255) * 100) : null,
          hs: a.color_mode === "hs",
        });
      }
    }
    return out.sort((x, y) => x.name.localeCompare(y.name));
  }

  _describe(p) {
    if (!p.on) return "off — black";
    if (p.hs) return `tinted, ${p.brightness ?? 100}%`;
    const k = p.kelvin ?? NEUTRAL;
    const dir = Math.abs(k - NEUTRAL) < 25 ? "native" : k > NEUTRAL ? "bluer" : "warmer";
    return `${k} K (${dir}), ${p.brightness ?? 100}%`;
  }

  _render() {
    if (this._card) {
      this._sync();
      return;
    }
    this._card = document.createElement("ha-card");
    this._card.header = "Display — this device";
    const body = document.createElement("div");
    body.style.cssText = "padding:0 16px 16px";

    this._select = document.createElement("select");
    this._select.style.cssText =
      "width:100%;padding:8px;font:inherit;color:var(--primary-text-color);" +
      "background:var(--card-background-color);" +
      "border:1px solid var(--divider-color);border-radius:4px";
    this._select.addEventListener("change", () => {
      setProfile(this._select.value);
      this._sig = null;
      this._sync();
    });

    this._status = document.createElement("div");
    this._status.style.cssText =
      "margin-top:12px;color:var(--secondary-text-color);font-size:0.9em";

    body.appendChild(this._select);
    body.appendChild(this._status);
    this._card.appendChild(body);
    this.appendChild(this._card);
    this._sync();
  }

  _sync() {
    const current = storedProfile();
    const profiles = this._profiles();
    const sig = JSON.stringify([current, profiles]);
    if (sig !== this._sig) {
      this._sig = sig;
      this._select.innerHTML = "";
      const off = document.createElement("option");
      off.value = "";
      off.textContent = "Unbound — native output";
      this._select.appendChild(off);
      let found = false;
      for (const p of profiles) {
        const el = document.createElement("option");
        el.value = p.id;
        el.textContent = `${p.name} (${this._describe(p)})`;
        if (p.id === current) found = true;
        this._select.appendChild(el);
      }
      if (current && !found) {
        const el = document.createElement("option");
        el.value = current;
        el.textContent = `${current} (missing)`;
        this._select.appendChild(el);
      }
      this._select.value = current;
    }

    const bound = profiles.find((p) => p.id === current);
    this._status.textContent = bound
      ? `Following “${bound.name}” — adjust it like a light, from anywhere.`
      : "This device shows native output.";
  }
}

customElements.define("display-card", DisplayCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "display-card",
  name: "Display",
  description: "Bind this display to a Display profile (a light entity).",
});
