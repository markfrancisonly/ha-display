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

from .const import DOMAIN, FRONTEND_SCRIPT_URL

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_FRONTEND_REGISTERED):
        integration = await async_get_integration(hass, DOMAIN)
        hass.http.register_view(
            DisplayScriptView(
                hass.config.path("custom_components/display/display.js")
            )
        )
        add_extra_js_url(hass, f"{FRONTEND_SCRIPT_URL}?{integration.version}")
        data[DATA_FRONTEND_REGISTERED] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
