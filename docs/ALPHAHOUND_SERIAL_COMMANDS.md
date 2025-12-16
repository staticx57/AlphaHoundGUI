# AlphaHound Serial Command Reference

Discovered through serial probing on 2025-12-15.

## Connection Settings
- Baud Rate: 9600
- Standard serial settings (8N1)

## Important: Command Parsing Behavior

The AlphaHound uses **single-character command parsing**. Each character in the stream is processed independently. For example:
- Sending `VER` is interpreted as `V`, `E`, `R` separately
- The `E` will trigger a display mode change!
- Two-letter commands like `DA` work because `A` modifies the `D` command

**Always send one command at a time with appropriate delays.**

---

## Core Spectrum/Dose Commands

| Command | Response | Description |
|---------|----------|-------------|
| `G` | 1028 lines | Get Gamma Spectrum (includes metadata) |
| `GA` | 1028 lines | Get Gamma Spectrum (same as G) |
| `GB` | 1028 lines | Get Gamma Spectrum (same as G) |
| `D` | float | Get Dose Rate (µRem/h) |
| `DA` | float | Get Dose Rate A |
| `DB` | float | Get Dose Rate B |
| `W` | (silent) | Wipe/Clear Spectrum on device |

**Note:** Any character after `G` is ignored (GA, GB, GX all return the same spectrum).

### Spectrum Response Format
```
Full 1024-int Array received:
Temp:24.12
CompFactor:0.95910
Comp
0,15.00
1,16.68
34,20.05
...
(1024 lines of count,energy pairs)
```

- `Temp` - Device temperature in °C
- `CompFactor` - Temperature compensation factor (~0.96)
- Data format: `count,energy` for each of 1024 channels

---

## Display Control Commands

| Command | Response | Description |
|---------|----------|-------------|
| `E` | (silent) | **Cycle display mode FORWARD** |
| `Q` | (silent) | **Cycle display mode BACKWARD** |

**Note:** Any character following `E` or `Q` is ignored.

Display modes cycle through:
- Spectrum view
- Alpha/Beta/Gamma starfield view
- (possibly others)

---

## Configuration/Status Commands

| Command | Response | Description |
|---------|----------|-------------|
| `K` | Multi-line | Get device configuration |
| `KA` | Multi-line | Get configuration A |
| `KB` | Multi-line | Get configuration B |
| `L` | `actThresh: ###` | Get activity threshold |
| `P` | `UB=C` | USB/connection mode info |

### K Command Response Format
```
actThresh: 228
5,5.00
NoiseFloor:31
```

- `actThresh` - Activity threshold setting (alarm level?)
- `5,5.00` - Unknown (possibly ROI or window settings)
- `NoiseFloor` - Noise floor threshold

---

## Calibration Commands

| Command | Response | Description |
|---------|----------|-------------|
| `C#,#,#,#` | (sets values) | Set calibration coefficients (4 polynomial terms) |

Format: `C<coef0>,<coef1>,<coef2>,<coef3>`

Example: `C0,7.4,0,0` for 7.4 keV/channel linear calibration

---

## Commands With No Response (Silent or Unknown)

These commands were tested but returned no serial response:
- `A`, `B`, `F`, `H`, `I`, `J`, `M`, `N`, `O`, `Q`, `R`, `S`, `T`, `U`, `V`, `X`, `Y`, `Z`

Some may perform actions without feedback (like `W` for wipe).

---

## DA/DB Dose Rate Analysis

Statistical analysis of 20 samples revealed:

| Ratio | Average |
|-------|---------|
| DA/DB | 1.006 |
| D/DB | 1.006 |
| D/DA | 1.000 |
| CompFactor | 0.958 |

**Conclusion:** D, DA, and DB are **essentially identical** (within noise). The CompFactor is NOT used to differentiate between them. All three return the same temperature-compensated dose rate.

The app uses `DB` which matches the device display, but any of them would work.

---

## Probe Date
2025-12-15 - AlphaHound device on COM8
