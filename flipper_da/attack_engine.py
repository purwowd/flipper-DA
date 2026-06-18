"""Signal generation and transmission for lab interference research."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol

import numpy as np

from flipper_da.config import SystemConfig
from flipper_da.rf_utils import normalize_signal


class RFTransceiver(Protocol):
    def configure_tx(self) -> bool: ...
    def configure_rx(self) -> bool: ...
    def set_frequency(self, frequency_hz: int) -> bool: ...
    def set_tx_frequency_fast(self, frequency_hz: int) -> bool: ...
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

    def build_brute_signal(self, duration_sec: float) -> np.ndarray:
        """Wideband aggressive waveform for sustained suppression."""
        sweep = self.generate_swept_noise(
            duration_sec,
            sweep_bandwidth=self.config.brute_sweep_bandwidth_hz,
        )
        noise = self.generate_noise(duration_sec)
        tone_low = self.generate_tone(duration_sec, frequency_offset=-75_000)
        tone_mid = self.generate_tone(duration_sec, frequency_offset=0.0)
        tone_high = self.generate_tone(duration_sec, frequency_offset=75_000)
        mixed = 0.45 * sweep + 0.35 * noise + 0.07 * tone_low + 0.07 * tone_mid + 0.06 * tone_high
        return normalize_signal(mixed, peak=0.99)

    def _dither_offsets(self) -> List[int]:
        dither = self.config.brute_freq_dither_hz
        if dither <= 0:
            return [0]
        return [-dither, -dither // 2, 0, dither // 2, dither]

    def _set_tx_frequency(self, frequency_hz: int) -> bool:
        if hasattr(self.rf, "set_tx_frequency_fast"):
            return self.rf.set_tx_frequency_fast(frequency_hz)
        return self.rf.set_frequency(frequency_hz)

    def execute_continuous_brute_lock(
        self,
        frequency_hz: int,
        verify_callback: Optional[Callable[[int], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Hammer one target with gapless TX. Stays in TX mode between chunks.
        Only switches to RX when verify_callback is set and interval elapsed.
        """
        chunk_sec = max(0.02, self.config.brute_chunk_sec)
        dither_offsets = self._dither_offsets()
        result: Dict[str, Any] = {
            "frequency": frequency_hz,
            "frequency_mhz": frequency_hz / 1e6,
            "start_time": datetime.now().isoformat(),
            "success": False,
            "error": None,
            "mode": "brute-continuous",
            "chunks_transmitted": 0,
            "suppressed": False,
            "dither_hz": self.config.brute_freq_dither_hz,
        }

        verify_interval = self.config.brute_verify_interval_sec
        self.logger.warning(
            "BRUTE CONTINUOUS LOCK %.3f MHz ±%d kHz — TX gapless (verify every %s)",
            frequency_hz / 1e6,
            self.config.brute_freq_dither_hz // 1000,
            f"{verify_interval:.0f}s" if verify_interval > 0 else "never (Ctrl+C to stop)",
        )

        chunks = 0
        start_mono = time.monotonic()

        try:
            if not self.rf.configure_tx():
                result["error"] = "Failed to configure TX mode"
                return result

            if not self._set_tx_frequency(frequency_hz):
                result["error"] = f"Failed to set frequency {frequency_hz}"
                return result

            last_verify = time.monotonic()
            chunk_idx = 0

            while True:
                offset = dither_offsets[chunk_idx % len(dither_offsets)]
                tx_freq = frequency_hz + offset
                if offset != 0:
                    self._set_tx_frequency(tx_freq)

                signal = self.build_brute_signal(chunk_sec)
                if not self.rf.transmit_samples(signal):
                    result["error"] = "Transmission failed during continuous brute"
                    break

                chunks += 1
                chunk_idx += 1

                if self.config.brute_max_chunks > 0 and chunks >= self.config.brute_max_chunks:
                    break

                if verify_callback and verify_interval > 0:
                    if time.monotonic() - last_verify >= verify_interval:
                        last_verify = time.monotonic()
                        if verify_callback(frequency_hz):
                            result["suppressed"] = True
                            self.logger.info(
                                "Continuous brute: target suppressed, releasing lock"
                            )
                            break

            result["chunks_transmitted"] = chunks
            result["success"] = chunks > 0 and result["error"] is None
            result["end_time"] = datetime.now().isoformat()
            result["duration_seconds"] = time.monotonic() - start_mono
            self.rf.configure_rx()
        except KeyboardInterrupt:
            result["chunks_transmitted"] = chunks
            result["success"] = chunks > 0
            result["end_time"] = datetime.now().isoformat()
            result["duration_seconds"] = time.monotonic() - start_mono
            self.rf.configure_rx()
            raise
        except Exception as exc:
            result["error"] = str(exc)
            self.logger.error("Continuous brute error: %s", exc)
            try:
                self.rf.configure_rx()
            except Exception:
                self.logger.exception("Failed to recover RX after continuous brute")

        self.attack_history.append(result)
        return result

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
            "mode": "burst",
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

    def execute_sustained_attack(
        self,
        frequency_hz: int,
        duration_sec: float | None = None,
    ) -> Dict[str, Any]:
        """Continuous chunked TX without switching to RX between chunks."""
        if duration_sec is None:
            duration_sec = self.config.brute_hold_sec

        chunk_sec = max(0.05, self.config.brute_chunk_sec)
        result: Dict[str, Any] = {
            "frequency": frequency_hz,
            "frequency_mhz": frequency_hz / 1e6,
            "duration": duration_sec,
            "start_time": datetime.now().isoformat(),
            "success": False,
            "error": None,
            "mode": "brute",
            "chunks_transmitted": 0,
        }

        self.logger.warning(
            "BRUTE sustained TX on %.3f MHz for %.1fs (chunk=%.2fs)",
            frequency_hz / 1e6,
            duration_sec,
            chunk_sec,
        )

        try:
            if not self.rf.configure_tx():
                result["error"] = "Failed to configure TX mode"
                return result

            if not self.rf.set_frequency(frequency_hz):
                result["error"] = f"Failed to set frequency {frequency_hz}"
                return result

            deadline = time.monotonic() + duration_sec
            chunks = 0

            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                current_chunk = min(chunk_sec, remaining)
                if current_chunk <= 0:
                    break

                signal = self.build_brute_signal(current_chunk)
                if not self.rf.transmit_samples(signal):
                    result["error"] = "Transmission failed during brute hold"
                    break
                chunks += 1

            result["chunks_transmitted"] = chunks
            result["success"] = chunks > 0 and result["error"] is None
            result["end_time"] = datetime.now().isoformat()
            self.rf.configure_rx()
        except Exception as exc:
            result["error"] = str(exc)
            self.logger.error("Brute attack error: %s", exc)
            try:
                self.rf.configure_rx()
            except Exception:
                self.logger.exception("Failed to recover RX mode after brute attack")

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

        if self.config.enable_brute_mode:
            return self.execute_brute_attack(detected_signals)

        sorted_signals = sorted(detected_signals, key=lambda item: item["power_db"], reverse=True)
        results: List[Dict[str, Any]] = []

        for signal in sorted_signals[: self.config.auto_attack_max_targets]:
            power = signal["power_db"]
            duration = min(5.0, max(1.0, self.config.attack_duration_sec * (1 + (power + 40) / 20)))
            results.append(self.execute_attack(signal["frequency"], duration))

        return results

    def execute_brute_attack(self, detected_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Jam strongest target with sustained wideband brute force."""
        sorted_signals = sorted(detected_signals, key=lambda item: item["power_db"], reverse=True)
        limit = 1 if self.config.brute_single_target else self.config.auto_attack_max_targets
        results = []

        for signal in sorted_signals[:limit]:
            if self.config.brute_continuous:
                results.append(
                    self.execute_continuous_brute_lock(signal["frequency"])
                )
            else:
                results.append(self.execute_sustained_attack(signal["frequency"]))

        return results
