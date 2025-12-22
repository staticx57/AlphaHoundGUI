# Radiacode Device Integration Plan

## 📋 Executive Summary

This document outlines the integration strategy for adding **Radiacode 103, 103G, and 110** scintillation detectors to the RadTrace application. These devices will complement the existing AlphaHound integration, providing users with broader hardware support.

---

## 🔬 Device Comparison

### Radiacode vs AlphaHound

| Feature | AlphaHound CsI(Tl) | Radiacode 103 | Radiacode 103G | Radiacode 110 |
|---------|-------------------|---------------|----------------|---------------|
| **Scintillator** | CsI(Tl) 1.1 cm³ | CsI(Tl) 1 cm³ | GAGG 1 cm³ | CsI(Tl) 3 cm³ |
| **FWHM @ 662 keV** | 10% | 8.4% | 7.4% | 8.4% |
| **Sensitivity** | 48 cps/µSv/h | 30 cps/µSv/h | 40 cps/µSv/h | 77 cps/µSv/h |
| **Channels** | 1024 | 1024 | 1024 | 1024 |
| **Connection** | USB Serial | USB + Bluetooth | USB + Bluetooth | USB + Bluetooth |
| **SDK** | Custom (NuclearGeekETH) | `cdump/radiacode` | `cdump/radiacode` | `cdump/radiacode` |

### Key Observations
- **103G has best resolution** (7.4% FWHM) - better isotope separation
- **110 has highest sensitivity** (77 cps/µSv/h) - fastest spectrum acquisition
- **Radiacode has Bluetooth** - can connect wirelessly (Linux only currently)
- **AlphaHound has better sensitivity per volume** - 48 cps with 1.1 cm³ vs 30 cps with 1 cm³

---

## 🛠️ SDK Analysis

### Python Library: `cdump/radiacode`

**Installation:**
```bash
pip install radiacode
```

**Key Features:**
- Open-source (MIT License)
- Community-developed (reverse-engineered protocol)
- No official API documentation from manufacturer
- Active maintenance (16 releases, 6 contributors)

### API Capabilities

```python
from radiacode import RadiaCode, RealTimeData

# Connect to device
device = RadiaCode()                              # USB (default)
device = RadiaCode(bluetooth_mac="52:43:...")     # Bluetooth (Linux only)
device = RadiaCode(serial_number="SN123")         # Specific device

# Get real-time dose rate
data = device.data_buf()
for record in data:
    if isinstance(record, RealTimeData):
        print(f"Dose rate: {record.dose_rate}")   # µSv/h

# Get spectrum
spectrum = device.spectrum()
print(f"Duration: {spectrum.duration}s")
print(f"Counts: {spectrum.counts}")               # List of 1024 values

# Energy calibration
coefficients = device.energy_calib()              # Returns calibration polynomial

# Device control
device.spectrum_reset()                           # Clear accumulated spectrum
device.dose_reset()                               # Reset dose accumulator
device.set_display_brightness(5)                  # 0-9
device.set_sound_on(True)
device.set_vibro_on(True)
```

### Platform Support

| Platform | USB | Bluetooth/BLE |
|----------|-----|---------------|
| Windows | ✅ | ✅ (via bleak) |
| Linux | ✅ | ✅ (via bleak) |
| macOS | ✅ | ✅ (via bleak) |

**Note:** BLE support added via `bleak` library for cross-platform Bluetooth Low Energy connectivity.

---

## 📐 Architecture Design

### Proposed Module Structure

```
backend/
├── device_manager.py          # [NEW] Abstract device manager
├── alphahound_serial.py       # Existing AlphaHound driver
├── radiacode_driver.py        # [NEW] Radiacode driver
├── routers/
│   ├── device.py              # [MODIFY] Add Radiacode routes
│   └── device_radiacode.py    # [NEW] Radiacode-specific endpoints
└── detector_efficiency.py     # [MODIFY] Add Radiacode detector specs
```

### Device Abstraction Layer

