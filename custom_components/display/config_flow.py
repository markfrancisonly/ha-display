from __future__ import annotations

from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .const import CONF_NAME, DOMAIN


def _build_schema(d: Dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): TextSelector(
                TextSelectorConfig(multiline=False)
            ),
        }
    )


class DisplayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Each entry is a named profile: a white-point and a brightness slider
    that any number of devices can bind to on the display-card."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_NAME):
                errors[CONF_NAME] = "required"
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=_build_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_NAME):
                errors[CONF_NAME] = "required"
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        defaults = (
            user_input
            if user_input is not None
            else {**self.entry.data, **self.entry.options}
        )
        return self.async_show_form(
            step_id="init", data_schema=_build_schema(defaults), errors=errors
        )
