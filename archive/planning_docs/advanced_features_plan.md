# Advanced Features Implementation Plan

## Goal
Integrate PyRIID (ML-based radioisotope identification) and leverage becquerel (spectral analysis) to enhance the N42 Viewer with advanced analytical capabilities.

## Library Overview

### PyRIID (Sandia National Labs)
**Purpose**: Machine learning-based radioisotope identification and estimation from gamma spectra.

**Key Features**:
- Pre-trained ML models for isotope identification
- Synthetic spectrum generation for training
- Anomaly detection in gamma spectra sequences
- Confidence scoring and uncertainty quantification
- GADRAS integration utilities

**Requirements**: Python 3.10-3.12, TensorFlow/Keras

---

### Becquerel (LBL-ANP)
**Purpose**: Nuclear spectroscopic measurement analysis toolkit.

**Key Features**:
- Spectral feature fitting (Gaussian, Voigt profiles)
- Detector energy calibration
- Spectrum rebinning and manipulation
- Nuclear data access (NNDC, XCOM)
- N42, CHN, CSV file format support
- Activity calculations and decay corrections

**Requirements**: numpy, scipy, matplotlib, pandas

---

## Proposed Changes

### Phase 1: Becquerel Enhanced Analysis

#### [NEW] `backend/spectral_analysis.py`
- Peak fitting with Gaussian/Voigt profiles
- FWHM (Full Width at Half Maximum) calculation
- Energy calibration refinement
- Net area calculation under peaks
- Background subtraction algorithms

#### [MODIFY] `backend/main.py`
- Add `/analyze/fit-peaks` endpoint for spectral fitting
- Add `/analyze/calibrate` endpoint for energy calibration
- Add `/analyze/activity` endpoint for activity estimation

#### [MODIFY] `frontend/app.js`
- Add "Advanced Analysis" panel
- Display fitted peak parameters (centroid, FWHM, net area)
- Show calibration curve visualization

---

### Phase 2: PyRIID ML Integration

#### [NEW] `backend/ml_identification.py`
- Load pre-trained PyRIID models
- Preprocess spectra for ML input (normalization, rebinning)
- Run inference and return isotope predictions with confidence
- Ensemble predictions from multiple models

#### [NEW] `backend/models/` directory
- Store pre-trained PyRIID model files (.h5, .pkl)
- Include model metadata and version info

#### [MODIFY] `backend/main.py`
- Add `/identify/ml` endpoint for ML-based identification
- Add `/identify/compare` endpoint to compare current vs ML results

#### [MODIFY] `frontend/app.js`
- Add "ML Identification" tab to isotope results
- Show confidence scores with visual bars
- Display comparison between database matching and ML results

---

### Phase 3: Advanced Reporting

#### [NEW] `backend/report_generator.py`
- Generate PDF reports using ReportLab or WeasyPrint
- Include spectrum plot, peak table, isotope matches
- Add metadata and analysis summary

#### [MODIFY] `main.py`
- Add `/export/pdf` endpoint

#### [MODIFY] `frontend/index.html`
- Add "Export PDF Report" button

---

## Dependencies to Add

```text
# requirements.txt additions
becquerel>=0.4.0
riid>=2.0.0
tensorflow>=2.10.0
reportlab>=4.0.0
```

## User Review Required

> [!IMPORTANT]
> **ML Model Selection**: PyRIID offers multiple pre-trained models (Neural Networks, Random Forests). Need to decide which model(s) to ship with the application.

> [!WARNING]
> **TensorFlow Dependency**: PyRIID requires TensorFlow which is ~500MB. This significantly increases installation size. Consider making it optional?

> [!NOTE]
> **Model Training**: For best results, models should be trained on spectra similar to your detector. Pre-trained models may have reduced accuracy on AlphaHound data.

---

## Verification Plan

### Automated Tests
- Unit tests for spectral fitting functions
- Integration tests for ML inference pipeline
- Accuracy benchmarks against known spectra

### Manual Verification
- Compare ML identification with database matching on test N42 files
- Verify peak fitting on spectra with known peaks
- Test PDF report generation
