"""Constants for the Watering Project integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "watering_project"

# --- Schema / storage -------------------------------------------------------

SCHEMA_VERSION: Final = 1
STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY: Final = 5  # seconds, debounced writes

# --- Defaults ---------------------------------------------------------------

DEFAULT_MOISTURE_THRESHOLD: Final = 70
DEFAULT_BATTERY_SUSPECT_DAYS: Final = 30
DEFAULT_NOTIFY_REPEAT_HOURS: Final = 24

#: A plant that is already dry must recover to ``threshold + DRY_HYSTERESIS``
#: before it counts as watered again. Fixed by design, not an option.
DRY_HYSTERESIS: Final = 5

MIN_MOISTURE_THRESHOLD: Final = 1
MAX_MOISTURE_THRESHOLD: Final = 100
MIN_BATTERY_SUSPECT_DAYS: Final = 1
MAX_BATTERY_SUSPECT_DAYS: Final = 365
MAX_NOTIFY_REPEAT_HOURS: Final = 168

# --- Options keys -----------------------------------------------------------

CONF_MOISTURE_DEFAULT: Final = "moisture_default"
CONF_BATTERY_SUSPECT_DAYS: Final = "battery_suspect_days"
CONF_INCLUDE_DEVICES: Final = "include_devices"
CONF_EXCLUDE_DEVICES: Final = "exclude_devices"
CONF_NOTIFY_ENABLED: Final = "notify_enabled"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_NOTIFY_REPEAT_HOURS: Final = "notify_repeat_hours"
CONF_NOTIFY_URL: Final = "notify_url"

# --- Verdict statuses -------------------------------------------------------

#: ``unavailable`` is deliberately not used as an enum value: an *available*
#: sensor holding the literal state ``unavailable`` would be indistinguishable
#: from a dead entity.
STATUS_SUSPECT_BATTERY: Final = "suspect_battery"
STATUS_NO_DATA: Final = "no_data"
STATUS_DRY: Final = "dry"
STATUS_HEALTHY: Final = "healthy"

#: Order matters: it is the rendered section order.
STATUS_ORDER: Final[tuple[str, ...]] = (
    STATUS_SUSPECT_BATTERY,
    STATUS_DRY,
    STATUS_NO_DATA,
    STATUS_HEALTHY,
)

# --- Discovery --------------------------------------------------------------

#: Device name/model substrings that mark a moisture sensor as "not a plant".
#: ``device_class: moisture`` is shared with water-leak sensors.
#: This list has exactly one copy in the codebase. Bare "water" is intentionally
#: absent — it matches too much (e.g. "Watering", "Water tank").
LEAK_KEYWORDS: Final[tuple[str, ...]] = (
    "leak",
    "leakage",
    "flood",
    "aquarium",
    "wasser",
    "überschwemmung",
    "ueberschwemmung",
    "tropf",
    "drip tray",
)

EXCLUDE_REASON_OPTION: Final = "option"
EXCLUDE_REASON_NOT_INCLUDED: Final = "not_included"
EXCLUDE_REASON_PERMISSION: Final = "permission"
EXCLUDE_REASON_KEYWORD_PREFIX: Final = "keyword:"

# --- Tracker ----------------------------------------------------------------

#: Battery records without a numeric reading for this long are pruned.
BATTERY_RECORD_TTL: Final = timedelta(days=90)

# --- Entity keys ------------------------------------------------------------

ENTITY_NEEDS_WATER: Final = "needs_water"
ENTITY_STATUS: Final = "status"
ENTITY_PLANTS_NEED_WATER: Final = "plants_need_water"
ENTITY_PLANTS_NEEDING_WATER: Final = "plants_needing_water"

# --- Events / websocket -----------------------------------------------------

EVENT_UPDATED: Final = f"{DOMAIN}_updated"
WS_SUBSCRIBE: Final = f"{DOMAIN}/subscribe"
WS_ERROR_NOT_LOADED: Final = "not_loaded"

# --- Timing -----------------------------------------------------------------

EVALUATE_DEBOUNCE_SECONDS: Final = 1.0
EVALUATE_INTERVAL: Final = timedelta(seconds=60)
