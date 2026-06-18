"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from flipper_da.config import SystemConfig
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
        choices=["auto", "detect", "attack", "full"],
        default="auto",
        help="auto: continuous autodetect+attack (default), detect/attack/full: single cycle",
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
        default=3.0,
        help="Transmission duration in seconds (default: 3.0)",
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
        help="RF gain in dB, range -15 to 60 (default: 40)",
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

    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> SystemConfig:
    return SystemConfig(
        detection_threshold_db=args.threshold,
        attack_duration_sec=args.duration,
        scan_step_hz=args.scan_step,
        aggressive_scan_step_hz=args.aggressive_scan_step,
        enable_aggressive_scan=args.aggressive_scan,
        target_frequency_hz=args.freq,
        rx_gain=args.gain,
        tx_gain=args.gain,
        log_level=args.log_level,
        output_dir=args.output_dir,
        auto_interval_sec=args.auto_interval,
        auto_max_cycles=args.auto_cycles,
        auto_attack_max_targets=args.auto_targets,
        auto_quick_scan=not args.no_quick_scan,
    )


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
