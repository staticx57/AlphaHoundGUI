# RadTrace Theory of Operation

## 📘 Overview

RadTrace is a web-based gamma spectroscopy analysis platform designed for educational and hobbyist applications. This document explains the internal workings of the system, from data acquisition to isotope identification.

---

## 🏗️ System Architecture

### High-Level Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend Client (Browser)"]
        UI[index.html]
        Logic[main.js]
        Charts[Chart.js]
        API_JS[api.js]
    end
    
    subgraph Backend["FastAPI Server (Python)"]
        Server[main.py]
        
        subgraph Routers["API Routers"]
            RouteDev[routers/device.py]
            RouteAna[routers/analysis.py]
            RouteIso[routers/isotopes.py]
        end
        
        subgraph Engines["Calculation Engines"]
            DecayEng[nuclides/decay_calculator.py]
            ActCalc[spectroscopy/activity_calculator.py]
            PeakFit[spectroscopy/peak_detection.py]
            MLID[ml/ml_analysis.py]
        end
        
        subgraph Parsers["Data Ingestion"]
            N42[formats/n42_parser.py]
            CSV[formats/csv_parser.py]
            UniLoad[formats/specutils_parser.py]
        end
    end
    
    subgraph Hardware["Hardware Layer"]
        Driver[devices/alphahound_serial.py]
        Device[AlphaHound Device]
    end
    
    UI --> Logic
    Logic --> API_JS
    API_JS --HTTP/WS--> Server
    
    Server --> RouteDev
    Server --> RouteAna
    Server --> RouteIso
    
    RouteDev --> Driver
    Driver <--> Device
    
    RouteAna --> Parsers
    RouteAna --> Engines
    RouteAna --> MLID
```

### API Routing Architecture

This diagram details how specific API endpoints route to backend modules.

```mermaid
graph LR
    Req[Client Request] --> Main[main.py / FastAPI]
    
    subgraph DeviceRoutes["/device (routers/device.py)"]
        D_Conn["/connect"] --> Serial[devices/alphahound_serial.py]
        D_Spec["/spectrum"] --> Serial
        D_Dose["/dose/stream"] --> WS[WebSocket]
    end
    
    subgraph AnalysisRoutes["/analyze (routers/analysis.py)"]
        A_Up["/upload"] --> ParserLogic{Parser Selector}
        A_ROI["/roi"] --> ActCalc[spectroscopy/activity_calculator.py]
        A_Decay["/decay-prediction"] --> DecayCalc[nuclides/decay_calculator.py]
        A_ML["/ml-identify"] --> ML[ml/ml_analysis.py]
    end
    
    subgraph ParserLogic["Universal Loader Strategy"]
        P_N42[.n42] --> N42P[n42_parser]
        P_CSV[.csv] --> CSVP[csv_parser]
        P_Gen[Other] --> SpecU[specutils_parser]
    end
    
    Main --> DeviceRoutes
    Main --> AnalysisRoutes
```

### Component Responsibilities

| Component | File | Purpose |
|-----------|------|---------|
| **Main Application** | `main.py` | FastAPI app entry point, WebSocket handler, router mounting |
| **Device Router** | `routers/device.py` | Serial port discovery, device connection, spectrum acquisition |
| **Analysis Router** | `routers/analysis.py` | File upload, peak fitting, ML identification, ROI analysis |
| **Isotopes Router** | `routers/isotopes.py` | Custom isotope management (CRUD operations) |
| **Peak Detection** | `spectroscopy/peak_detection.py` | Scipy-based peak finding algorithm |
| **Isotope Database** | `nuclides/isotope_database.py` | 100+ isotopes with gamma energies from IAEA/NNDC |
| **ML Analysis** | `ml/ml_analysis.py` | scikit-learn MLP training (synthetic spectra) and prediction |
| **Core Settings** | `core.py` | Default thresholds and confidence filtering logic |

---

## 📊 Data Flow Pipeline

### File Upload Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Parser
    participant PeakDetect
    participant IsotopeDB
    participant MLAnalysis
    
    User->>Frontend: Upload N42/CSV file
    Frontend->>Backend: POST /upload
    Backend->>Parser: parse_n42() or parse_csv()
    Parser-->>Backend: {energies, counts, metadata}
    Backend->>PeakDetect: detect_peaks(energies, counts)
    PeakDetect-->>Backend: [{energy, counts, index}, ...]
    Backend->>IsotopeDB: identify_isotopes(peaks)
    IsotopeDB-->>Backend: [{isotope, confidence, peaks_matched}, ...]
    Backend->>IsotopeDB: identify_decay_chains(peaks)
    IsotopeDB-->>Backend: [{chain_name, detected_members, confidence}, ...]
    Backend-->>Frontend: Full analysis response
    Frontend-->>User: Display spectrum + results
    
    Note over User,MLAnalysis: Optional ML Identification
    User->>Frontend: Click "AI Identify"
    Frontend->>Backend: POST /analyze/ml-identify
    Backend->>MLAnalysis: identify(counts)
    MLAnalysis-->>Backend: [{isotope, confidence}, ...]
    Backend-->>Frontend: ML predictions
```

