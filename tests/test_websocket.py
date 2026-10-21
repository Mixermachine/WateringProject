"""Tests for the websocket subscription and the permission filter."""

from __future__ import annotations

from typing import Any

from custom_components.watering_project.const import DOMAIN, SCHEMA_VERSION
from homeassistant.core import HomeAssistant
from tests.helpers import MOISTURE_ATTRS, add_entry, add_plant, setup_entry

SUBSCRIBE = f"{DOMAIN}/subscribe"


class FakeUser:
    """Minimal stand-in for a restricted user with a permission policy."""

    def __init__(self, denied: set[str]) -> None:
        self.is_admin = False
        self.denied = denied
        self.permissions = self

    def check_entity(self, entity_id: str, policy: str) -> bool:
        return entity_id not in self.denied


async def _receive_event(ws) -> dict[str, Any]:
    message = await ws.receive_json()
    assert message["type"] == "event"
    return message["event"]


async def test_subscribe_sends_initial_payload(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", name="Ficus", moisture="42")
    await setup_entry(hass, entry)

    ws = await hass_ws_client(hass)
    try:
        await ws.send_json({"id": 3, "type": SUBSCRIBE})
        result = await ws.receive_json()
        assert result["type"] == "result"
        assert result["success"] is True

        payload = await _receive_event(ws)
    finally:
        await ws.close()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["dry"] == 1
    assert payload["summary"]["needs_water"] is True
    plant = payload["plants"][0]
    assert plant["label"] == "Ficus"
    assert plant["status"] == "dry"
    assert plant["needs_water"] is True
    assert plant["battery"]["never_reported"] is False


async def test_push_on_status_change_only(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)
    moisture_id = plant["moisture"]
    assert moisture_id is not None

    ws = await hass_ws_client(hass)
    try:
        await ws.send_json({"id": 3, "type": SUBSCRIBE})
        await ws.receive_json()
        first = await _receive_event(ws)

        # Moisture churn inside the same status must not push a payload.
        hass.states.async_set(moisture_id, "41", MOISTURE_ATTRS)
        await entry.runtime_data.coordinator.async_evaluate()
        await hass.async_block_till_done()

        # Crossing the threshold does.
        hass.states.async_set(moisture_id, "95", MOISTURE_ATTRS)
        await entry.runtime_data.coordinator.async_evaluate()
        second = await _receive_event(ws)
    finally:
        await ws.close()

    assert first["plants"][0]["status"] == "dry"
    assert second["plants"][0]["status"] == "healthy"


async def test_subscribe_without_entry_reports_not_loaded(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)
    # Unload cleanly (cancels timers), then drop the runtime data so the command
    # finds the integration registered but not loaded.
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data = None

    ws = await hass_ws_client(hass)
    try:
        await ws.send_json({"id": 3, "type": SUBSCRIBE})
        result = await ws.receive_json()
    finally:
        await ws.close()

    assert result["type"] == "result"
    assert result["success"] is False
    assert result["error"]["code"] == "not_loaded"


async def test_permission_filter_removes_records(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    visible = add_plant(hass, entry, "ficus", name="Ficus", moisture="42")
    add_plant(hass, entry, "basil", name="Basil", moisture="20")
    await setup_entry(hass, entry)

    coordinator = entry.runtime_data.coordinator
    denied_entity = visible["moisture"]
    assert denied_entity is not None
    user = FakeUser(denied={denied_entity})

    payload = coordinator.snapshot(
        entity_allowed=lambda entity_id: user.check_entity(entity_id, "read")
    )

    assert len(payload["plants"]) == 1
    assert payload["plants"][0]["label"] == "Basil"
    assert payload["summary"]["total"] == 1
    assert any(item["reason"] == "permission" for item in payload["excluded"])


async def test_admin_sees_everything(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)

    payload = entry.runtime_data.coordinator.snapshot(entity_allowed=None)

    assert len(payload["plants"]) == 1
