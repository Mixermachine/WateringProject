"""Notification decisions and repair issues.

Two behaviours here are deliberate and were expensive to get right:

**Confirmed recovery.** ``last_notified`` is cleared only when no plant is dry
*and* no plant is unavailable or battery-suspect. A plant that blinks off the
mesh must not re-arm notifications, otherwise a flapping sensor produces an
unbounded stream of pushes that ignores ``notify_repeat_hours``.

**Write-ahead state.** ``last_notified`` is persisted *before* dispatch (and
saved immediately, bypassing the debounce). A crash between "decided to notify"
and "recorded that we notified" would otherwise duplicate the push on restart.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .classification import PlantRecord, Verdict
from .const import (
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_REPEAT_HOURS,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_URL,
    DEFAULT_NOTIFY_REPEAT_HOURS,
    DOMAIN,
    STATUS_DRY,
    STATUS_NO_DATA,
    STATUS_SUSPECT_BATTERY,
)
from .store import SECTION_NOTIFY, WateringStore, isoformat, parse_datetime

_LOGGER: Final = logging.getLogger(__name__)

ISSUE_NOTIFY_SERVICE: Final = "notify_service_missing"
ISSUE_BATTERY_SUSPECT: Final = "battery_suspect"

NOTIFY_TITLE: Final = "Plants need water"


def _option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def should_notify(
    last_notified: datetime | None,
    now: datetime,
    repeat_hours: int,
) -> bool:
    """Whether a drought notification may be sent right now.

    An unannounced drought always notifies. Afterwards the hard floor applies:
    repeats need ``repeat_hours`` to have elapsed, and ``0`` means "never repeat
    until the drought ends".
    """
    if last_notified is None:
        return True
    if repeat_hours <= 0:
        return False
    return now - last_notified >= timedelta(hours=repeat_hours)


def build_message(labels: Iterable[str]) -> tuple[str, str]:
    """Render the push title and body."""
    names = list(labels)
    if len(names) == 1:
        return NOTIFY_TITLE, f"1 plant needs water: {names[0]}"
    return NOTIFY_TITLE, f"{len(names)} plants need water: {', '.join(names)}"


class NotificationManager:
    """Owns the ``notify`` store section and the related repair issues."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: WateringStore) -> None:
        """Initialise the manager on an already-loaded store."""
        self.hass = hass
        self.entry = entry
        self.store = store

    # -- persisted state ---------------------------------------------------

    @property
    def _section(self) -> dict[str, Any]:
        return self.store.section(SECTION_NOTIFY)

    @property
    def last_notified(self) -> datetime | None:
        """When the current drought was last announced."""
        return parse_datetime(self._section.get("last_notified"))

    async def _set_last_notified(self, value: datetime | None) -> None:
        self._section["last_notified"] = isoformat(value)
        self.store.mark_dirty()
        await self.store.async_save_now()

    # -- evaluation hook ---------------------------------------------------

    async def async_process(
        self,
        verdicts: Mapping[str, Verdict],
        plants: Mapping[str, PlantRecord],
        now: datetime,
    ) -> None:
        """Decide and send, once per evaluation."""
        await self._async_sync_battery_issue(verdicts, plants)

        dry_labels = [
            plants[plant_id].label
            for plant_id, verdict in verdicts.items()
            if verdict.status == STATUS_DRY and plant_id in plants
        ]
        blocked = any(
            verdict.status in (STATUS_NO_DATA, STATUS_SUSPECT_BATTERY)
            for verdict in verdicts.values()
        )

        if not dry_labels and not blocked:
            # Confirmed recovery: re-arm for the next drought.
            if self.last_notified is not None:
                _LOGGER.debug("All plants recovered; re-arming notifications")
                await self._set_last_notified(None)
            return

        if not dry_labels:
            return

        if not bool(_option(self.entry, CONF_NOTIFY_ENABLED, False)):
            return

        repeat_hours = int(
            _option(self.entry, CONF_NOTIFY_REPEAT_HOURS, DEFAULT_NOTIFY_REPEAT_HOURS)
        )
        if not should_notify(self.last_notified, now, repeat_hours):
            return

        service = _option(self.entry, CONF_NOTIFY_SERVICE, "") or ""
        if not service:
            self._async_raise_notify_issue("no_service")
            return

        # Write-ahead: record the decision before dispatching.
        await self._set_last_notified(now)
        self._async_dispatch(service, dry_labels)

    # -- dispatch ----------------------------------------------------------

    def _async_dispatch(self, service: str, labels: list[str]) -> None:
        title, message = build_message(labels)
        data: dict[str, Any] = {}
        url = _option(self.entry, CONF_NOTIFY_URL, "")
        if url:
            data["url"] = url

        async def _send() -> None:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {"title": title, "message": message, **({"data": data} if data else {})},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.warning("Notify service %s failed: %s", service, err)
                self._async_raise_notify_issue(str(err))
                return
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_NOTIFY_SERVICE)

        # Never block the evaluation loop on a phone.
        self.entry.async_create_background_task(self.hass, _send(), name=f"{DOMAIN}_notify")

    def _async_raise_notify_issue(self, detail: str) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_NOTIFY_SERVICE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NOTIFY_SERVICE,
            translation_placeholders={
                "service": str(_option(self.entry, CONF_NOTIFY_SERVICE, "")),
                "detail": detail,
            },
        )

    # -- repair issues -----------------------------------------------------

    async def _async_sync_battery_issue(
        self,
        verdicts: Mapping[str, Verdict],
        plants: Mapping[str, PlantRecord],
    ) -> None:
        """Report plants whose battery is untrustworthy.

        This is the mitigation for the accepted trade-off that a suspect plant is
        never notified as thirsty: the problem surfaces as a repair issue plus a
        dedicated card section instead of a silent blind spot.
        """
        labels = sorted(
            plants[plant_id].label
            for plant_id, verdict in verdicts.items()
            if verdict.status == STATUS_SUSPECT_BATTERY and plant_id in plants
        )
        if not labels:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_BATTERY_SUSPECT)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_BATTERY_SUSPECT,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_BATTERY_SUSPECT,
            translation_placeholders={"plants": ", ".join(labels)},
        )
