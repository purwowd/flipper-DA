"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np
import pytest

from flipper_da.config import SystemConfig


class MockRFManager:
    """In-memory RF backend for unit tests."""

    def __init__(self, config: SystemConfig):
        self.config = config
        self.current_frequency = 0
        self.tx_calls: List[np.ndarray] = []
        self.rx_generator: Optional[Callable[[int], np.ndarray]] = None
        self.configure_tx_calls = 0
        self.configure_rx_calls = 0
        self.is_initialized = True

    def set_rx_power(self, power_linear: float) -> None:
        amplitude = float(np.sqrt(power_linear))

        def _generate(num_samples: int) -> np.ndarray:
            return amplitude * (np.ones(num_samples, dtype=np.complex64) + 0j)

        self.rx_generator = _generate

    def set_frequency(self, frequency_hz: int) -> bool:
        self.current_frequency = frequency_hz
        return True

    def set_tx_frequency_fast(self, frequency_hz: int) -> bool:
        return self.set_frequency(frequency_hz)

    def receive_samples(self, num_samples: int) -> Optional[np.ndarray]:
        if self.rx_generator is None:
            return np.zeros(num_samples, dtype=np.complex64)
        return self.rx_generator(num_samples)

    def configure_tx(self) -> bool:
        self.configure_tx_calls += 1
        return True

    def configure_rx(self) -> bool:
        self.configure_rx_calls += 1
        return True

    def transmit_samples(self, samples: np.ndarray) -> bool:
        self.tx_calls.append(np.array(samples, copy=True))
        return True


@pytest.fixture
def config() -> SystemConfig:
    return SystemConfig(
        sample_rate=2_000_000,
        scan_duration_ms=1.0,
        detection_threshold_db=-40.0,
        attack_duration_sec=0.01,
    )


@pytest.fixture
def mock_rf(config: SystemConfig) -> MockRFManager:
    return MockRFManager(config)