### Device Acquisition Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Serial
    participant Device
    
    User->>Frontend: Select COM port
    Frontend->>Backend: POST /device/connect
    Backend->>Serial: connect(port)
    Serial->>Device: Open serial connection
    Device-->>Serial: ACK
    Serial-->>Backend: Connected
    Backend-->>Frontend: {status: "connected"}
    
    Note over User,Device: Real-time Dose Monitoring
    loop Every 1 second
        Serial->>Device: 'D' (dose request)
        Device-->>Serial: dose_rate (μR/hr)
        Serial-->>Backend: WebSocket update
        Backend-->>Frontend: {dose_rate: value}
    end
    
    Note over User,Device: Spectrum Acquisition
    User->>Frontend: Start acquisition (5 min)
    Frontend->>Backend: POST /device/spectrum
    Backend->>Serial: clear_spectrum()
    Serial->>Device: 'W' (clear)
    
    loop 5 minutes
        Backend->>Backend: Wait...
    end
    
    Backend->>Serial: request_spectrum()
    Serial->>Device: 'G' (get spectrum)
    Device-->>Serial: 1024 channel data
    Serial-->>Backend: [(count, energy), ...]
    Backend->>Backend: Analyze spectrum
    Backend-->>Frontend: Full results
```

### Universal File Parsing Strategy

The system employs a cascading strategy to handle diverse spectrum formats:

```mermaid
flowchart TD
    Start[Upload Request] --> Ext{File Extension?}
    
    Ext -- .n42 / .xml --> N42[Native N42 Parser]
    Ext -- .csv --> CSV[Native CSV Parser]
    Ext -- .chn/.spe --> Multi[CHN/SPE Parser]
    Ext -- Other --> Fallback{SandiaSpecUtils?}
    
    N42 --> Success{Success?}
    CSV --> Success
    Multi --> Success
    
    Success -- Yes --> Norm[Normalize Data]
    Success -- No --> Fallback
    
    Fallback -- Try Generic --> SpecU[SpecUtils Wrapper]
    SpecU --> Found{Valid Spectrum?}
    
    Found -- Yes --> Norm
    Found -- No --> Error[Return 400 Error]
    
    Norm --> Analyze[Analysis Pipeline]
```

---

## 🔍 Peak Detection Algorithm

The peak detection uses `scipy.signal.find_peaks` with adaptive thresholds based on spectrum characteristics.

### Algorithm Details

```python
# From spectroscopy/peak_detection.py
def detect_peaks(energies, counts, prominence_factor=0.05, distance=10):
    # 1. Calculate adaptive prominence threshold
    max_count = np.max(counts)
    prominence = max_count * prominence_factor  # 5% of max
    
    # 2. Find peaks with constraints
    peak_indices, properties = find_peaks(
        counts,
        prominence=prominence,   # Minimum "stand-out" height
        distance=distance,       # Minimum samples between peaks
        height=max_count * 0.01  # Minimum absolute height (1% of max)
    )
    
    # 3. Sort by counts and return top 20
    return sorted(peaks, key=lambda x: x['counts'], reverse=True)[:20]
```

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `prominence_factor` | 0.05 (5%) | Peak must stand out by this fraction of max count |
| `distance` | 10 channels | Minimum separation between peaks |
| `height` | 1% of max | Minimum absolute count threshold |

### Energy Tolerance in Matching

When matching detected peaks to known isotope energies:

- **Default tolerance**: 20 keV (Simple mode)
- **Upload tolerance**: 30 keV (for potentially uncalibrated data)
- **Advanced mode**: User-adjustable via Settings panel

---

## 🔬 Isotope Identification

### Database Structure

The isotope database contains gamma-ray energies from authoritative sources:

```python
# Simple Mode: 30 hobbyist-focused isotopes
ISOTOPE_DATABASE_SIMPLE = {
    "Co-60": [1173.2, 1332.5],
    "Cs-137": [661.7],
    "Am-241": [59.5],
    "K-40": [1460.8],
    # ... 30 total
}

