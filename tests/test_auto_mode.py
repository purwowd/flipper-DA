"""Tests for autodetect and auto-attack modes."""

import numpy as np

from flipper_da.config import SystemConfig
from flipper_da.scanner import SpectrumScanner
from flipper_da.system import FlipperAttackSystem
from tests.conftest import MockRFManager


def test_scan_quick_detects_common_frequency(config, mock_rf):
    mock_rf.set_rx_power(1.0)
    scanner = SpectrumScanner(mock_rf, config)

    results = scanner.scan_quick()

    assert len(results) >= 1
    assert all(result.get("scan_phase") == "quick" for result in results)


def test_scan_auto_detect_uses_quick_scan_first(config, mock_rf):
    mock_rf.set_rx_power(1.0)
    scanner = SpectrumScanner(mock_rf, config)

    results = scanner.scan_auto_detect()

    assert len(results) >= 1
    assert results[0].get("scan_phase") == "quick"


def test_scan_auto_detect_falls_back_to_full_scan(config, mock_rf):
    config.auto_quick_scan = True
    scanner = SpectrumScanner(mock_rf, config)
    mock_rf.set_rx_power(0.0)

    results = scanner.scan_auto_detect()

    assert results == []


def test_run_auto_loop_detects_and_attacks(config, mock_rf):
    config.auto_max_cycles = 1
    config.auto_interval_sec = 0.01
    config.attack_duration_sec = 0.001
    mock_rf.set_rx_power(1.0)

    system = FlipperAttackSystem(config, rf_manager=mock_rf)
    summary = system.run_auto_loop()

    assert summary["mode"] == "auto"
    assert summary["cycle_count"] == 1
    assert summary["total_detections"] >= 1
    assert summary["total_attacks"] >= 1
    assert summary["successful_attacks"] >= 1
    assert len(mock_rf.tx_calls) >= 1


def test_run_auto_loop_waits_when_no_signal(config, mock_rf, monkeypatch):
    config.auto_max_cycles = 2
    config.auto_interval_sec = 0.01
    mock_rf.set_rx_power(0.0)

    sleep_calls = []
    monkeypatch.setattr("flipper_da.system.time.sleep", lambda sec: sleep_calls.append(sec))

    system = FlipperAttackSystem(config, rf_manager=mock_rf)
    summary = system.run_auto_loop()

    assert summary["cycle_count"] == 2
    assert summary["total_attacks"] == 0
    assert len(sleep_calls) == 2
