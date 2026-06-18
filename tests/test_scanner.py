"""Tests for spectrum scanner logic."""

from flipper_da.config import SystemConfig
from flipper_da.scanner import SpectrumScanner
from tests.conftest import MockRFManager


def test_scan_frequency_detects_above_threshold(config, mock_rf):
    mock_rf.set_rx_power(1.0)
    scanner = SpectrumScanner(mock_rf, config)

    power_db = scanner.scan_frequency(433_920_000)

    assert power_db is not None
    assert power_db > config.detection_threshold_db
    assert mock_rf.current_frequency == 433_920_000


def test_scan_band_returns_only_signals_above_threshold(config, mock_rf):
    mock_rf.set_rx_power(0.0001)
    scanner = SpectrumScanner(mock_rf, config)

    results = scanner.scan_band(433_000_000, 435_000_000, step_hz=1_000_000)

    assert results == []


def test_scan_target_frequency_manual_mode(config, mock_rf):
    config.target_frequency_hz = 433_920_000
    mock_rf.set_rx_power(1.0)
    scanner = SpectrumScanner(mock_rf, config)

    results = scanner.scan_all_bands()

    assert len(results) == 1
    assert results[0]["is_manual_target"] is True
    assert results[0]["frequency"] == 433_920_000


def test_aggressive_scan_uses_finer_step(config):
    config.enable_aggressive_scan = True
    scanner = SpectrumScanner(MockRFManager(config), config)

    assert scanner.effective_scan_step_hz == config.aggressive_scan_step_hz
