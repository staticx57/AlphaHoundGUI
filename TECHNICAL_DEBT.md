# Technical Debt Report

**Date:** 2025-12-16  
**Version:** 2.5

---

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| 🔴 High | 3 | Pending |
| 🟡 Medium | 3 | Pending |
| 🟢 Low | 3 | Pending |
| ✅ Good Practices | 5 | N/A |

---

## 🔴 High Priority

| Issue | Location | Lines | Recommendation |
|-------|----------|-------|----------------|
| **analysis.py too large** | `backend/routers/analysis.py` | 1,464 | Split into upload, export, ml, roi modules |
| **roi_analysis.py complex** | `backend/roi_analysis.py` | ~1,190 | Separate analysis logic from utilities |
| **Test coverage unknown** | `backend/test_*` (6 files) | - | Run tests and generate coverage report |

---

## 🟡 Medium Priority

| Issue | Description |
|-------|-------------|
| Duplicate isotope data | IAEA + NNDC + custom isotopes in multiple files |
| Multiple parser files | n42, csv, chn, spe parsers should share interface |
| Settings scattered | Analysis settings in multiple locations |

---

## 🟢 Low Priority

| Issue | Description |
|-------|-------------|
| Debug prints | Some `print()` calls remain in fitting engine |
| Inline SVG repetition | Consider SVG sprite/component system |
| No offline support | Service worker not implemented |

---

## ✅ Good Practices Found

- ✅ No `import *` statements
- ✅ Type hints throughout Python code
- ✅ Pydantic input validation
- ✅ Rate limiting implemented
- ✅ No unaddressed TODO/FIXME comments
