"""Tests for brute lock-on auto mode."""

from flipper_da.system import FlipperAttackSystem
from tests.conftest import MockRFManager


def test_brute_auto_loop_locks_and_reattacks(config, mock_rf):
    config.brute_hold_sec = 0.05
    config.brute_chunk_sec = 0.02
    config.auto_max_cycles = 3
    mock_rf.set_rx_power(1.0)

    system = FlipperAttackSystem(config, rf_manager=mock_rf)
    summary = system.run_auto_loop()

    assert summary["mode"] == "auto-brute"
    assert summary["lock_events"] >= 1
    assert summary["total_attacks"] >= 2
    assert len(mock_rf.tx_calls) >= 2


def test_brute_auto_releases_lock_when_signal_weak(config, mock_rf):
    config.brute_hold_sec = 0.02
    config.brute_chunk_sec = 0.01
    config.auto_max_cycles = 2
    config.brute_suppression_margin_db = 0.0
    mock_rf.set_rx_power(1.0)

    system = FlipperAttackSystem(config, rf_manager=mock_rf)

    # After first brute hold, simulate suppressed target
    original_scan = system.scanner.scan_frequency

    def scan_with_drop(frequency_hz):
        if len(mock_rf.tx_calls) >= 1:
            mock_rf.set_rx_power(0.0)
        return original_scan(frequency_hz)

    system.scanner.scan_frequency = scan_with_drop  # type: ignore[method-assign]

    summary = system.run_auto_loop()

    assert summary["suppression_events"] >= 1
