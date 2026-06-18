"""Pure RF signal conversion and measurement helpers."""

from __future__ import annotations

import numpy as np

from flipper_da.config import SC16_Q11_SCALE


def sc16_q11_interleaved_to_complex(samples: np.ndarray) -> np.ndarray:
    """
    Convert interleaved SC16_Q11 int16 IQ buffer to normalized complex64.

    BladeRF sync API returns interleaved [I0, Q0, I1, Q1, ...] int16 values.
    """
    if samples.size == 0:
        return np.array([], dtype=np.complex64)

    interleaved = np.asarray(samples, dtype=np.int16).reshape(-1)
    if interleaved.size % 2 != 0:
        interleaved = interleaved[:-1]

    i_samples = interleaved[0::2].astype(np.float32) / SC16_Q11_SCALE
    q_samples = interleaved[1::2].astype(np.float32) / SC16_Q11_SCALE
    return i_samples + 1j * q_samples


def complex_to_sc16_q11_interleaved(samples: np.ndarray) -> np.ndarray:
    """Convert normalized complex64 samples to interleaved SC16_Q11 int16."""
    samples = np.asarray(samples, dtype=np.complex64).reshape(-1)
    scaled_i = np.clip(np.round(samples.real * SC16_Q11_SCALE), -2048, 2047).astype(np.int16)
    scaled_q = np.clip(np.round(samples.imag * SC16_Q11_SCALE), -2048, 2047).astype(np.int16)

    interleaved = np.empty(scaled_i.size * 2, dtype=np.int16)
    interleaved[0::2] = scaled_i
    interleaved[1::2] = scaled_q
    return interleaved


def power_to_db(iq: np.ndarray, floor_db: float = -120.0) -> float:
    """
    Compute relative average power in dB from IQ samples.

    This is not absolute dBm; it is useful for comparing signals with a fixed
    gain configuration during lab sweeps.
    """
    if iq is None or len(iq) == 0:
        return floor_db

    power = float(np.mean(np.abs(iq) ** 2))
    if power <= 0.0:
        return floor_db

    return 10.0 * np.log10(power)


def normalize_signal(samples: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """Normalize complex signal to avoid clipping during transmission."""
    samples = np.asarray(samples, dtype=np.complex64)
    max_val = float(np.max(np.abs(samples)))
    if max_val <= 0.0:
        return samples
    return samples / max_val * peak


def deduplicate_signals(
    results: list[dict],
    frequency_key: str = "frequency",
    power_key: str = "power_db",
) -> list[dict]:
    """Keep the strongest reading per frequency."""
    unique: dict[int, dict] = {}
    for result in results:
        freq = result[frequency_key]
        if freq not in unique or result[power_key] > unique[freq][power_key]:
            unique[freq] = result
    return sorted(unique.values(), key=lambda item: item[frequency_key])
