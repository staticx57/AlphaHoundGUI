# RadTrace Modularity Guide

## 📘 Overview

This guide explains how to extend and modify RadTrace for your specific needs. The application is designed with modularity in mind, making it easy to add new device drivers, isotopes, analysis methods, and UI features.

**Who is this for?**
- **Beginners**: New to Python/JavaScript or FastAPI - start with the "Getting Started" section
- **Intermediate**: Familiar with web development - jump to specific extension tutorials
- **Advanced**: Experienced developers - use the reference sections and API patterns

---

## 🚀 Getting Started for Developers

### Prerequisites

Before you begin, make sure you have:

1. **Python 3.10+** installed ([Download Python](https://www.python.org/downloads/))
2. **A code editor** (VS Code recommended)
3. **Basic familiarity** with:
   - Python (functions, classes, dictionaries)
   - JavaScript (async/await, DOM manipulation)
   - Command line/terminal usage

### Understanding the Technology Stack

| Technology | What it does | Where it's used |
|------------|--------------|-----------------|
| **FastAPI** | Python web framework | Backend API server |
| **Pydantic** | Data validation | Request/response models |
| **Chart.js** | JavaScript charting | Spectrum visualization |
| **WebSockets** | Real-time communication | Live dose rate streaming |
| **PyRIID** | Machine learning | Isotope identification |

### Key Concepts

#### 1. How Data Flows Through the App

```
User Action → Frontend (JS) → API Call → Backend (Python) → Response → UI Update
```

**Example: Uploading a file**
1. User drags file onto page
2. `main.js` catches the drop event
3. `api.js` sends file to `/upload` endpoint
4. `routers/analysis.py` receives and processes it
5. Response sent back with peaks, isotopes, etc.
6. `ui.js` renders the results

#### 2. Router Pattern (Backend)

Routers group related API endpoints. Think of them as "folders" for your API:

```python
# routers/device.py handles all /device/* endpoints:
#   GET  /device/ports     → List serial ports
#   POST /device/connect   → Connect to device
#   POST /device/spectrum  → Acquire spectrum
```

#### 3. State Management (Frontend)

The app stores current state in `window.appState`:

```javascript
window.appState = {
    currentSpectrum: { counts: [...], energies: [...] },
    currentPeaks: [...],
    settings: { mode: 'simple', ... }
};
```

### Your First Modification: Add a Custom Isotope

**Goal**: Add a new isotope to the database so it can be detected.

**Time**: ~5 minutes

**Steps**:

1. Open `backend/isotope_database.py`
2. Find the `ISOTOPE_DATABASE_SIMPLE` dictionary (around line 3)
3. Add your isotope:

```python
ISOTOPE_DATABASE_SIMPLE = {
    # ... existing isotopes ...
    
    # Add your isotope here - just the name and gamma energies in keV
    "My-Test-Isotope": [511.0, 1274.5],  # Example: Na-22 energies
}
```

4. Save the file
5. Restart the server: close and re-run `run.bat`
6. Upload a spectrum - your isotope will now be checked!

### Your Second Modification: Change the UI Theme Colors

**Goal**: Customize the dark theme colors.

**Time**: ~5 minutes

**Steps**:

1. Open `backend/static/style.css`
2. Find the `:root` section (around line 1-20)
3. Modify CSS variables:

```css
:root {
    --bg-primary: #1a1a2e;      /* Main background */
    --bg-secondary: #16213e;    /* Panel backgrounds */
    --accent-color: #e94560;    /* Buttons, highlights */
    --text-primary: #ffffff;    /* Main text */
}
```

4. Save and refresh the browser

### Understanding the File Structure

```
backend/
├── main.py              ← START HERE: App entry point
├── routers/
│   └── analysis.py      ← API endpoints for file analysis
├── isotope_database.py  ← Isotope data (easy to edit!)
├── peak_detection.py    ← Peak finding algorithm
└── static/
    └── js/
        └── main.js      ← Frontend application logic
```

**Tip**: Start by reading `main.py` - it's only ~70 lines and shows how everything connects.

### Common Beginner Tasks

| Task | Difficulty | File to Edit |
|------|------------|--------------|
| Add a new isotope | ⭐ Easy | `isotope_database.py` |
| Change UI colors | ⭐ Easy | `style.css` |
| Modify peak detection sensitivity | ⭐⭐ Medium | `peak_detection.py` |
| Add a new API endpoint | ⭐⭐ Medium | `routers/analysis.py` |
| Add a new device driver | ⭐⭐⭐ Advanced | New file + router |
| Modify ML training | ⭐⭐⭐ Advanced | `ml_analysis.py` |

### Running in Development Mode

For active development with auto-reload:

```bash
cd backend
python -m uvicorn main:app --reload --port 3200
```

The `--reload` flag automatically restarts the server when you save changes!

### Debugging Tips

1. **Check the terminal** - Python errors appear in the console
2. **Check browser DevTools** (F12) - JavaScript errors and network requests
3. **Add print statements** - Simple but effective:
   ```python
   print(f"DEBUG: peaks = {peaks}")
   ```
4. **Use the Network tab** - See API requests/responses in browser DevTools

---

## 📁 Project Structure

```
AlphaHoundGUI/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── core.py                 # Shared settings and utilities
│   ├── routers/                # API endpoint modules
│   │   ├── analysis.py         # File upload, peak detection, ML
│   │   ├── device.py           # AlphaHound device control
│   │   └── isotopes.py         # Custom isotope CRUD
│   ├── alphahound_serial.py    # Device communication driver
│   ├── isotope_database.py     # Isotope energy lookup
│   ├── peak_detection.py       # Peak finding algorithm
│   ├── ml_analysis.py          # PyRIID ML integration
│   ├── n42_parser.py           # N42/XML file parser
│   ├── csv_parser.py           # CSV file parser
│   ├── detector_efficiency.py  # Detector calibration data
│   ├── spectral_analysis.py    # Gaussian peak fitting
│   ├── roi_analysis.py         # Region-of-interest analysis
│   ├── isotope_roi_database.py # ROI isotope definitions
│   └── report_generator.py     # PDF export
│   └── static/                 # Frontend files
│       ├── index.html          # Main HTML
│       ├── style.css           # Styling
│       └── js/
│           ├── main.js         # Application logic
│           ├── api.js          # Backend API calls
│           ├── charts.js       # Chart.js configuration
│           ├── ui.js           # UI rendering helpers
│           ├── calibration.js  # Calibration UI
│           └── isotopes_ui.js  # Isotope management UI
├── THEORY_OF_OPERATION.md      # System architecture docs
├── PYRIID_GUIDE.md             # ML integration guide
├── CALIBRATION_GUIDE.md        # Calibration instructions
└── requirements.txt            # Python dependencies
```

---

## 🔌 Adding a New Device Driver

### Step 1: Create the Driver Module

Create a new file `backend/mydevice_serial.py`:

```python
"""
MyDevice Serial Communication Module

Provides communication with MyDevice gamma spectrometer.
"""

import serial
import serial.tools.list_ports
import threading
from typing import Optional, List, Dict, Callable

class MyDevice:
    """Manager for MyDevice serial communication"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.current_dose: float = 0.0
        self.spectrum: List[tuple] = []
        
    @staticmethod
    def list_ports() -> List[Dict[str, str]]:
        """Get list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [{"device": p.device, "description": p.description} for p in ports]
    
    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """Connect to device"""
        try:
            self.serial_conn = serial.Serial(port, baudrate, timeout=1.0)
            # Start background read thread if needed
            return True
        except Exception as e:
            print(f"[MyDevice] Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
    
    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self.serial_conn is not None and self.serial_conn.is_open
    
    def request_spectrum(self):
        """Request spectrum from device - implement device-specific protocol"""
        # Your device's spectrum request command
        self._write(b'YOUR_SPECTRUM_COMMAND')
    
    def get_dose_rate(self) -> float:
        """Get current dose rate"""
        return self.current_dose
    
    def get_spectrum(self) -> List[tuple]:
        """Get spectrum as [(count, energy), ...]"""
        return self.spectrum.copy()
    
    def _write(self, data: bytes):
        """Thread-safe write to serial port"""
        if self.serial_conn:
            self.serial_conn.write(data)

# Global instance
my_device = MyDevice()
```

### Step 2: Create the Router

Create `backend/routers/mydevice.py`:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mydevice_serial import my_device
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, apply_abundance_weighting, apply_confidence_filtering

router = APIRouter(prefix="/mydevice", tags=["mydevice"])

class ConnectRequest(BaseModel):
    port: str = Field(..., min_length=3, max_length=50)

@router.get("/ports")
async def list_ports():
    return {"ports": my_device.list_ports()}

@router.post("/connect")
async def connect(request: ConnectRequest):
    if my_device.is_connected():
        return {"status": "already_connected"}
    
    success = my_device.connect(request.port)
    if success:
        return {"status": "connected", "port": request.port}
    raise HTTPException(status_code=500, detail="Failed to connect")

@router.post("/disconnect")
async def disconnect():
    my_device.disconnect()
    return {"status": "disconnected"}

@router.get("/status")
async def status():
    return {
        "connected": my_device.is_connected(),
        "dose_rate": my_device.get_dose_rate() if my_device.is_connected() else None
    }

@router.post("/spectrum")
async def acquire_spectrum():
    if not my_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    my_device.request_spectrum()
    # Wait for spectrum acquisition...
    
    spectrum = my_device.get_spectrum()
    counts = [c for c, e in spectrum]
    energies = [e for c, e in spectrum]
    
    # Use existing analysis pipeline
    peaks = detect_peaks(energies, counts)
    isotopes = identify_isotopes(peaks)
    chains = identify_decay_chains(peaks, isotopes)
    
    return {
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
        "decay_chains": chains
    }
```

### Step 3: Register the Router

In `backend/main.py`:

```python
from routers import device, analysis, isotopes, mydevice  # Add mydevice

# ...

# Routers
app.include_router(device.router)
app.include_router(analysis.router)
app.include_router(isotopes.router)
app.include_router(mydevice.router)  # Add new router
```

---

## ⚛️ Extending the Isotope Database

### Adding Single Isotopes

Edit `backend/isotope_database.py`:

```python
# In ISOTOPE_DATABASE_SIMPLE (for hobby use):
ISOTOPE_DATABASE_SIMPLE = {
    # Existing isotopes...
    
    # Add your isotope with gamma energies (keV)
    "My-Isotope": [123.4, 456.7, 789.0],
}

# In ISOTOPE_DATABASE_ADVANCED (for professional use):
ISOTOPE_DATABASE_ADVANCED = {
    **ISOTOPE_DATABASE_SIMPLE,
    
    # Add more specialized isotopes
    "Rare-Isotope-1": [111.1, 222.2],
    "Rare-Isotope-2": [333.3, 444.4, 555.5],
}
```

### Adding Custom Isotopes via API

Users can add isotopes at runtime:

```http
POST /isotopes/custom
Content-Type: application/json

{
    "name": "My-Custom-Isotope",
    "energies": [123.4, 456.7]
}
```

Custom isotopes persist in `backend/custom_isotopes.json`.

### Adding Decay Chains

Edit the `DECAY_CHAINS` dictionary in `isotope_database.py`:

```python
DECAY_CHAINS = {
    "My-Custom-Chain": {
        "description": "Custom decay chain description",
        "key_isotopes": ["Parent-A", "Daughter-B", "Daughter-C", "Stable-D"],
        "key_energies": {
            "Parent-A": [100.0],
            "Daughter-B": [200.0, 250.0],
            "Daughter-C": [400.0],
        },
        "sources": [
            {"name": "Reference Source", "url": "https://example.com"}
        ]
    }
}
```

---

## 🧪 Adding New Analysis Methods

### Creating a New Analysis Endpoint

Add to `backend/routers/analysis.py`:

```python
class MyAnalysisRequest(BaseModel):
    """Request model for custom analysis."""
    counts: List[float] = Field(..., min_length=10)
    custom_param: float = Field(default=1.0, ge=0, le=100)

@router.post("/analyze/my-analysis")
async def my_analysis(request: MyAnalysisRequest):
    """
    Perform custom analysis on spectrum data.
    """
    counts = request.counts
    param = request.custom_param
    
    # Your analysis logic here
    results = perform_my_analysis(counts, param)
    
    return {
        "results": results,
        "method": "My Custom Analysis",
        "status": "success"
    }
```

### Creating Analysis Modules

For complex analysis, create a separate module:

```python
# backend/my_analysis.py
"""
Custom analysis module for specialized spectral analysis.
"""

import numpy as np
from typing import List, Dict

def perform_my_analysis(counts: List[float], param: float) -> Dict:
    """
    Perform custom spectral analysis.
    
    Args:
        counts: Spectrum count data
        param: Analysis parameter
        
    Returns:
        Analysis results dictionary
    """
    counts_array = np.array(counts)
    
    # Example: Calculate some metrics
    total_counts = np.sum(counts_array)
    peak_channel = np.argmax(counts_array)
    
    return {
        "total_counts": int(total_counts),
        "peak_channel": int(peak_channel),
        "analysis_param": param
    }
```

---

## 🖥️ Frontend Extension

### Adding UI Components

#### 1. Add HTML Structure

In `backend/static/index.html`:

```html
<!-- Add a new panel -->
<div id="my-analysis-panel" class="panel hidden">
    <h3>My Custom Analysis</h3>
    <div class="controls">
        <label>
            Parameter:
            <input type="number" id="my-param" value="1.0" min="0" max="100">
        </label>
        <button id="btn-my-analysis" class="btn-primary">
            Run Analysis
        </button>
    </div>
    <div id="my-analysis-results"></div>
</div>
```

#### 2. Add JavaScript Handler

In `backend/static/js/main.js`:

```javascript
// My Analysis button handler
document.getElementById('btn-my-analysis')?.addEventListener('click', async () => {
    const param = parseFloat(document.getElementById('my-param').value);
    const counts = window.appState?.currentSpectrum?.counts || [];
    
    if (counts.length === 0) {
        showToast('No spectrum loaded', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/analyze/my-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ counts, custom_param: param })
        });
        
        const data = await response.json();
        renderMyAnalysisResults(data.results);
    } catch (error) {
        showToast('Analysis failed: ' + error.message, 'error');
    }
});

