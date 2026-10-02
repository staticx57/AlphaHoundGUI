# AlphaHound GUI Installation Options

## 🚀 Quick Start

Choose your installation mode:

### **Lightweight Mode** (Recommended for most users)
✅ ~10MB dependencies  
✅ All core features (analysis, isotopes, device control)  
❌ No ML identification

```bash
install_lightweight.bat
run_lightweight.bat
```

### **Full Mode** (with Machine Learning)
✅ All features including AI identification (scikit-learn)  
✅ Small extra dependency (scikit-learn, already included in the full install)  
⏱️ Longer installation time

```bash
install.bat
run.bat
```

## 📦 Installation Details

### Lightweight Dependencies
- FastAPI, Uvicorn (web server)
- NumPy, SciPy, Pandas (analysis)
- Matplotlib, ReportLab (plotting, PDF)
- PySerial, WebSockets (device communication)

### Full Dependencies (adds)
- scikit-learn (neural-network classifier for AI identification)

> [!WARNING]
> **Curie Database Initialization Issue**  
> If the backend crashes on startup with `ValueError: ... ziegler.db exists but is of zero size`, the `curie` package failed to download its nuclear databases. You must manually download them into your `site-packages/curie/data/` folder. Please refer to the README.md Troubleshooting section for the python script to fix this.

## 🔄 Switching Modes

You can always upgrade from lightweight to full:
```bash
python -m pip install scikit-learn
```

The app automatically detects scikit-learn and enables ML features if installed. (PyRIID is no longer used: it pins numpy 1.26 / scipy 1.13 / TensorFlow 2.16, which conflict with the rest of the app.)

## 🌐 Usage

1. Run the application: `run.bat` or `run_lightweight.bat`
2. Open browser: `http://localhost:3200`
3. Upload N42 or CSV files, or connect AlphaHound device

## 📋 Features by Mode

| Feature | Lightweight | Full |
|---------|-------------|------|
| File Upload (N42, CSV) | ✅ | ✅ |
| Peak Detection | ✅ | ✅ |
| Isotope Identification (Rule-based) | ✅ | ✅ |
| Decay Chain Detection | ✅ | ✅ |
| Custom Isotopes (Add/Import/Export) | ✅ | ✅ |
| Background Subtraction | ✅ | ✅ |
| Energy Calibration | ✅ | ✅ |
| ROI Analysis (Advanced Mode) | ✅ | ✅ |
| Uranium Enrichment Analysis | ✅ | ✅ |
| PDF Export | ✅ | ✅ |
| Device Control (AlphaHound) | ✅ | ✅ |
| Rate Limiting (API Security) | ✅ | ✅ |
| ML Identification (scikit-learn) | ❌ | ✅ |
