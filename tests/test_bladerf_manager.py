"""Tests for BladeRF manager initialization flow."""

from types import SimpleNamespace

import pytest

from flipper_da.bladerf_manager import BladeRFManager
from flipper_da.config import SystemConfig


class MockChannel:
    def __init__(self):
        self.sample_rate = None
        self.bandwidth = None
        self.gain = None
        self.frequency = None
        self.enable = False


class MockBladeRFDevice:
    def __init__(self, device_identifier=None):
        self.device_identifier = device_identifier
        self.devinfo = "mock-bladerf"
        self.fpga_configured = True
        self.sync_layout = None
        self.rx_channel = MockChannel()
        self.tx_channel = MockChannel()
        self.closed = False

    def Channel(self, channel_id):
        if channel_id & 1 == 0:  # RX
            return self.rx_channel
        return self.tx_channel

    def sync_config(self, layout, fmt, num_buffers, buffer_size, num_transfers, stream_timeout=None):
        self.sync_layout = layout

    def close(self):
        self.closed = True


@pytest.fixture
def mock_bladerf_module(monkeypatch):
    module = SimpleNamespace(
        BladeRF=MockBladeRFDevice,
        CHANNEL_RX=lambda ch: (ch << 1) | 0,
        CHANNEL_TX=lambda ch: (ch << 1) | 1,
        Direction=SimpleNamespace(RX="RX", TX="TX"),
        Format=SimpleNamespace(SC16_Q11="SC16_Q11"),
    )
    monkeypatch.setattr("flipper_da.bladerf_manager.bladerf", module)
    return module


def test_initialize_configures_rx_before_marking_ready(mock_bladerf_module):
    manager = BladeRFManager(SystemConfig())

    assert manager.initialize() is True
    assert manager.is_initialized is True
    assert manager._active_direction == "rx"
    assert manager.device.rx_channel.enable is True
    assert manager.device.sync_layout == "RX"


def test_initialize_fails_when_fpga_not_loaded(mock_bladerf_module):
    def _device_without_fpga(device_identifier=None):
        device = MockBladeRFDevice(device_identifier)
        device.fpga_configured = False
        return device

    mock_bladerf_module.BladeRF = _device_without_fpga
    manager = BladeRFManager(SystemConfig())

    assert manager.initialize() is False
    assert manager.is_initialized is False
