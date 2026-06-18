"""Compatibility helpers for different libbladeRF Python binding versions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from flipper_da.config import SystemConfig

# libbladeRF C API constants for SISO streams
BLADERF_RX_X1 = 0
BLADERF_TX_X1 = 1


def get_sc16_format(bladerf_module: Any) -> Any:
    if hasattr(bladerf_module, "Format"):
        return bladerf_module.Format.SC16_Q11
    if hasattr(bladerf_module, "BLADERF_FORMAT_SC16_Q11"):
        return bladerf_module.BLADERF_FORMAT_SC16_Q11
    return 0


def get_sync_layout(bladerf_module: Any, direction: str) -> Any:
    """
    Resolve sync_config layout for RX or TX across binding versions.

    Modern bindings expose ChannelLayout.RX_X1 / TX_X1.
    Older bindings expose Direction.RX / TX or raw module constants.
    """
    if hasattr(bladerf_module, "ChannelLayout"):
        return (
            bladerf_module.ChannelLayout.RX_X1
            if direction == "rx"
            else bladerf_module.ChannelLayout.TX_X1
        )

    try:
        from bladerf._bladerf import ChannelLayout  # type: ignore

        return ChannelLayout.RX_X1 if direction == "rx" else ChannelLayout.TX_X1
    except Exception:
        pass

    if hasattr(bladerf_module, "Direction"):
        return (
            bladerf_module.Direction.RX
            if direction == "rx"
            else bladerf_module.Direction.TX
        )

    return BLADERF_RX_X1 if direction == "rx" else BLADERF_TX_X1


def sync_config(device: Any, bladerf_module: Any, direction: str, config: SystemConfig) -> None:
    """Call device.sync_config with the correct layout and argument count."""
    layout = get_sync_layout(bladerf_module, direction)
    fmt = get_sc16_format(bladerf_module)

    try:
        device.sync_config(
            layout,
            fmt,
            config.sync_num_buffers,
            config.sync_buffer_size,
            config.sync_num_transfers,
            config.sync_stream_timeout_ms,
        )
        return
    except TypeError:
        device.sync_config(
            layout,
            fmt,
            config.sync_num_buffers,
            config.sync_buffer_size,
            config.sync_num_transfers,
        )


def set_channel_enabled(
    device: Any,
    channel: Any,
    channel_id: Optional[int],
    enabled: bool,
) -> None:
    """Enable or disable an RF channel across binding versions."""
    if hasattr(channel, "enable"):
        channel.enable = enabled
        return

    if channel_id is not None and hasattr(device, "enable_module"):
        device.enable_module(channel_id, enabled)
        return

    raise AttributeError("No supported channel enable API found on this bladerf binding")


def describe_binding(bladerf_module: Any) -> str:
    if hasattr(bladerf_module, "ChannelLayout"):
        api = "modern (ChannelLayout)"
    elif hasattr(bladerf_module, "Direction"):
        api = "legacy (Direction)"
    else:
        api = "unknown"

    version = getattr(bladerf_module, "__version__", "unknown")
    return f"bladerf binding: {api}, version={version}"


def log_binding_info(logger: logging.Logger, bladerf_module: Any) -> None:
    logger.info(describe_binding(bladerf_module))
