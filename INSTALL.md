# AlphaHound GUI Installation Options

## Requirements

- **Python 3.11 or newer** (tested on 3.12). The install scripts check this and say what to do if it is missing or too old.
- **Windows** for the `.bat` scripts. On macOS or Linux use the commands under [Without the scripts](#without-the-scripts).
- An internet connection **for the installation only**: the application runs offline afterwards.
- A device is optional: everything except live acquisition works with files alone.

## Quick Start

Choose your installation mode:

### **Lightweight Mode**
The core of the application, small.

```bash
install_lightweight.bat
run_lightweight.bat
```

### **Full Mode** (recommended)
Everything, including AI identification, the nuclide data libraries and the Radiacode.

```bash
install_deps.bat
run.bat
```

Both start scripts run the same server; whatever is not installed is simply not offered.

## 📦 What Each Install Brings

**Lightweight** (`requirements_lightweight.txt`): the web server (FastAPI, Uvicorn, WebSockets, SlowAPI), NumPy, SciPy, Pandas,
Matplotlib, ReportLab (PDF reports) and PySerial (the AlphaHound).

**Full** (`backend/requirements.txt`) adds:

| Package | What it adds |
|---------|--------------|
| scikit-learn | AI identification |
| radioactivedecay | exact decay chains and decay prediction (the built-in tables are used without it) |
| curie | the shielding and emissions calculators, X-ray data |
| SandiaSpecUtils | reading and writing other spectrum formats (PCF and more) |
| radiacode, bleak, libusb-package | the Radiacode device: USB, Bluetooth |

> [!WARNING]
> **Curie Database Initialization Issue**  
> If the backend crashes on startup with `ValueError: ... ziegler.db exists but is of zero size`, the `curie` package failed to download its nuclear databases. You must manually download them into your `site-packages/curie/data/` folder. Please refer to the README.md Troubleshooting section for the python script to fix this.

## 📋 Features by Mode

Checked on 2026-10-05 by running the application with every package the lightweight install leaves out made unavailable: a radium
spectrum gave the same answer as in the full install (U-238 series, the same isotope list), and the routes below answered as listed.

| Feature | Lightweight | Full |
|---------|-------------|------|
| File upload (N42, RadiaCode XML, CSV, CHN, SPE) | ✅ | ✅ |
| Peak detection, isotope identification (rule-based), decay chains | ✅ (built-in nuclide tables) | ✅ |
| Custom isotopes, background subtraction, energy calibration | ✅ | ✅ |
| ROI analysis, uranium enrichment, decay prediction | ✅ | ✅ |
| PDF export | ✅ | ✅ |
| AlphaHound device | ✅ | ✅ |
| Shielding and emissions calculators | ❌ ("The curie package is not installed") | ✅ |
| Other spectrum formats (PCF and more) | ❌ | ✅ |
| Radiacode device | ❌ | ✅ |
| AI identification (scikit-learn) | ❌ | ✅ |

## 🔎 Check What You Have

```bash
python backend\tools\check_install.py
```

It reports the Python version, the packages the application cannot start without, each optional package and what it adds, and which
peak finder is in use. The install scripts run it when they finish, and `run.bat` runs it before starting (it stops and says what is
missing, instead of a traceback).

## Optional: the InterSpec Peak Finder

When [InterSpec](https://github.com/sandialabs/InterSpec) (Sandia National Laboratories, LGPL-2.1) is found, its batch tool finds and fits
the peaks (it separates overlapping and shoulder peaks the built-in detector misses). Without it the built-in detector is used and
nothing else changes.

1. Download an InterSpec release for Windows (1.0.14 is the version tested) and unpack it to
   `%USERPROFILE%\tools\InterSpec\InterSpec-win32-x64_WebView2_v1.0.14\`, so that `InterSpec_batch.exe` is in that folder.
2. Or unpack it anywhere and set `ALPHAHOUND_INTERSPEC_BATCH` to the full path of `InterSpec_batch.exe`.
   Keep the path **short**: InterSpec trips over Windows' 260-character path limit.
3. `ALPHAHOUND_PEAKS=builtin` uses the built-in detector even when InterSpec is there.

`check_install.py` shows which one is in use.

## 🌐 Usage

1. Run `run.bat` (or `run_lightweight.bat`). It starts the server and **opens the browser when the server answers** (loading takes up to
   half a minute); if the application is already running it opens that instead of starting a second server. Stop it with Ctrl+C.
2. The address is `http://localhost:3200`; from another computer on the network, `http://<this computer's address>:3200`.
3. Upload a spectrum file, or connect the AlphaHound or the Radiacode.

For development with automatic restarts: `cd backend` and `python -m uvicorn main:app --reload --port 3200`. A restart drops a connected
device and stops a running acquisition, which is why `run.bat` does not do it.

## 🔄 Switching Modes

To go from lightweight to full, run `install_deps.bat`. Or add one thing at a time:

```bash
python -m pip install scikit-learn                # AI identification
python -m pip install radioactivedecay curie      # exact decay data, shielding, emissions
python -m pip install SandiaSpecUtils             # other spectrum formats
python -m pip install radiacode bleak libusb-package   # the Radiacode
```

The application detects what is installed and enables the matching features. (PyRIID is no longer used: it pins numpy 1.26 / scipy 1.13 / TensorFlow 2.16, which conflict with the rest of the app.)

## Without the Scripts

```bash
python -m pip install -r requirements.txt          # everything; or requirements_lightweight.txt for the core
cd backend
python main.py                                     # http://localhost:3200
```

For the tests also `python -m pip install -r backend/requirements-dev.txt`.
