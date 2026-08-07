"""Display — white-point, tint and brightness correction for the frontend.

Serves the frontend module (filter + card) as an extra module URL so every
browser loads it automatically. Each config entry is a named PROFILE — one
light entity (color temp = white point, hs = tint, brightness, off =
native); devices bind to a profile on the display-card (stored in that
browser's localStorage), and no binding means native output.
"""
from __future__ import annotations

from aiohttp import web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_when_setup

from .const import DOMAIN, FRONTEND_SCRIPT_URL

import logging

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT]
DATA_FRONTEND_REGISTERED = "frontend_registered"


class DisplayScriptView(HomeAssistantView):
    """Serve the module with Cache-Control: no-cache.

    A header-less response (StaticPathConfig cache_headers=False) is NOT
    "don't cache" — browsers apply heuristic freshness from Last-Modified
    and WebViews reuse stale copies across reloads. no-cache forces an
    ETag revalidation every load; unchanged files still 304."""

    url = FRONTEND_SCRIPT_URL
    name = "display:script"
    requires_auth = False

    def __init__(self, path: str) -> None:
        self._path = path

    async def get(self, request):
        return web.FileResponse(
            self._path, headers={"Cache-Control": "no-cache"}
        )


class BootScriptView(DisplayScriptView):
    """The frozen first-paint shim (see boot.js)."""

    url = "/display/boot.js"
    name = "display:boot"


async def _async_register_resource(hass: HomeAssistant, version: str) -> None:
    """Ensure a versioned lovelace resource entry for the module.

    NOT extra_js_url: that list is baked into index.html, and the frontend's
    service worker serves a CACHED app shell for navigations — clients keep
    loading the old script URL (and its cached body) through every version
    bump and restart. The lovelace resource list arrives over the websocket
    fresh on every dashboard load, so a ?v change reliably delivers new code.
    """
    target = f"{FRONTEND_SCRIPT_URL}?v={version}"
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.warning("Lovelace resources unavailable; add '%s' as a module", target)
        return
    await resources.async_get_info()
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] != FRONTEND_SCRIPT_URL:
            continue
        if item["url"] != target:
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": target}
            )
            _LOGGER.info("Updated lovelace resource to %s", target)
        return
    await resources.async_create_item({"res_type": "module", "url": target})
    _LOGGER.info("Registered lovelace resource %s", target)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_FRONTEND_REGISTERED):
        integration = await async_get_integration(hass, DOMAIN)
        hass.http.register_view(
            DisplayScriptView(
                hass.config.path("custom_components/display/display.js")
            )
        )
        hass.http.register_view(
            BootScriptView(hass.config.path("custom_components/display/boot.js"))
        )
        # extra_js_url = part of the app shell = runs at logo time. The shell
        # (and this URL) may be served stale by the service worker, which is
        # fine: boot.js is frozen and only replays the cached matrix.
        add_extra_js_url(hass, "/display/boot.js")

        async def register_script(hass: HomeAssistant, _component: str) -> None:
            await _async_register_resource(hass, integration.version)

        async_when_setup(hass, "lovelace", register_script)
        data[DATA_FRONTEND_REGISTERED] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
