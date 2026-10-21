"""Trivial single-instance flow: the dev integration needs a config entry."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

DOMAIN = "fake_plants"


class FakePlantsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the fake hardware once."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the single entry."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Fake Plants", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
