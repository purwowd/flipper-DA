"""Tests for bladerf API compatibility helpers."""

from types import SimpleNamespace

from flipper_da.bladerf_compat import (
    BLADERF_RX_X1,
    BLADERF_TX_X1,
    EnumValue,
    ensure_enum_like,
    get_sc16_format,
    get_sync_layout,
    sync_config,
)
from flipper_da.config import SystemConfig


def test_get_sync_layout_prefers_channel_layout():
    module = SimpleNamespace(
        ChannelLayout=SimpleNamespace(RX_X1="RX_X1", TX_X1="TX_X1"),
        Direction=SimpleNamespace(RX="RX", TX="TX"),
    )

    assert get_sync_layout(module, "rx") == "RX_X1"
    assert get_sync_layout(module, "tx") == "TX_X1"


def test_get_sync_layout_falls_back_to_direction():
    module = SimpleNamespace(Direction=SimpleNamespace(RX="RX", TX="TX"))

    assert get_sync_layout(module, "rx") == "RX"
    assert get_sync_layout(module, "tx") == "TX"


def test_get_sync_layout_falls_back_to_wrapped_numeric_constants():
    module = SimpleNamespace()

    layout = get_sync_layout(module, "rx")

    assert isinstance(layout, EnumValue)
    assert layout.value == BLADERF_RX_X1
    assert get_sync_layout(module, "tx").value == BLADERF_TX_X1


def test_ensure_enum_like_wraps_plain_int():
    wrapped = ensure_enum_like(3)
    assert wrapped.value == 3


def test_ensure_enum_like_preserves_existing_enum():
    original = SimpleNamespace(value=9)
    assert ensure_enum_like(original) is original


def test_sync_config_wraps_numeric_layout_for_value_based_binding():
    config = SystemConfig()
    module = SimpleNamespace()
    calls = []

    class Device:
        def sync_config(self, layout, fmt, *args):
            calls.append((layout.value, fmt.value, args))

    sync_config(Device(), module, "rx", config)

    assert calls[0][0] == BLADERF_RX_X1
    assert calls[0][1] == 0


def test_sync_config_uses_six_arg_signature_first():
    config = SystemConfig()
    module = SimpleNamespace(
        Direction=SimpleNamespace(RX="RX", TX="TX"),
        Format=SimpleNamespace(SC16_Q11="SC16_Q11"),
    )
    calls = []

    class Device:
        def sync_config(self, *args):
            calls.append(args)

    sync_config(Device(), module, "rx", config)

    assert calls[0][0] == "RX"
    assert calls[0][1] == "SC16_Q11"
    assert calls[0][2] == config.sync_num_buffers


def test_get_sc16_format_from_format_enum():
    module = SimpleNamespace(Format=SimpleNamespace(SC16_Q11="fmt"))

    assert get_sc16_format(module) == "fmt"
