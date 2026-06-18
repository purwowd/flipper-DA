"""Tests for full jam mode."""

from flipper_da.config import JAM_433_MHZ_HZ
from flipper_da.system import FlipperAttackSystem


def test_run_full_jam_uses_433_default(config, mock_rf):
    config.target_frequency_hz = None
    config.brute_max_chunks = 3
    config.brute_chunk_sec = 0.01

    system = FlipperAttackSystem(config, rf_manager=mock_rf)
    summary = system.run_full_jam()

    assert summary["mode"] == "jam"
    assert summary["frequency_hz"] == JAM_433_MHZ_HZ
    assert summary["chunks_transmitted"] == 3
    assert len(mock_rf.tx_calls) == 3


def test_build_config_jam_mode_defaults():
    from flipper_da.cli import build_config, parse_arguments

    config = build_config(parse_arguments(["--mode", "jam"]))

    assert config.target_frequency_hz == JAM_433_MHZ_HZ
    assert config.brute_verify_interval_sec == 0.0
    assert config.tx_gain == 60
