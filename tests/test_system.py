"""Tests for application orchestration."""

from flipper_da.system import FlipperAttackSystem
from tests.conftest import MockRFManager


def test_run_detection_cycle_with_mock_rf(config, mock_rf):
    mock_rf.set_rx_power(1.0)
    system = FlipperAttackSystem(config, rf_manager=mock_rf)

    results = system.run_detection_cycle()

    assert len(results) >= 1
    assert all("power_db" in item for item in results)


def test_run_full_cycle_skips_attack_when_no_signals(config, mock_rf):
    mock_rf.set_rx_power(0.0)
    system = FlipperAttackSystem(config, rf_manager=mock_rf)

    summary = system.run_full_cycle()

    assert summary["detection_count"] == 0
    assert summary["attack_count"] == 0
    assert summary["attacks"] == []


def test_initialize_without_bladerf_returns_false(config, monkeypatch):
    monkeypatch.setattr("flipper_da.bladerf_manager.bladerf", None)
    system = FlipperAttackSystem(config)

    assert system.initialize() is False
