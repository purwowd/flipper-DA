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

### Full jam 433.92 MHz (B210-style continuous TX)

Inspired by SoapySDR/B210 Wi-Fi jam scripts: reused TX buffer + `noise`/`chirp`/`both` payload.

```bash
# ULTRA jam 433.92 MHz — max aggression (default for --mode jam)
python attack.py --mode jam -ch 433

# Same with explicit TX gain
python attack.py --mode jam -ch 433 --tx-gain 60 --brute-dither 200000

# Timed jam (optional): stop after 60 seconds
python attack.py --mode jam -ch 433 --duration 60

# Same, explicit
python attack.py --mode jam --freq 433920000 --payload-mode both --tx-gain 60
```

| Flag | B210 reference | Flipper-DA |
|------|----------------|------------|
| `-ch 433` | `-ch 6 11` (Wi-Fi) | Sub-GHz: `315 433 868 915` |
| `--payload-mode both` | `--mode both` | noise / chirp / both / brute |
| `--bufsize 32768` | `--bufsize 32768` | Reused TX buffer |
| continuous `writeStream` | `while True: writeStream` | `while True: transmit_samples` |

### Auto mode (default) — autodetect + brute lock-on jam

Runs continuously with **brute mode** enabled by default:
1. Detect target frequency
2. **Lock** and transmit continuously for `--brute-hold` seconds (default 15s)
3. Verify — if target still active, **re-attack immediately** (no idle gap)
4. Release lock only when signal drops below threshold

```bash
python attack.py --mode auto
```

Max aggression (lab only):

```bash
python attack.py --freq 433920000 --tx-gain 60 --brute-chunk 0.05 --brute-dither 100000
```

**Continuous brute (default):** once locked, TX runs **without RX gaps** until you press `Ctrl+C`.
Verify scan is **disabled** by default (no more muncul-hilang from RX peek).

Disable brute (short burst attacks instead):

```bash
python attack.py --no-brute
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
