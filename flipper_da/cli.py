"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from flipper_da.config import JAM_433_MHZ_HZ, SystemConfig, apply_jam_ultra_preset, resolve_channel_frequencies
from flipper_da.logging_setup import setup_logging
from flipper_da.system import FlipperAttackSystem


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flipper Zero spectrum research toolkit (BladeRF)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
LEGAL WARNING:
This tool is for educational and research purposes only.
Use only in controlled laboratory environments with explicit authorization.
Unauthorized transmission on radio frequencies is illegal.
        """,
    )

    parser.add_argument(
        "--mode",
        "-m",
        choices=["auto", "detect", "attack", "full", "jam"],
        default="auto",
        help="jam: full continuous TX on 433.92 MHz (or --freq), auto: autodetect+attack",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=-40.0,
        help="Relative detection threshold in dB (default: -40.0)",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=None,
        help="Burst attack duration in sec (default 3). Jam mode: omit = until Ctrl+C",
    )
    parser.add_argument(
        "--scan-step",
        "-s",
        type=int,
        default=1_000_000,
        help="Scan step size in Hz (default: 1000000)",
    )
    parser.add_argument(
        "--aggressive-scan-step",
        type=int,
        default=100_000,
        help="Fine scan step in Hz when --aggressive-scan is enabled (default: 100000)",
    )
    parser.add_argument(
        "--aggressive-scan",
        action="store_true",
        help="Use finer scan resolution across bands and common frequencies",
    )
    parser.add_argument(
        "-ch",
        "--channels",
        type=int,
        nargs="+",
        default=None,
        help="Flipper channel codes: 315 433 868 915 (433 = 433.92 MHz)",
    )
    parser.add_argument(
        "--payload-mode",
        choices=["noise", "chirp", "both", "brute", "ultra"],
        default="both",
        help="TX waveform: noise/chirp/both/ultra (max)/brute",
    )
    parser.add_argument(
        "--bufsize",
        type=int,
        default=32768,
        help="TX buffer size in samples, reused in continuous jam (default: 32768)",
    )
    parser.add_argument(
        "--freq",
        "-f",
        type=int,
        default=None,
        help="Manual target frequency in Hz (e.g. 433920000)",
    )
    parser.add_argument(
        "--gain",
        "-g",
        type=int,
        default=40,
        help="RX gain in dB (default: 40)",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="logs",
        help="Output directory for logs and reports (default: logs)",
    )
    parser.add_argument(
        "--auto-interval",
        type=float,
        default=2.0,
        help="Seconds to wait between autodetect cycles when no signal found (default: 2.0)",
    )
    parser.add_argument(
        "--auto-cycles",
        type=int,
        default=0,
        help="Max auto cycles before stopping, 0=unlimited until Ctrl+C (default: 0)",
    )
    parser.add_argument(
        "--auto-targets",
        type=int,
        default=3,
        help="Max signals to auto-attack per cycle, strongest first (default: 3)",
    )
    parser.add_argument(
        "--no-quick-scan",
        action="store_true",
        help="Disable fast common-frequency autodetect phase",
    )
    parser.add_argument(
        "--no-brute",
        action="store_true",
        help="Disable brute lock-on sustained jamming (use short burst attacks)",
    )
    parser.add_argument(
        "--brute-hold",
        type=float,
        default=15.0,
        help="Seconds of continuous TX per brute hold (default: 15)",
    )
    parser.add_argument(
        "--brute-chunk",
        type=float,
        default=0.05,
        help="TX chunk size in seconds during brute hold (default: 0.05)",
    )
    parser.add_argument(
        "--brute-dither",
        type=int,
        default=75_000,
        help="Frequency dither +/- Hz around target (default: 75000)",
    )
    parser.add_argument(
        "--brute-verify-interval",
        type=float,
        default=0.0,
        help="RX verify interval in seconds, 0=never (default: 0, jam until Ctrl+C)",
    )
    parser.add_argument(
        "--no-ultra",
        action="store_true",
        help="Disable ultra brute preset in jam mode (weaker payload/dither)",
    )

    parser.add_argument(
        "--tx-gain",
        type=int,
        default=None,
        help="TX gain in dB, no software cap — set per your BladeRF hardware (default: same as --gain)",
    )

    return parser.parse_args(argv)


def _resolve_target_frequency(args: argparse.Namespace) -> int | None:
    if args.freq is not None:
        return args.freq
    if args.channels:
        freqs = resolve_channel_frequencies(args.channels)
        if freqs:
            return freqs[0]
    return None


def build_config(args: argparse.Namespace) -> SystemConfig:
    target_freq = _resolve_target_frequency(args)
    tx_gain = args.tx_gain if args.tx_gain is not None else args.gain
    enable_brute = not args.no_brute
    brute_verify = args.brute_verify_interval
    brute_dither = args.brute_dither
    brute_chunk = args.brute_chunk
    payload_mode = args.payload_mode
    jam_duration = 0.0

    if args.mode == "jam":
        target_freq = target_freq or JAM_433_MHZ_HZ
        enable_brute = True
        brute_verify = 0.0
        brute_dither = max(brute_dither, 100_000)
        brute_chunk = min(brute_chunk, 0.05)
        jam_duration = args.duration if args.duration is not None else 0.0
        if args.tx_gain is None and args.gain == 40:
            tx_gain = 60
        if args.payload_mode not in ("both", "ultra"):
            payload_mode = args.payload_mode

    config = SystemConfig(
        detection_threshold_db=args.threshold,
        attack_duration_sec=args.duration if args.duration is not None else 3.0,
        scan_step_hz=args.scan_step,
        aggressive_scan_step_hz=args.aggressive_scan_step,
        enable_aggressive_scan=args.aggressive_scan,
        target_frequency_hz=target_freq,
        rx_gain=args.gain,
        log_level=args.log_level,
        output_dir=args.output_dir,
        auto_interval_sec=args.auto_interval,
        auto_max_cycles=args.auto_cycles,
        auto_attack_max_targets=args.auto_targets,
        auto_quick_scan=not args.no_quick_scan,
        enable_brute_mode=enable_brute,
        brute_hold_sec=args.brute_hold,
        brute_chunk_sec=brute_chunk,
        brute_freq_dither_hz=brute_dither,
        brute_verify_interval_sec=brute_verify,
        tx_gain=tx_gain,
        payload_mode=payload_mode,
        tx_buffer_samples=args.bufsize,
        jam_duration_sec=jam_duration,
    )

    if args.mode == "jam" and not args.no_ultra:
        apply_jam_ultra_preset(config)

    return config


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    setup_logging(args.log_level, args.output_dir)
    logger = logging.getLogger("Main")

    logger.info("=" * 60)
    logger.info("FLIPPER ZERO SPECTRUM RESEARCH SYSTEM")
    logger.info("RESEARCH PURPOSES ONLY - VERSION 2.1.0")
    logger.info("=" * 60)
    logger.warning("UNAUTHORIZED USE IS ILLEGAL AND UNETHICAL")
    logger.warning("Use only in controlled laboratory environments")
    logger.info("=" * 60)

    config = build_config(args)
    system = FlipperAttackSystem(config)

    try:
        if not system.initialize():
            logger.error("Failed to initialize system. Exiting.")
            return 1

        if args.mode == "detect":
            results = system.run_detection_cycle()
            summary = {
                "mode": "detect",
                "detection_count": len(results),
                "signals": results,
                "timestamp": datetime.now().isoformat(),
            }
        elif args.mode == "attack":
            system.run_detection_cycle()
            results = system.run_attack_cycle()
            summary = {
                "mode": "attack",
                "attack_count": len(results),
                "attacks": results,
                "timestamp": datetime.now().isoformat(),
            }
        elif args.mode == "full":
            summary = system.run_full_cycle()
            summary["mode"] = "full"
        elif args.mode == "jam":
            summary = system.run_full_jam()
        else:
            summary = system.run_auto_loop()

        system.save_report(summary)

        logger.info("=" * 60)
        logger.info("OPERATION COMPLETE")
        logger.info("Mode: %s", summary["mode"])
        if summary["mode"] == "auto":
            logger.info("Auto cycles completed: %s", summary.get("cycle_count", 0))
            logger.info("Total signals detected: %s", summary.get("total_detections", 0))
            logger.info("Total transmissions: %s", summary.get("total_attacks", 0))
            logger.info("Successful transmissions: %s", summary.get("successful_attacks", 0))
        elif summary["mode"] == "auto-brute":
            logger.info("Brute cycles: %s", summary.get("cycle_count", 0))
            logger.info("Lock events: %s", summary.get("lock_events", 0))
            logger.info("Suppressions: %s", summary.get("suppression_events", 0))
            logger.info("Total brute holds: %s", summary.get("total_attacks", 0))
        elif summary["mode"] == "jam":
            logger.info("Jam frequency: %.3f MHz", summary.get("frequency_mhz", 0))
            logger.info("Chunks transmitted: %s", summary.get("chunks_transmitted", 0))
            logger.info("Duration: %.1fs", summary.get("duration_seconds", 0))
        else:
            if "detection_count" in summary:
                logger.info("Signals detected: %s", summary["detection_count"])
            if "attack_count" in summary:
                logger.info("Transmissions executed: %s", summary["attack_count"])
                logger.info("Successful transmissions: %s", summary.get("successful_attacks", 0))
        logger.info("=" * 60)
        return 0
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 130
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        import traceback

        logger.error(traceback.format_exc())
        return 1
    finally:
        system.shutdown()


if __name__ == "__main__":
    sys.exit(main())
