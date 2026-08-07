from __future__ import annotations

import colorsys

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData

from .const import (
    ATTR_RGB_GAIN,
    ATTR_RGB_MATRIX,
    CONF_NAME,
    DEFAULT_KELVIN,
    DOMAIN,
    MAX_KELVIN,
    MIN_KELVIN,
)
from .helpers import rgb_gains, rgb_matrix


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    async_add_entities([DisplayLight(entry)])


class DisplayLight(RestoreEntity, LightEntity):
    """A profile's output correction, modeled as a light.

    Color temp = the white point (6500 K leaves colors alone, higher pulls
    displays bluer, lower warmer — the full 2000-12000 K wheel). An hs color
    tints instead (e.g. red night mode). Brightness dims in the same matrix,
    all the way down. OFF = black screen. Native output = on at 6500 K full
    brightness (unbound devices are never affected either way).

    The ``rgb_gain`` attribute is the ground truth devices bound to this
    profile apply."""

    _attr_should_poll = False
    _attr_icon = "mdi:monitor-shimmer"
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.HS}
    _attr_min_color_temp_kelvin = MIN_KELVIN
    _attr_max_color_temp_kelvin = MAX_KELVIN

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        name = {**entry.data, **entry.options}.get(CONF_NAME) or "Display"
        self._attr_name = f"{name} Display"
        self._attr_unique_id = f"{entry.entry_id}_display"
        self._on = True
        self._brightness = 255
        self._kelvin = float(DEFAULT_KELVIN)
        self._hs = (0.0, 0.0)
        self._mode = ColorMode.COLOR_TEMP

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def brightness(self) -> int:
        return self._brightness

    @property
    def color_mode(self) -> ColorMode:
        return self._mode

    @property
    def color_temp_kelvin(self) -> int:
        return int(self._kelvin)

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._hs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Display",
        )

    def _gains(self) -> list[float]:
        if not self._on:
            return [0.0, 0.0, 0.0]
        factor = self._brightness / 255.0
        if self._mode is ColorMode.HS and self._hs[1] > 0:
            # V=1 keeps the largest channel at 1.0 — attenuation only
            base = colorsys.hsv_to_rgb(self._hs[0] / 360.0, self._hs[1] / 100.0, 1.0)
        else:
            base = rgb_gains(self._kelvin)
        return [round(c * factor, 4) for c in base]

    def _matrix(self) -> list[float]:
        # Kelvin gets the full Bradford adaptation (hues track at deep
        # warmth); an hs tint is artistic and stays a plain channel scale.
        if not self._on:
            return [0.0] * 9
        factor = self._brightness / 255.0
        if self._mode is ColorMode.HS and self._hs[1] > 0:
            r, g, b = colorsys.hsv_to_rgb(self._hs[0] / 360.0, self._hs[1] / 100.0, 1.0)
            m = [r, 0.0, 0.0, 0.0, g, 0.0, 0.0, 0.0, b]
        else:
            m = rgb_matrix(self._kelvin)
        return [round(v * factor, 4) for v in m]

    @property
    def extra_state_attributes(self) -> dict:
        # rgb_gain stays for bound clients running older display.js
        return {ATTR_RGB_GAIN: self._gains(), ATTR_RGB_MATRIX: self._matrix()}

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        # HA strips a light's attributes while it is off; persist the tune
        # separately so an off profile keeps its values across restarts
        return RestoredExtraData(
            {
                "brightness": self._brightness,
                "kelvin": self._kelvin,
                "hs": list(self._hs),
                "mode": self._mode.value,
            }
        )

    async def async_turn_on(self, **kwargs) -> None:
        self._on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = int(kwargs[ATTR_BRIGHTNESS])
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._kelvin = float(
                min(MAX_KELVIN, max(MIN_KELVIN, kwargs[ATTR_COLOR_TEMP_KELVIN]))
            )
            self._mode = ColorMode.COLOR_TEMP
        elif ATTR_HS_COLOR in kwargs:
            self._hs = tuple(kwargs[ATTR_HS_COLOR])
            self._mode = ColorMode.HS
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._on = last.state == "on"
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            d = extra.as_dict()
            self._brightness = int(d.get("brightness", 255))
            self._kelvin = float(d.get("kelvin", DEFAULT_KELVIN))
            self._hs = tuple(d.get("hs", (0.0, 0.0)))
            self._mode = ColorMode.HS if d.get("mode") == "hs" else ColorMode.COLOR_TEMP
        elif last is not None:
            a = last.attributes
            if a.get("brightness"):
                self._brightness = int(a["brightness"])
            if a.get("color_temp_kelvin"):
                self._kelvin = float(a["color_temp_kelvin"])
            if a.get("hs_color"):
                self._hs = tuple(a["hs_color"])
            if a.get("color_mode") == "hs":
                self._mode = ColorMode.HS
        self.async_write_ha_state()
