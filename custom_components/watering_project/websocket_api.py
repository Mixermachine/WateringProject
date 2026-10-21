"""Websocket subscription: the only transport between integration and card.

Why a subscription and not request/response plus an event: custom event types
are rejected by ``subscribe_events`` for non-admin users (``SUBSCRIBE_ALLOWLIST``
covers core events only), so a custom event silently stops updating household
members' dashboards. A custom websocket command is not admin-gated.

The initial payload is sent as an **event**, not only as the command result:
``connection.subscribeMessage`` resubscribes after a reconnect but discards the
fresh ``result``, so state delivered that way is lost for good on a flaky link.
Every push is a complete payload — no diffs, and therefore no watermark to keep
in sync across restarts.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, WS_ERROR_NOT_LOADED, WS_SUBSCRIBE

_LOGGER: Final = logging.getLogger(__name__)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the subscription command (idempotent, once per process)."""
    websocket_api.async_register_command(hass, ws_subscribe)


def _coordinator(hass: HomeAssistant):
    """Resolve the loaded entry at call time.

    Never close over the entry: ``async_register_command`` has no unregister, so a
    captured entry would outlive ``async_unload_entry`` and serve dead options.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            return runtime.coordinator
    return None


def _allowed_predicate(connection: websocket_api.ActiveConnection):
    """Build the per-connection entity permission filter."""
    user = connection.user
    if user is None or user.is_admin:
        return None
    permissions = user.permissions

    @callback
    def _allowed(entity_id: str) -> bool:
        return bool(permissions.check_entity(entity_id, POLICY_READ))

    return _allowed


@websocket_api.websocket_command({vol.Required("type"): WS_SUBSCRIBE})
@websocket_api.async_response
async def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the current payload, then push a new one on every change."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], WS_ERROR_NOT_LOADED, "Watering Project is not loaded")
        return

    entity_allowed = _allowed_predicate(connection)
    connection.send_result(msg["id"])

    @callback
    def _push() -> None:
        if msg["id"] not in connection.subscriptions:
            # The client unsubscribed between scheduling and sending.
            return
        try:
            connection.send_event(msg["id"], coordinator.snapshot(entity_allowed=entity_allowed))
        except Exception:
            _LOGGER.debug("Dropping payload push to a closed connection", exc_info=True)

    # Subscribe first: ``_push`` refuses to send while the message id is not in
    # ``connection.subscriptions``, which would swallow the initial payload.
    connection.subscriptions[msg["id"]] = coordinator.async_add_payload_listener(_push)
    _push()
