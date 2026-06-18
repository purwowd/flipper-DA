"""Spectrum scanning and signal detection."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

from flipper_da.config import COMMON_FLIPPER_FREQS, FLIPPER_BANDS, SystemConfig
from flipper_da.rf_utils import deduplicate_signals, power_to_db


class RFReceiver(Protocol):
    def set_frequency(self, frequency_hz: int) -> bool: ...
    def receive_samples(self, num_samples: int) -> Optional[np.ndarray]: ...


class SpectrumScanner:
    """Frequency sweeps and relative-power signal detection."""

    def __init__(self, rf_manager: RFReceiver, config: SystemConfig):
        self.rf = rf_manager
        self.config = config
        self.logger = logging.getLogger("SpectrumScanner")
        self.detected_signals: List[Dict[str, Any]] = []

    @property
    def effective_scan_step_hz(self) -> int:
        if self.config.enable_aggressive_scan:
            return self.config.aggressive_scan_step_hz
        return self.config.scan_step_hz

    def scan_frequency(self, frequency_hz: int) -> Optional[float]:
        """Scan one frequency and return relative power in dB."""
        if not self.rf.set_frequency(frequency_hz):
            return None

        num_samples = int(self.config.sample_rate * (self.config.scan_duration_ms / 1000.0))
        num_samples = max(num_samples, 64)

        iq = self.rf.receive_samples(num_samples)
        if iq is None or len(iq) == 0:
            return None

        return power_to_db(iq)

    def scan_band(self, low_hz: int, high_hz: int, step_hz: int | None = None) -> List[Dict[str, Any]]:
        """Scan a frequency band and return signals above threshold."""
        step = step_hz or self.effective_scan_step_hz
        results: List[Dict[str, Any]] = []
        freq = low_hz

        self.logger.debug("Scanning band: %.1f - %.1f MHz", low_hz / 1e6, high_hz / 1e6)

        while freq <= high_hz:
            power_db = self.scan_frequency(freq)
            if power_db is not None and power_db > self.config.detection_threshold_db:
                result = {
                    "frequency": freq,
                    "frequency_mhz": freq / 1e6,
                    "power_db": round(power_db, 2),
                    "timestamp": datetime.now().isoformat(),
                }
                results.append(result)
                self.logger.info(
                    "Signal detected at %.3f MHz (relative power: %.1f dB)",
                    freq / 1e6,
                    power_db,
                )
            freq += step

        return results

    def scan_target_frequency(self, frequency_hz: int) -> List[Dict[str, Any]]:
        """Scan a single manually specified frequency."""
        power_db = self.scan_frequency(frequency_hz)
        if power_db is None or power_db <= self.config.detection_threshold_db:
            return []

        result = {
            "frequency": frequency_hz,
            "frequency_mhz": frequency_hz / 1e6,
            "power_db": round(power_db, 2),
            "timestamp": datetime.now().isoformat(),
            "is_manual_target": True,
        }
        self.logger.info(
            "Manual target detected at %.3f MHz (relative power: %.1f dB)",
            frequency_hz / 1e6,
            power_db,
        )
        return [result]

    def scan_all_bands(self) -> List[Dict[str, Any]]:
        """Scan Flipper-related bands and common frequencies."""
        if self.config.target_frequency_hz is not None:
            self.detected_signals = self.scan_target_frequency(self.config.target_frequency_hz)
            return self.detected_signals

        all_results: List[Dict[str, Any]] = []

        for low, high in FLIPPER_BANDS:
            self.logger.info("Scanning band: %.1f - %.1f MHz", low / 1e6, high / 1e6)
            all_results.extend(self.scan_band(low, high, self.effective_scan_step_hz))

        self.logger.info("Performing targeted scan on common frequencies")
        common_step = (
            self.config.aggressive_scan_step_hz
            if self.config.enable_aggressive_scan
            else min(self.config.scan_step_hz, 250_000)
        )

        for freq in COMMON_FLIPPER_FREQS:
            in_range = any(low <= freq <= high for low, high in FLIPPER_BANDS)
            if not in_range:
                continue

            if self.config.enable_aggressive_scan:
                window = common_step * 2
                all_results.extend(self.scan_band(freq - window, freq + window, common_step))
            else:
                power_db = self.scan_frequency(freq)
                if power_db is not None and power_db > self.config.detection_threshold_db:
                    all_results.append(
                        {
                            "frequency": freq,
                            "frequency_mhz": freq / 1e6,
                            "power_db": round(power_db, 2),
                            "timestamp": datetime.now().isoformat(),
                            "is_common": True,
                        }
                    )
                    self.logger.info(
                        "Signal detected at common frequency %.3f MHz (relative power: %.1f dB)",
                        freq / 1e6,
                        power_db,
                    )

        self.detected_signals = deduplicate_signals(all_results)
        return self.detected_signals

    def scan_quick(self) -> List[Dict[str, Any]]:
        """Fast scan of common Flipper frequencies for responsive autodetect."""
        results: List[Dict[str, Any]] = []

        for freq in COMMON_FLIPPER_FREQS:
            in_range = any(low <= freq <= high for low, high in FLIPPER_BANDS)
            if not in_range:
                continue

            power_db = self.scan_frequency(freq)
            if power_db is not None and power_db > self.config.detection_threshold_db:
                results.append(
                    {
                        "frequency": freq,
                        "frequency_mhz": freq / 1e6,
                        "power_db": round(power_db, 2),
                        "timestamp": datetime.now().isoformat(),
                        "is_common": True,
                        "scan_phase": "quick",
                    }
                )
                self.logger.info(
                    "Quick autodetect: %.3f MHz (relative power: %.1f dB)",
                    freq / 1e6,
                    power_db,
                )

        return deduplicate_signals(results)

    def scan_auto_detect(self) -> List[Dict[str, Any]]:
        """
        Autodetect pipeline: quick common-frequency scan first,
        then full band sweep if nothing is found.
        """
        if self.config.target_frequency_hz is not None:
            self.detected_signals = self.scan_target_frequency(self.config.target_frequency_hz)
            return self.detected_signals

        if self.config.auto_quick_scan:
            quick_results = self.scan_quick()
            if quick_results:
                self.detected_signals = quick_results
                self.logger.info(
                    "Autodetect (quick): %s signal(s) found", len(quick_results)
                )
                return self.detected_signals

        self.logger.info("Autodetect (full): scanning all bands")
        return self.scan_all_bands()

    def get_strongest_signal(self) -> Optional[Dict[str, Any]]:
        if not self.detected_signals:
            return None
        return max(self.detected_signals, key=lambda item: item["power_db"])
