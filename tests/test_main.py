"""Smoke tests for Epic E0 — config loads, CLI parser builds (DoD spec §13 Phase 0)."""

from app.config import Settings, get_settings
from app.main import build_parser


def test_settings_load_with_defaults() -> None:
    s = Settings(_env_file=None)  # ignore local .env for determinism
    assert s.max_advisor_consults == 3  # guard R-1 default
    assert s.decision_temperature == 0.0


def test_settings_singleton() -> None:
    assert get_settings() is get_settings()


def test_demo_now_override_parsing() -> None:
    s = Settings(_env_file=None, demo_now_override="2024-04-15T10:00:00Z")
    assert s.now().year == 2024  # risk #4: DB seeded for 2024


def test_cli_parser_builds() -> None:
    parser = build_parser()
    args = parser.parse_args(["--check-config"])
    assert args.check_config is True
