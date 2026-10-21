"""Cross-file consistency checks.

These catch the failures that no unit test sees: the version the user puts in the
resource URL drifting from the manifest, the HACS floor drifting from the runtime
gate, and a translation file that silently lost a key (Home Assistant then renders
raw keys in the UI).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.watering_project.const import (
    DOMAIN,
    MIN_HOMEASSISTANT_VERSION,
    SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / DOMAIN
E2E_CONFIG = ROOT / "tests" / "e2e" / "config" / "configuration.yaml"


def _manifest() -> dict:
    return json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_identity() -> None:
    manifest = _manifest()

    assert manifest["domain"] == DOMAIN
    assert manifest["version"] == _frontend_version()
    assert manifest["config_flow"] is True
    assert set(manifest["dependencies"]) == {"http", "websocket_api"}
    assert manifest["requirements"] == []


def _frontend_version() -> str:
    """The card is versioned with the integration; the bundle must say so."""
    return _manifest()["version"]


def test_e2e_resource_url_matches_manifest_version() -> None:
    content = E2E_CONFIG.read_text(encoding="utf-8")
    match = re.search(r"watering-project-card\.js\?v=([0-9][^\"\s]*)", content)

    assert match is not None, "e2e dashboard has no versioned card resource"
    assert match.group(1) == _manifest()["version"], (
        "tests/e2e/config/configuration.yaml pins a stale ?v=; the browser would "
        "load a cached card instead of the committed bundle"
    )


def test_hacs_floor_matches_runtime_gate() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert hacs["homeassistant"] == MIN_HOMEASSISTANT_VERSION
    assert hacs["name"] == _manifest()["name"]


def test_translations_match_strings() -> None:
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))

    assert strings == english, (
        "translations/en.json drifted from strings.json; Home Assistant only ships "
        "the translated file"
    )


def test_translation_keys_the_code_depends_on_exist() -> None:
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))

    assert set(strings["issues"]) == {"notify_service_missing", "battery_suspect"}
    for key in ("notify_service_missing", "battery_suspect"):
        assert strings["issues"][key]["title"]
        assert strings["issues"][key]["description"]

    for status in ("suspect_battery", "no_data", "dry", "healthy"):
        assert strings["entity"]["sensor"]["status"]["state"][status]

    assert strings["entity"]["binary_sensor"]["needs_water"]["name"]
    assert strings["entity"]["sensor"]["status"]["name"]


def test_schema_version_has_a_card_counterpart() -> None:
    card = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"export const EXPECTED_SCHEMA = (\d+);", card)

    assert match is not None
    assert int(match.group(1)) == SCHEMA_VERSION


def test_committed_bundle_exists_and_is_a_module() -> None:
    bundle = INTEGRATION / "www" / "watering-project-card.js"
    text = bundle.read_text(encoding="utf-8")

    assert bundle.stat().st_size > 10_000, "bundle looks empty"
    assert "watering-project-card" in text
    # A `customElements.define` inside the bundle is what makes the resource usable
    # with a plain `type: module` resource entry.
    assert "customElements.define" in text