```python
# Abstract base class for all detectors
class DetectorDriver(ABC):
    @abstractmethod
    def connect(self, port_or_address: str) -> bool: ...
    
    @abstractmethod
    def disconnect(self) -> None: ...
    
    @abstractmethod
    def is_connected(self) -> bool: ...
    
    @abstractmethod
    def get_dose_rate(self) -> float: ...
    
    @abstractmethod
    def get_spectrum(self) -> Tuple[List[int], List[float]]: ...
    
    @abstractmethod
    def clear_spectrum(self) -> None: ...
    
    @abstractmethod
    def get_calibration(self) -> Tuple[float, float, float]: ...
    
    @property
    @abstractmethod
    def device_name(self) -> str: ...
    
    @property
    @abstractmethod
    def device_type(self) -> str: ...  # "AlphaHound" or "Radiacode"
```

---

## 🔧 Implementation Plan

### Phase 1: Core Integration (3-4 hours)

#### 1.1 Add Radiacode Dependency
```python
# requirements.txt
radiacode>=0.4.0
```

#### 1.2 Create Radiacode Driver
**File:** `backend/radiacode_driver.py`

```python
from radiacode import RadiaCode, RealTimeData
from typing import Optional, List, Tuple

class RadiacodeDevice:
    def __init__(self):
        self._device: Optional[RadiaCode] = None
        self._device_model: str = "Unknown"
    
    def connect(self, address: str = None, use_bluetooth: bool = False) -> bool:
        try:
            if use_bluetooth and address:
                self._device = RadiaCode(bluetooth_mac=address)
            else:
                self._device = RadiaCode()
            return True
        except Exception as e:
            print(f"[Radiacode] Connection failed: {e}")
            return False
    
    def is_connected(self) -> bool:
        return self._device is not None
    
    def get_dose_rate(self) -> Optional[float]:
        if not self._device:
            return None
        data = self._device.data_buf()
        for record in data:
            if isinstance(record, RealTimeData):
                return record.dose_rate
        return None
    
    def get_spectrum(self) -> Tuple[List[int], List[float]]:
        if not self._device:
            return [], []
        spectrum = self._device.spectrum()
        counts = list(spectrum.counts)
        
        # Apply energy calibration
        coeffs = self._device.energy_calib()
        energies = [coeffs[0] + coeffs[1]*i + coeffs[2]*i**2 
                    for i in range(len(counts))]
        return counts, energies
    
    def clear_spectrum(self):
        if self._device:
            self._device.spectrum_reset()
```

#### 1.3 Add Detector Efficiency Database
**File:** `backend/detector_efficiency.py` (modify)

```python
DETECTOR_DATABASE = {
    # ... existing AlphaHound entries ...
    
    "Radiacode 103": {
        "type": "CsI(Tl)",
        "description": "Radiacode 103 - CsI(Tl) 10x10x10mm",
        "volume_cm3": 1.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 30.0,
        "energy_resolution_662keV": 0.084,  # 8.4% FWHM
        "efficiencies": { ... }
    },
    "Radiacode 103G": {
        "type": "GAGG",
        "description": "Radiacode 103G - GAGG 10x10x10mm",
        "volume_cm3": 1.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 40.0,
        "energy_resolution_662keV": 0.074,  # 7.4% FWHM
        "efficiencies": { ... }
    },
    "Radiacode 110": {
        "type": "CsI(Tl)",
        "description": "Radiacode 110 - CsI(Tl) 14x14x14mm",
        "volume_cm3": 3.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 77.0,
        "energy_resolution_662keV": 0.084,  # 8.4% FWHM
        "efficiencies": { ... }
    }
}
```

### Phase 2: API Endpoints (2-3 hours)

#### 2.1 Create Radiacode Router
**File:** `backend/routers/device_radiacode.py`

```python
from fastapi import APIRouter, HTTPException
from radiacode_driver import RadiacodeDevice

router = APIRouter(prefix="/radiacode", tags=["radiacode"])
device = RadiacodeDevice()

@router.post("/connect")
async def connect_radiacode(bluetooth_mac: str = None):
    success = device.connect(address=bluetooth_mac, use_bluetooth=bool(bluetooth_mac))
    if not success:
        raise HTTPException(400, "Failed to connect to Radiacode")
    return {"status": "connected", "device": device._device_model}

@router.get("/dose")
async def get_radiacode_dose():
    if not device.is_connected():
        raise HTTPException(400, "Device not connected")
    rate = device.get_dose_rate()
    return {"dose_rate_uSv_h": rate}

@router.get("/spectrum")
async def get_radiacode_spectrum():
    if not device.is_connected():
        raise HTTPException(400, "Device not connected")
    counts, energies = device.get_spectrum()
    # Run peak detection, isotope ID, etc.
    return {
        "counts": counts,
        "energies": energies,
        "metadata": {"source": "Radiacode Device"}
    }
```

