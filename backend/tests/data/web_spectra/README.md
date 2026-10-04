# Real spectra published by others

Test fixtures for identification on sources this project has no access to. Each folder keeps the licence of the repository it came from;
the files are unchanged copies. Labels are what each sample physically is, from the authors' own descriptions, never from this app's output.
Used by `tests/test_web_spectra.py`.

## ckuethe/ — [ckuethe/radiacode-tools](https://github.com/ckuethe/radiacode-tools) (MIT), RadiaCode-103 XML exports

| File | Source |
|---|---|
| `Ba133_a.xml`, `Eu152_b.xml`, `Ba133_a+Eu152_b.xml` | Ba-133 and Eu-152 calibration sources, alone and together (the repository's dead-time tests) |
| `Co60_a.xml`, `Cs137_b.xml`, `Co60_a+Cs137_b.xml` | Co-60 and Cs-137 calibration sources, alone and together |
| `data_am241.xml` | Am-241 source |
| `data_th232_plus_background.xml` | Th-232 source with background |
| `trinitite.xml` | Trinitite (fallout glass: Cs-137, Eu-152, Am-241, Ba-133) |
| `bg.xml` | Background |

## dmamontov/ — [dmamontov/periodic-table](https://github.com/dmamontov/periodic-table) (MIT), the author's own RadiaCode measurements

| File | Sample |
|---|---|
| `am-95-his07.xml`, `np-93-his07.xml` | HIS-07 Am-241 source (only the 59.5 keV line shows) |
| `pu-94-rid6m.xml` | RID-6M Pu-239 source (only its Am-241 line shows) |
| `ra-88-spd.xml`, `rn-86-spd.xml` | Radium luminous compound (Ra-226 and daughters) |
| `ra-88-mazda0a2.xml` | Radium sample (this unit reads ~3-4 % low) |
| `th-90-pendant.xml` | Thorium "scalar energy" pendant |
| `th-90-wt20.xml` | WT-20 thoriated tungsten electrodes |
| `u-92-glass.xml` | Uranium glass (Th-234 92.6 keV, U-235 185.7 keV; no radium) |
| `ni-28-r26.xml` | R-26 spark-gap tube, Ni-63: bremsstrahlung only, no gamma lines |
| `po-84-staticmaster.xml` | Staticmaster Po-210 (no usable gamma; the author marked radium-series background lines) |
| `bg-lead-shield.xml` | Background inside a lead shield (Pb X-rays near 75 keV) |

## lbl-anp/ — [lbl-anp/becquerel](https://github.com/lbl-anp/becquerel) test samples (LBNL BSD-style licence, `LICENSE.txt`)

HPGe and NaI spectra in SPE, SPC and CNF formats with no source labels (environmental backgrounds, pottery, field sites). Used for the
formats and for detector handling (an HPGe file that names no detector), not for identification scores; `digibase_5min_30_1.spe` has
all-zero calibration coefficients (uncalibrated).
