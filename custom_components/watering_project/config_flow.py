"""Config and options flow for the Watering Project integration."""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_BATTERY_SUSPECT_DAYS,
    CONF_EXCLUDE_DEVICES,
    CONF_INCLUDE_DEVICES,
    CONF_MOISTURE_DEFAULT,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_REPEAT_HOURS,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_URL,
    DEFAULT_BATTERY_SUSPECT_DAYS,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_NOTIFY_REPEAT_HOURS,
    DOMAIN,
    MAX_BATTERY_SUSPECT_DAYS,
    MAX_MOISTURE_THRESHOLD,
    MAX_NOTIFY_REPEAT_HOURS,
    MIN_BATTERY_SUSPECT_DAYS,
    MIN_MOISTURE_THRESHOLD,
)

TITLE: Final = "Watering Project"
NOTIFY_DOMAIN: Final = "notify"


def normalise_notify_service(value: str | None) -> str:
    """Store the bare service name; the domain is implicit."""
    if not value:
        return ""
    name = value.strip()
    if name.startswith(f"{NOTIFY_DOMAIN}."):
        name = name[len(NOTIFY_DOMAIN) + 1 :]
    return name


def notify_service_exists(hass: HomeAssistant, service: str) -> bool:
    """Whether ``notify.<service>`` is currently registered."""
    if not service:
        return False
    services = hass.services.async_services().get(NOTIFY_DOMAIN, {})
    return service in services


class WateringProjectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow; all tuning lives in the options flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the only allowed config entry."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(title=TITLE, data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WateringProjectOptionsFlow()


class WateringProjectOptionsFlow(OptionsFlow):
    """Threshold, inclusion and notification settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and validate the options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            service = normalise_notify_service(user_input.get(CONF_NOTIFY_SERVICE))
            enabled = bool(user_input.get(CONF_NOTIFY_ENABLED, False))

            if enabled and not service:
                errors[CONF_NOTIFY_SERVICE] = "notify_service_required"
            elif enabled and not notify_service_exists(self.hass, service):
                errors[CONF_NOTIFY_SERVICE] = "notify_service_not_found"

            if not errors:
                options = dict(user_input)
                options[CONF_NOTIFY_SERVICE] = service
                options[CONF_INCLUDE_DEVICES] = list(options.get(CONF_INCLUDE_DEVICES) or [])
                options[CONF_EXCLUDE_DEVICES] = list(options.get(CONF_EXCLUDE_DEVICES) or [])
                return self.async_create_entry(title="", data=options)

        defaults = {
            CONF_MOISTURE_DEFAULT: self.config_entry.options.get(
                CONF_MOISTURE_DEFAULT, DEFAULT_MOISTURE_THRESHOLD
            ),
            CONF_BATTERY_SUSPECT_DAYS: self.config_entry.options.get(
                CONF_BATTERY_SUSPECT_DAYS, DEFAULT_BATTERY_SUSPECT_DAYS
            ),
            CONF_INCLUDE_DEVICES: self.config_entry.options.get(CONF_INCLUDE_DEVICES, []),
            CONF_EXCLUDE_DEVICES: self.config_entry.options.get(CONF_EXCLUDE_DEVICES, []),
            CONF_NOTIFY_ENABLED: self.config_entry.options.get(CONF_NOTIFY_ENABLED, False),
            CONF_NOTIFY_SERVICE: self.config_entry.options.get(CONF_NOTIFY_SERVICE, ""),
            CONF_NOTIFY_REPEAT_HOURS: self.config_entry.options.get(
                CONF_NOTIFY_REPEAT_HOURS, DEFAULT_NOTIFY_REPEAT_HOURS
            ),
            CONF_NOTIFY_URL: self.config_entry.options.get(CONF_NOTIFY_URL, ""),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(defaults),
            errors=errors,
        )

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        """Build the options schema."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_MOISTURE_DEFAULT, default=defaults[CONF_MOISTURE_DEFAULT]
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_MOISTURE_THRESHOLD,
                        max=MAX_MOISTURE_THRESHOLD,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Required(
                    CONF_BATTERY_SUSPECT_DAYS,
                    default=defaults[CONF_BATTERY_SUSPECT_DAYS],
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_BATTERY_SUSPECT_DAYS,
                        max=MAX_BATTERY_SUSPECT_DAYS,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Optional(
                    CONF_INCLUDE_DEVICES, default=defaults[CONF_INCLUDE_DEVICES]
                ): selector.DeviceSelector(selector.DeviceSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_EXCLUDE_DEVICES, default=defaults[CONF_EXCLUDE_DEVICES]
                ): selector.DeviceSelector(selector.DeviceSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_NOTIFY_ENABLED, default=defaults[CONF_NOTIFY_ENABLED]
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_NOTIFY_SERVICE, default=defaults[CONF_NOTIFY_SERVICE]
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_NOTIFY_REPEAT_HOURS,
                    default=defaults[CONF_NOTIFY_REPEAT_HOURS],
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=MAX_NOTIFY_REPEAT_HOURS,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                ),
                vol.Optional(
                    CONF_NOTIFY_URL, default=defaults[CONF_NOTIFY_URL]
                ): selector.TextSelector(),
            }
        )


__all__ = [
    "WateringProjectConfigFlow",
    "WateringProjectOptionsFlow",
    "normalise_notify_service",
    "notify_service_exists",
    "slugify",
]