### Phase 3: UI Integration (2-3 hours)

#### 3.1 Device Selector
Add device type toggle to connect panel:

```html
<div class="device-selector">
    <label><input type="radio" name="device-type" value="alphahound" checked> AlphaHound</label>
    <label><input type="radio" name="device-type" value="radiacode"> Radiacode</label>
</div>
```

#### 3.2 Connection Mode (Radiacode-specific)
```html
<div id="radiacode-options" style="display: none;">
    <label><input type="radio" name="rc-conn" value="usb" checked> USB</label>
    <label><input type="radio" name="rc-conn" value="bluetooth"> Bluetooth (Linux)</label>
    <input type="text" id="rc-bluetooth-mac" placeholder="52:43:01:02:03:04" disabled>
</div>
```

### Phase 4: ML Tuning (1-2 hours)

Update `ml_analysis.py` to support multiple detector profiles:

```python
DETECTOR_PROFILES = {
    "AlphaHound CsI(Tl)": {
        "n_channels": 1024,
        "keV_per_channel": 3.0,
        "fwhm_662keV": 0.10,  # 10%
    },
    "Radiacode 103": {
        "n_channels": 1024,
        "keV_per_channel": 3.0,
        "fwhm_662keV": 0.084,  # 8.4%
    },
    "Radiacode 103G": {
        "n_channels": 1024,
        "keV_per_channel": 3.0,
        "fwhm_662keV": 0.074,  # 7.4%
    },
    "Radiacode 110": {
        "n_channels": 1024,
        "keV_per_channel": 3.0,
        "fwhm_662keV": 0.084,  # 8.4%
    }
}
```

---

## ⚠️ Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| No official SDK documentation | Medium | Library is mature and well-tested by community |
| Bluetooth Linux-only | Low | USB works on all platforms |
| Different calibration formats | Medium | Normalize to common keV/channel format |
| Protocol changes in future firmware | Medium | Pin to tested radiacode library version |

---

## 📅 Estimated Timeline

| Phase | Description | Time |
|-------|-------------|------|
| 1 | Core driver + detector database | 3-4 hours |
| 2 | API endpoints | 2-3 hours |
| 3 | UI integration | 2-3 hours |
| 4 | ML tuning for Radiacode profiles | 1-2 hours |
| 5 | Testing & documentation | 2-3 hours |
| **Total** | **Complete Radiacode Integration** | **10-15 hours** |

---

## ✅ Success Criteria (COMPLETED)

- [x] Connect to Radiacode 103/103G/110 via USB
- [x] Connect to Radiacode via Bluetooth/BLE (cross-platform via bleak)
- [x] Display live dose rate from Radiacode
- [x] Acquire and display spectrum from Radiacode
- [x] Run peak detection and isotope ID on Radiacode spectra
- [x] ROI Analysis works with Radiacode detector profiles
- [x] ML identification tuned for Radiacode FWHM
- [x] Device selector allows switching between AlphaHound and Radiacode
- [x] BLE device scanning and discovery

---

## 📚 References

- **Radiacode Python Library**: [github.com/cdump/radiacode](https://github.com/cdump/radiacode)
- **PyPI Package**: [pypi.org/project/radiacode](https://pypi.org/project/radiacode/)
- **Radiacode Official**: [radiacode.com](https://radiacode.com/)
- **Device Specs**: [radiacode.com/products](https://radiacode.com/products)
- **EDA Blog Post**: [Exploratory Data Analysis - Gamma Spectroscopy in Python](https://towardsdatascience.com/exploratory-data-analysis-gamma-spectroscopy-in-python/)

---

*Created: 2025-12-12*  
*Author: RadTrace Development Team*