# Advanced Mode: 100+ isotopes
ISOTOPE_DATABASE_ADVANCED = {
    **ISOTOPE_DATABASE_SIMPLE,
    # Fission products
    "Ru-103": [497.1, 295.0, 443.8, 179.3],
    "Zr-95": [724.2, 756.7],
    # Rare earths
    "Eu-152": [121.8, 244.7, 344.3, 778.9, 964.1, 1085.8, 1112.1, 1408.0],
    # ... 100+ total
}
```

### Confidence Scoring

```python
def identify_isotopes(peaks, energy_tolerance=20.0, mode='simple'):
    for isotope, expected_energies in database.items():
        matched = 0
        for exp_energy in expected_energies:
            for peak in peaks:
                if abs(peak['energy'] - exp_energy) <= tolerance:
                    matched += 1
                    break
        
        confidence = (matched / len(expected_energies)) * 100
        
        # Assign confidence level
        if confidence >= 70:
            level = "HIGH"
        elif confidence >= 40:
            level = "MEDIUM"
        else:
            level = "LOW"
```

### Mode Differences

| Feature | Simple Mode | Advanced Mode |
|---------|-------------|---------------|
| Isotope count | ~30 | 100+ |
| Min confidence | 40% | User-adjustable |
| Max results | 5 isotopes | Unlimited |
| Energy tolerance | 20 keV | User-adjustable |

---

## ⛓️ Decay Chain Detection

### Natural Decay Series

RadTrace detects three natural radioactive decay series:

#### U-238 Series (Uranium)
```
U-238 → Th-234 → Pa-234m → U-234 → Th-230 → Ra-226 → Rn-222 → Po-218 → Pb-214 → Bi-214 → Po-214 → Pb-210 → Bi-210 → Po-210 → Pb-206 (stable)
```

#### U-235 Series (Actinium)
```
U-235 → Th-231 → Pa-231 → Ac-227 → Th-227 → Ra-223 → Rn-219 → Po-215 → Pb-211 → Bi-211 → Tl-207 → Pb-207 (stable)
```

#### Th-232 Series (Thorium)
```
Th-232 → Ra-228 → Ac-228 → Th-228 → Ra-224 → Rn-220 → Po-216 → Pb-212 → Bi-212 → Tl-208/Po-212 → Pb-208 (stable)
```

### Natural Abundance Weighting

Chain confidence is weighted by natural isotopic abundance:

```python
abundance_weights = {
    'U-238': 1.0,      # 99.274% of natural uranium
    'U-235': 0.007,    # 0.720% of natural uranium
    'Th-232': 0.35     # ~3.5× more abundant than U in crust
}

# Example: If raw U-235 confidence is 70%
# Weighted confidence = 70% × 0.007 = 0.49%
# This prevents false U-235 identification in natural samples
```

### Chain Confidence Levels

| Level | Criteria |
|-------|----------|
| **HIGH** | ≥4 members detected OR ≥80% of key isotopes |
| **MEDIUM** | ≥3 members detected OR ≥60% of key isotopes |
| **LOW** | < 3 members OR weighted confidence < 15% |

---

## 🤖 ML Integration (scikit-learn)

See [ML_GUIDE.md](ML_GUIDE.md) for the current training pipeline (physics-based synthesiser, energy-grid resampling, series classes). The diagram and snippet below are the original PyRIID-era design and are kept for history.

### Training Pipeline

```mermaid
flowchart LR
    subgraph Training["Training Phase (First Run)"]
        DB[(Isotope Database)]
        SynGen[Synthetic Spectrum Generator]
        SS1[SampleSet]
        MLP[MLPClassifier]
    end
    
    subgraph Prediction["Prediction Phase"]
        Input[User Spectrum]
        SS2[SampleSet]
        Model[Trained Model]
        Results[Predictions]
    end
    
    DB --> SynGen
    SynGen --> |1500 samples| SS1
    SS1 --> MLP
    MLP --> |25 epochs| Model
    
    Input --> SS2
    SS2 --> Model
    Model --> Results
