"""Tests for attack signal generation and execution."""

import numpy as np

from flipper_da.attack_engine import AttackEngine
from flipper_da.config import SystemConfig
from tests.conftest import MockRFManager


def test_generate_noise_has_expected_length(config):
    engine = AttackEngine(MockRFManager(config), config)
    samples = engine.generate_noise(0.01)

    assert samples.dtype == np.complex64
    assert samples.size == int(config.sample_rate * 0.01)


def test_build_attack_signal_is_normalized(config):
    engine = AttackEngine(MockRFManager(config), config)
    samples = engine.build_attack_signal(0.01)

    assert np.max(np.abs(samples)) <= 0.9 + 1e-6


def test_execute_attack_success(config, mock_rf):
    engine = AttackEngine(mock_rf, config)
    result = engine.execute_attack(433_920_000, duration_sec=0.01)

    assert result["success"] is True
    assert result["error"] is None
    assert len(mock_rf.tx_calls) == 1
    assert mock_rf.configure_tx_calls >= 1
    assert mock_rf.configure_rx_calls >= 1


def test_execute_sustained_attack_transmits_multiple_chunks(config, mock_rf):
    config.brute_hold_sec = 0.5
    config.brute_chunk_sec = 0.1
    engine = AttackEngine(mock_rf, config)

    result = engine.execute_sustained_attack(433_920_000)

    assert result["success"] is True
    assert result["mode"] == "brute"
    assert result["chunks_transmitted"] >= 4
    assert len(mock_rf.tx_calls) >= 4


def test_execute_brute_attack_targets_strongest_only(config, mock_rf):
    config.enable_brute_mode = True
    config.brute_hold_sec = 0.05
    config.brute_chunk_sec = 0.02
    engine = AttackEngine(mock_rf, config)
    signals = [
        {"frequency": 315_000_000, "power_db": -20},
        {"frequency": 433_920_000, "power_db": -5},
    ]

    results = engine.execute_brute_attack(signals)

    assert len(results) == 1
    assert results[0]["frequency"] == 433_920_000


def test_execute_adaptive_attack_limits_to_config_targets(config, mock_rf):
    config.enable_brute_mode = False
    config.auto_attack_max_targets = 3
    engine = AttackEngine(mock_rf, config)
    signals = [
        {"frequency": 315_000_000 + idx * 1_000_000, "power_db": -10 - idx}
        for idx in range(8)
    ]

    results = engine.execute_adaptive_attack(signals)

    assert len(results) == 3
    assert all(result["success"] for result in results)
