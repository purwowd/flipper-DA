"""Tests for B210-style payload and channel map."""

import numpy as np

from flipper_da.attack_engine import AttackEngine
from flipper_da.config import FLIPPER_CHANNELS, JAM_433_MHZ_HZ, resolve_channel_frequencies


def test_flipper_channel_map():
    assert FLIPPER_CHANNELS[433] == JAM_433_MHZ_HZ
    assert resolve_channel_frequencies([433]) == [433_920_000]


def test_generate_payload_modes(config, mock_rf):
    config.tx_buffer_samples = 4096
    engine = AttackEngine(mock_rf, config)

    for mode in ("noise", "chirp", "both", "brute", "ultra"):
        config.payload_mode = mode
        buf = engine.generate_payload(4096)
        assert buf.dtype == np.complex64
        assert buf.size == 4096
        assert np.max(np.abs(buf)) <= 0.99 + 1e-5


def test_build_config_jam_respects_high_tx_gain():
    from flipper_da.cli import build_config, parse_arguments

    config = build_config(parse_arguments(["--mode", "jam", "-ch", "433", "--tx-gain", "73"]))

    assert config.tx_gain == 73
    assert config.ultra_brute is True


def test_build_config_jam_with_channel_code():
    from flipper_da.cli import build_config, parse_arguments

    config = build_config(parse_arguments(["--mode", "jam", "-ch", "433"]))

    assert config.target_frequency_hz == 433_920_000
    assert config.payload_mode == "ultra"
    assert config.ultra_brute is True
    assert config.jam_refresh_buffers is True
    assert config.brute_freq_dither_hz >= 200_000
    assert config.tx_gain == 60
