# RadView Technical Clarification Questions

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
