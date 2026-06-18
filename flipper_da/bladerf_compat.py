"""Compatibility helpers for different libbladeRF Python binding versions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from flipper_da.config import SystemConfig

# libbladeRF C API constants for SISO streams
BLADERF_RX_X1 = 0
BLADERF_TX_X1 = 1
BLADERF_FORMAT_SC16_Q11 = 0


class EnumValue:
    """Minimal enum-like wrapper for bindings that call `.value` on sync args."""

    __slots__ = ("value",)

    def __init__(self, value: int):
        self.value = value


def ensure_enum_like(value: Any) -> Any:
    if hasattr(value, "value"):
        return value
    if isinstance(value, int):
        return EnumValue(value)
    return value


def _resolve_internal_module(bladerf_module: Any) -> Any | None:
    for attr in ("_bladerf", "bladerf", "_BladeRF"):
        submodule = getattr(bladerf_module, attr, None)
        if submodule is not None and (
            hasattr(submodule, "ChannelLayout") or hasattr(submodule, "Direction")
        ):
            return submodule

    try:
        import bladerf._bladerf as internal  # type: ignore

        return internal
    except Exception:
        return None


def get_sc16_format(bladerf_module: Any) -> Any:
    internal = _resolve_internal_module(bladerf_module)

    if internal is not None and hasattr(internal, "Format"):
        return internal.Format.SC16_Q11

    if hasattr(bladerf_module, "Format"):
        return bladerf_module.Format.SC16_Q11

    if hasattr(bladerf_module, "BLADERF_FORMAT_SC16_Q11"):
        return ensure_enum_like(bladerf_module.BLADERF_FORMAT_SC16_Q11)

    return ensure_enum_like(BLADERF_FORMAT_SC16_Q11)


def get_sync_layout(bladerf_module: Any, direction: str) -> Any:
    """
    Resolve sync_config layout for RX or TX across binding versions.

    Modern bindings expose ChannelLayout.RX_X1 / TX_X1.
    Some installs only export enums from the internal `_bladerf` module.
    """
    internal = _resolve_internal_module(bladerf_module)

    if internal is not None and hasattr(internal, "ChannelLayout"):
        return (
            internal.ChannelLayout.RX_X1
            if direction == "rx"
            else internal.ChannelLayout.TX_X1
        )

    if hasattr(bladerf_module, "ChannelLayout"):
        return (
            bladerf_module.ChannelLayout.RX_X1
            if direction == "rx"
            else bladerf_module.ChannelLayout.TX_X1
        )

    if internal is not None and hasattr(internal, "Direction"):
        return internal.Direction.RX if direction == "rx" else internal.Direction.TX

    if hasattr(bladerf_module, "Direction"):
        return (
            bladerf_module.Direction.RX
            if direction == "rx"
            else bladerf_module.Direction.TX
        )

    raw = BLADERF_RX_X1 if direction == "rx" else BLADERF_TX_X1
    return ensure_enum_like(raw)


def sync_config(device: Any, bladerf_module: Any, direction: str, config: SystemConfig) -> None:
    """Call device.sync_config with the correct layout and argument count."""
    layout = ensure_enum_like(get_sync_layout(bladerf_module, direction))
    fmt = ensure_enum_like(get_sc16_format(bladerf_module))

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
    internal = _resolve_internal_module(bladerf_module)

    if hasattr(bladerf_module, "ChannelLayout") or (
        internal is not None and hasattr(internal, "ChannelLayout")
    ):
        api = "modern (ChannelLayout)"
    elif hasattr(bladerf_module, "Direction") or (
        internal is not None and hasattr(internal, "Direction")
    ):
        api = "legacy (Direction)"
    else:
        api = "wrapped-constants"

    version = getattr(bladerf_module, "__version__", "unknown")
    internal_name = getattr(internal, "__name__", None) if internal is not None else None
    if internal_name:
        return f"bladerf binding: {api}, version={version}, internal={internal_name}"
    return f"bladerf binding: {api}, version={version}"


def log_binding_info(logger: logging.Logger, bladerf_module: Any) -> None:
    logger.info(describe_binding(bladerf_module))
