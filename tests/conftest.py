"""Pytest configuration for the Watering Project test suite.

The harness is authoritative on Linux (CI and the docker/test image). Two
harness behaviours are Linux-specific: it disables sockets except AF_UNIX (which
asyncio needs for its self-pipe), and it constructs an ``aiodns`` resolver in an
autouse fixture (aiodns refuses the Proactor loop Windows forces on Home
Assistant). The block below neutralises both so native Windows runs stay usable
for quick iteration; it is not a substitute for the Linux suite.
"""

from __future__ import annotations

import os

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

if os.name == "nt":  # pragma: no cover - developer convenience only
    from unittest.mock import MagicMock

    import pytest_homeassistant_custom_component.plugins as _ha_plugins
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None  # type: ignore[assignment]
    _ha_plugins.AsyncResolver = lambda *args, **kwargs: MagicMock()  # type: ignore[assignment]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the golden-fixture regeneration flag."""
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite frontend/test/fixtures/plants.golden.json instead of asserting it.",
    )


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    """Whether the current run regenerates the golden contract fixture."""
    return bool(request.config.getoption("--update-golden"))
