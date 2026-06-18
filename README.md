# Flipper-DA

Spectrum research toolkit for Sub-GHz ISM bands commonly used by Flipper Zero, built on BladeRF SDR hardware.

**Research and laboratory use only.** Unauthorized RF transmission is illegal in most jurisdictions.

## What changed in v2.1.0

- BladeRF integration aligned with official `libbladeRF` Python bindings (`Channel`, `sync_config`, `sync_rx`, `sync_tx`)
- Correct SC16_Q11 IQ conversion (scale factor 2048)
- Relative power measurement documented explicitly (not calibrated dBm)
- Chunked TX transmission to avoid oversized buffers
- `enable_aggressive_scan` implemented via `--aggressive-scan`
- Manual frequency targeting via `--freq`
- Modular package layout with pytest coverage

## Requirements

- Python 3.10+
- NumPy
- libbladeRF + Python bindings (`bladerf`)
- BladeRF hardware (for live runs)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install BladeRF drivers/bindings from Nuand documentation before running on hardware.

## Usage

### Auto mode (default) — autodetect + auto-attack loop

Runs continuously: scan for RF signals, auto-attack the strongest targets, repeat.
Stop with `Ctrl+C`.

```bash
python attack.py
# same as:
python attack.py --mode auto
```

Limit cycles and tune behavior:

```bash
python attack.py --mode auto --auto-cycles 10 --auto-interval 3 --auto-targets 3
```

Autodetect uses a **quick scan** of common Flipper frequencies first (315, 433.92, 868, 915 MHz),
then falls back to a full band sweep if nothing is found. Disable quick scan with `--no-quick-scan`.

Detect signals across default bands (single cycle):

```bash
python attack.py --mode detect
```

Target one frequency (Hz):

```bash
python attack.py --mode detect --freq 433920000
```

Full detect + lab transmission cycle:

```bash
python attack.py --mode full --threshold -40 --duration 3
```

Fine-grained scan:

```bash
python attack.py --mode detect --aggressive-scan --aggressive-scan-step 100000
```

## Tests

```bash
pytest
```

Tests use a mock RF backend and do not require BladeRF hardware.

## Project layout

```text
flipper-DA/
  attack.py                 # CLI entry point
  flipper_da/
    config.py               # bands + SystemConfig
    rf_utils.py             # IQ conversion + power helpers
    bladerf_manager.py      # hardware wrapper
    scanner.py              # spectrum detection
    attack_engine.py        # waveform generation/transmission
    system.py               # orchestration
    cli.py                  # argparse + main
  tests/
```

## Notes for researchers

- Detection is based on relative RF power above a threshold, not protocol fingerprinting.
- Threshold values are meaningful only with a fixed gain configuration in your lab setup.
- Keep TX experiments isolated and authorized.
