"""Signal generation and transmission for lab interference research."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

from flipper_da.config import SystemConfig
from flipper_da.rf_utils import normalize_signal


class RFTransceiver(Protocol):
    def configure_tx(self) -> bool: ...
    def configure_rx(self) -> bool: ...
    def set_frequency(self, frequency_hz: int) -> bool: ...
    def transmit_samples(self, samples: np.ndarray) -> bool: ...


class AttackEngine:
    """Generate and transmit lab interference waveforms."""

    def __init__(self, rf_manager: RFTransceiver, config: SystemConfig):
        self.rf = rf_manager
        self.config = config
        self.logger = logging.getLogger("AttackEngine")
        self.attack_history: List[Dict[str, Any]] = []

    def generate_noise(self, duration_sec: float) -> np.ndarray:
        num_samples = int(self.config.sample_rate * duration_sec)
        noise_real = np.random.normal(0, self.config.noise_amplitude, num_samples)
        noise_imag = np.random.normal(0, self.config.noise_amplitude, num_samples)
        return normalize_signal(noise_real + 1j * noise_imag)

    def generate_tone(self, duration_sec: float, frequency_offset: float = 0.0) -> np.ndarray:
        num_samples = int(self.config.sample_rate * duration_sec)
        t = np.arange(num_samples) / self.config.sample_rate
        return np.exp(1j * 2 * np.pi * frequency_offset * t).astype(np.complex64)

    def generate_swept_noise(self, duration_sec: float, sweep_bandwidth: float = 1e6) -> np.ndarray:
        num_samples = int(self.config.sample_rate * duration_sec)
        t = np.arange(num_samples) / self.config.sample_rate
        freq_sweep = (t / duration_sec - 0.5) * sweep_bandwidth
        phase = 2 * np.pi * np.cumsum(freq_sweep) / self.config.sample_rate
        noise = np.random.normal(0, self.config.noise_amplitude, num_samples)
        return normalize_signal(noise * np.exp(1j * phase))

    def build_attack_signal(self, duration_sec: float) -> np.ndarray:
        noise_samples = self.generate_noise(duration_sec)
        tone_samples = self.generate_tone(duration_sec, frequency_offset=50_000)
        return normalize_signal(0.7 * noise_samples + 0.3 * tone_samples)

    def execute_attack(self, frequency_hz: int, duration_sec: float | None = None) -> Dict[str, Any]:
        if duration_sec is None:
            duration_sec = self.config.attack_duration_sec

        result: Dict[str, Any] = {
            "frequency": frequency_hz,
            "frequency_mhz": frequency_hz / 1e6,
            "duration": duration_sec,
            "start_time": datetime.now().isoformat(),
            "success": False,
            "error": None,
        }

        self.logger.warning(
            "Executing lab transmission on %.3f MHz for %.1fs",
            frequency_hz / 1e6,
            duration_sec,
        )

        try:
            if not self.rf.configure_tx():
                result["error"] = "Failed to configure TX mode"
                self.logger.error(result["error"])
                return result

            if not self.rf.set_frequency(frequency_hz):
                result["error"] = f"Failed to set frequency {frequency_hz}"
                self.logger.error(result["error"])
                return result

            attack_signal = self.build_attack_signal(duration_sec)
            if not self.rf.transmit_samples(attack_signal):
                result["error"] = "Transmission failed"
                self.logger.error(result["error"])
                return result

            time.sleep(0.1)
            result["success"] = True
            result["end_time"] = datetime.now().isoformat()
            self.logger.info("Transmission completed on %.3f MHz", frequency_hz / 1e6)
            self.rf.configure_rx()
        except Exception as exc:
            result["error"] = str(exc)
            self.logger.error("Attack error: %s", exc)
            try:
                self.rf.configure_rx()
            except Exception:
                self.logger.exception("Failed to recover RX mode after attack error")

        self.attack_history.append(result)
        return result

    def execute_sequential_attacks(self, frequencies: List[int]) -> List[Dict[str, Any]]:
        results = []
        for freq in frequencies:
            results.append(self.execute_attack(freq))
            time.sleep(0.5)
        return results

    def execute_adaptive_attack(self, detected_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not detected_signals:
            self.logger.info("No signals detected for transmission")
            return []

        sorted_signals = sorted(detected_signals, key=lambda item: item["power_db"], reverse=True)
        results: List[Dict[str, Any]] = []

        for signal in sorted_signals[: self.config.auto_attack_max_targets]:
            power = signal["power_db"]
            duration = min(5.0, max(1.0, self.config.attack_duration_sec * (1 + (power + 40) / 20)))
            results.append(self.execute_attack(signal["frequency"], duration))

        return results