```

### Synthetic Training Data

Training spectra are generated with realistic characteristics:

```python
def generate_training_spectrum(isotope_energies):
    # Base: Poisson-distributed background
    spectrum = np.random.poisson(5, 1024)
    
    for energy in isotope_energies:
        channel = int(energy / 3.0)  # 3 keV/channel
        
        # Energy-dependent intensity (decreases with energy)
        intensity = max(50, 300 - energy / 10)
        
        # Gaussian peak with detector-matched FWHM
        fwhm = get_fwhm_channels(energy)  # CsI(Tl) resolution
        sigma = fwhm / 2.355
        
        for i in range(-fwhm, fwhm + 1):
            if 0 <= channel + i < 1024:
                spectrum[channel + i] += np.random.poisson(
                    intensity * np.exp(-i**2 / (2 * sigma**2))
                )
    
    return spectrum
```

### Energy-Dependent Resolution Model

CsI(Tl) detector resolution follows scintillator physics:

```
FWHM(E) = 0.10 × E × √(662/E)
```

| Energy (keV) | FWHM (keV) | FWHM (channels) | Resolution |
|--------------|------------|-----------------|------------|
| 186 | ~35 | ~12 | 18.8% |
| 662 | 66.2 | ~22 | 10.0% |
| 1461 | ~98 | ~33 | 6.7% |

### Mixture Recognition

The ML model recognizes 7 realistic source mixtures:

| Mixture | Component Isotopes |
|---------|-------------------|
| UraniumGlass | Bi-214, Pb-214, Ra-226, Th-234, U-238 |
| ThoriumMantle | Th-232, Ac-228, Tl-208, Pb-212 |
| MedicalWaste | Tc-99m, I-131, Mo-99 |
| IndustrialGauge | Cs-137, Co-60 |
| CalibrationSource | Am-241, Ba-133, Cs-137, Co-60 |
| NaturalBackground | K-40, Bi-214, Tl-208 |

---

## 📡 Device Communication Protocol

### AlphaHound Serial Commands

| Command | Byte | Description |
|---------|------|-------------|
| Request Dose | `D` | Returns current dose rate in μR/hr |
| Get Spectrum | `G` | Downloads 1024-channel spectrum |
| Clear Spectrum | `W` | Clears accumulated counts |

### Spectrum Data Format

```
Device sends:
"Comp"           <- Start marker
count,energy     <- 1024 lines, comma-separated
count,energy
...
(1024 lines total)
```

### Calibration Constants

> [!IMPORTANT]
> The AlphaHound device sends pre-calibrated energy values.
> **Verified calibration: ~7.39 keV/channel (15-7572 keV range)**
> 
> Do NOT assume 3 keV/channel - this causes false U-235 identification.

---

## ⚙️ Configuration System

### Default Settings (Simple Mode)

```python
DEFAULT_SETTINGS = {
    "mode": "simple",
    "isotope_min_confidence": 30.0,    # Minimum for display
    "chain_min_confidence": 30.0,      # Minimum chain confidence
    "energy_tolerance": 20.0,          # keV tolerance in matching
    "chain_min_isotopes_medium": 3,    # Members for MEDIUM
    "chain_min_isotopes_high": 4,      # Members for HIGH
    "max_isotopes": 5                  # Limit results
}
```

### Upload Settings (Lenient)

```python
UPLOAD_SETTINGS = {
    "chain_min_confidence": 1.0,       # Very permissive
    "energy_tolerance": 30.0,          # Wider tolerance
    "chain_min_isotopes_medium": 1     # Lower threshold
}
```

```

### Universal File Support (SandiaSpecUtils)

For files not natively supported (e.g., `.spc`, `.pcf`, `.dat`), the system wraps `SandiaSpecUtils`:

```python
# formats/specutils_parser.py
def parse_generic_file(file_path):
    # 1. Detect format using SpecUtils
    spec = SpecUtils.Spectrum(file_path)
    
    # 2. Extract standard attributes
    counts = spec.counts
    energies = spec.energies
    live_time = spec.live_time
    
    # 3. Normalize metadata structure
    return {
        "energies": energies,
        "counts": counts,
        "metadata": {...}
    }
```

---

## ☢️ Radiometric Calculations

