# RadView Technical Clarification Questions

## Status (2026-10-04)

Most of these have since been answered, by measurement or by the device's own documentation. What is left is short.

| Question | Status |
|----------|--------|
| Q1 Is ~7.4 keV/channel hardcoded? | **Answered.** 7.4 is the average slope of the device's own axis, a cubic polynomial of four coefficients (about 1.7 keV/channel at the bottom, 18 at the top; see `CALIBRATION_GUIDE.md`). The 3.0 keV/channel axis was ours: a forced linear axis in older saved N42 files. |
| Q2 A command to recalibrate? | The command reference lists `C<c0>,<c1>,<c2>,<c3>` (four polynomial terms). The application never sends it, because it would overwrite the factory calibration, so whether the device accepts it and keeps it is **unverified**. Still worth asking. |
| Q3 Factory calibration source | **Open.** The factory axis is good at low energy (the 239 keV Pb-212 line is within 2 %) and reads progressively low above it: about 2 % at 583 keV and 8 % at 2615 keV on three thoriated-lens captures. Is that the response of the crystal and photodetector (non-proportionality, saturation) or the calibration, and was it made with a particular source? |
| Q4 Command reference | `ALPHAHOUND_SERIAL_COMMANDS.md` (observed, not official; many commands answer nothing). An official reference would still help. |
| Q5 Firmware, temperature, battery, bias | Temperature **answered**: the device sends `Temp:` and `CompFactor:` with every spectrum (about 29-30 C, in steps of 0.125 C) and the application now saves both with each spectrum. Firmware version, battery level and bias voltage: not found. |
| Q6-Q7 Dead time | **Open.** |
| Q8-Q9 Crystal and resolution | **Answered** by the published specification (CsI(Tl), 1.1 cm3, 10 % FWHM or better at 662 keV) and by measurement: 7.1 % on the Cs-137 verification file. |

The original questions follow.

## 1. Energy Calibration & Firmware
**Observation:** The device outputs spectrum data as `count, energy` pairs via serial. The observed default scaling appears to be ~7.4 keV/channel (based on legacy code and initial data), but our testing with Thorium/Uranium sources indicates that **3.0 keV/channel** provides correct peak alignment (e.g., Pb-214 @ 352 keV, Bi-214 @ 609 keV).
- **Q1:** Is the ~7.4 keV calibration factor hardcoded in the firmware?
- **Q2:** Does the firmware support a serial command to recalibrate or update this factor onboard?
- **Q3:** Is the factory calibration performed with a specific source (e.g., Cs-137) that might explain the discrepancy?

## 2. Serial Protocol & Controls
**Observation:** We are currently using the following commands: `G` (Get Spectrum), `W` (Clear Spectrum), `D` (Get Dose).
- **Q4:** Is there a comprehensive command reference available?
- **Q5:** Specifically, are there commands for:
    - Querying Firmware Version?
    - Reading Internal Temperature (for SiPM gain drift compensation)?
    - Checking Battery Level?
    - Adjusting Bias Voltage / Gain?

## 3. Dead Time & Timing
**Observation:** The serial data does not explicit "Live Time" vs "Real Time" headers. We currently assume `Live Time == Real Time`.
- **Q6:** Does the device perform internal dead-time correction?
- **Q7:** If not, is there a predictable dead-time model (e.g., non-paralyzable model with $\tau$ ~10$\mu$s) we should apply in software? 

## 4. Hardware Specifications
**Assumptions:** We are modeling the detector as a CsI(Tl) scintillator for our efficiency and resolution calculations.
- **Q8:** Can you confirm the crystal material and dimensions (e.g., CsI(Tl) 10mm³)? (Crucial for our Absolute Efficiency calculations).
- **Q9:** What is the nominal Energy Resolution (FWHM @ 662 keV)? We are seeing ~7-10% and have tuned our ML models to this, but a factory spec would be better.
