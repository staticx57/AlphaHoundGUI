# Three-Tier UI Mode Testing Guide

**Date:** 2025-12-16 | **Version:** 2.6

---

## Quick Test Checklist

### 1. Settings Modal
- [ ] Open Settings (⚙️ button in header)
- [ ] Verify "UI Complexity Mode" section appears above "Detection Mode"
- [ ] Verify three radio buttons: Simple, Advanced, Expert

### 2. Mode Switching
| Action | Expected Result |
|--------|-----------------|
| Select **Simple** | ROI panel, Background, Calibration sections HIDDEN |
| Select **Advanced** | ROI panel, Background, Calibration VISIBLE; Decay Prediction HIDDEN |
| Select **Expert** | ALL panels VISIBLE |

### 3. Persistence
- [ ] Set mode to "Advanced"
- [ ] Refresh page (F5)
- [ ] Verify mode is still "Advanced"
- [ ] Check console: `[UI Mode] Applying "advanced" mode: ...`

### 4. Takumar Lens Source
- [ ] Open ROI Analysis panel
- [ ] Check Source Type dropdown has "Takumar Lens (Th + Natural U)"

---

## Debug Console Commands

```javascript
// Check current settings
JSON.parse(localStorage.getItem('analysisSettings'))

// Force apply a mode
applyUIMode('expert')

// Check UI_MODE_CONFIG
console.log(UI_MODE_CONFIG)

// Reset to defaults
localStorage.removeItem('analysisSettings')
location.reload()
```

---

## Common Issues

| Symptom | Fix |
|---------|-----|
| Panel doesn't hide | Check element ID in HTML matches `UI_MODE_CONFIG` |
| Mode not persisting | Check localStorage in DevTools > Application |
| Console errors on load | Ensure radios exist before `querySelectorAll` |

---

## Panel ID Reference

```javascript
// Simplified config:
// Simple:   hides roi-analysis-panel, advanced-settings
// Advanced: shows roi-analysis-panel
// Expert:   shows roi-analysis-panel, advanced-settings
```
