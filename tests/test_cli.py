"""Tests for CLI argument parsing."""

from flipper_da.cli import build_config, parse_arguments


def test_parse_arguments_defaults():
    args = parse_arguments([])

    assert args.mode == "auto"
    assert args.threshold == -40.0
    assert args.aggressive_scan is False
    assert args.freq is None
    assert args.auto_interval == 2.0
    assert args.auto_cycles == 0


def test_build_config_with_manual_frequency():
    args = parse_arguments(["--freq", "433920000", "--aggressive-scan"])
    config = build_config(args)

    assert config.target_frequency_hz == 433_920_000
    assert config.enable_aggressive_scan is True
    assert config.aggressive_scan_step_hz == 100_000
