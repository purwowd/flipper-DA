"""Configuration and frequency band definitions."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

# SC16_Q11: 16-bit signed samples with 11 fractional bits
SC16_Q11_SCALE = 2048.0

FLIPPER_BANDS: List[Tuple[int, int]] = [
    (300_000_000, 348_000_000),
    (387_000_000, 464_000_000),
    (779_000_000, 928_000_000),
]

COMMON_FLIPPER_FREQS: List[int] = [
    315_000_000,
    433_920_000,
    868_000_000,
    915_000_000,
]

# Sub-GHz channel map (analogous to Wi-Fi CHANNELS in B210 reference scripts)
FLIPPER_CHANNELS: dict[int, int] = {
    315: 315_000_000,
    433: 433_920_000,
    868: 868_000_000,
    915: 915_000_000,
}

# Default full-jam target (433.92 MHz ISM)
JAM_433_MHZ_HZ: int = FLIPPER_CHANNELS[433]


def resolve_channel_frequencies(channel_codes: List[int]) -> List[int]:
    """Map Flipper channel codes (315, 433, ...) to center frequencies in Hz."""
    freqs: List[int] = []
    for code in channel_codes:
        freq = FLIPPER_CHANNELS.get(code)
        if freq is not None:
            freqs.append(freq)
    return freqs


@dataclass
class SystemConfig:
    """System-wide configuration parameters."""

    sample_rate: int = 2_000_000
    bandwidth: int = 1_500_000
    rx_gain: int = 40
    tx_gain: int = 40
    # Relative power threshold in dB (not calibrated dBm; see rf_utils.power_to_db)
    detection_threshold_db: float = -40.0
    scan_step_hz: int = 1_000_000
    aggressive_scan_step_hz: int = 100_000
    scan_duration_ms: float = 10.0
    attack_duration_sec: float = 3.0
    noise_amplitude: float = 0.5
    enable_aggressive_scan: bool = False
    log_level: str = "INFO"
    output_dir: str = "logs"
    # Optional manual target frequency (Hz) for detect/attack modes
    target_frequency_hz: Optional[int] = None
    sync_num_buffers: int = 16
    sync_buffer_size: int = 8192
    sync_num_transfers: int = 8
    sync_stream_timeout_ms: int = 3500
    pll_settle_sec: float = 0.005
    tx_chunk_samples: int = 8192
    # Auto mode: continuous detect -> attack loop
    auto_interval_sec: float = 2.0
    auto_max_cycles: int = 0  # 0 = run until Ctrl+C
    auto_attack_max_targets: int = 3
    auto_quick_scan: bool = True
    enable_brute_mode: bool = True
    brute_hold_sec: float = 15.0
    brute_chunk_sec: float = 0.05
    brute_sweep_bandwidth_hz: float = 1_500_000
    brute_single_target: bool = True
    brute_reattack_delay_sec: float = 0.0
    brute_suppression_margin_db: float = 3.0
    # Continuous lock: TX without RX gaps (0 = never verify, jam until Ctrl+C)
    brute_continuous: bool = True
    brute_verify_interval_sec: float = 0.0
    brute_freq_dither_hz: int = 75_000
    brute_pll_settle_sec: float = 0.001
    brute_max_chunks: int = 0  # 0 = unlimited; set in tests to avoid infinite loops
    # Payload style (inspired by B210 SoapySDR jam reference: noise / chirp / both)
    payload_mode: str = "both"
    tx_buffer_samples: int = 32768
    jam_duration_sec: float = 0.0  # 0 = until Ctrl+C
    ultra_brute: bool = False
    jam_refresh_buffers: bool = False  # regen noise/chirp every TX chunk


def apply_jam_ultra_preset(config: SystemConfig) -> SystemConfig:
    """Max-aggression defaults for --mode jam (lab use only)."""
    config.ultra_brute = True
    config.jam_refresh_buffers = True
    config.payload_mode = "ultra"
    config.brute_freq_dither_hz = max(config.brute_freq_dither_hz, 200_000)
    config.brute_chunk_sec = min(config.brute_chunk_sec, 0.02)
    config.brute_sweep_bandwidth_hz = max(config.brute_sweep_bandwidth_hz, 1_500_000)
    config.noise_amplitude = 1.0
    config.bandwidth = max(config.bandwidth, 1_500_000)
    # Only bump factory-default gain; never cap user-supplied --tx-gain
    if config.tx_gain == 40:
        config.tx_gain = 60
    config.brute_pll_settle_sec = 0.0005
    return config
