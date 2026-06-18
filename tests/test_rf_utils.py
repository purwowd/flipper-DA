"""Tests for RF conversion and measurement helpers."""

import numpy as np

from flipper_da.config import SC16_Q11_SCALE
from flipper_da.rf_utils import (
    complex_to_sc16_q11_interleaved,
    deduplicate_signals,
    normalize_signal,
    power_to_db,
    sc16_q11_interleaved_to_complex,
)


def test_sc16_q11_round_trip():
    original = np.array([0.5 + 0.25j, -0.1 - 0.8j], dtype=np.complex64)
    interleaved = complex_to_sc16_q11_interleaved(original)
    restored = sc16_q11_interleaved_to_complex(interleaved)

    assert interleaved.dtype == np.int16
    assert interleaved.size == original.size * 2
    np.testing.assert_allclose(restored, original, atol=1 / SC16_Q11_SCALE)


def test_sc16_q11_interleaved_to_complex_handles_odd_length():
    raw = np.array([100, -50, 200], dtype=np.int16)
    iq = sc16_q11_interleaved_to_complex(raw)
    assert iq.size == 1
    assert iq.dtype == np.complex64


def test_power_to_db_stronger_signal_is_higher():
    weak = np.full(128, 0.01 + 0.01j, dtype=np.complex64)
    strong = np.full(128, 1.0 + 0.0j, dtype=np.complex64)

    assert power_to_db(strong) > power_to_db(weak)


def test_power_to_db_empty_returns_floor():
    assert power_to_db(np.array([], dtype=np.complex64)) == -120.0


def test_normalize_signal_limits_peak():
    samples = np.array([3 + 4j, -1 - 1j], dtype=np.complex64)
    normalized = normalize_signal(samples, peak=0.9)

    assert np.max(np.abs(normalized)) <= 0.9 + 1e-6


def test_deduplicate_signals_keeps_strongest_power():
    results = [
        {"frequency": 433_920_000, "power_db": -35.0},
        {"frequency": 433_920_000, "power_db": -20.0},
        {"frequency": 315_000_000, "power_db": -30.0},
    ]

    deduped = deduplicate_signals(results)

    assert len(deduped) == 2
    assert deduped[0]["frequency"] == 315_000_000
    assert deduped[1]["frequency"] == 433_920_000
    assert deduped[1]["power_db"] == -20.0