function renderMyAnalysisResults(results) {
    const container = document.getElementById('my-analysis-results');
    container.innerHTML = `
        <div class="result-card">
            <h4>Results</h4>
            <p>Total Counts: ${results.total_counts}</p>
            <p>Peak Channel: ${results.peak_channel}</p>
        </div>
    `;
}
```

#### 3. Add Styling

In `backend/static/style.css`:

```css
#my-analysis-panel {
    background: var(--panel-bg);
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
}

#my-analysis-panel .controls {
    display: flex;
    gap: 1rem;
    align-items: center;
    margin-bottom: 1rem;
}

#my-analysis-panel .result-card {
    background: var(--card-bg);
    border-radius: 4px;
    padding: 0.75rem;
}
```

### API Client Pattern

The `api.js` module provides a template for API calls:

```javascript
// backend/static/js/api.js

/**
 * API client for RadTrace backend
 */
const API = {
    baseUrl: '',
    
    async get(endpoint) {
        const response = await fetch(this.baseUrl + endpoint);
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },
    
    async post(endpoint, data) {
        const response = await fetch(this.baseUrl + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },
    
    // Add your custom methods
    async myAnalysis(counts, param) {
        return this.post('/analyze/my-analysis', { counts, custom_param: param });
    }
};
```

---

## 🧠 Extending ML Training

### Adding Isotopes to ML Training

Edit `backend/ml_analysis.py`:

```python
# The ML module automatically uses all isotopes from the database
# Just add isotopes to ISOTOPE_DATABASE_ADVANCED and restart

# To add custom mixture types:
mixtures = {
    'MyCustomMixture': {
        'isotopes': ['Cs-137', 'Co-60', 'My-Isotope'],
        'ratios': [1.0, 0.8, 0.5]  # Relative intensities
    },
    # ... existing mixtures
}
```

### Modifying Training Parameters

```python
class MLIdentifier:
    def __init__(self):
        self.n_channels = 1024          # Number of spectrum channels
        self.keV_per_channel = 3.0      # Energy calibration
        self.n_samples_single = 15      # Samples per isotope
        self.n_samples_mixture = 25     # Samples per mixture
        self.epochs = 25                 # Training epochs
```

### Using Custom Training Data

```python
def train_on_real_data(self, labeled_spectra):
    """Train on user-provided labeled spectra."""
    train_ss = SampleSet()
    
    spectra_list = []
    labels = []
    for spectrum, label in labeled_spectra:
        spectra_list.append(spectrum)
        labels.append(label)
    
    train_ss.spectra = pd.DataFrame(spectra_list)
    # ... configure sources DataFrame
    
    self.model.fit(train_ss, epochs=50)
```

---

## 🔧 Configuration Options

### Environment Variables

Create `.env` file for configuration:

```bash
# Server settings
HOST=0.0.0.0
PORT=3200

# Analysis defaults
DEFAULT_ENERGY_TOLERANCE=20.0
DEFAULT_ISOTOPE_CONFIDENCE=30.0

# Device settings
SERIAL_BAUDRATE=115200
SERIAL_TIMEOUT=1.0
```

### Runtime Settings

Settings can be modified via the frontend Settings panel and persist in localStorage:

```javascript
// Default frontend settings
const defaultSettings = {
    mode: 'simple',
    isotopeMinConfidence: 30,
    chainMinConfidence: 30,
    energyTolerance: 20,
    theme: 'dark'
};
```

---

## ✅ Contribution Guidelines

### Code Style

- **Python**: Follow PEP 8, use type hints
- **JavaScript**: Use ES6+ syntax, JSDoc comments
- **CSS**: BEM naming convention, CSS variables for theming

### Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for new functionality
4. Ensure all tests pass
5. Update documentation
6. Submit PR with clear description

### Testing

```bash
# Run Python tests
cd backend
pytest tests/

# Run frontend tests (if implemented)
npm test
```

### Documentation

- Update relevant `.md` files for any new features
- Add JSDoc comments for JavaScript functions
- Add docstrings for Python functions
- Update CHANGELOG.md with changes

---

## 📚 Related Documentation

- [Theory of Operation](THEORY_OF_OPERATION.md) - System architecture
- [PyRIID Guide](PYRIID_GUIDE.md) - ML integration details
- [Calibration Guide](CALIBRATION_GUIDE.md) - Energy calibration
- [README](README.md) - Quick start guide

---

*Last Updated: 2024-12-14*
*RadTrace Modularity Guide v1.0*
