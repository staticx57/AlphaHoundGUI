# AI Identification (ML) Guide

`backend/ml_analysis.py` — a small neural network (scikit-learn `MLPClassifier`) that classifies a gamma
spectrum. It is a second opinion next to the line-matching / decay-chain / spectrum-fit analysis, not a
replacement. PyRIID was evaluated and dropped (its numpy 1.26 / scipy 1.13 / TensorFlow 2.16 pins cannot
coexist with this app, and it only supplied an MLP; the spectrum synthesis was already this project's code).

## How it works

1. **Training (first use, ~7 s, cached in memory).** Spectra are synthesised from the isotope database
   (`isotope_database.py`, IAEA/NNDC lines with intensities). Each training spectrum has:
   one gain (±3 %) and offset (±8 keV) error for the whole spectrum, a resolution scale, a log-uniform
   total (5 k – 2 M counts), Gaussian photopeaks with energy-dependent FWHM, efficiency falling with
   energy, a Compton shelf, environmental background (K-40, Bi-214, Tl-208, ...) and Poisson noise.
2. **Classes** are named for what a spectrum shows, not for objects. A gamma spectrum cannot tell a
   thoriated lens from a mantle, so both are `Th-232 series`.

   | Class | Meaning |
   |---|---|
   | `Th-232 series` | Th-232 chain (Ac-228, Pb-212, Bi-212, Tl-208, ...), incl. aged / fresh disequilibrium |
   | `U-238 series` | U-238 chain with Th-234 / Pa-234m and radon daughters (uranium glass, ore) |
   | `Ra-226 series` | Radium with radon daughters (Pb-214, Bi-214), without the U-238 head |
   | `Cs-137 + Co-60`, `Am-241 + Ba-133 + Cs-137 + Co-60`, `Tc-99m + I-131 + Mo-99` | multi-source mixtures |
   | `Natural background (K-40, Ra/Th daughters)`, `Background` | environmental background |
   | single isotopes (`Cs-137`, `Am-241`, `K-40`, ...) | sources that occur alone |

   Natural-series daughters (Pb-214, Ac-228, ...) are *not* standalone classes: they never occur alone, and
   training them alone made a thorium lens read as "Pb-214".
3. **Identification.** The input spectrum is resampled onto the model's energy grid using its own channel
   energies (`MLIdentifier.resample`), so a Radiacode (~2.4 keV/channel) and an AlphaHound (~3 keV/channel)
   both land on the right channels. Features are `sqrt(counts)`, L2-normalised. Without energies the input
   is assumed to be on the model grid (much less reliable). `POST /analyze/ml-identify` accepts `energies`.

## Checking it

```
python backend/tests/ml_benchmark.py     # real labelled spectra (same set as real_benchmark.py)
python -m pytest backend/tests/test_ml_analysis.py
```

Current result: 8 of 9 real spectra consistent; the miss is a weak community uranium-glaze CSV. The
benchmark was used while tuning, so treat it as optimistic. Grow the labelled set before trusting small
differences.

## Extending

- **New class**: add a mixture to `mixtures` in `MLIdentifier.lazy_train` (use `'label'` to fold variants
  into one class) or add the isotope to `HOBBY_ISOTOPES`. Re-run the benchmark.
- **Detector**: add a profile to `DETECTOR_PROFILES` (channels, keV/channel, FWHM at 662 keV).
- **Real spectra in training** are off by default (`ML_USE_REAL_DATA=1` enables them): the loader labels by
  filename and ignores calibration.
- **ONNX export** (`POST /analyze/export-model`) needs the optional `skl2onnx` package.
