"""BladeRF hardware manager using official libbladeRF Python bindings."""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from flipper_da.config import SystemConfig
from flipper_da.rf_utils import (
    complex_to_sc16_q11_interleaved,
    sc16_q11_interleaved_to_complex,
)

try:
    import bladerf
except ImportError:  # pragma: no cover - exercised when hardware driver missing
    bladerf = None


class BladeRFManager:
    """High-level manager for BladeRF SDR RX/TX operations."""

    def __init__(self, config: SystemConfig, device_identifier: Optional[str] = None):
        self.config = config
        self.device_identifier = device_identifier
        self.device: Optional[object] = None
        self.rx_channel: Optional[object] = None
        self.tx_channel: Optional[object] = None
        self.logger = logging.getLogger("BladeRFManager")
        self.is_initialized = False
        self._active_direction: Optional[str] = None

    def initialize(self) -> bool:
        """Open and configure the BladeRF device for RX."""
        if bladerf is None:
            self.logger.error(
                "bladerf Python bindings not installed. Install libbladeRF and its Python package."
            )
            return False

        try:
            self.device = bladerf.BladeRF(self.device_identifier)
            self.logger.info("BladeRF device opened: %s", self.device.devinfo)

            self.rx_channel = self.device.Channel(bladerf.CHANNEL_RX(0))
            self.tx_channel = self.device.Channel(bladerf.CHANNEL_TX(0))

            self._configure_channel(self.rx_channel, self.config.rx_gain)
            self.rx_channel.frequency = 433_000_000

            if not self.configure_rx():
                return False

            self.is_initialized = True
            self.logger.info("BladeRF initialized successfully")
            return True
        except Exception as exc:
            self.logger.error("Failed to initialize BladeRF: %s", exc)
            self.is_initialized = False
            return False

    def close(self) -> None:
        """Close the BladeRF device and release resources."""
        if self.device is not None:
            try:
                self._disable_active_channel()
                self.device.close()
                self.logger.info("BladeRF connection closed")
            except Exception as exc:
                self.logger.error("Error closing BladeRF: %s", exc)
        self.device = None
        self.rx_channel = None
        self.tx_channel = None
        self.is_initialized = False
        self._active_direction = None

    def configure_tx(self) -> bool:
        """Configure device for transmission mode."""
        if not self.is_initialized or self.device is None or self.tx_channel is None:
            self.logger.error("Device not initialized")
            return False

        try:
            self._disable_active_channel()
            self._configure_channel(self.tx_channel, self.config.tx_gain)
            self.device.sync_config(
                bladerf.ChannelLayout.TX_X1,
                bladerf.Format.SC16_Q11,
                self.config.sync_num_buffers,
                self.config.sync_buffer_size,
                self.config.sync_num_transfers,
                self.config.sync_stream_timeout_ms,
            )
            self.tx_channel.enable = True
            self._active_direction = "tx"
            return True
        except Exception as exc:
            self.logger.error("Failed to configure TX: %s", exc)
            return False

    def configure_rx(self) -> bool:
        """Configure device for reception mode."""
        if not self.is_initialized or self.device is None or self.rx_channel is None:
            self.logger.error("Device not initialized")
            return False

        try:
            self._disable_active_channel()
            self._configure_channel(self.rx_channel, self.config.rx_gain)
            self.device.sync_config(
                bladerf.ChannelLayout.RX_X1,
                bladerf.Format.SC16_Q11,
                self.config.sync_num_buffers,
                self.config.sync_buffer_size,
                self.config.sync_num_transfers,
                self.config.sync_stream_timeout_ms,
            )
            self.rx_channel.enable = True
            self._active_direction = "rx"
            return True
        except Exception as exc:
            self.logger.error("Failed to configure RX: %s", exc)
            return False

    def set_frequency(self, frequency_hz: int) -> bool:
        """Set center frequency on the active RF channel."""
        if not self.is_initialized:
            return False

        channel = self._active_channel()
        if channel is None:
            self.logger.error("No active RF channel configured")
            return False

        try:
            channel.frequency = frequency_hz
            time.sleep(self.config.pll_settle_sec)
            return True
        except Exception as exc:
            self.logger.error("Failed to set frequency %s: %s", frequency_hz, exc)
            return False

    def receive_samples(self, num_samples: int) -> Optional[np.ndarray]:
        """Receive IQ samples as normalized complex64."""
        if not self.is_initialized or self.device is None:
            return None

        if num_samples < 1:
            return None

        try:
            bytes_per_sample = 4
            buffer = bytearray(num_samples * bytes_per_sample)
            self.device.sync_rx(buffer, num_samples)
            raw = np.frombuffer(buffer, dtype=np.int16)
            return sc16_q11_interleaved_to_complex(raw)
        except Exception as exc:
            self.logger.error("Receive error: %s", exc)
            return None

    def transmit_samples(self, samples: np.ndarray) -> bool:
        """Transmit complex64 samples using chunked SC16_Q11 buffers."""
        if not self.is_initialized or self.device is None:
            return False

        try:
            interleaved = complex_to_sc16_q11_interleaved(samples)
            chunk_samples = max(1, self.config.tx_chunk_samples)
            total_samples = interleaved.size // 2
            offset = 0

            while offset < total_samples:
                count = min(chunk_samples, total_samples - offset)
                start = offset * 2
                end = start + count * 2
                chunk = interleaved[start:end]
                self.device.sync_tx(chunk.tobytes(), count)
                offset += count

            return True
        except Exception as exc:
            self.logger.error("Transmit error: %s", exc)
            return False

    def _configure_channel(self, channel: object, gain: int) -> None:
        channel.sample_rate = self.config.sample_rate
        channel.bandwidth = self.config.bandwidth
        channel.gain = gain

    def _active_channel(self) -> Optional[object]:
        if self._active_direction == "tx":
            return self.tx_channel
        if self._active_direction == "rx":
            return self.rx_channel
        return self.rx_channel

    def _disable_active_channel(self) -> None:
        if self._active_direction == "tx" and self.tx_channel is not None:
            self.tx_channel.enable = False
        elif self._active_direction == "rx" and self.rx_channel is not None:
            self.rx_channel.enable = False
        self._active_direction = None
