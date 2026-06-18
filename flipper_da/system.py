"""Main application orchestration."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from flipper_da.attack_engine import AttackEngine
from flipper_da.bladerf_manager import BladeRFManager
from flipper_da.config import JAM_433_MHZ_HZ, SystemConfig
from flipper_da.scanner import SpectrumScanner


class FlipperAttackSystem:
    """Orchestrate detection and lab transmission cycles."""

    def __init__(self, config: SystemConfig, rf_manager: BladeRFManager | None = None):
        self.config = config
        self.logger = logging.getLogger("FlipperAttackSystem")
        self.rf_manager = rf_manager or BladeRFManager(config)
        self.scanner = SpectrumScanner(self.rf_manager, config)
        self.attack_engine = AttackEngine(self.rf_manager, config)
        self.scan_results: List[Dict[str, Any]] = []
        self.attack_results: List[Dict[str, Any]] = []

    def initialize(self) -> bool:
        self.logger.info("Initializing Flipper research system")
        return self.rf_manager.initialize()

    def shutdown(self) -> None:
        self.logger.info("Shutting down system")
        self.rf_manager.close()

    def run_detection_cycle(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting detection cycle")
        self.scan_results = self.scanner.scan_all_bands()

        if self.scan_results:
            self.logger.info("Detection complete. Found %s signals:", len(self.scan_results))
            for signal in self.scan_results:
                self.logger.info(
                    "  %.3f MHz @ %.1f dB (relative)",
                    signal["frequency_mhz"],
                    signal["power_db"],
                )
        else:
            self.logger.info("No signals detected above threshold")

        return self.scan_results

    def run_auto_detection_cycle(self) -> List[Dict[str, Any]]:
        """Run autodetect scan (quick common freqs, then full sweep)."""
        self.logger.info("Starting autodetect cycle")
        self.scan_results = self.scanner.scan_auto_detect()

        if self.scan_results:
            self.logger.info("Autodetect found %s signal(s):", len(self.scan_results))
            for signal in self.scan_results:
                phase = signal.get("scan_phase", "full")
                self.logger.info(
                    "  %.3f MHz @ %.1f dB [%s]",
                    signal["frequency_mhz"],
                    signal["power_db"],
                    phase,
                )
        else:
            self.logger.info("Autodetect: no signals above threshold")

        return self.scan_results

    def run_auto_attack_cycle(self) -> List[Dict[str, Any]]:
        """Auto-attack all detected signals (strongest first, adaptive duration)."""
        if not self.scan_results:
            return []

        self.logger.info(
            "Auto-attack: targeting up to %s strongest signal(s)",
            self.config.auto_attack_max_targets,
        )
        self.attack_results = self.attack_engine.execute_adaptive_attack(self.scan_results)

        successful = sum(1 for result in self.attack_results if result.get("success", False))
        self.logger.info(
            "Auto-attack complete: %s/%s successful",
            successful,
            len(self.attack_results),
        )
        return self.attack_results

    def run_attack_cycle(self) -> List[Dict[str, Any]]:
        if not self.scan_results:
            self.logger.warning("No detection results available. Running detection first.")
            self.run_detection_cycle()
            if not self.scan_results:
                self.logger.warning("Still no signals detected. Skipping transmission.")
                return []

        self.logger.info("Starting transmission cycle on %s detected signals", len(self.scan_results))
        self.attack_results = self.attack_engine.execute_adaptive_attack(self.scan_results)

        successful = sum(1 for result in self.attack_results if result.get("success", False))
        self.logger.info(
            "Transmission cycle complete. %s/%s successful",
            successful,
            len(self.attack_results),
        )
        return self.attack_results

    def run_full_cycle(self) -> Dict[str, Any]:
        start_time = datetime.now()
        summary: Dict[str, Any] = {
            "start_time": start_time.isoformat(),
            "detection_count": 0,
            "attack_count": 0,
            "successful_attacks": 0,
            "failed_attacks": 0,
            "signals": [],
            "attacks": [],
        }

        try:
            self.scan_results = self.run_detection_cycle()
            summary["detection_count"] = len(self.scan_results)
            summary["signals"] = self.scan_results

            if self.scan_results:
                self.attack_results = self.run_attack_cycle()
                summary["attack_count"] = len(self.attack_results)
                summary["successful_attacks"] = sum(
                    1 for result in self.attack_results if result.get("success", False)
                )
                summary["failed_attacks"] = summary["attack_count"] - summary["successful_attacks"]
                summary["attacks"] = self.attack_results
            else:
                self.logger.info("No signals detected. Skipping transmission phase.")
        except KeyboardInterrupt:
            self.logger.info("Operation interrupted by user")
        except Exception as exc:
            self.logger.error("Unexpected error during cycle: %s", exc)

        summary["end_time"] = datetime.now().isoformat()
        summary["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return summary

    def run_auto_loop(self) -> Dict[str, Any]:
        """
        Continuous autodetect -> auto-attack loop until Ctrl+C or max cycles.

        In brute mode, locks onto a frequency and re-jams immediately if the
        target is still present after each hold period (no idle gap).
        """
        if self.config.enable_brute_mode:
            return self._run_brute_auto_loop()
        return self._run_standard_auto_loop()

    def _run_standard_auto_loop(self) -> Dict[str, Any]:
        start_time = datetime.now()
        summary: Dict[str, Any] = {
            "mode": "auto",
            "start_time": start_time.isoformat(),
            "cycle_count": 0,
            "total_detections": 0,
            "total_attacks": 0,
            "successful_attacks": 0,
            "failed_attacks": 0,
            "cycles": [],
        }

        cycle_num = 0
        self.logger.info(
            "AUTO MODE: autodetect + auto-attack (interval=%.1fs, max_cycles=%s)",
            self.config.auto_interval_sec,
            self.config.auto_max_cycles or "unlimited",
        )

        try:
            while True:
                cycle_num += 1
                if self.config.auto_max_cycles > 0 and cycle_num > self.config.auto_max_cycles:
                    self.logger.info("Reached max cycles (%s). Stopping.", self.config.auto_max_cycles)
                    break

                cycle_start = datetime.now()
                cycle_summary: Dict[str, Any] = {
                    "cycle": cycle_num,
                    "start_time": cycle_start.isoformat(),
                    "signals": [],
                    "attacks": [],
                    "detection_count": 0,
                    "attack_count": 0,
                    "successful_attacks": 0,
                }

                self.logger.info("--- Auto cycle %s ---", cycle_num)
                self.scan_results = self.run_auto_detection_cycle()
                cycle_summary["detection_count"] = len(self.scan_results)
                cycle_summary["signals"] = list(self.scan_results)
                summary["total_detections"] += len(self.scan_results)

                if self.scan_results:
                    self.attack_results = self.run_auto_attack_cycle()
                    cycle_summary["attacks"] = list(self.attack_results)
                    cycle_summary["attack_count"] = len(self.attack_results)
                    successful = sum(
                        1 for result in self.attack_results if result.get("success", False)
                    )
                    cycle_summary["successful_attacks"] = successful
                    summary["total_attacks"] += len(self.attack_results)
                    summary["successful_attacks"] += successful
                    summary["failed_attacks"] += len(self.attack_results) - successful
                else:
                    self.logger.info(
                        "No target found. Waiting %.1fs before next autodetect...",
                        self.config.auto_interval_sec,
                    )
                    time.sleep(self.config.auto_interval_sec)

                cycle_summary["end_time"] = datetime.now().isoformat()
                cycle_summary["duration_seconds"] = (
                    datetime.now() - cycle_start
                ).total_seconds()
                summary["cycles"].append(cycle_summary)
                summary["cycle_count"] = cycle_num

        except KeyboardInterrupt:
            self.logger.info("Auto mode stopped by user after %s cycle(s)", cycle_num)

        summary["end_time"] = datetime.now().isoformat()
        summary["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return summary

    def _run_brute_auto_loop(self) -> Dict[str, Any]:
        """Brute auto loop: lock frequency and hammer until suppressed."""
        start_time = datetime.now()
        summary: Dict[str, Any] = {
            "mode": "auto-brute",
            "start_time": start_time.isoformat(),
            "cycle_count": 0,
            "total_detections": 0,
            "total_attacks": 0,
            "successful_attacks": 0,
            "failed_attacks": 0,
            "lock_events": 0,
            "suppression_events": 0,
            "cycles": [],
        }

        cycle_num = 0
        locked_frequency: int | None = None

        self.logger.info(
            "BRUTE AUTO: continuous gapless TX (chunk=%.2fs, dither=±%d kHz, verify=%s)",
            self.config.brute_chunk_sec,
            self.config.brute_freq_dither_hz // 1000,
            f"{self.config.brute_verify_interval_sec:.0f}s"
            if self.config.brute_verify_interval_sec > 0
            else "disabled",
        )

        def _verify_suppressed(center_hz: int) -> bool:
            verify_power = self.scanner.scan_frequency(center_hz)
            threshold = (
                self.config.detection_threshold_db - self.config.brute_suppression_margin_db
            )
            if verify_power is None or verify_power <= threshold:
                self.logger.info(
                    "Verify: %.3f MHz quiet (power=%s dB)",
                    center_hz / 1e6,
                    f"{verify_power:.1f}" if verify_power is not None else "n/a",
                )
                return True
            self.logger.warning(
                "Verify: %.3f MHz still active (%.1f dB) — resuming TX",
                center_hz / 1e6,
                verify_power,
            )
            if not self.rf_manager.configure_tx():
                self.logger.error("Failed to re-enter TX after verify peek")
            return False

        verify_cb = _verify_suppressed if self.config.brute_verify_interval_sec > 0 else None

        try:
            while True:
                cycle_num += 1
                if self.config.auto_max_cycles > 0 and cycle_num > self.config.auto_max_cycles:
                    self.logger.info("Reached max cycles (%s). Stopping.", self.config.auto_max_cycles)
                    break

                cycle_start = datetime.now()
                cycle_summary: Dict[str, Any] = {
                    "cycle": cycle_num,
                    "start_time": cycle_start.isoformat(),
                    "locked_frequency": locked_frequency,
                    "attacks": [],
                    "suppressed": False,
                }

                if locked_frequency is None:
                    self.logger.info("--- Brute cycle %s: scanning for target ---", cycle_num)
                    self.scan_results = self.run_auto_detection_cycle()
                    summary["total_detections"] += len(self.scan_results)

                    if not self.scan_results:
                        self.logger.info(
                            "No target. Waiting %.1fs before rescan...",
                            self.config.auto_interval_sec,
                        )
                        time.sleep(self.config.auto_interval_sec)
                        cycle_summary["detection_count"] = 0
                        summary["cycles"].append(cycle_summary)
                        summary["cycle_count"] = cycle_num
                        continue

                    strongest = max(self.scan_results, key=lambda item: item["power_db"])
                    locked_frequency = strongest["frequency"]
                    summary["lock_events"] += 1
                    self.logger.warning(
                        "BRUTE LOCK acquired: %.3f MHz (%.1f dB)",
                        strongest["frequency_mhz"],
                        strongest["power_db"],
                    )

                attack_result = self.attack_engine.execute_continuous_brute_lock(
                    locked_frequency,
                    verify_callback=verify_cb,
                )
                self.attack_results = [attack_result]
                cycle_summary["attacks"] = [attack_result]
                cycle_summary["locked_frequency"] = locked_frequency
                summary["total_attacks"] += 1
                if attack_result.get("success"):
                    summary["successful_attacks"] += 1
                else:
                    summary["failed_attacks"] += 1

                if attack_result.get("suppressed"):
                    locked_frequency = None
                    cycle_summary["suppressed"] = True
                    summary["suppression_events"] += 1
                elif attack_result.get("error"):
                    self.logger.error("Brute error, releasing lock: %s", attack_result["error"])
                    locked_frequency = None

                cycle_summary["end_time"] = datetime.now().isoformat()
                cycle_summary["duration_seconds"] = (
                    datetime.now() - cycle_start
                ).total_seconds()
                summary["cycles"].append(cycle_summary)
                summary["cycle_count"] = cycle_num

        except KeyboardInterrupt:
            self.logger.info("Brute auto mode stopped by user after %s cycle(s)", cycle_num)

        summary["end_time"] = datetime.now().isoformat()
        summary["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return summary

    def run_full_jam(self) -> Dict[str, Any]:
        """Full continuous jam on a fixed frequency — no scan, TX until Ctrl+C."""
        frequency_hz = self.config.target_frequency_hz or JAM_433_MHZ_HZ
        start_time = datetime.now()

        self.logger.warning(
            "FULL JAM: continuous TX on %.3f MHz (%s)",
            frequency_hz / 1e6,
            f"max {self.config.jam_duration_sec:.0f}s"
            if self.config.jam_duration_sec > 0
            else "Ctrl+C to stop",
        )

        summary: Dict[str, Any] = {
            "mode": "jam",
            "frequency_hz": frequency_hz,
            "frequency_mhz": frequency_hz / 1e6,
            "start_time": start_time.isoformat(),
            "attacks": [],
        }

        try:
            attack_result = self.attack_engine.execute_continuous_brute_lock(frequency_hz)
            summary["attacks"] = [attack_result]
            summary["successful"] = attack_result.get("success", False)
            summary["chunks_transmitted"] = attack_result.get("chunks_transmitted", 0)
        except KeyboardInterrupt:
            self.logger.info("Full jam stopped by user")

        summary["end_time"] = datetime.now().isoformat()
        summary["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return summary

    def save_report(self, summary: Dict[str, Any]) -> str:
        os.makedirs(self.config.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(self.config.output_dir, f"attack_report_{timestamp}.json")

        with open(report_file, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, default=str)

        self.logger.info("Report saved to %s", report_file)
        return report_file