### Activity Calculation

Source activity is calculated using the standard equation:

```
Activity (Bq) = Net Counts / (Efficiency × Branching Ratio × Time)
```

- **Net Counts**: Counts in peak area minus background/continuum.
- **Efficiency**: Interpolated intrinsic efficiency of the CsI(Tl) detector at that energy.
- **Branching Ratio**: Probability of gamma emission (from NNDC/IAEA/Curie data).
- **Time**: Live Acquisition Time in seconds.

**Unit Conversions**:
- 1 Bq = 1 disintegration/second
- 1 μCi = 37,000 Bq
- `activity_uci = activity_bq / 37000.0` (factor 2.703e-5)

### Decay Prediction Engine

The decay predictor uses a hybrid engine to model parent/daughter relationships over time:

1.  **Primary Engine (`curie`)**:
    - Uses authoritative nuclear data (half-lives, branching fractions) from the `curie` C++ library.
    - Example: `curie.Isotope("U-238").decay(days=365)` returns daughter activities.

2.  **Fallback Engine (Bateman Solver)**:
    - Custom Python implementation of the **Bateman Equations** for linear decay chains.
    - Used if `curie` library is unavailable or installation fails.
    - Solves:
      ```
      dN_1/dt = -λ_1 N_1
      dN_i/dt = λ_{i-1} N_{i-1} - λ_i N_i
      ```

### Dose Rate Estimation

Gamma dose rate is estimated using the "Gamma Constant" approximation for a point source:

```
Dose Rate (μSv/h) = (Activity_MBq × Γ × 1000) / Distance_mm²
```

- **Γ (Gamma Constant)**: Specific gamma ray constant for the nuclide (mSv·cm²/MBq·h).
- **Distance**: User-specified distance from source (default 100mm).

### Decay Prediction Workflow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant DecayEngine
    participant CurieLib
    participant BatemanSolver
    
    User->>Frontend: Open Decay Modal
    Frontend->>Frontend: Check previous ROI Activity
    Frontend->>User: Auto-populate "Activity" (if avail)
    
    User->>Frontend: Click "Calculate & Plot"
    Frontend->>API: POST /analyze/decay-prediction
    
    API->>DecayEngine: predict_decay_chain(isotope, activity, time)
    
    alt Curie Library Available
        DecayEngine->>CurieLib: Get Decay Data
        CurieLib-->>DecayEngine: Half-lives & Branching
    else Curie Unavailable
        DecayEngine->>BatemanSolver: Use Internal Database
    end
    
    DecayEngine->>DecayEngine: Solve Bateman Equations
    DecayEngine-->>API: {time_points, activities_per_isotope}
    
    API-->>Frontend: JSON Response
    Frontend->>Frontend: Render Chart.js (Log Scale)
    Frontend-->>User: Display Decay Curves
```

---

## 🔐 Security Features

| Feature | Implementation |
|---------|----------------|
| **Rate Limiting** | `slowapi` - 60 requests/minute/IP |
| **Input Validation** | Pydantic models with Field validators |
| **File Validation** | Size limits (10 MB), extension whitelist |
| **Port Sanitization** | Regex pattern matching for COM/tty ports |
| **CORS** | Configured for all origins (development mode) |

---

## 📁 Data Storage

### Persistent Data

| Data | Location | Format |
|------|----------|--------|
| Custom Isotopes | `backend/custom_isotopes.json` | JSON |
| Auto-saved Spectra | `backend/data/acquisitions/` | CSV |
| Frontend Settings | Browser localStorage | JSON |

### Auto-Save Format (CSV)

```csv
# RadTrace Auto-Save
# Date: 2024-12-14 00:30:15
# Source: AlphaHound Device
channel,counts,energy
0,5,15.00
1,7,22.39
...
```

---

## 📚 References

### Data Sources
- **IAEA NDS**: Nuclear Data Services database
- **NNDC ENSDF**: Evaluated Nuclear Structure Data File
- **CapGam**: Capture gamma-ray database
- **LBNL**: Lawrence Berkeley National Lab isotope data

### Libraries
- **scikit-learn**: MLP classifier for AI identification
- **scipy.signal**: Peak detection algorithms
- **FastAPI**: Modern Python web framework
- **Chart.js**: Frontend visualization

---

*Last Updated: 2024-12-14*
*RadTrace Theory of Operation v1.0*
