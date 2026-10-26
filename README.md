# Display

Correct the **white point, tint and brightness of the Home Assistant
frontend itself** — for displays that render wrong and offer no controls of
their own (wall-mounted tablets that show pure white slightly warm, for
example).

Every device opts in per browser, and everything is tuned through a normal
**light entity** — from anywhere, including scenes, automations and voice.

## How it works

- Each **config entry is a named profile**: one light entity
  (`light.<name>_display`).
  - **Color temp** = the white point, full 2000–12000 K wheel: 6500 =
    untouched, higher = bluer, lower = warmer.
  - **An hs color** tints instead (e.g. a red night mode).
  - **Brightness** dims in the same matrix, all the way down.
  - **Off** = black screen — the profile behaves like a real light.
    Native output = on at 6500 K, full brightness.
- On the bundled `display-card` each login session **opts in to a profile**
  with a dropdown (stored in that browser's localStorage, key
  `display_profile`). No binding = native output, always — an unbound
  device is never affected, not even by off.
- A bound device whose profile isn't loaded (Home Assistant restarting, or
  the profile deleted) keeps its last correction; pick Unbound on the card
  for native output.
- Tuning happens through the normal light UI — more-info dialog, tile
  cards, scenes, automations, voice — and adjusts every device bound to
  that profile, from anywhere.
- Shared correction = several devices bound to one profile; per-device
  correction = a dedicated profile for that display.

Gains are computed server-side (blackbody curve for color temp, HSV for
tints, times brightness) and published as the light's `rgb_gain` attribute
— the single ground truth devices apply. The frontend module (a dashboard
resource the integration adds itself) applies them through an SVG
`feColorMatrix` filter on `<body>`. That recolors every rendered
pixel — UI, images, camera streams — it is **not** a translucent overlay.
Because gains only attenuate (nothing can exceed 100% without clipping
white), going bluer dims red/green slightly and going warmer dims blue —
the same trade every software white-balance shift makes.

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markfrancisonly&repository=ha-display&category=integration)

Or manually add the custom repository:

<details>
<summary>Step-by-step HACS installation</summary>

1. Open **HACS** in your Home Assistant dashboard
2. Click the **⋮** menu (top right) → **Custom repositories**
3. Add this URL and set the category to **Integration**, then click **Add**:
   ```
   https://github.com/markfrancisonly/ha-display
   ```
4. The repository now appears in the custom repositories list. Close the dialog.
5. Back in HACS, search for **Display** and open the result
6. Click **Download** (or **Install**) and confirm
7. **Restart Home Assistant**

</details>

### Manual Installation

1. Download `display.zip` from the [latest release](https://github.com/markfrancisonly/ha-display/releases)
2. Extract it into `custom_components/display/` inside your HA config directory
3. Restart Home Assistant

### Setup

Add the integration (Settings → Devices & Services → Add Integration →
Display) once per profile you want — a profile is just a name.

The frontend module is added to your dashboard resources automatically.
Dashboards in YAML mode need it added by hand: `/display/display.js` as a
JavaScript module.

## Usage

1. Create a profile (e.g. `Tablets`) — you get `light.tablets_display`.
2. Put the card on any dashboard the target devices can reach:

   ```yaml
   type: custom:display-card
   ```

3. On each device that should be corrected, pick the profile in the card's
   dropdown. Done — the device now follows that light.
4. Tune the light from anywhere. A tile card works well next to the
   binding card:

   ```yaml
   type: tile
   entity: light.tablets_display
   features:
     - type: light-brightness
     - type: light-color-temp
   ```

Remote per-device binding (e.g. wall tablets, with
[browser_mod](https://github.com/thomasloven/hass-browser_mod)) without
touching the screen:

```yaml
service: browser_mod.javascript
data:
  browser_id: <id>
  code: >-
    localStorage.setItem('display_profile', 'light.living_room_display');
    window.dispatchEvent(new Event('display-changed'));
```

## Notes

- The module is served with an explicit `Cache-Control: no-cache` view —
  a header-less static response is heuristically cached by WebViews, which
  then reuse stale copies across reloads. no-cache forces an ETag
  revalidation every load; unchanged files still 304.
- Filter target is `<body>`, NOT `<html>`: a filter on the root element
  misses fixed/promoted compositing layers in Chromium (the sidebar escapes
  it); on a non-root element the filter is a containing block, so those
  layers paint inside it.
- `color-interpolation-filters="sRGB"` is set on the filter so gains scale
  gamma-encoded values like a display LUT; without it SVG filters operate in
  linear RGB and the shift comes out too strong.
- A profile's tune is preserved across restarts even while off (restore
  extra data — a light's plain attributes are stripped when off).
- Because off blacks the bound displays, keep profile lights out of
  blanket "all lights off" groups/scenes unless that's what you want.
- Brand icons ship in `custom_components/display/brand/` (HA 2026.3+).
